"""
Backtest de COBRO DE FUNDING con posición cubierta (hipótesis, no es lo que
corre el bot).

Idea: comprar el activo en spot y vender la misma cantidad en el perpetuo. El
precio deja de importar (lo que gana una pata lo pierde la otra) y el resultado
es el funding que cobra el corto cuando la tasa es positiva, menos costos.

Reglas, sobre datos diarios UTC:
- Señal: funding medio de los últimos `lookback_days`, anualizado. Se entra en
  los símbolos líquidos con mayor funding si supera `entry_apr`; se sale cuando
  cae bajo `exit_apr` (tras `min_hold_days`). Ejecución a la apertura siguiente.
- Capital: una parte compra el spot y el resto es margen del perpetuo
  (`perp_leverage` 2 → 2/3 en spot, 1/3 de margen), repartido en `max_positions`.
- Costos: comisión y slippage en las DOS patas al entrar y al salir, y el costo
  de reequilibrar margen cuando el precio se aleja `rebalance_move` de la entrada.
- El resultado incluye la variación de la base (precio perpetuo − spot).

Desde `backend-python/`:

    python -m app.backtest.carry --start 2022-11-11 --end 2026-11-11
    python -m app.backtest.carry --symbols ETHUSDT --always-on

Solo usa endpoints públicos de mainnet (spot y futuros); caché en
`backtest_data/trend/`. Límites: docs/analisis-bot/08-funding-cubierto.md.
"""

import argparse
import json
import math
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.backtest.data import _http_get_json
from app.backtest.trend import (
    DAY_MS, EXCLUDED, _iso, _parse_day, _read_csv, _write_csv, load_daily, load_funding,
)

SPOT_BASE = "https://api.binance.com"
Bars = Dict[int, Tuple[float, float, float, float, float]]


# ---------------------------------------------------------------------------
# Datos spot
# ---------------------------------------------------------------------------

def spot_symbol(perp: str) -> Tuple[str, float]:
    """Par spot equivalente y multiplicador de precio (1000PEPEUSDT → PEPEUSDT × 1000)."""
    m = re.match(r"^(10+)([A-Z].*)$", perp)
    if m:
        return m.group(2), float(m.group(1))
    return perp, 1.0


def load_spot_filters(cache_dir: str, offline: bool = False) -> Dict[str, Dict[str, float]]:
    """{símbolo spot: {step_size, min_notional}} de los pares USDT en TRADING (hoy)."""
    path = os.path.join(cache_dir, "spot_filters.json")
    if offline or os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    info = _http_get_json("/api/v3/exchangeInfo", {"permissions": "SPOT"}, base=SPOT_BASE)
    out: Dict[str, Dict[str, float]] = {}
    for s in info.get("symbols", []):
        if s.get("status") != "TRADING" or s.get("quoteAsset") != "USDT":
            continue
        flt = {"step_size": 0.0001, "min_notional": 5.0}
        for f in s.get("filters", []):
            if f.get("filterType") == "LOT_SIZE":
                flt["step_size"] = float(f["stepSize"])
            elif f.get("filterType") in ("NOTIONAL", "MIN_NOTIONAL"):
                flt["min_notional"] = float(f.get("minNotional", 5.0))
        out[s["symbol"]] = flt
    os.makedirs(cache_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f)
    return out


def load_spot_daily(perp: str, start_ms: int, end_ms: int, cache_dir: str,
                    offline: bool = False) -> Bars:
    """Velas diarias spot del par equivalente a `perp`, ya en la unidad del perpetuo."""
    spot, mult = spot_symbol(perp)
    path = os.path.join(cache_dir, f"{perp}_spot_1d.csv")
    rows = {int(r[0]): tuple(float(x) for x in r[1:6]) for r in _read_csv(path)}
    if not offline:
        cursor = (max(rows) + 1) * DAY_MS if rows else start_ms
        changed = False
        while cursor + DAY_MS <= end_ms:
            try:
                data = _http_get_json("/api/v3/klines", {
                    "symbol": spot, "interval": "1d", "startTime": cursor,
                    "endTime": end_ms - 1, "limit": 1000}, base=SPOT_BASE)
            except RuntimeError:
                break
            data = [k for k in data if int(k[0]) + DAY_MS <= end_ms]
            if not data:
                break
            for k in data:
                rows[int(k[0]) // DAY_MS] = (float(k[1]) * mult, float(k[2]) * mult, float(k[3]) * mult,
                                             float(k[4]) * mult, float(k[7]))
            changed = True
            cursor = int(data[-1][0]) + DAY_MS
            time.sleep(0.1)
        if changed or not os.path.exists(path):
            _write_csv(path, [(d, *map(repr, v)) for d, v in sorted(rows.items())])
    lo, hi = start_ms // DAY_MS, end_ms // DAY_MS
    return {d: v for d, v in rows.items() if lo <= d < hi}


