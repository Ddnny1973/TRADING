"""Pure unit tests for indicators.py (ATR, grid bounds, PnL, SL/TP) - no I/O."""

from decimal import Decimal

import pytest

from app.services.indicators import (
    calculate_atr,
    calculate_grid_bounds,
    calculate_grid_pnl,
    check_sl_tp,
)
from tests.conftest import make_klines


def test_calculate_atr_constant_true_range():
    # make_klines() yields a constant TR of 2*spread per candle (see conftest docstring)
    klines = make_klines(count=15, base_price=Decimal("42500"), spread=Decimal("100"))
    atr = calculate_atr(klines, period=14)
    assert atr == Decimal("200")


def test_calculate_atr_requires_period_plus_one_klines():
    klines = make_klines(count=10)
    with pytest.raises(ValueError, match="al menos"):
        calculate_atr(klines, period=14)


def test_calculate_atr_rejects_invalid_period():
    with pytest.raises(ValueError):
        calculate_atr(make_klines(count=15), period=0)


def test_calculate_grid_bounds_centers_on_current_price():
    bounds = calculate_grid_bounds(
        current_price=Decimal("42500"),
        atr=Decimal("200"),
        multiplier=Decimal("2"),
    )
    assert bounds == {"lower_price": Decimal("42100"), "upper_price": Decimal("42900")}


def test_calculate_grid_bounds_rejects_non_positive_inputs():
    with pytest.raises(ValueError):
        calculate_grid_bounds(Decimal("0"), Decimal("200"), Decimal("2"))
    with pytest.raises(ValueError):
        calculate_grid_bounds(Decimal("42500"), Decimal("0"), Decimal("2"))


def test_calculate_grid_bounds_rejects_lower_bound_at_or_below_zero():
    with pytest.raises(ValueError, match="lower_price"):
        calculate_grid_bounds(Decimal("100"), Decimal("100"), Decimal("2"))


def _order(side, price, quantity, status="FILLED"):
    return {"side": side, "price": price, "quantity": quantity, "status": status}


def test_calculate_grid_pnl_no_filled_orders_is_all_zero():
    orders = [_order("BUY", "40000", "0.001", status="NEW")]
    pnl = calculate_grid_pnl(orders, current_price=Decimal("42500"))

    assert pnl["realized_pnl"] == Decimal("0")
    assert pnl["unrealized_pnl"] == Decimal("0")
    assert pnl["total_pnl"] == Decimal("0")
    assert pnl["net_position_qty"] == Decimal("0")


def test_calculate_grid_pnl_matched_buy_sell_is_fully_realized():
    orders = [
        _order("BUY", "40000", "0.001"),
        _order("SELL", "45000", "0.001"),
    ]
    pnl = calculate_grid_pnl(orders, current_price=Decimal("42500"))

    # matched_qty=0.001, realized = 0.001 * (45000 - 40000) = 5
    assert pnl["realized_pnl"] == Decimal("5")
    assert pnl["unrealized_pnl"] == Decimal("0")
    assert pnl["total_pnl"] == Decimal("5")
    assert pnl["net_position_qty"] == Decimal("0")


def test_calculate_grid_pnl_unmatched_buy_is_unrealized_long():
    orders = [_order("BUY", "40000", "0.002")]
    pnl = calculate_grid_pnl(orders, current_price=Decimal("42500"))

    assert pnl["realized_pnl"] == Decimal("0")
    # unrealized = net_qty * (current - avg_buy) = 0.002 * (42500-40000) = 5
    assert pnl["unrealized_pnl"] == Decimal("5")
    assert pnl["total_pnl"] == Decimal("5")
    assert pnl["net_position_qty"] == Decimal("0.002")


def test_calculate_grid_pnl_ignores_non_filled_orders():
    orders = [
        _order("BUY", "40000", "0.001", status="FILLED"),
        _order("SELL", "100000", "0.001", status="PARTIALLY_FILLED"),
        _order("SELL", "999999", "1", status="CANCELED"),
    ]
    pnl = calculate_grid_pnl(orders, current_price=Decimal("40000"))

    assert pnl["filled_sell_qty"] == Decimal("0")
    assert pnl["net_position_qty"] == Decimal("0.001")


@pytest.mark.parametrize(
    "total_pnl,stop_loss,take_profit,expected",
    [
        (Decimal("-50"), Decimal("50"), Decimal("100"), "STOP_LOSS"),
        (Decimal("-49.99"), Decimal("50"), Decimal("100"), None),
        (Decimal("100"), Decimal("50"), Decimal("100"), "TAKE_PROFIT"),
        (Decimal("99.99"), Decimal("50"), Decimal("100"), None),
        (Decimal("0"), None, None, None),
        (Decimal("0"), Decimal("0"), Decimal("0"), "STOP_LOSS"),  # tie-break: SL wins
    ],
)
def test_check_sl_tp(total_pnl, stop_loss, take_profit, expected):
    assert check_sl_tp(total_pnl, stop_loss, take_profit) == expected
