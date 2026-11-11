"""
Backtester (N6): el simulador de un grid debe comportarse como GridService.

Lo que se verifica aquí es la FIDELIDAD: helpers copiados idénticos a los de
producción, PnL en float igual al `calculate_grid_pnl` real, y las reglas de
fills / reposición / cierre.
"""

from decimal import Decimal

import pytest

from app import config_auto_params as policy
from app.backtest.grid_sim import (
    GridRejected, SimConfig, SimGrid, max_duration_hours, max_net_position_units, snap_down,
)
from app.services.grid_service import GridService
from app.services.indicators import calculate_grid_pnl

FILTERS = {"tick_size": Decimal("0.01"), "step_size": Decimal("0.01"), "min_notional": Decimal("5")}
HOUR = 3_600_000


def make_grid(cfg=None, mode="NEUTRAL", price=100.0, lower=90.0, upper=110.0, levels=11,
              qty=0.06, stop_loss=1.0, take_profit=3.0, max_duration=224.0, **kw):
    """
    Grid de referencia: 11 niveles geométricos entre 90 y 110 con el precio en 100.
    Niveles ≈ 90, 91.83, 93.69, 95.59, 97.53, 99.50 | 101.52, 103.58, 105.68, 107.82, 110.
    El BUY más cercano es el índice 5 y el SELL más cercano el 6.
    """
    return SimGrid(cfg or SimConfig(), "TESTUSDT", lower, upper, levels, qty, 3,
                   stop_loss, take_profit, max_duration, mode, 0, price, FILTERS, **kw)


def record_fills(grid):
    """Registra cada fill como una orden al estilo de grid_orders."""
    orders = []
    original = grid._fill

    def spy(order, price, taker=False):
        original(order, price, taker)
        orders.append({"side": order.side, "price": Decimal(str(price)),
                       "quantity": Decimal(str(grid.qty)), "executed_qty": Decimal(str(grid.qty)),
                       "avg_fill_price": Decimal(str(price))})

    grid._fill = spy
    return orders


# ---------------------------------------------------------------- helpers copiados

@pytest.mark.parametrize("value,step", [("123.4567", "0.01"), ("0.000123", "0.00001"), ("5", "1")])
def test_snap_down_matches_grid_service(value, step):
    assert snap_down(Decimal(value), Decimal(step)) == GridService._snap_down(Decimal(value), Decimal(step))


@pytest.mark.parametrize("interval", ["1h", "4h", "1d", "15m", "desconocido"])
def test_max_duration_matches_grid_service(interval):
    assert max_duration_hours(interval, 14) == GridService._calculate_max_duration_hours(interval, 14)


@pytest.mark.parametrize("levels", range(4, 21))
def test_max_net_position_matches_grid_service(levels):
    qty = Decimal("0.07")
    expected = GridService._max_net_position_qty({"quantity_per_order": qty, "levels": levels})
    assert max_net_position_units(levels) * qty == expected


# ------------------------------------------------------------------------- PnL

def test_bot_pnl_matches_calculate_grid_pnl():
    grid = make_grid()
    orders = record_fills(grid)
    # Camino con vaivén y deriva: llena compras y ventas en varios ciclos.
    path = [(101, 97), (99, 94), (103, 96), (107, 101), (104, 95), (99, 92), (106, 98)]
    for high, low in path:
        grid.apply_bar(high, low)
        grid.replenish((high + low) / 2)
    assert grid.fills >= 8 and grid.cycles >= 2

    for price in (93.0, 100.0, 108.5):
        expected = calculate_grid_pnl(orders, Decimal(str(price)), fee_rate=Decimal("0.0002"))
        assert grid.bot_pnl(price) == pytest.approx(float(expected["total_pnl"]), abs=1e-9)
        assert grid.position == pytest.approx(float(expected["net_position_qty"]), abs=1e-12)