# ---------------------------------------------------------------------------
# Simulación
# ---------------------------------------------------------------------------

@dataclass
class CarryConfig:
    balance: float = 100.0
    perp_leverage: float = 2.0        # 2 → 2/3 del capital en spot, 1/3 de margen
    max_positions: int = 3
    universe_size: int = 30
    volume_days: int = 30
    min_history_days: int = 90
    lookback_days: int = 7
    entry_apr: float = 0.10           # funding anualizado mínimo para entrar
    exit_apr: float = 0.0
    min_hold_days: int = 7
    spot_fee: float = 0.001
    perp_fee: float = 0.0005
    slippage_bps: float = 5.0         # por pata y por lado
    rebalance_move: float = 0.30      # mover margen si el precio se aleja ±30 %
    always_on: bool = False           # mantener siempre los símbolos dados, sin señal


@dataclass
class CarryPosition:
    symbol: str
    qty: float
    entry_day: int
    spot_entry: float
    perp_entry: float
    ref_price: float
    entry_notional: float = 0.0
    funding: float = 0.0
    fees: float = 0.0
    rebalances: int = 0
    realized_basis: float = 0.0   # resultado de precio ya liquidado en reequilibrios


@dataclass
class CarryTrade:
    symbol: str
    entry_day: int
    exit_day: int
    notional: float
    funding: float
    basis_pnl: float
    fees: float
    pnl: float
    rebalances: int
    reason: str


@dataclass
class CarryResult:
    config: CarryConfig
    start_day: int
    end_day: int
    trades: List[CarryTrade] = field(default_factory=list)
    equity: List[Tuple[int, float]] = field(default_factory=list)
    stats: Dict[str, int] = field(default_factory=dict)
    invested_days: int = 0


