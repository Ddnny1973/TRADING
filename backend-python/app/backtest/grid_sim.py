"""
Simulación de UN grid: espejo en memoria de lo que hace `GridService` contra
Binance + SQLite (create_grid, fills, replenish_filled_orders,
close_grid_if_triggered, recenter_grid, cancel_grid).

Reglas de fidelidad:
- Los niveles salen de `GridEngine` y las validaciones de `indicators`
  (se reusa el código real, no una copia).
- Las constantes salen de `app.config_auto_params` salvo que `SimConfig` las
  sobreescriba (para eso sirve un backtester: probar otra política).
- Aritmética en float por velocidad; `tests/test_backtest_grid_sim.py` verifica
  que el PnL coincide con `calculate_grid_pnl` (Decimal) y que los helpers
  copiados coinciden con los de `GridService`.

Dos PnL por grid:
- `bot_pnl`: el que ve el bot (`calculate_grid_pnl` con fee maker). Es el que
  dispara SL/TP y el que queda en `historical_grid_logs`.
- `true_pnl`: caja real. Todas las comisiones (maker en límite, taker en
  órdenes que cruzan y en el cierre a mercado) y slippage del cierre.
"""

import math
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from typing import Callable, Dict, List, Optional

from app import config_auto_params as policy
from app.core.config import settings
from app.services.grid_engine import GridEngine, GridType
from app.services.indicators import validate_grid_step

_INTERVAL_HOURS = {
    "1m": 1 / 60, "3m": 3 / 60, "5m": 5 / 60, "15m": 15 / 60, "30m": 30 / 60,
    "1h": 1, "2h": 2, "4h": 4, "6h": 6, "8h": 8, "12h": 12,
    "1d": 24, "3d": 72, "1w": 168,
}


class GridRejected(ValueError):
    """El grid no se pudo crear (mismos motivos por los que create_grid lanza)."""


@dataclass
class SimConfig:
    # Perfil de capital (A2 por defecto: como corre el demo desde 2026-10-26)
    balance: float = 100.0
    max_concurrent_grids: int = 2
    max_risk_pct: float = 0.25

    # Política. None = la constante vigente en config_auto_params.
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    er_max_tradeable: Optional[float] = None
    out_of_range_policy: Optional[str] = None      # "RECENTER" | "CLOSE"
    max_recenters: Optional[int] = None            # None = sin tope (como el código hoy)

    # Ejecución
    maker_fee: float = 0.0002
    taker_fee: float = 0.0005
    slippage_bps: float = 3.0       # sobre el cierre a mercado
    fill_mode: str = "through"      # "through": el precio debe cruzar el nivel; "touch": basta tocarlo

    # Orquestación (n8n)
    cycle_minutes: int = 5          # WF2
    wf1_interval_hours: int = 4     # WF1
    watchdog_cycles: int = 3        # ciclos de WF2 sin grids antes de relanzar WF1
    kill_switch: bool = True        # T15; se asume rearme manual al día UTC siguiente
    grid_type: str = "GEOMETRIC"

    def policy_value(self, name: str):
        override = {
            "OUT_OF_RANGE_POLICY": self.out_of_range_policy,
        }.get(name)
        return override if override is not None else getattr(policy, name)


def snap_down(value: Decimal, step: Decimal) -> Decimal:
    """Copia de GridService._snap_down."""
    if step <= 0:
        return value
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step


def max_duration_hours(klines_interval: str, atr_period: int) -> float:
    """Copia de GridService._calculate_max_duration_hours."""
    return _INTERVAL_HOURS.get(klines_interval, 4.0) * atr_period * 4


def max_net_position_units(levels: int) -> int:
    """
    Copia de GridService._max_net_position_qty, expresada en múltiplos de
    quantity_per_order (todas las órdenes de un grid tienen la misma cantidad).
    """
    by_levels = math.ceil(levels * float(policy.MAX_NET_POSITION_RATIO) - 1e-12)
    return max(int(settings.MAX_NET_POSITION_LEVELS), by_levels)


