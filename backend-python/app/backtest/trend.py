"""
Backtest de SEGUIMIENTO DE TENDENCIA (hipótesis, no es lo que corre el bot).

Regla (estilo Donchian / "tortugas"), sobre velas diarias UTC:
- Entrada: el cierre supera el máximo de los N días previos → largo; cae bajo
  el mínimo → corto. Se ejecuta a la apertura del día siguiente.
- Salida: el cierre cruza el canal contrario de M días (M < N), o se toca el
  stop fijo a `stop_atr` × ATR de la entrada (se revisa contra el máximo/mínimo
  del día; si el día abre más allá del stop, se sale a la apertura).
- Tamaño: cada operación arriesga `risk_pct` del capital hasta su stop, así un
  activo más volátil lleva menos nocional.
- Universo: cada día, los `universe_size` perpetuos USDT con más volumen en los
  30 días previos (ranking a esa fecha, no el de hoy).

Costos: comisión taker + slippage en cada lado y el funding real de Binance.

Desde `backend-python/`:

    python -m app.backtest.trend --start 2022-11-11 --end 2026-11-11
    python -m app.backtest.trend --entry-days 40 --exit-days 20 --long-only

Solo usa endpoints públicos de mainnet; caché en `backtest_data/trend/`.
Límites: ver docs/analisis-bot/07-seguimiento-tendencia.md.
"""

import argparse
import csv
import json
import math
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from app.backtest.data import _http_get_json

DAY_MS = 24 * 60 * 60 * 1000
# Pares que no son una apuesta direccional sobre un criptoactivo.
EXCLUDED = {"USDCUSDT", "FDUSDUSDT", "BTCDOMUSDT", "DEFIUSDT"}


# ---------------------------------------------------------------------------
# Datos
# ---------------------------------------------------------------------------

def _read_csv(path: str) -> List[List[str]]:
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return [r for r in csv.reader(f) if r and not r[0].startswith("#")]


def _write_csv(path: str, rows: List[tuple]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)


