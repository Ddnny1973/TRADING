"""
funding_resumen.py — Cuantifica el impacto del funding en el PnL (T22, paso 1).

Contexto (docs/analisis-bot/04-estrategia-y-portafolio.md §6): el bot opera
perpetuos, un grid NEUTRAL carga posición neta por horas y el funding se
liquida cada 8h. calculate_grid_pnl() solo descuenta fees de trading; el
funding no aparece en grid_cycles, ni en pnl_snapshots, ni en el dashboard.
Con un edge de ~0,43 USD por ciclo, el funding puede consumirlo sin dejar
rastro.

Este script trae el historial real de income de Binance testnet
(GET /fapi/v1/income, firmado) desde el primer snapshot en Postgres, lo
agrupa por incomeType (FUNDING_FEE vs TRANSFER/recargas vs REALIZED_PNL/
COMMISSION) y lo compara contra el PnL de ciclos y el PnL de cierres del
mismo período. Si el funding es comparable al edge (material), se incorpora
al pipeline del dashboard (paso 2 de T22).

Ejecutar DENTRO del contenedor del backend (tiene claves, deps y red a
Postgres y a Binance testnet):

    docker compose exec trading-backend python -m app.scripts.funding_resumen

No modifica nada: solo lee (income de Binance + SELECTs en Postgres).
"""

import asyncio
import sys
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text

from app.database.connection import postgres_engine
from app.services.binance_client import BinanceClient


def _ms(valor) -> int:
    return int(valor * 1000)


def resumir_income(registros: List[Dict[str, Any]]) -> Tuple[Dict[str, float], Dict[str, float]]:
    """
    Agrupa registros de /fapi/v1/income.
    Devuelve (por_tipo, funding_por_simbolo): por_tipo[incomeType] = suma neta
    USDT flotante; funding_por_simbolo[symbol] = suma de FUNDING_FEE USDT.
    Puro y testeable.
    """
    por_tipo: Dict[str, float] = {}
    funding_por_simbolo: Dict[str, float] = {}
    for r in registros:
        tipo = r.get("incomeType") or "?"
        monto = float(r.get("income") or 0)
        por_tipo[tipo] = por_tipo.get(tipo, 0.0) + monto
        if tipo == "FUNDING_FEE":
            s = r.get("symbol") or "?"
            funding_por_simbolo[s] = funding_por_simbolo.get(s, 0.0) + monto
    return por_tipo, funding_por_simbolo


