"""
Tests for the replenish_status reporting added by T1: replenish_filled_orders
must surface *why* it paused (paused_position) instead of only logging a
warning, so POST /refresh can notify via WF2 and the dashboard can trace it.
"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.config_auto_params import REPLENISH_POSITION_TOLERANCE_RATIO
from app.database import connection
from app.services.grid_service import GridService
from tests.conftest import DEFAULT_FILTERS

QUANTITY = "0.002"
GRID_ID = "grid-t1"


def _filled_order(order_id, side, level_index):
    return {
        "id": order_id,
        "side": side,
        "level_index": level_index,
        "status": "FILLED",
        "executed_qty": QUANTITY,
        "quantity": QUANTITY,
        "replenished": 0,
        "cycle": 0,
    }


def _seed_grid(orders=None, status="RUNNING"):
    """Insert a RUNNING NEUTRAL grid + orders in SQLite, mirroring create_grid()."""
    conn = connection.get_sqlite_connection()
    try:
        cursor = conn.cursor()
        for column_def in (
            "leverage INTEGER DEFAULT 3",
            "quantity_per_order NUMERIC",
            "grid_mode TEXT DEFAULT 'NEUTRAL'",
        ):
            try:
                cursor.execute(f"ALTER TABLE grids ADD COLUMN {column_def}")
            except Exception:
                pass  # column already exists
        cursor.execute(
            """INSERT INTO grids
               (id, symbol, lower_price, upper_price, levels, grid_type, status,
                stop_loss, take_profit, leverage, quantity_per_order, grid_mode)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (GRID_ID, "BTCUSDT", "40000", "45000", 10, "GEOMETRIC", status,
             None, None, 3, QUANTITY, "NEUTRAL"),
        )
        for o in (orders or []):
            cursor.execute(
                """INSERT INTO grid_orders
                   (id, grid_id, price, quantity, side, type, status, executed_qty,
                    replenished, level_index, cycle)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (o["id"], GRID_ID, "42500", o["quantity"], o["side"], "LIMIT",
                 o["status"], o["executed_qty"], o["replenished"],
                 o["level_index"], 0),
            )
        conn.commit()
    finally:
        conn.close()


def _replenish(position_amt):
    service = GridService()
    service.binance.place_batch_orders = AsyncMock(
        return_value=[{"orderId": 9001, "status": "NEW"}]
    )
    service.binance.get_symbol_filters = AsyncMock(return_value=dict(DEFAULT_FILTERS))
    service.binance.get_position = AsyncMock(
        return_value={"positionAmt": str(position_amt)}
    )
    return service, asyncio.run(service.replenish_filled_orders(GRID_ID))


def test_position_within_tolerance_replenishes_and_reports_ok():
    # SELL at level 5 -> opposite BUY at level 4, not blocked (position ~0)
    _seed_grid(orders=[_filled_order("o1", "SELL", 5)])

    _, result = _replenish("0.001")

    assert result["replenish_status"] == "ok"
    assert result["replenish_placed"] == 1
    assert result["replenish_paused"] == 0
    assert result["replenish_blocked_side"] is None


def test_position_over_tolerance_pauses_and_reports_reason():
    # Positive inventory over tolerance -> paused side is BUY. A SELL fill
    # wants to replenish with BUY (the blocked side) -> must be skipped and
    # the reason surfaced in the result.
    _seed_grid(orders=[_filled_order("o1", "SELL", 5)])

    _, result = _replenish("0.05")

    expected_tolerance = float(
        GridService._max_net_position_qty(
            {"quantity_per_order": QUANTITY, "levels": 10}
        )
        * REPLENISH_POSITION_TOLERANCE_RATIO
    )
    assert result["replenish_status"] == "paused_position"
    assert result["replenish_placed"] == 0
    assert result["replenish_paused"] == 1
    assert result["replenish_blocked_side"] == "BUY"
    assert result["replenish_position_amt"] == pytest.approx(0.05)
    assert result["replenish_tolerance"] == pytest.approx(expected_tolerance)


def test_non_running_grid_reports_skipped():
    _seed_grid(status="PAUSED", orders=[_filled_order("o1", "SELL", 5)])

    _, result = _replenish("0")

    assert result["replenish_status"] == "skipped"
    assert result["replenish_placed"] == 0
    assert result["replenish_reason"] == "grid not running or not found"


def test_refresh_response_includes_replenish_status(client):
    # Endpoint-level: /refresh must propagate the transient replenish fields
    # into GridDetailResponse even when nothing was placed this cycle.
    _seed_grid(orders=[])

    response = client.post(f"/api/v1/grids/{GRID_ID}/refresh")
    assert response.status_code == 200
    data = response.json()
    assert data["refresh_status"] == "ok"
    assert data["replenish_status"] == "ok"
    assert data["replenish_placed"] == 0
    assert data["replenish_paused"] == 0
    assert data["replenish_blocked_side"] is None
    assert data["replenish_position_amt"] == 0.0
    assert isinstance(data["replenish_tolerance"], float)