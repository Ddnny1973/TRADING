"""
Backtest de FUNDING EXTREMO COMO SEÑAL DE DIRECCIÓN (hipótesis, no es lo que
corre el bot).

Idea: un funding muy alto sostenido indica demasiados largos apalancados; se opera
en contra (corto). Uno muy negativo, lo contrario (largo). A diferencia de
`carry.py`, el funding aquí es información, no ingreso.

Reusa el motor de `trend.py` (ejecución a la apertura siguiente, stop por ATR,
tamaño por riesgo, universo por volumen a cada fecha, comisiones, slippage y
funding real). Solo cambia la señal: `_decide`.

Desde `backend-python/`:

    python -m app.backtest.fundsig --offline
    python -m app.backtest.fundsig --offline --entry-apr 1.0 --hold-days 10 --short-only

Reglas y criterio de aprobación: docs/analisis-bot/09-funding-senal.md.
"""

import argparse
import os
import sys
from dataclasses import dataclass
from typing import List, Optional, Tuple

from app.backtest import trend
from app.backtest.trend import (
    DAY_MS, TrendBacktest, TrendConfig, _parse_day, format_text, load_market, summarize,
)


@dataclass
class FundingSignalConfig(TrendConfig):
    lookback_days: int = 3            # media del funding de estos días, anualizada
    entry_apr: float = 0.5            # umbral absoluto (0,5 = 50 %/año)
    hold_days: int = 5                # permanencia máxima
    top_k: int = 3                    # entradas nuevas por lado y día
    allow_long: bool = True
    # Controles: `invert` opera a favor de la multitud; `shift_days` usa el funding de
    # otro momento del periodo (dando la vuelta), es decir, una señal sin información.
    invert: bool = False
    shift_days: int = 0
    span: Optional[Tuple[int, int]] = None   # (inicio, fin) del funding disponible para el desfase
    # Valores distintos a los de tendencia
    stop_atr: float = 2.5
    entry_funding_share: float = 2.0 / 3.0


class FundingSignalBacktest(TrendBacktest):
    exit_reason = "TIME"

    def _apr(self, symbol: str, day: int) -> Optional[float]:
        """Funding medio de `lookback_days` hasta `day` incluido, anualizado (None si falta algún día)."""
        cfg = self.cfg
        f = self.funding.get(symbol, {})
        if cfg.shift_days and cfg.span:
            lo, hi = cfg.span
            day = lo + (day - lo + cfg.shift_days) % (hi - lo)
        values = [f.get(d) for d in range(day - cfg.lookback_days + 1, day + 1)]
        if any(v is None for v in values):
            return None
        return sum(values) / cfg.lookback_days * 365.0

    def _decide(self, day: int):
        cfg = self.cfg
        exits = [s for s, p in self.positions.items() if day + 1 - p.entry_day >= cfg.hold_days]
        # Contra la multitud: funding alto → corto. Invertido: a favor.
        side_when_high = 1 if cfg.invert else -1
        longs: List[Tuple[float, str, int, float]] = []
        shorts: List[Tuple[float, str, int, float]] = []
        for s in self.universe(day):
            if s in self.positions:
                continue
            apr = self._apr(s, day)
            atr = self._atr(s, day)
            if apr is None or not atr or self.bars[s].get(day) is None:
                continue
            if apr > cfg.entry_apr:
                side = side_when_high
            elif apr < -cfg.entry_apr:
                side = -side_when_high
            else:
                continue
            if (side > 0 and not cfg.allow_long) or (side < 0 and not cfg.allow_short):
                continue
            (longs if side > 0 else shorts).append((abs(apr), s, side, cfg.stop_atr * atr))
        entries = sorted(longs, reverse=True)[:cfg.top_k] + sorted(shorts, reverse=True)[:cfg.top_k]
        return exits, entries


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.backtest.fundsig", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default="2022-11-11")
    ap.add_argument("--end", default="2026-11-11")
    ap.add_argument("--balance", type=float, default=100.0)
    ap.add_argument("--entry-apr", type=float, default=0.5)
    ap.add_argument("--lookback-days", type=int, default=3)
    ap.add_argument("--hold-days", type=int, default=5)
    ap.add_argument("--top-k", type=int, default=3)
    ap.add_argument("--stop-atr", type=float, default=2.5)
    ap.add_argument("--risk-pct", type=float, default=0.01)
    ap.add_argument("--max-positions", type=int, default=10)
    ap.add_argument("--universe", type=int, default=20)
    ap.add_argument("--short-only", action="store_true")
    ap.add_argument("--long-only", action="store_true")
    ap.add_argument("--invert", action="store_true", help="control: operar a favor de la multitud")
    ap.add_argument("--shift-days", type=int, default=0, help="control: usar el funding de otro momento")
    ap.add_argument("--cache-dir", default=os.path.join("backtest_data", "trend"))
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--label", default="")
    args = ap.parse_args(argv)

    start_day, end_day = _parse_day(args.start), _parse_day(args.end)
    bars, filters, funding = load_market(start_day, end_day, args.cache_dir, args.offline)
    cfg = FundingSignalConfig(
        balance=args.balance, entry_apr=args.entry_apr, lookback_days=args.lookback_days,
        hold_days=args.hold_days, top_k=args.top_k, stop_atr=args.stop_atr, risk_pct=args.risk_pct,
        max_positions=args.max_positions, universe_size=args.universe,
        allow_short=not args.long_only, allow_long=not args.short_only,
        invert=args.invert, shift_days=args.shift_days, span=(start_day, end_day),
    )
    result = FundingSignalBacktest(bars, filters, funding, cfg, start_day, end_day).run()
    print(format_text(summarize(result), args.label or "funding como señal"))
    return 0


if __name__ == "__main__":
    for _var in ("BINANCE_API_KEY", "BINANCE_API_SECRET", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"):
        os.environ.setdefault(_var, "backtest")
    sys.exit(main())