async def _traer_income(client: BinanceClient, start_ms: int,
                        income_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """Página todo el historial de income desde start_ms (limit 1000 por call,
    avanza start_time al último registro recibido para no perder registros
    contiguos de mismo timestamp)."""
    todos: List[Dict[str, Any]] = []
    start = start_ms
    for _ in range(60):  # tope de seguridad; ~60 páginas cubren muy de sobra
        batch = await client.get_income_history(
            income_type=income_type, start_time=start, limit=1000)
        if not batch:
            break
        todos.extend(batch)
        if len(batch) < 1000:
            break
        last_time = max(int(r.get("time") or start) for r in batch)
        if last_time <= start:
            # No avanzó (timestamps repetidos): evitar loop infinito.
            break
        start = last_time + 1
    return todos


def _querys_analitica() -> dict:
    """Lee de postgres-trading: PnL de ciclos, PnL de cierres y rango de
    pnl_snapshots (reusa la misma lógica del dashboard)."""
    if postgres_engine is None:
        raise RuntimeError("postgres_engine no disponible (¿corres dentro del contenedor?)")
    with postgres_engine.begin() as c:
        ciclos = dict(c.execute(text(
            "SELECT COALESCE(SUM(net_pnl), 0) AS pnl, COUNT(*) AS total FROM grid_cycles")).one())
        cierres = dict(c.execute(text(
            "SELECT COALESCE(SUM(total_pnl), 0) AS pnl, COUNT(*) AS total FROM historical_grid_logs")).one())
        rango = dict(c.execute(text(
            "SELECT MIN(taken_at) AS primero, MAX(taken_at) AS ultimo FROM pnl_snapshots")).one())
        balances = dict(c.execute(text(
            "SELECT (SELECT account_balance FROM pnl_snapshots ORDER BY taken_at ASC LIMIT 1) AS inicial, "
            "(SELECT account_balance FROM pnl_snapshots ORDER BY taken_at DESC LIMIT 1) AS final")).one())
    return {"ciclos": ciclos, "cierres": cierres, "rango": rango, "balances": balances}


async def main() -> int:
    print("=== T22 / paso 1: cuantificar el funding ===")
    print()

    analitica = _querys_analitica()
    primero = analitica["rango"]["primero"]
    ultimo = analitica["rango"]["ultimo"]
    if primero is None:
        print("No hay pnl_snapshots en postgres-trading: aún no hay período que reconciliar.")
        return 1
    start_ms = _ms(primero.timestamp())
    print(f"Período de snapshots: {primero.isoformat()} → {ultimo.isoformat()}")

    client = BinanceClient()
    print("\nDescargando historial de income desde Binance testnet ...")
    todos = await _traer_income(client, start_ms)
    print(f"  {len(todos)} registros de income.")
    por_tipo, funding_por_simbolo = resumir_income(todos)
    funding_total = por_tipo.get("FUNDING_FEE", 0.0)

    print("\n--- Income por tipo (USDT) ---")
    if not por_tipo:
        print("  (sin registros)")
    else:
        for tipo, monto in sorted(por_tipo.items(), key=lambda kv: -abs(kv[1])):
            print(f"  {tipo:<22} {monto:>12.4f}")

    print("\n--- Funding por símbolo (FUNDING_FEE, USDT) ---")
    if not funding_por_simbolo:
        print("  (sin funding en el período)")
    else:
        for s, monto in sorted(funding_por_simbolo.items(), key=lambda kv: -abs(kv[1])):
            print(f"  {s:<12} {monto:>12.4f}")

    ciclos = analitica["ciclos"]
    cierres = analitica["cierres"]
    bal = analitica["balances"]
    ciclos_pnl = float(ciclos["pnl"])
    cierres_pnl = float(cierres["pnl"])
    inicial, final = bal["inicial"], bal["final"]
    balance_roi = None
    if inicial:
        inicial_f, final_f = float(inicial), float(final)
        balance_roi = (final_f - inicial_f) / inicial_f * 100

    print("\n--- Comparación (mismo período) ---")
    print(f"  PnL neto de ciclos (grid_cycles)          {ciclos_pnl:>12.4f} USDT  ({ciclos['total']} ciclos)")
    print(f"  PnL final de cierres (grid_closures/hist.){cierres_pnl:>12.4f} USDT  ({cierres['total']} grids)")
    print(f"  FUNDING neto (Binance income)              {funding_total:>12.4f} USDT")

    denom = abs(ciclos_pnl)
    if denom == 0:
        denom = max(abs(cierres_pnl), 1e-9)
    frac = abs(funding_total) / denom * 100 if denom else 0.0
    print(f"\n  Funding respecto al PnL de ciclos       = {frac:6.1f} %")
    if abs(funding_total) > 0.05 * denom:
        print("  → MATERIAL: el funding ~5%+ del PnL de ciclos. Procede el paso 2 de T22")
        print("    (capturar cumulative_funding en pnl_snapshots + dashboard).")
    else:
        print("  → No material (con el umbral de 5%). Revisa el número y decide.")

    if inicial:
        print(f"\n  Billetera (snapshots): {inicial_f:.2f} → {final_f:.2f} USDT "
              f"(balance_roi {balance_roi:+.2f} %). La diferencia frente al PnL de")
        print("  la estrategia se explica por TRANSFER (recargas faucet), FUNDING_FEE y COMMISSION.")
    print("\nConsulta más en pgAdmin si quieres desglosar por grid_cycles en el período.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))