def test_bot_pnl_with_inherited_inventory_matches_orders_for_pnl():
    grid = make_grid(mode="LONG", inherited_units=4)
    orders = [{"side": "BUY", "price": Decimal("100"), "quantity": Decimal("0.24"),
               "executed_qty": Decimal("0.24"), "avg_fill_price": Decimal("100")}]
    fills = record_fills(grid)
    grid.apply_bar(105.0, 99.6)  # llena los SELL de 101.52 y 103.58
    assert grid.pos_units == 2 and len(fills) == 2
    expected = calculate_grid_pnl(orders + fills, Decimal("104"), fee_rate=Decimal("0.0002"))
    assert grid.bot_pnl(104.0) == pytest.approx(float(expected["total_pnl"]), abs=1e-9)


def test_true_pnl_counts_all_fees_and_slippage():
    cfg = SimConfig(slippage_bps=10.0)
    grid = make_grid(cfg)
    grid.apply_bar(100.0, 99.0)  # llena solo la compra de 99.50
    assert grid.pos_units == 1
    buy = grid.price_levels[5]
    record = grid.close_market(HOUR, 97.0, "STOP_LOSS")
    exec_price = 97.0 * (1 - 0.001)
    expected = 0.06 * (exec_price - buy) - 0.06 * buy * 0.0002 - 0.06 * exec_price * 0.0005
    assert record.true_pnl == pytest.approx(expected, abs=1e-12)
    assert record.true_pnl < record.bot_pnl  # el bot no ve taker ni slippage
    assert grid.pos_units == 0


# ----------------------------------------------------------- fills y reposición

def test_orders_start_buy_below_and_sell_above_price():
    grid = make_grid()
    assert all(o.side == "BUY" for o in grid.open_orders if o.price < 100.0)
    assert all(o.side == "SELL" for o in grid.open_orders if o.price >= 100.0)
    assert len(grid.open_orders) == 11


def test_fill_mode_through_requires_crossing_the_level():
    level = make_grid().price_levels[5]
    through = make_grid(SimConfig(fill_mode="through"))
    touch = make_grid(SimConfig(fill_mode="touch"))
    assert through.apply_bar(100.0, level) == 0
    assert touch.apply_bar(100.0, level) == 1
    assert through.apply_bar(100.0, level - 0.01) == 1


def test_cycle_closes_when_replenish_order_fills():
    grid = make_grid()
    buy, sell = grid.price_levels[5], grid.price_levels[6]
    grid.apply_bar(100.0, buy - 0.01)
    assert grid.cycles == 0
    assert grid.replenish(buy) == 1          # SELL en el nivel de arriba
    grid.apply_bar(sell + 0.01, buy)
    assert grid.cycles == 1
    expected = 0.06 * (sell - buy) - 0.06 * (buy + sell) * 0.0002
    assert grid.cycles_net == pytest.approx(expected, abs=1e-12)
    # Igual que en producción: en ese nivel ya descansaba el SELL inicial, así
    # que se llenan los dos y el grid queda corto una unidad.
    assert grid.pos_units == -1


def test_replenish_that_crosses_the_market_fills_as_taker():
    grid = make_grid()
    buy, sell = grid.price_levels[5], grid.price_levels[6]
    grid.apply_bar(100.0, buy - 0.01)
    fees_before = grid.fees
    grid.replenish(sell + 1.0)  # el precio ya rebotó por encima del nivel de venta
    assert grid.cycles == 1 and grid.pos_units == 0
    assert grid.fees - fees_before == pytest.approx(0.06 * (sell + 1.0) * 0.0005)


def _long_six_then_one_sell(mode):
    """Llena las 6 compras, repone, y deja un SELL llenado pendiente de reponer."""
    grid = make_grid(mode=mode)
    grid.apply_bar(100.0, 89.0)
    assert grid.pos_units == 6
    assert grid.replenish(89.5) == 6         # un SELL por cada BUY llenado
    grid.apply_bar(91.9, 89.5)               # se llena el SELL de 91.83
    assert grid.pos_units == 5 and len(grid.pending_replenish) == 1
    grid.pos_units = 6                       # como si otro BUY se hubiera llenado a la vez
    return grid


