"""
Tests for the balance-relative stop-loss / take-profit policy.
"""

from decimal import Decimal

import pytest

from app.auto_params import derive_stop_loss_take_profit
from app import config_auto_params


def test_thresholds_are_derived_from_balance():
    stop_loss, take_profit, reason = derive_stop_loss_take_profit(Decimal("3000"))

    assert stop_loss == Decimal("30.00")
    assert take_profit == Decimal("90.00")
    assert "3000" in reason


def test_zero_percentage_disables_the_threshold(monkeypatch):
    monkeypatch.setattr(config_auto_params, "GRID_TAKE_PROFIT_PCT_OF_BALANCE", Decimal("0"))
    monkeypatch.setattr("app.auto_params.GRID_TAKE_PROFIT_PCT_OF_BALANCE", Decimal("0"))

    stop_loss, take_profit, reason = derive_stop_loss_take_profit(Decimal("1000"))

    assert stop_loss == Decimal("10.00")
    assert take_profit is None
    assert "deshabilitado" in reason


@pytest.mark.parametrize("balance", [Decimal("50"), Decimal("125.75"), Decimal("100000")])
def test_stop_loss_is_always_below_take_profit(balance):
    stop_loss, take_profit, _ = derive_stop_loss_take_profit(balance)

    assert stop_loss is not None and take_profit is not None
    assert stop_loss < take_profit