class CarryBacktest:
    def __init__(self, perp: Dict[str, Bars], spot: Dict[str, Bars],
                 funding: Dict[str, Dict[int, float]], perp_filters: Dict[str, Dict[str, Any]],
                 spot_filters: Dict[str, Dict[str, float]], cfg: CarryConfig,
                 start_day: int, end_day: int, symbols: Optional[List[str]] = None):
        usable = [s for s in perp if s in spot and spot[s] and s in funding and s not in EXCLUDED]
        if symbols:
            usable = [s for s in usable if s in symbols]
        self.perp = {s: perp[s] for s in usable}
        self.spot = {s: spot[s] for s in usable}
        self.funding = funding
        self.perp_filters, self.spot_filters = perp_filters, spot_filters
        self.cfg = cfg
        self.start_day, self.end_day = start_day, end_day
        self.first_day = {s: max(min(self.perp[s]), min(self.spot[s])) for s in usable}
        self.positions: Dict[str, CarryPosition] = {}
        self.realized = 0.0
        self.trades: List[CarryTrade] = []
        self.stats: Dict[str, int] = {}
        self.last: Dict[str, Tuple[float, float]] = {}   # símbolo → (spot, perp) al último cierre

    def _bump(self, key: str) -> None:
        self.stats[key] = self.stats.get(key, 0) + 1

    # ------------------------------------------------------------- señales

    def trailing_apr(self, symbol: str, day: int) -> Optional[float]:
        """Funding medio de los `lookback_days` hasta `day` incluido, anualizado."""
        f = self.funding.get(symbol, {})
        n = self.cfg.lookback_days
        values = [f.get(d) for d in range(day - n + 1, day + 1)]
        if any(v is None for v in values):
            return None
        return sum(values) / n * 365.0

    def universe(self, day: int) -> List[str]:
        cfg = self.cfg
        ranked = []
        for s, b in self.perp.items():
            if day - self.first_day[s] < cfg.min_history_days or day not in b or day not in self.spot[s]:
                continue
            vols = [b.get(d) for d in range(day - cfg.volume_days + 1, day + 1)]
            if any(v is None for v in vols):
                continue
            ranked.append((sum(v[4] for v in vols), s))
        ranked.sort(reverse=True)
        return [s for _, s in ranked[:cfg.universe_size]]

    # ----------------------------------------------------------- ejecución

    def _unrealized(self, p: CarryPosition) -> float:
        spot, perp = self.last.get(p.symbol, (p.spot_entry, p.perp_entry))
        return (p.qty * (spot - p.spot_entry) - p.qty * (perp - p.perp_entry)
                + p.realized_basis + p.funding - p.fees)

    def _target_qty(self, symbol: str, equity: float, spot_px: float) -> float:
        cfg = self.cfg
        target = equity * cfg.perp_leverage / (1.0 + cfg.perp_leverage) / cfg.max_positions
        pf = self.perp_filters.get(symbol, {})
        sf = self.spot_filters.get(spot_symbol_name(symbol), {})
        step = max(float(pf.get("step_size", 0.001)), float(sf.get("step_size", 0.0001)))
        return math.floor(target / spot_px / step + 1e-9) * step if target > 0 else 0.0

    def _rebalance(self, pos: CarryPosition, spot_px: float, perp_px: float, equity: float) -> None:
        """
        El precio se alejó: el spot está totalmente pagado y el margen del
        perpetuo es finito, así que hay que devolver el nocional a su objetivo
        (vender spot y recomprar perpetuo si subió; lo contrario si bajó).
        Se liquida el resultado de precio acumulado y se paga comisión y
        slippage solo sobre la cantidad que cambia.
        """
        cfg = self.cfg
        new_qty = self._target_qty(pos.symbol, equity, spot_px) or pos.qty
        pos.realized_basis += pos.qty * (spot_px - pos.spot_entry) - pos.qty * (perp_px - pos.perp_entry)
        delta = abs(new_qty - pos.qty)
        pos.fees += delta * (spot_px * cfg.spot_fee + perp_px * cfg.perp_fee
                             + (spot_px + perp_px) * cfg.slippage_bps / 10_000.0)
        pos.qty, pos.spot_entry, pos.perp_entry, pos.ref_price = new_qty, spot_px, perp_px, perp_px
        pos.rebalances += 1
        self._bump("rebalances")

    def equity(self) -> float:
        return self.cfg.balance + self.realized + sum(self._unrealized(p) for p in self.positions.values())

    def _open(self, symbol: str, day: int, equity: float) -> None:
        cfg = self.cfg
        slip = cfg.slippage_bps / 10_000.0
        spot_px = self.spot[symbol][day][0] * (1 + slip)     # compra spot
        perp_px = self.perp[symbol][day][0] * (1 - slip)     # venta del perpetuo
        pf = self.perp_filters.get(symbol, {})
        sf = self.spot_filters.get(spot_symbol_name(symbol), {})
        qty = self._target_qty(symbol, equity, spot_px)
        if qty <= 0 or qty * perp_px < float(pf.get("min_notional", 5)) \
                or qty * spot_px < float(sf.get("min_notional", 5.0)):
            self._bump("entry_skipped_min_notional")
            return
        pos = CarryPosition(symbol, qty, day, spot_px, perp_px, perp_px)
        pos.entry_notional = qty * spot_px
        pos.fees = qty * spot_px * cfg.spot_fee + qty * perp_px * cfg.perp_fee
        self.positions[symbol] = pos
        self.last[symbol] = (spot_px, perp_px)
        self._bump("entries")

    def _close(self, pos: CarryPosition, day: int, spot_raw: float, perp_raw: float, reason: str) -> None:
        cfg = self.cfg
        slip = cfg.slippage_bps / 10_000.0
        spot_px, perp_px = spot_raw * (1 - slip), perp_raw * (1 + slip)
        fees = pos.fees + pos.qty * spot_px * cfg.spot_fee + pos.qty * perp_px * cfg.perp_fee
        basis = (pos.qty * (spot_px - pos.spot_entry) - pos.qty * (perp_px - pos.perp_entry)
                 + pos.realized_basis)
        pnl = basis + pos.funding - fees
        self.realized += pnl
        self.trades.append(CarryTrade(pos.symbol, pos.entry_day, day, pos.entry_notional,
                                      pos.funding, basis, fees, pnl, pos.rebalances, reason))
        del self.positions[pos.symbol]

    # ------------------------------------------------------------------ run

    def run(self) -> CarryResult:
        cfg = self.cfg
        curve: List[Tuple[int, float]] = []
        pending_exits: List[str] = []
        pending_entries: List[str] = []
        equity_prev = cfg.balance
        invested_days = 0

        for day in range(self.start_day, self.end_day):
            # 1. Órdenes de ayer, a la apertura de hoy.
            for s in pending_exits:
                if s in self.positions and day in self.spot[s] and day in self.perp[s]:
                    self._close(self.positions[s], day, self.spot[s][day][0], self.perp[s][day][0], "SIGNAL")
            for s in pending_entries:
                if s in self.positions or len(self.positions) >= cfg.max_positions:
                    continue
                if day in self.spot[s] and day in self.perp[s]:
                    self._open(s, day, equity_prev)
            pending_exits, pending_entries = [], []

            # 2. Funding del día, marca al cierre y reequilibrio de margen.
            for pos in self.positions.values():
                sb, pb = self.spot[pos.symbol].get(day), self.perp[pos.symbol].get(day)
                if sb is None or pb is None:
                    continue
                self.last[pos.symbol] = (sb[3], pb[3])
                rate = self.funding.get(pos.symbol, {}).get(day, 0.0)
                # El día de entrada ya pasó el cobro de las 00:00: cuentan 2 de 3.
                share = 2.0 / 3.0 if pos.entry_day == day else 1.0
                pos.funding += pos.qty * pb[3] * rate * share      # el corto cobra si la tasa es > 0
                if abs(pb[3] / pos.ref_price - 1) >= cfg.rebalance_move:
                    self._rebalance(pos, sb[3], pb[3], equity_prev)
            if self.positions:
                invested_days += 1
            equity_prev = self.equity()
            curve.append((day, equity_prev))

            # 3. Señales al cierre → órdenes para mañana.
            if cfg.always_on:
                pending_entries = [s for s in self.perp if s not in self.positions]
                continue
            for s, pos in self.positions.items():
                apr = self.trailing_apr(s, day)
                if apr is not None and apr < cfg.exit_apr and day - pos.entry_day >= cfg.min_hold_days:
                    pending_exits.append(s)
            ranked = []
            for s in self.universe(day):
                if s in self.positions:
                    continue
                apr = self.trailing_apr(s, day)
                if apr is not None and apr >= cfg.entry_apr:
                    ranked.append((apr, s))
            ranked.sort(reverse=True)
            free = cfg.max_positions - len(self.positions) + len(pending_exits)
            pending_entries = [s for _, s in ranked[:max(free, 0)]]

        last = self.end_day - 1
        for pos in list(self.positions.values()):
            spot, perp = self.last.get(pos.symbol, (pos.spot_entry, pos.perp_entry))
            self._close(pos, last, spot, perp, "END")
        if curve:
            curve[-1] = (last, self.equity())
        return CarryResult(cfg, self.start_day, self.end_day, self.trades, curve, self.stats, invested_days)


