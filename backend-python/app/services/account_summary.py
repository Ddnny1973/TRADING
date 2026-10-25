"""
A1b: resultado neto real del bot leído de Binance, independiente de la
contabilidad interna (grid_cycles / pnl_snapshots / historical_grid_logs).

Fuente: GET /fapi/v1/income (REALIZED_PNL, COMMISSION, FUNDING_FEE, ...) más
GET /fapi/v2/account para el PnL no realizado de las posiciones abiertas.
Las transferencias (TRANSFER, recargas del faucet) se reportan aparte y NO
cuentan como resultado de la estrategia.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

# Tipos de income que son resultado de operar. El resto (TRANSFER, bonos,
# airdrops...) mueve la billetera sin ser resultado de la estrategia.
TRADING_INCOME_TYPES = ("REALIZED_PNL", "COMMISSION", "FUNDING_FEE")

# Binance solo conserva ~3 meses de /fapi/v1/income.
MAX_LOOKBACK_DAYS = 90

_MAX_PAGES = 60  # tope de seguridad: 60 × 1000 registros


async def fetch_all_income(client, start_ms: int,
                           income_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """Pagina /fapi/v1/income desde start_ms (limit 1000 por llamada),
    avanzando start_time al último registro recibido."""
    todos: List[Dict[str, Any]] = []
    start = start_ms
    for _ in range(_MAX_PAGES):
        batch = await client.get_income_history(
            income_type=income_type, start_time=start, limit=1000)
        if not batch:
            break
        todos.extend(batch)
        if len(batch) < 1000:
            break
        last_time = max(int(r.get("time") or start) for r in batch)
        if last_time <= start:
            break  # timestamps repetidos: evitar loop infinito
        start = last_time + 1
    return todos


def summarize_income(records: List[Dict[str, Any]],
                     account: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Agrega registros de income (puro, testeable).

    net_trading = REALIZED_PNL + COMMISSION + FUNDING_FEE del período.
    net_with_open = net_trading + PnL no realizado actual (si hay account).
    """
    by_type: Dict[str, float] = {}
    by_symbol: Dict[str, Dict[str, float]] = {}
    per_day: Dict[str, float] = {}
    for r in records:
        tipo = r.get("incomeType") or "?"
        monto = float(r.get("income") or 0)
        by_type[tipo] = by_type.get(tipo, 0.0) + monto
        if tipo not in TRADING_INCOME_TYPES:
            continue
        sym = r.get("symbol") or "?"
        s = by_symbol.setdefault(sym, {"realized_pnl": 0.0, "commission": 0.0, "funding": 0.0, "net": 0.0})
        key = {"REALIZED_PNL": "realized_pnl", "COMMISSION": "commission", "FUNDING_FEE": "funding"}[tipo]
        s[key] += monto
        s["net"] += monto
        day = datetime.fromtimestamp(int(r.get("time") or 0) / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        per_day[day] = per_day.get(day, 0.0) + monto

    realized = by_type.get("REALIZED_PNL", 0.0)
    commission = by_type.get("COMMISSION", 0.0)
    funding = by_type.get("FUNDING_FEE", 0.0)
    net_trading = realized + commission + funding

    unrealized = None
    account_view = None
    if account:
        unrealized = float(account.get("totalUnrealizedProfit") or 0)
        account_view = {
            "wallet_balance": float(account.get("totalWalletBalance") or 0),
            "unrealized_pnl": unrealized,
            "margin_balance": float(account.get("totalMarginBalance") or 0),
            "available_balance": float(account.get("availableBalance") or 0),
        }

    return {
        "records": len(records),
        "realized_pnl": realized,
        "commission": commission,
        "funding": funding,
        "net_trading": net_trading,
        "net_with_open": net_trading + unrealized if unrealized is not None else None,
        "transfers": by_type.get("TRANSFER", 0.0),
        "by_type": by_type,
        "by_symbol": dict(sorted(by_symbol.items(), key=lambda kv: kv[1]["net"])),
        "per_day": [{"day": d, "net": v} for d, v in sorted(per_day.items())],
        "account": account_view,
    }


async def build_income_summary(client, days: int) -> Dict[str, Any]:
    """Trae income de los últimos `days` días (≤ MAX_LOOKBACK_DAYS) + cuenta."""
    days = max(1, min(int(days), MAX_LOOKBACK_DAYS))
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    records = await fetch_all_income(client, int(start.timestamp() * 1000))
    account = await client.get_account_info()
    summary = summarize_income(records, account)
    summary["period"] = {"days": days, "start": start.isoformat(), "end": end.isoformat()}
    return summary