def test_neutral_grid_pauses_accumulating_side_over_tolerance():
    tolerance = max_net_position_units(11) * float(policy.REPLENISH_POSITION_TOLERANCE_RATIO)
    assert 5 < tolerance < 6

    grid = _long_six_then_one_sell("NEUTRAL")
    assert grid.replenish(91.0) == 0         # el BUY que tocaría reponer acumula: en pausa
    assert len(grid.pending_replenish) == 1  # sigue reclamable
    grid.pos_units = 4
    assert grid.replenish(91.0) == 1         # bajó la posición: ahora sí se repone

    long_grid = _long_six_then_one_sell("LONG")
    assert long_grid.replenish(91.0) == 1    # LONG/SHORT no tienen ese freno


# ---------------------------------------------------------------------- cierres

def test_stop_loss_and_take_profit_use_bot_pnl():
    grid = make_grid(stop_loss=0.5, take_profit=3.0)
    grid.apply_bar(100.0, 89.0)
    assert grid.check_close(10 * 60_000, 96.0, lambda: 1.0) is None
    assert grid.check_close(10 * 60_000, 85.0, lambda: 1.0) == "STOP_LOSS"


def test_out_of_range_needs_grace_buffer_and_two_strikes():
    grid = make_grid(stop_loss=None, take_profit=None)
    atr = lambda: 2.0  # buffer = 1.0
    assert grid.check_close(10 * 60_000, 120.0, atr) is None          # dentro de la gracia
    assert grid.check_close(31 * 60_000, 110.5, atr) is None          # fuera, pero dentro del buffer
    assert grid.out_of_range_strikes == 0
    assert grid.check_close(36 * 60_000, 112.0, atr) is None          # primer strike
    assert grid.check_close(41 * 60_000, 109.0, atr) is None          # volvió: reinicia
    assert grid.check_close(46 * 60_000, 112.0, atr) is None
    assert grid.check_close(51 * 60_000, 112.0, atr) == "OUT_OF_RANGE"


def test_expired_and_max_position():
    grid = make_grid(stop_loss=None, take_profit=None, max_duration=56.0)
    assert grid.check_close(56 * HOUR, 100.0, lambda: 1.0) == "EXPIRED"
    grid = make_grid(stop_loss=None, take_profit=None)
    hard = max_net_position_units(11) * float(policy.MAX_POSITION_HARD_MULTIPLE)
    grid.pos_units = int(hard) + 1
    assert grid.check_close(HOUR, 100.0, lambda: 1.0) == "MAX_POSITION"


def test_recenter_chain_accounting_adds_up():
    """Padre re-centrado + hijo liquidado = una sola operación, sin PnL fantasma."""
    parent = make_grid()
    parent.apply_bar(100.0, 93.0)
    units = parent.pos_units
    assert units > 0
    cash_before = parent.cash
    rec_parent = parent.close_keep_inventory(HOUR, 92.0, "RECENTERED")

    child = make_grid(mode="LONG", price=92.0, lower=84.0, upper=100.0, inherited_units=units)
    assert child.bot_pnl(92.0) == pytest.approx(-units * 0.06 * 92.0 * 0.0002)  # solo el fee de salida estimado
    rec_child = child.close_market(HOUR, 92.0, "STOP_LOSS")

    cfg = SimConfig()
    exec_price = 92.0 * (1 - cfg.slippage_bps / 10_000)
    direct = cash_before + units * 0.06 * exec_price - units * 0.06 * exec_price * cfg.taker_fee
    assert rec_parent.true_pnl + rec_child.true_pnl == pytest.approx(direct, abs=1e-9)


def test_grid_with_step_below_fee_floor_is_rejected():
    with pytest.raises(GridRejected):
        make_grid(lower=99.9, upper=100.1, levels=11)
    with pytest.raises(GridRejected):
        make_grid(qty=0.01)  # nocional por debajo del mínimo