def spot_symbol_name(perp: str) -> str:
    return spot_symbol(perp)[0]


# ---------------------------------------------------------------------------
# Reporte
# ---------------------------------------------------------------------------

def summarize(result: CarryResult) -> Dict[str, Any]:
    cfg, eq, trades = result.config, result.equity, result.trades
    days = max(result.end_day - result.start_day, 1)
    final = eq[-1][1] if eq else cfg.balance
    peak, max_dd, prev, rets = cfg.balance, 0.0, cfg.balance, []
    by_year: Dict[str, float] = {}
    year, year_start = None, cfg.balance
    for d, v in eq:
        peak = max(peak, v)
        max_dd = max(max_dd, 1 - v / peak if peak > 0 else 0.0)
        rets.append(v / prev - 1 if prev > 0 else 0.0)
        y = _iso(d)[:4]
        if y != year:
            year, year_start = y, prev
        by_year[y] = (v / year_start - 1) * 100 if year_start > 0 else 0.0
        prev = v
    mean = sum(rets) / len(rets) if rets else 0.0
    var = sum((r - mean) ** 2 for r in rets) / len(rets) if rets else 0.0
    pnls = sorted(t.pnl for t in trades)
    return {
        "period": {"start": _iso(result.start_day), "end": _iso(result.end_day), "days": days},
        "config": asdict(cfg),
        "final_equity": final,
        "total_return_pct": (final / cfg.balance - 1) * 100,
        "cagr_pct": ((final / cfg.balance) ** (365.0 / days) - 1) * 100 if final > 0 else -100.0,
        "max_drawdown_pct": max_dd * 100,
        "sharpe": mean / math.sqrt(var) * math.sqrt(365) if var > 0 else 0.0,
        "by_year_pct": by_year,
        "trades": len(trades),
        "win_rate_pct": 100 * sum(1 for t in trades if t.pnl > 0) / len(trades) if trades else 0.0,
        "funding": sum(t.funding for t in trades),
        "basis_pnl": sum(t.basis_pnl for t in trades),
        "fees": sum(t.fees for t in trades),
        "pnl_without_top3": sum(pnls[:-3]) if len(pnls) > 3 else 0.0,
        "avg_hold_days": sum(t.exit_day - t.entry_day for t in trades) / len(trades) if trades else 0.0,
        "invested_days_pct": 100 * result.invested_days / days,
        "stats": result.stats,
    }


