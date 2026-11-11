"""Resumen de un backtest: mismas métricas que se miran en el demo (doc 05 §10-§11)."""

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, List

from app.backtest.engine import BacktestResult

_DAY_MS = 24 * 60 * 60 * 1000
_WEEK_MS = 7 * _DAY_MS


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


def _group(records, key) -> Dict[str, Dict[str, float]]:
    out: Dict[str, Dict[str, float]] = {}
    for r in records:
        g = out.setdefault(key(r), {"grids": 0, "bot_pnl": 0.0, "true_pnl": 0.0,
                                    "cycles_net": 0.0, "hours": 0.0})
        g["grids"] += 1
        g["bot_pnl"] += r.bot_pnl
        g["true_pnl"] += r.true_pnl
        g["cycles_net"] += r.cycles_net
        g["hours"] += (r.closed_ms - r.opened_ms) / 3_600_000.0
    for g in out.values():
        g["avg_hours"] = g.pop("hours") / g["grids"]
    return out


def summarize(result: BacktestResult) -> Dict[str, Any]:
    records = result.records
    closed = [r for r in records if r.trigger != "OPEN_AT_END"]
    balance = result.config.balance
    days = max((result.end_ms - result.start_ms) / _DAY_MS, 1e-9)

    true_total = sum(r.true_pnl for r in records)
    bot_total = sum(r.bot_pnl for r in records)
    cycles = sum(r.cycles for r in records)
    cycles_net = sum(r.cycles_net for r in records)
    fees = sum(r.fees for r in records)

    # Cadenas: un grid y sus re-centrados son una sola operación económica.
    chains: Dict[int, List] = {}
    for r in records:
        chains.setdefault(r.root_id, []).append(r)
    chain_pnls = [sum(r.true_pnl for r in rs) for rs in chains.values()
                  if rs[-1].trigger != "OPEN_AT_END"]

    # Drawdown y semanas sobre la curva horaria de PnL real.
    peak = 0.0
    max_dd = 0.0
    for _, eq in result.equity:
        peak = max(peak, eq)
        max_dd = max(max_dd, peak - eq)
    weekly: List[float] = []
    prev = 0.0
    boundary = result.start_ms + _WEEK_MS
    last_eq = 0.0
    for ms, eq in result.equity:
        while ms > boundary:
            weekly.append(last_eq - prev)
            prev = last_eq
            boundary += _WEEK_MS
        last_eq = eq
    if result.equity and (result.equity[-1][0] - (boundary - _WEEK_MS)) >= 0.5 * _WEEK_MS:
        weekly.append(last_eq - prev)  # semana final solo si está al menos a medias

    return {
        "period": {"start": _iso(result.start_ms), "end": _iso(result.end_ms), "days": round(days, 1)},
        "symbols": len(result.symbols),
        "config": asdict(result.config),
        "totals": {
            "true_pnl": true_total,
            "bot_pnl": bot_total,
            "roi_pct": 100 * true_total / balance,
            "roi_pct_month": 100 * true_total / balance * 30 / days,
            "fees": fees,
            "cycles": cycles,
            "cycles_net": cycles_net,
            "closure_drag": true_total - cycles_net,
            "max_drawdown": max_dd,
            "max_drawdown_pct": 100 * max_dd / balance,
        },
        "grids": {
            "launched": result.stats.get("grids_launched", 0),
            "records": len(records),
            "closed": len(closed),
            "per_day": len(closed) / days,
            "zero_cycle_pct": 100 * sum(1 for r in closed if r.cycles == 0) / len(closed) if closed else 0.0,
            "profitable_pct": 100 * sum(1 for r in closed if r.true_pnl > 0) / len(closed) if closed else 0.0,
            "chains": len(chain_pnls),
            "chains_profitable_pct": 100 * sum(1 for p in chain_pnls if p > 0) / len(chain_pnls) if chain_pnls else 0.0,
        },
        "weeks": {
            "pnl": weekly,
            "positive": sum(1 for w in weekly if w > 0),
            "total": len(weekly),
        },
        "by_trigger": _group(records, lambda r: r.trigger),
        "by_symbol": _group(records, lambda r: r.symbol),
        "stats": dict(result.stats),
    }


def format_text(summary: Dict[str, Any], label: str = "") -> str:
    t, g, w = summary["totals"], summary["grids"], summary["weeks"]
    p = summary["period"]
    lines = [
        f"=== Backtest {label} ===".replace("  ", " "),
        f"Periodo: {p['start']} -> {p['end']} UTC ({p['days']} días) | {summary['symbols']} símbolos | "
        f"balance {summary['config']['balance']:g} USDT",
        "",
        f"Resultado real:      {t['true_pnl']:+8.2f} USDT  ({t['roi_pct']:+.1f} % | {t['roi_pct_month']:+.2f} %/mes)",
        f"Resultado según bot: {t['bot_pnl']:+8.2f} USDT",
        f"Cosecha de ciclos:   {t['cycles_net']:+8.2f} USDT  ({t['cycles']} ciclos)",
        f"Arrastre de cierres: {t['closure_drag']:+8.2f} USDT  (inventario + costo de salida)",
        f"Comisiones:          {t['fees']:8.2f} USDT",
        f"Drawdown máximo:     {t['max_drawdown']:8.2f} USDT  ({t['max_drawdown_pct']:.1f} % del balance)",
        "",
        f"Grids cerrados: {g['closed']} ({g['per_day']:.2f}/día) | rentables {g['profitable_pct']:.0f} % | "
        f"con 0 ciclos {g['zero_cycle_pct']:.0f} % | cadenas rentables {g['chains_profitable_pct']:.0f} % de {g['chains']}",
        f"Semanas positivas: {w['positive']} de {w['total']}",
        "",
        f"{'Trigger':<16}{'grids':>6}{'real':>10}{'bot':>10}{'ciclos':>10}{'horas':>8}",
    ]
    for name, v in sorted(summary["by_trigger"].items(), key=lambda kv: kv[1]["true_pnl"]):
        lines.append(f"{name:<16}{v['grids']:>6}{v['true_pnl']:>+10.2f}{v['bot_pnl']:>+10.2f}"
                     f"{v['cycles_net']:>+10.2f}{v['avg_hours']:>8.1f}")
    lines += ["", f"{'Símbolo':<16}{'grids':>6}{'real':>10}{'ciclos':>10}"]
    for name, v in sorted(summary["by_symbol"].items(), key=lambda kv: kv[1]["true_pnl"]):
        lines.append(f"{name:<16}{v['grids']:>6}{v['true_pnl']:>+10.2f}{v['cycles_net']:>+10.2f}")
    lines += ["", "Eventos: " + ", ".join(f"{k}={v}" for k, v in sorted(summary["stats"].items()))]
    return "\n".join(lines)
