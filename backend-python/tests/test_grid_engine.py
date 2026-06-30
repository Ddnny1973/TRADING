"""Pure unit tests for GridEngine - no I/O, no mocking needed."""

from decimal import Decimal

import pytest

from app.services.grid_engine import GridEngine, GridType


def test_geometric_grid_has_correct_level_count_and_bounds():
    engine = GridEngine("BTCUSDT", 40000.0, 45000.0, 10, GridType.GEOMETRIC)
    levels = engine.calculate_grid_levels()

    assert len(levels) == 10
    assert levels[0] == Decimal("40000")
    # Each level is truncated down (ROUND_DOWN) after a fractional-exponent
    # Decimal power, so the top level lands a hair under upper_price rather
    # than exactly on it - never above, within one tick (1e-8) of it.
    assert Decimal("44999.99999999") <= levels[-1] <= Decimal("45000")
    assert levels == sorted(levels)


def test_arithmetic_grid_is_evenly_spaced():
    engine = GridEngine("BTCUSDT", 40000.0, 45000.0, 6, GridType.ARITHMETIC)
    levels = engine.calculate_grid_levels()

    assert len(levels) == 6
    assert levels[0] == Decimal("40000")
    assert levels[-1] == Decimal("45000")

    expected_step = Decimal("1000")  # (45000-40000)/(6-1), exact in Decimal
    for i in range(1, len(levels)):
        assert levels[i] - levels[i - 1] == expected_step


@pytest.mark.parametrize("grid_type", [GridType.GEOMETRIC, GridType.ARITHMETIC])
def test_levels_below_two_returns_just_the_two_bounds(grid_type):
    """
    Known, documented quirk: levels=0 or levels=1 does not raise - both
    _calculate_geometric_grid and _calculate_arithmetic_grid special-case
    levels<2 into [lower_price, upper_price]. grid_service.create_grid does
    not validate `levels` itself, so this silently produces a 2-order grid
    from a levels=0 request (see docs/manual-test-plan-swagger.md, case 2.5b).
    """
    engine = GridEngine("BTCUSDT", 40000.0, 45000.0, 0, grid_type)
    levels = engine.calculate_grid_levels()

    assert levels == [Decimal("40000"), Decimal("45000")]


def test_geometric_levels_are_deduplicated_and_sorted():
    # A very narrow range with many levels can produce duplicate truncated
    # prices - calculate_grid_levels() must still return a sorted, unique list.
    engine = GridEngine("BTCUSDT", 100.0, 100.001, 50, GridType.GEOMETRIC)
    levels = engine.calculate_grid_levels()

    assert levels == sorted(set(levels))
    assert len(levels) == len(set(levels))