def format_text(s: Dict[str, Any], label: str = "") -> str:
    c, p = s["config"], s["period"]
    return "\n".join([
        f"=== Funding cubierto {label} ===",
        f"Periodo: {p['start']} -> {p['end']} ({p['days']} días) | capital {c['balance']:.0f} USDT | "
        f"{c['max_positions']} posiciones | entra >= {c['entry_apr']*100:.0f} %/año, sale < {c['exit_apr']*100:.0f} %/año",
        "",
        f"Capital final:    {s['final_equity']:8.2f} USDT  ({s['total_return_pct']:+.1f} % | {s['cagr_pct']:+.1f} %/año)",
        f"Drawdown máximo:  {s['max_drawdown_pct']:8.2f} %",
        f"Sharpe (diario):  {s['sharpe']:8.2f}",
        "Por año:          " + "  ".join(f"{y} {r:+.1f} %" for y, r in s["by_year_pct"].items()),
        "",
        f"Funding cobrado {s['funding']:+.2f} | base {s['basis_pnl']:+.2f} | comisiones y slippage {s['fees']:.2f}",
        f"Operaciones: {s['trades']} | positivas {s['win_rate_pct']:.0f} % | duración media {s['avg_hold_days']:.0f} días | "
        f"invertido el {s['invested_days_pct']:.0f} % del tiempo",
        f"Resultado sin las 3 mejores operaciones: {s['pnl_without_top3']:+.2f}",
        "Contadores: " + "  ".join(f"{k}={v}" for k, v in sorted(s["stats"].items())),
    ])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def load_market(start_day: int, end_day: int, cache_dir: str, offline: bool,
                symbols: Optional[List[str]] = None, warmup_days: int = 200):
    from app.backtest.data import load_exchange_filters

    perp_filters = load_exchange_filters(cache_dir, offline=offline)
    spot_filters = load_spot_filters(cache_dir, offline=offline)
    lo, hi = (start_day - warmup_days) * DAY_MS, end_day * DAY_MS
    if symbols is None:
        # Candidatos: perpetuos con funding ya en caché (los que alguna vez fueron líquidos).
        symbols = sorted(f[:-len("_funding.csv")] for f in os.listdir(cache_dir) if f.endswith("_funding.csv"))
    symbols = [s for s in symbols if s in perp_filters and spot_symbol_name(s) in spot_filters
               and s not in EXCLUDED]
    perp, spot, funding = {}, {}, {}
    for n, s in enumerate(symbols, 1):
        print(f"\rDatos {n}/{len(symbols)} {s:<16}", end="", file=sys.stderr, flush=True)
        perp[s] = load_daily(s, lo, hi, cache_dir, offline)
        spot[s] = load_spot_daily(s, lo, hi, cache_dir, offline)
        funding[s] = load_funding(s, lo, hi, cache_dir, offline)
    print("", file=sys.stderr)
    return perp, spot, funding, perp_filters, spot_filters


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.backtest.carry", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default="2022-11-11")
    ap.add_argument("--end", default=None)
    ap.add_argument("--balance", type=float, default=100.0)
    ap.add_argument("--symbols", help="lista fija separada por comas")
    ap.add_argument("--always-on", action="store_true", help="mantener siempre --symbols, sin señal")
    ap.add_argument("--max-positions", type=int, default=3)
    ap.add_argument("--entry-apr", type=float, default=0.10)
    ap.add_argument("--exit-apr", type=float, default=0.0)
    ap.add_argument("--lookback-days", type=int, default=7)
    ap.add_argument("--min-hold-days", type=int, default=7)
    ap.add_argument("--perp-leverage", type=float, default=2.0)
    ap.add_argument("--cache-dir", default=os.path.join("backtest_data", "trend"))
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--label", default="")
    args = ap.parse_args(argv)

    start_day = _parse_day(args.start)
    end_day = _parse_day(args.end) if args.end else int(time.time()) // 86400
    symbols = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else None
    perp, spot, funding, pf, sf = load_market(start_day, end_day, args.cache_dir, args.offline, symbols)
    cfg = CarryConfig(
        balance=args.balance, max_positions=args.max_positions if not args.always_on else len(perp),
        entry_apr=args.entry_apr, exit_apr=args.exit_apr, lookback_days=args.lookback_days,
        min_hold_days=args.min_hold_days, perp_leverage=args.perp_leverage, always_on=args.always_on,
    )
    result = CarryBacktest(perp, spot, funding, pf, sf, cfg, start_day, end_day, symbols).run()
    print(format_text(summarize(result), args.label))
    return 0


if __name__ == "__main__":
    sys.exit(main())