def load_daily(symbol: str, start_ms: int, end_ms: int, cache_dir: str,
               offline: bool = False) -> Dict[int, Tuple[float, float, float, float, float]]:
    """Velas diarias cerradas: {día: (open, high, low, close, volumen USDT)}."""
    path = os.path.join(cache_dir, f"{symbol}_1d.csv")
    rows = {int(r[0]): tuple(float(x) for x in r[1:6]) for r in _read_csv(path)}
    if not offline:
        cursor = (max(rows) + 1) * DAY_MS if rows else start_ms
        changed = False
        while cursor + DAY_MS <= end_ms:
            try:
                data = _http_get_json("/fapi/v1/klines", {
                    "symbol": symbol, "interval": "1d", "startTime": cursor,
                    "endTime": end_ms - 1, "limit": 1500})
            except RuntimeError:
                break
            data = [k for k in data if int(k[0]) + DAY_MS <= end_ms]  # sin la vela en formación
            if not data:
                break
            for k in data:
                rows[int(k[0]) // DAY_MS] = (float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[7]))
            changed = True
            cursor = int(data[-1][0]) + DAY_MS
            time.sleep(0.1)
        if changed or not os.path.exists(path):
            _write_csv(path, [(d, *map(repr, v)) for d, v in sorted(rows.items())])
    lo, hi = start_ms // DAY_MS, end_ms // DAY_MS
    return {d: v for d, v in rows.items() if lo <= d < hi}


def load_funding(symbol: str, start_ms: int, end_ms: int, cache_dir: str,
                 offline: bool = False) -> Dict[int, float]:
    """Funding por día UTC: {día: suma de las tasas cobradas ese día}."""
    path = os.path.join(cache_dir, f"{symbol}_funding.csv")
    rows = {int(r[0]): float(r[1]) for r in _read_csv(path)}
    if not offline:
        cursor = max(rows) + 1 if rows else start_ms
        changed = False
        while cursor < end_ms:
            try:
                data = _http_get_json("/fapi/v1/fundingRate", {
                    "symbol": symbol, "startTime": cursor, "endTime": end_ms, "limit": 1000})
            except RuntimeError:
                break
            if not data:
                break
            for k in data:
                rows[int(k["fundingTime"])] = float(k["fundingRate"])
            changed = True
            cursor = int(data[-1]["fundingTime"]) + 1
            time.sleep(0.7)  # este endpoint tiene un límite bajo (500 / 5 min)
            if len(data) < 1000:
                break
        if changed or not os.path.exists(path):
            _write_csv(path, [(t, repr(r)) for t, r in sorted(rows.items())])
    out: Dict[int, float] = {}
    for t, rate in rows.items():
        if start_ms <= t < end_ms:
            out[t // DAY_MS] = out.get(t // DAY_MS, 0.0) + rate
    return out


# ---------------------------------------------------------------------------
# Simulación
# ---------------------------------------------------------------------------

@dataclass
class TrendConfig:
    balance: float = 100.0
    entry_days: int = 20
    exit_days: int = 10
    atr_days: int = 20
    stop_atr: float = 2.0
    risk_pct: float = 0.01            # del capital, por operación, hasta el stop
    max_positions: int = 10
    max_leverage: float = 2.0         # nocional total / capital
    max_position_pct: float = 0.5     # nocional de una posición / capital
    universe_size: int = 20
    volume_days: int = 30
    min_history_days: int = 90
    allow_short: bool = True
    taker_fee: float = 0.0005
    slippage_bps: float = 5.0
    use_funding: bool = True


@dataclass
class Position:
    symbol: str
    side: int                # +1 largo, -1 corto
    qty: float
    entry_day: int
    entry_price: float
    stop: float
    costs: float = 0.0       # comisiones (positivo = pagado)
    funding: float = 0.0     # funding neto (positivo = cobrado)


@dataclass
class Trade:
    symbol: str
    side: int
    entry_day: int
    exit_day: int
    entry_price: float
    exit_price: float
    qty: float
    pnl: float               # neto de comisiones y funding
    fees: float
    funding: float
    reason: str              # CHANNEL | STOP | END


@dataclass
class TrendResult:
    config: TrendConfig
    start_day: int
    end_day: int
    trades: List[Trade] = field(default_factory=list)
    equity: List[Tuple[int, float]] = field(default_factory=list)   # (día, capital al cierre)
    stats: Dict[str, int] = field(default_factory=dict)


Bars = Dict[int, Tuple[float, float, float, float, float]]


class TrendBacktest:
    def __init__(self, bars: Dict[str, Bars], filters: Dict[str, Dict[str, Decimal]],
                 funding: Dict[str, Dict[int, float]], cfg: TrendConfig,
                 start_day: int, end_day: int):
        self.bars = {s: b for s, b in bars.items() if s not in EXCLUDED and b}
        self.filters = filters
        self.funding = funding
        self.cfg = cfg
        self.start_day, self.end_day = start_day, end_day
        self.first_day = {s: min(b) for s, b in self.bars.items()}
        self.positions: Dict[str, Position] = {}
        self.realized = 0.0
        self.trades: List[Trade] = []
        self.stats: Dict[str, int] = {}
        self.last_close: Dict[str, float] = {}

    def _bump(self, key: str) -> None:
        self.stats[key] = self.stats.get(key, 0) + 1

    # ------------------------------------------------------------ indicadores

    def _window(self, symbol: str, day: int, n: int) -> Optional[List[tuple]]:
        """Las n velas ANTERIORES a `day` (sin incluirlo), o None si falta alguna."""
        b = self.bars[symbol]
        out = []
        for d in range(day - n, day):
            v = b.get(d)
            if v is None:
                return None
            out.append(v)
        return out

    def _atr(self, symbol: str, day: int) -> Optional[float]:
        """ATR simple de `atr_days` con las velas hasta `day` incluido."""
        w = self._window(symbol, day + 1, self.cfg.atr_days + 1)
        if w is None:
            return None
        trs = [max(w[i][1] - w[i][2], abs(w[i][1] - w[i - 1][3]), abs(w[i][2] - w[i - 1][3]))
               for i in range(1, len(w))]
        return sum(trs) / len(trs)

    def universe(self, day: int) -> List[str]:
        """Top por volumen de los `volume_days` hasta `day` incluido (ranking a esa fecha)."""
        cfg = self.cfg
        ranked = []
        for s, b in self.bars.items():
            if day - self.first_day[s] < cfg.min_history_days or day not in b:
                continue
            vol = 0.0
            for d in range(day - cfg.volume_days + 1, day + 1):
                v = b.get(d)
                if v is None:
                    vol = -1.0
                    break
                vol += v[4]
            if vol > 0:
                ranked.append((vol, s))
        ranked.sort(reverse=True)
        return [s for _, s in ranked[:cfg.universe_size]]

    # ------------------------------------------------------------- ejecución

    def equity(self) -> float:
        total = self.cfg.balance + self.realized
        for p in self.positions.values():
            price = self.last_close.get(p.symbol, p.entry_price)
            total += p.side * p.qty * (price - p.entry_price) - p.costs + p.funding
        return total

    def _gross(self) -> float:
        return sum(p.qty * self.last_close.get(p.symbol, p.entry_price) for p in self.positions.values())

    def _open(self, symbol: str, side: int, stop_dist: float, day: int, open_price: float,
              equity: float) -> None:
        cfg = self.cfg
        slip = cfg.slippage_bps / 10_000.0
        price = open_price * (1 + side * slip)
        if stop_dist <= 0 or equity <= 0:
            return
        notional = cfg.risk_pct * equity / stop_dist * price
        notional = min(notional, cfg.max_position_pct * equity,
                       cfg.max_leverage * equity - self._gross())
        flt = self.filters.get(symbol, {})
        step = float(flt.get("step_size", Decimal("0.001")))
        qty = math.floor(notional / price / step + 1e-9) * step if notional > 0 else 0.0
        if qty <= 0 or qty * price < float(flt.get("min_notional", Decimal("5"))):
            self._bump("entry_skipped_min_notional")
            return
        pos = Position(symbol, side, qty, day, price, price - side * stop_dist)
        pos.costs = qty * price * cfg.taker_fee
        self.positions[symbol] = pos
        self._bump("entries")

    def _close(self, pos: Position, day: int, raw_price: float, reason: str) -> None:
        cfg = self.cfg
        price = raw_price * (1 - pos.side * cfg.slippage_bps / 10_000.0)
        fees = pos.costs + pos.qty * price * cfg.taker_fee
        pnl = pos.side * pos.qty * (price - pos.entry_price) - fees + pos.funding
        self.realized += pnl
        self.trades.append(Trade(pos.symbol, pos.side, pos.entry_day, day, pos.entry_price, price,
                                 pos.qty, pnl, fees, pos.funding, reason))
        del self.positions[pos.symbol]

    # ------------------------------------------------------------------ run

    def run(self) -> TrendResult:
        cfg = self.cfg
        equity_curve: List[Tuple[int, float]] = []
        pending_exits: List[str] = []
        pending_entries: List[Tuple[float, str, int, float]] = []   # (fuerza, símbolo, lado, dist. stop)
        equity_prev = cfg.balance

        for day in range(self.start_day, self.end_day):
            # 1. Órdenes decididas al cierre de ayer: se ejecutan a la apertura de hoy.
            for s in pending_exits:
                bar = self.bars[s].get(day)
                if s in self.positions and bar is not None:
                    self._close(self.positions[s], day, bar[0], "CHANNEL")
            pending_entries.sort(reverse=True)
            for _, s, side, stop_dist in pending_entries:
                bar = self.bars[s].get(day)
                if bar is None or s in self.positions:
                    continue
                if len(self.positions) >= cfg.max_positions:
                    self._bump("entry_skipped_slots_full")
                    continue
                self._open(s, side, stop_dist, day, bar[0], equity_prev)
            pending_exits, pending_entries = [], []

            # 2. Stops contra el rango del día (incluye posiciones abiertas hoy).
            for pos in list(self.positions.values()):
                bar = self.bars[pos.symbol].get(day)
                if bar is None:
                    continue
                o, h, l, _c, _ = bar
                if pos.side > 0 and l <= pos.stop:
                    self._close(pos, day, min(o, pos.stop) if pos.entry_day < day else pos.stop, "STOP")
                elif pos.side < 0 and h >= pos.stop:
                    self._close(pos, day, max(o, pos.stop) if pos.entry_day < day else pos.stop, "STOP")

            # 3. Funding del día y marca al cierre.
            for pos in self.positions.values():
                bar = self.bars[pos.symbol].get(day)
                if bar is None:
                    continue
                self.last_close[pos.symbol] = bar[3]
                if cfg.use_funding:
                    rate = self.funding.get(pos.symbol, {}).get(day, 0.0)
                    pos.funding -= pos.side * pos.qty * bar[3] * rate   # el largo paga si la tasa es > 0
            equity_prev = self.equity()
            equity_curve.append((day, equity_prev))

            # 4. Señales con los cierres hasta hoy → órdenes para mañana.
            for s, pos in self.positions.items():
                bar = self.bars[s].get(day)
                w = self._window(s, day, cfg.exit_days)
                if bar is None or w is None:
                    continue
                if (pos.side > 0 and bar[3] < min(x[2] for x in w)) or \
                   (pos.side < 0 and bar[3] > max(x[1] for x in w)):
                    pending_exits.append(s)
            for s in self.universe(day):
                bar = self.bars[s].get(day)
                w = self._window(s, day, cfg.entry_days)
                atr = self._atr(s, day)
                if bar is None or w is None or not atr:
                    continue
                side = 1 if bar[3] > max(x[1] for x in w) else -1 if bar[3] < min(x[2] for x in w) else 0
                if side == 0 or (side < 0 and not cfg.allow_short):
                    continue
                held = self.positions.get(s)
                if held is not None and held.side == side:
                    continue
                channel = max(x[1] for x in w) if side > 0 else min(x[2] for x in w)
                pending_entries.append((abs(bar[3] - channel) / atr, s, side, cfg.stop_atr * atr))

        last = self.end_day - 1
        for pos in list(self.positions.values()):
            self._close(pos, last, self.last_close.get(pos.symbol, pos.entry_price), "END")
        if equity_curve:
            equity_curve[-1] = (last, self.equity())
        return TrendResult(cfg, self.start_day, self.end_day, self.trades, equity_curve, self.stats)


# ---------------------------------------------------------------------------
# Reporte
# ---------------------------------------------------------------------------

def _iso(day: int) -> str:
    return datetime.fromtimestamp(day * 86400, tz=timezone.utc).strftime("%Y-%m-%d")


def summarize(result: TrendResult) -> Dict[str, Any]:
    cfg, eq, trades = result.config, result.equity, result.trades
    days = max(result.end_day - result.start_day, 1)
    final = eq[-1][1] if eq else cfg.balance
    total_ret = final / cfg.balance - 1
    cagr = (final / cfg.balance) ** (365.0 / days) - 1 if final > 0 else -1.0

    peak, max_dd = cfg.balance, 0.0
    rets, prev = [], cfg.balance
    for _, v in eq:
        peak = max(peak, v)
        max_dd = max(max_dd, 1 - v / peak if peak > 0 else 0.0)
        rets.append(v / prev - 1 if prev > 0 else 0.0)
        prev = v
    mean = sum(rets) / len(rets) if rets else 0.0
    var = sum((r - mean) ** 2 for r in rets) / len(rets) if rets else 0.0
    sharpe = mean / math.sqrt(var) * math.sqrt(365) if var > 0 else 0.0

    by_year: Dict[str, float] = {}
    prev_v, prev_year = cfg.balance, None
    start_of_year = cfg.balance
    for d, v in eq:
        y = _iso(d)[:4]
        if y != prev_year:
            start_of_year, prev_year = prev_v, y
        by_year[y] = v / start_of_year - 1 if start_of_year > 0 else 0.0
        prev_v = v

    wins = [t.pnl for t in trades if t.pnl > 0]
    losses = [t.pnl for t in trades if t.pnl <= 0]
    gross_win, gross_loss = sum(wins), -sum(losses)
    top3 = sum(sorted(wins, reverse=True)[:3])
    return {
        "period": {"start": _iso(result.start_day), "end": _iso(result.end_day), "days": days},
        "config": asdict(cfg),
        "final_equity": final, "total_return_pct": total_ret * 100, "cagr_pct": cagr * 100,
        "max_drawdown_pct": max_dd * 100, "sharpe": sharpe,
        "by_year_pct": {y: r * 100 for y, r in by_year.items()},
        "trades": len(trades),
        "win_rate_pct": 100 * len(wins) / len(trades) if trades else 0.0,
        "avg_win": gross_win / len(wins) if wins else 0.0,
        "avg_loss": -gross_loss / len(losses) if losses else 0.0,
        "profit_factor": gross_win / gross_loss if gross_loss > 0 else float("inf") if gross_win else 0.0,
        "top3_share_of_gross_win_pct": 100 * top3 / gross_win if gross_win > 0 else 0.0,
        "avg_hold_days": sum(t.exit_day - t.entry_day for t in trades) / len(trades) if trades else 0.0,
        "pnl_long": sum(t.pnl for t in trades if t.side > 0),
        "pnl_short": sum(t.pnl for t in trades if t.side < 0),
        "fees": sum(t.fees for t in trades), "funding": sum(t.funding for t in trades),
        "by_reason": {r: [sum(1 for t in trades if t.reason == r),
                          sum(t.pnl for t in trades if t.reason == r)]
                      for r in sorted({t.reason for t in trades})},
        "stats": result.stats,
    }


def format_text(s: Dict[str, Any], label: str = "") -> str:
    c, p = s["config"], s["period"]
    lines = [
        f"=== Tendencia {label} ===".replace("  ", " "),
        f"Periodo: {p['start']} -> {p['end']} ({p['days']} días) | capital {c['balance']:.0f} USDT | "
        f"canal {c['entry_days']}/{c['exit_days']} | stop {c['stop_atr']}×ATR | riesgo {c['risk_pct']*100:.1f} % | "
        f"{'largo y corto' if c['allow_short'] else 'solo largo'}",
        "",
        f"Capital final:     {s['final_equity']:8.2f} USDT  ({s['total_return_pct']:+.1f} % | {s['cagr_pct']:+.1f} %/año)",
        f"Drawdown máximo:   {s['max_drawdown_pct']:8.1f} %",
        f"Sharpe (diario):   {s['sharpe']:8.2f}",
        "Por año:           " + "  ".join(f"{y} {r:+.1f} %" for y, r in s["by_year_pct"].items()),
        "",
        f"Operaciones: {s['trades']} | aciertos {s['win_rate_pct']:.0f} % | ganancia media {s['avg_win']:+.2f} | "
        f"pérdida media {s['avg_loss']:+.2f} | factor de beneficio {s['profit_factor']:.2f}",
        f"Las 3 mejores explican el {s['top3_share_of_gross_win_pct']:.0f} % de lo ganado | "
        f"duración media {s['avg_hold_days']:.1f} días",
        f"Largos {s['pnl_long']:+.2f} | cortos {s['pnl_short']:+.2f} | comisiones {s['fees']:.2f} | funding {s['funding']:+.2f}",
        "Salidas: " + "  ".join(f"{r} {n} ({v:+.2f})" for r, (n, v) in s["by_reason"].items()),
        "Contadores: " + "  ".join(f"{k}={v}" for k, v in sorted(s["stats"].items())),
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_day(value: str) -> int:
    return int(datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()) // 86400


def load_market(start_day: int, end_day: int, cache_dir: str, offline: bool, symbols=None,
                with_funding: bool = True, warmup_days: int = 200):
    """Descarga (o lee de caché) velas diarias de todos los perpetuos USDT y su funding."""
    from app.backtest.data import load_exchange_filters

    filters = load_exchange_filters(cache_dir, offline=offline)
    symbols = symbols or sorted(s for s in filters if s not in EXCLUDED)
    lo, hi = (start_day - warmup_days) * DAY_MS, end_day * DAY_MS
    bars: Dict[str, Bars] = {}
    for n, s in enumerate(symbols, 1):
        print(f"\rVelas diarias {n}/{len(symbols)} {s:<16}", end="", file=sys.stderr, flush=True)
        b = load_daily(s, lo, hi, cache_dir, offline)
        if b:
            bars[s] = b
    print("", file=sys.stderr)
    funding: Dict[str, Dict[int, float]] = {}
    if with_funding:
        # Solo hace falta el funding de lo que alguna vez entra al universo.
        probe = TrendBacktest(bars, filters, {}, TrendConfig(universe_size=30), start_day, end_day)
        needed = sorted({s for d in range(start_day, end_day, 7) for s in probe.universe(d)})
        for n, s in enumerate(needed, 1):
            print(f"\rFunding {n}/{len(needed)} {s:<16}", end="", file=sys.stderr, flush=True)
            funding[s] = load_funding(s, start_day * DAY_MS, hi, cache_dir, offline)
        print("", file=sys.stderr)
    return bars, filters, funding


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.backtest.trend", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default="2022-11-11")
    ap.add_argument("--end", default=None, help="por defecto, hoy (UTC)")
    ap.add_argument("--balance", type=float, default=100.0)
    ap.add_argument("--entry-days", type=int, default=20)
    ap.add_argument("--exit-days", type=int, default=10)
    ap.add_argument("--stop-atr", type=float, default=2.0)
    ap.add_argument("--risk-pct", type=float, default=0.01)
    ap.add_argument("--max-positions", type=int, default=10)
    ap.add_argument("--max-leverage", type=float, default=2.0)
    ap.add_argument("--universe", type=int, default=20)
    ap.add_argument("--long-only", action="store_true")
    ap.add_argument("--no-funding", action="store_true")
    ap.add_argument("--slippage-bps", type=float, default=5.0)
    ap.add_argument("--cache-dir", default=os.path.join("backtest_data", "trend"))
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--json")
    ap.add_argument("--label", default="")
    args = ap.parse_args(argv)

    start_day = _parse_day(args.start)
    end_day = _parse_day(args.end) if args.end else int(time.time()) // 86400
    bars, filters, funding = load_market(start_day, end_day, args.cache_dir, args.offline,
                                         with_funding=not args.no_funding)
    cfg = TrendConfig(
        balance=args.balance, entry_days=args.entry_days, exit_days=args.exit_days,
        stop_atr=args.stop_atr, risk_pct=args.risk_pct, max_positions=args.max_positions,
        max_leverage=args.max_leverage, universe_size=args.universe,
        allow_short=not args.long_only, slippage_bps=args.slippage_bps,
        use_funding=not args.no_funding,
    )
    result = TrendBacktest(bars, filters, funding, cfg, start_day, end_day).run()
    summary = summarize(result)
    print(format_text(summary, args.label))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"label": args.label, "summary": summary,
                       "trades": [asdict(t) for t in result.trades], "equity": result.equity}, f, indent=1)
    return 0


if __name__ == "__main__":
    for _var in ("BINANCE_API_KEY", "BINANCE_API_SECRET", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"):
        os.environ.setdefault(_var, "backtest")
    sys.exit(main())
