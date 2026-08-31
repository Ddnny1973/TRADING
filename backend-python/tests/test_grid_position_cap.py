"""
Tests for the inventory cap that replaced the fixed MAX_POSITION trigger.
"""

from decimal import Decimal

import pytest

from app.core.config import settings
from app.services.grid_service import GridService


def _grid(levels: int, qty: str = "0.01"):
    return {"levels": levels, "quantity_per_order": qty}


def test_cap_scales_with_grid_levels():
    # 12 levels * 0.6 = 7.2 -> 8 slots (ceiling), well above the floor of 3
    assert GridService._max_net_position_qty(_grid(12)) == Decimal("8") * Decimal("0.01")


def test_floor_applies_to_small_grids():
    # 4 levels * 0.6 = 2.4 -> 3 slots, which equals the configured floor
    cap = GridService._max_net_position_qty(_grid(4))
    assert cap == Decimal(settings.MAX_NET_POSITION_LEVELS) * Decimal("0.01")


def test_cap_is_never_below_the_configured_floor():
    for levels in range(2, 21):
        cap = GridService._max_net_position_qty(_grid(levels))
        assert cap >= Decimal(settings.MAX_NET_POSITION_LEVELS) * Decimal("0.01")


def test_cap_is_larger_than_the_old_fixed_three_levels_for_wide_grids():
    old_cap = Decimal("3") * Decimal("0.01") * Decimal("1.05")
    assert GridService._max_net_position_qty(_grid(10)) > old_cap


@pytest.mark.parametrize("grid", [{"levels": 10}, {"levels": 10, "quantity_per_order": 0}])
def test_missing_quantity_disables_the_cap(grid):
    assert GridService._max_net_position_qty(grid) == Decimal("0")