@dataclass
class SimOrder:
    side: str
    price: float
    level_index: int
    cycle: int = 0
    source: Optional["SimOrder"] = None
    fill_price: Optional[float] = None


@dataclass
class GridRecord:
    """Resultado de un grid cerrado (equivale a una fila de historical_grid_logs)."""
    grid_id: int
    root_id: int
    symbol: str
    mode: str
    opened_ms: int
    closed_ms: int
    trigger: str
    levels: int
    leverage: int
    lower: float
    upper: float
    qty: float
    entry_price: float
    exit_price: float
    fills: int
    cycles: int
    cycles_net: float
    bot_pnl: float
    true_pnl: float
    fees: float
    recenter_count: int
    position_units_at_close: int


class SimGrid:
    _next_id = 0

    def __init__(self, cfg: SimConfig, symbol: str, lower: float, upper: float,
                 levels: int, qty: float, leverage: int,
                 stop_loss: Optional[float], take_profit: Optional[float],
                 max_duration: Optional[float], mode: str, now_ms: int,
                 price: float, filters: Dict[str, Decimal],
                 recenter_count: int = 0, root_id: Optional[int] = None,
                 inherited_units: int = 0):
        SimGrid._next_id += 1
        self.id = SimGrid._next_id
        self.root_id = root_id if root_id is not None else self.id
        self.cfg = cfg
        self.symbol = symbol
        self.levels = levels
        self.leverage = leverage
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.max_duration = max_duration
        self.mode = mode
        self.created_ms = now_ms
        self.entry_price = price
        self.recenter_count = recenter_count
        self.filters = filters

        if lower >= upper:
            raise GridRejected("lower_price must be less than upper_price")

        engine = GridEngine(symbol, lower, upper, levels, GridType(cfg.grid_type))
        raw_levels = engine.calculate_grid_levels()
        self.lower = float(engine.lower_price)
        self.upper = float(engine.upper_price)

        qty_dec = snap_down(Decimal(str(qty)), filters["step_size"])
        if qty_dec <= 0:
            raise GridRejected("quantity_per_order is smaller than the minimum step size")
        if min(raw_levels) * qty_dec < filters["min_notional"]:
            raise GridRejected("quantity_per_order too small: order notional below min_notional")
        try:
            validate_grid_step(
                Decimal(str(lower)), Decimal(str(upper)), levels,
                Decimal(str(cfg.maker_fee)), Decimal(str(settings.MIN_STEP_FEE_MULTIPLE)),
            )
        except ValueError as e:
            raise GridRejected(str(e))

        self.qty = float(qty_dec)
        self.price_levels = [float(snap_down(p, filters["tick_size"])) for p in raw_levels]

        # Estado
        self.open_orders: List[SimOrder] = []
        self.pending_replenish: List[SimOrder] = []
        self.pos_units = 0
        self.buy_qty = 0.0
        self.buy_cost = 0.0
        self.sell_qty = 0.0
        self.sell_proceeds = 0.0
        self.cash = 0.0
        self.fees = 0.0
        self.fills = 0
        self.cycles = 0
        self.cycles_net = 0.0
        self.out_of_range_strikes = 0
        self.replenish_paused_cycles = 0

        # Inventario heredado de un re-centrado: entra como un fill sintético al
        # precio de marca (A1a, GridService._orders_for_pnl), sin comisión.
        if inherited_units:
            q = abs(inherited_units) * self.qty
            if inherited_units > 0:
                self.buy_qty += q
                self.buy_cost += q * price
            else:
                self.sell_qty += q
                self.sell_proceeds += q * price
            self.cash -= inherited_units * self.qty * price
            self.pos_units = inherited_units

        for idx, level_price in enumerate(self.price_levels):
            side = "BUY" if level_price < price else "SELL"
            self.open_orders.append(SimOrder(side, level_price, idx))

    # ------------------------------------------------------------------ fills

    @property
    def position(self) -> float:
        return self.pos_units * self.qty

    def _fill(self, order: SimOrder, price: float, taker: bool = False) -> None:
        q = self.qty
        fee = q * price * (self.cfg.taker_fee if taker else self.cfg.maker_fee)
        if order.side == "BUY":
            self.buy_qty += q
            self.buy_cost += q * price
            self.cash -= q * price
            self.pos_units += 1
        else:
            self.sell_qty += q
            self.sell_proceeds += q * price
            self.cash += q * price
            self.pos_units -= 1
        self.cash -= fee
        self.fees += fee
        self.fills += 1
        order.fill_price = price
        self.pending_replenish.append(order)

        # Un ciclo se cierra cuando se llena una orden de reposición
        # (GridService._record_completed_cycles).
        if order.source is not None and order.source.fill_price is not None:
            if order.side == "SELL":
                buy_p, sell_p = order.source.fill_price, price
            else:
                buy_p, sell_p = price, order.source.fill_price
            gross = q * (sell_p - buy_p)
            self.cycles += 1
            self.cycles_net += gross - q * (buy_p + sell_p) * self.cfg.maker_fee

    def apply_bar(self, high: float, low: float) -> int:
        """Llena las órdenes límite que la vela alcanzó. Devuelve cuántas."""
        if not self.open_orders:
            return 0
        touch = self.cfg.fill_mode == "touch"
        still_open: List[SimOrder] = []
        filled = 0
        for o in self.open_orders:
            if o.side == "BUY":
                hit = low <= o.price if touch else low < o.price
            else:
                hit = high >= o.price if touch else high > o.price
            if hit:
                self._fill(o, o.price)
                filled += 1
            else:
                still_open.append(o)
        self.open_orders = still_open
        return filled

    # -------------------------------------------------------------- reposición

    def replenish(self, price: float) -> int:
        """Espejo de replenish_filled_orders. Devuelve cuántas órdenes repuso."""
        blocked: Optional[str] = None
        if self.mode == "NEUTRAL":
            tolerance = max_net_position_units(self.levels) * float(policy.REPLENISH_POSITION_TOLERANCE_RATIO)
            if tolerance > 0 and abs(self.pos_units) > tolerance:
                blocked = "BUY" if self.pos_units > 0 else "SELL"

        placed = 0
        remaining: List[SimOrder] = []
        pending, self.pending_replenish = self.pending_replenish, []
        n = len(self.price_levels)
        for o in pending:
            if o.side == "BUY" and o.level_index + 1 < n:
                new_idx, new_side = o.level_index + 1, "SELL"
            elif o.side == "SELL" and o.level_index - 1 >= 0:
                new_idx, new_side = o.level_index - 1, "BUY"
            else:
                continue  # fill en el borde: no hay nivel adyacente
            if new_side == blocked:
                remaining.append(o)  # queda reclamable para cuando baje la posición
                continue
            new_order = SimOrder(new_side, self.price_levels[new_idx], new_idx,
                                 cycle=o.cycle + 1, source=o)
            # Una GTC que ya cruza el mercado se ejecuta de inmediato como taker.
            crosses = (new_side == "SELL" and new_order.price < price) or \
                      (new_side == "BUY" and new_order.price > price)
            if crosses:
                self._fill(new_order, price, taker=True)
            else:
                self.open_orders.append(new_order)
            placed += 1
        # Los fills taker de arriba quedaron en pending_replenish para el próximo ciclo.
        self.pending_replenish = remaining + self.pending_replenish
        if blocked and remaining:
            self.replenish_paused_cycles += 1
        return placed

    # --------------------------------------------------------------------- PnL

    def bot_pnl(self, price: float) -> float:
        """Espejo en float de indicators.calculate_grid_pnl (fee maker)."""
        fee = self.cfg.maker_fee
        avg_buy = self.buy_cost / self.buy_qty if self.buy_qty > 0 else 0.0
        avg_sell = self.sell_proceeds / self.sell_qty if self.sell_qty > 0 else 0.0
        matched = min(self.buy_qty, self.sell_qty)
        realized = 0.0
        if matched > 0:
            realized = matched * (avg_sell - avg_buy) - matched * avg_buy * fee - matched * avg_sell * fee
        net = self.buy_qty - self.sell_qty
        if net > 0:
            unrealized = net * (price - avg_buy)
        elif net < 0:
            unrealized = -net * (avg_sell - price)
        else:
            unrealized = 0.0
        unrealized -= abs(net) * price * fee
        return realized + unrealized

    def true_pnl_marked(self, price: float) -> float:
        """Caja real + inventario a precio de marca (sin costo de salida)."""
        return self.cash + self.position * price

    # ------------------------------------------------------------------ cierre

    def check_close(self, now_ms: int, price: float,
                    atr_4h: Callable[[], Optional[float]]) -> Optional[str]:
        """
        Espejo de close_grid_if_triggered: devuelve el trigger o None.
        `atr_4h` es perezoso: solo se evalúa si el precio está fuera del rango.
        """
        age_hours = (now_ms - self.created_ms) / 3_600_000.0
        if self.max_duration is not None and age_hours >= self.max_duration:
            return "EXPIRED"

        if age_hours * 60 >= policy.CHECK_CLOSE_GRACE_MINUTES:
            decisive_out = False
            if price < self.lower or price > self.upper:
                atr = atr_4h() or 0.0
                buffer = atr * float(policy.OUT_OF_RANGE_ATR_BUFFER)
                decisive_out = price < (self.lower - buffer) or price > (self.upper + buffer)
            self.out_of_range_strikes = self.out_of_range_strikes + 1 if decisive_out else 0
            if decisive_out and self.out_of_range_strikes >= policy.OUT_OF_RANGE_STRIKES_TO_TRIGGER:
                return "OUT_OF_RANGE"

        soft_cap = max_net_position_units(self.levels)
        if soft_cap > 0 and abs(self.pos_units) > soft_cap * float(policy.MAX_POSITION_HARD_MULTIPLE):
            return "MAX_POSITION"

        pnl = self.bot_pnl(price)
        if self.stop_loss is not None and pnl <= -self.stop_loss:
            return "STOP_LOSS"
        if self.take_profit is not None and pnl >= self.take_profit:
            return "TAKE_PROFIT"
        return None

    def _record(self, now_ms: int, trigger: str, price: float, bot_pnl: float,
                true_pnl: float, units_at_close: int) -> GridRecord:
        return GridRecord(
            grid_id=self.id, root_id=self.root_id, symbol=self.symbol, mode=self.mode,
            opened_ms=self.created_ms, closed_ms=now_ms, trigger=trigger,
            levels=self.levels, leverage=self.leverage, lower=self.lower, upper=self.upper,
            qty=self.qty, entry_price=self.entry_price, exit_price=price,
            fills=self.fills, cycles=self.cycles, cycles_net=self.cycles_net,
            bot_pnl=bot_pnl, true_pnl=true_pnl, fees=self.fees,
            recenter_count=self.recenter_count, position_units_at_close=units_at_close,
        )

    def close_market(self, now_ms: int, price: float, trigger: str) -> GridRecord:
        """Espejo de cancel_grid: cancela órdenes y cierra la posición a mercado."""
        bot_pnl = self.bot_pnl(price)  # cancel_grid lo calcula ANTES de cerrar
        units = self.pos_units
        if units:
            slip = self.cfg.slippage_bps / 10_000.0
            exec_price = price * (1 - slip) if units > 0 else price * (1 + slip)
            fee = abs(self.position) * exec_price * self.cfg.taker_fee
            self.cash += self.position * exec_price - fee
            self.fees += fee
            self.pos_units = 0
        self.open_orders = []
        return self._record(now_ms, trigger, price, bot_pnl, self.cash, units)

    def close_keep_inventory(self, now_ms: int, price: float, trigger: str) -> GridRecord:
        """
        Cierra el grid SIN tocar la posición (re-centrado, o fin del backtest):
        el resultado queda a precio de marca y el inventario pasa a quien siga.
        """
        bot_pnl = self.bot_pnl(price)
        true_pnl = self.true_pnl_marked(price)
        self.open_orders = []
        return self._record(now_ms, trigger, price, bot_pnl, true_pnl, self.pos_units)
