"""
CLI del backtester. Desde `backend-python/`:

    python -m app.backtest --days 180
    python -m app.backtest --start 2026-10-27 --end 2026-11-08 --symbols SOLUSDT,ZECUSDT,SUIUSDT
    python -m app.backtest --days 180 --sl-pct 0.03 --label "SL 3%"

Solo usa endpoints públicos de mainnet (velas) y escribe en `backtest_data/`.
"""

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone

# app.core.config valida estas variables al importarse; el backtester no las usa.
for _var, _val in (("BINANCE_API_KEY", "backtest"), ("BINANCE_API_SECRET", "backtest"),
                   ("POSTGRES_USER", "backtest"), ("POSTGRES_PASSWORD", "backtest"),
                   ("POSTGRES_DB", "backtest")):
    os.environ.setdefault(_var, _val)

from app.backtest.data import (  # noqa: E402
    DEMO_FAPI_BASE, HistoricalMarket, load_bars, load_exchange_filters, top_symbols_by_volume,
)
from app.backtest.engine import Backtest  # noqa: E402
from app.backtest.grid_sim import SimConfig  # noqa: E402
from app.backtest.report import format_text, summarize  # noqa: E402

_DAY_MS = 24 * 60 * 60 * 1000
_WARMUP_DAYS = 55  # el ER de velas diarias necesita ~50 días previos


def _parse_date(value: str) -> int:
    fmt = "%Y-%m-%d %H:%M" if " " in value else "%Y-%m-%d"
    return int(datetime.strptime(value, fmt).replace(tzinfo=timezone.utc).timestamp() * 1000)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.backtest", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=float, default=180, help="días a simular hacia atrás desde --end")
    ap.add_argument("--start", help="inicio UTC (YYYY-MM-DD o 'YYYY-MM-DD HH:MM'); anula --days")
    ap.add_argument("--end", help="fin UTC; por defecto, ahora")
    ap.add_argument("--symbols", help="lista separada por comas; por defecto, top por volumen de hoy")
    ap.add_argument("--top", type=int, default=40, help="tamaño del universo si no se da --symbols")
    ap.add_argument("--balance", type=float, default=100.0)
    ap.add_argument("--max-grids", type=int, default=2)
    ap.add_argument("--max-risk", type=float, default=0.25)
    ap.add_argument("--sl-pct", type=float, help="stop-loss como fracción del balance")
    ap.add_argument("--tp-pct", type=float, help="take-profit como fracción del balance")
    ap.add_argument("--er-max", type=float, help="ER máximo para considerar el mercado lateral")
    ap.add_argument("--policy", choices=["RECENTER", "CLOSE"], help="qué hacer ante OUT_OF_RANGE")
    ap.add_argument("--max-recenters", type=int, help="tope de re-centrados por grid")
    ap.add_argument("--regime-action", choices=["OBSERVE", "PAUSE", "CANCEL_SIDE", "REDUCE", "CLOSE"],
                    default="OBSERVE", help="A6: qué hacer ante tendencia con el grid abierto")
    ap.add_argument("--regime-interval", help="velas del ER de régimen (por defecto 4h, como producción)")
    ap.add_argument("--regime-er", type=float, help="umbral de ER de régimen (por defecto 0.35)")
    ap.add_argument("--regime-strikes", type=int, help="ciclos seguidos en tendencia antes de actuar")
    ap.add_argument("--fill-mode", choices=["through", "touch"], default="through")
    ap.add_argument("--slippage-bps", type=float, default=3.0)
    ap.add_argument("--no-kill-switch", action="store_true")
    ap.add_argument("--source", choices=["mainnet", "demo"], default="mainnet",
                    help="de dónde salen los precios; 'demo' sirve para validar contra lo que hizo el bot")
    ap.add_argument("--cache-dir", default="backtest_data")
    ap.add_argument("--offline", action="store_true", help="usar solo la caché, sin red")
    ap.add_argument("--json", help="ruta donde guardar el resumen + grids en JSON")
    ap.add_argument("--label", default="")
    args = ap.parse_args(argv)

    end_ms = _parse_date(args.end) if args.end else int(time.time() * 1000)
    end_ms -= end_ms % (5 * 60 * 1000)
    start_ms = _parse_date(args.start) if args.start else end_ms - int(args.days * _DAY_MS)

    filters = load_exchange_filters(args.cache_dir, offline=args.offline)
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    else:
        symbols = top_symbols_by_volume(args.top, filters)
    unknown = [s for s in symbols if s not in filters]
    if unknown:
        print(f"Sin filtros de mainnet (se omiten): {', '.join(unknown)}", file=sys.stderr)
    symbols = [s for s in symbols if s in filters]

    bars = {}
    for n, s in enumerate(symbols, 1):
        print(f"\rVelas {n}/{len(symbols)} {s:<14}", end="", file=sys.stderr, flush=True)
        b = load_bars(s, start_ms - _WARMUP_DAYS * _DAY_MS, end_ms, args.cache_dir, offline=args.offline)
        if len(b):
            bars[s] = b
    print("", file=sys.stderr)

    volume_bars = None
    if args.source == "demo":
        volume_bars = bars
        bars = {}
        demo_dir = os.path.join(args.cache_dir, "demo")
        for n, s in enumerate(symbols, 1):
            print(f"\rVelas demo {n}/{len(symbols)} {s:<14}", end="", file=sys.stderr, flush=True)
            b = load_bars(s, start_ms - _WARMUP_DAYS * _DAY_MS, end_ms, demo_dir,
                          offline=args.offline, base_url=DEMO_FAPI_BASE)
            if len(b):
                bars[s] = b
        print("", file=sys.stderr)

    cfg = SimConfig(
        balance=args.balance, max_concurrent_grids=args.max_grids, max_risk_pct=args.max_risk,
        stop_loss_pct=args.sl_pct, take_profit_pct=args.tp_pct, er_max_tradeable=args.er_max,
        out_of_range_policy=args.policy, max_recenters=args.max_recenters,
        fill_mode=args.fill_mode, slippage_bps=args.slippage_bps,
        kill_switch=not args.no_kill_switch,
        regime_action=args.regime_action, regime_interval=args.regime_interval,
        regime_er_threshold=args.regime_er, regime_strikes=args.regime_strikes,
    )
    market = HistoricalMarket(bars, filters, volume_bars)
    t0 = time.time()
    result = asyncio.run(Backtest(market, cfg, list(bars), start_ms, end_ms).run())
    summary = summarize(result)
    print(format_text(summary, args.label))
    print(f"\n({time.time() - t0:.1f} s de simulación)", file=sys.stderr)

    if args.json:
        from dataclasses import asdict
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"label": args.label, "summary": summary,
                       "grids": [asdict(r) for r in result.records],
                       "equity": result.equity}, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
