"""
Tests for T2 RECENTER: OUT_OF_RANGE must not fire on a single tick or on
noise; only a decisive departure that persists OUT_OF_RANGE_STRIKES_TO_TRIGGER
consecutive WF2 cycles triggers it. When OUT_OF_RANGE_POLICY == "RECENTER",
the grid is re-centred (inventory kept) instead of being liquidated at market.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app.config_auto_params import (
    OUT_OF_RANGE_POLICY,
    OUT_OF_RANGE_STRIKES_TO_TRIGGER,
)
from app.database import connection
from app.main import grid_service as main_grid_service
from app.services.grid_service import GridService
from tests.conftest import DEFAULT_FILTERS, DEFAULT_MARK_PRICE, make_klines

GRID_ID = "grid-recenter"
SYMBOL = "BTCUSDT"
LOWER = "40000"
UPPER = "45000"


def _insert_grid(status="RUNNING", strikes=0, created_ago_hours=2):
    conn = connection.get_sqlite_connection()
    try:
        cursor = conn.cursor()
        for column_def in (
            "leverage INTEGER DEFAULT 3",
            "quantity_per_order NUMERIC",
            "grid_mode TEXT DEFAULT 'NEUTRAL'",
            "recenter_count INTEGER DEFAULT 0",
            "out_of_range_strikes INTEGER DEFAULT 0",
            "parent_grid_id TEXT",
        ):
            try:
                cursor.execute(f"ALTER TABLE grids ADD COLUMN {column_def}")
            except Exception:
                pass
        created = datetime.now(timezone.utc) - timedelta(hours=created_ago_hours)
        cursor.execute(
            """INSERT INTO grids
               (id, symbol, lower_price, upper_price, levels, grid_type, status,
                stop_loss, take_profit, leverage, quantity_per_order, grid_mode,
                created_at, recenter_count, out_of_range_strikes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (GRID_ID, SYMBOL, LOWER, UPPER, 10, "GEOMETRIC", status,
             "100", "300", 3, "0.002", "NEUTRAL",
             created.strftime("%Y-%m-%d %H:%M:%S"), 0, strikes),
        )
        conn.commit()
    finally:
        conn.close()


def _service(mocks):
    svc = GridService()
    for name, mock in mocks.items():
        setattr(svc.binance, name, mock)
    return svc


def _price_below_buffer(price="39800"):
    # lower=40000, ATR from make_klines = 200, buffer = 0.5*200 = 100.
    # Decisive departure below requires price < 40000 - 100 = 39900.
    return AsyncMock(return_value={"symbol": SYMBOL, "price": price})


def _close_check(mocks, service_mocks=None):
    svc = _service(mocks)
    for name, mock in (service_mocks or {}).items():
        setattr(svc, name, mock)
    return asyncio.run(svc.close_grid_if_triggered(GRID_ID))


@pytest.mark.parametrize("policy", ["CLOSE", "RECENTER"])
def test_first_decisive_strike_does_not_trigger(policy, monkeypatch):
    """
    A single decisive departure (strike 1 of OUT_OF_RANGE_STRIKES_TO_TRIGGER=2)
    must increment the counter and NOT close/recenter.
    """
    monkeypatch.setattr("app.services.grid_service.OUT_OF_RANGE_POLICY", policy)
    _insert_grid(strikes=0)

    mock_recenter = AsyncMock(return_value={"new_grid_id": "new-1", "grid_mode": "LONG", "triggered": "RECENTERED"})
    mocks = {
        "get_mark_price": _price_below_buffer(),
        "get_klines": AsyncMock(return_value=make_klines(count=15, base_price=DEFAULT_MARK_PRICE, spread=100)),
        "cancel_grid": AsyncMock(return_value={"id": GRID_ID, "status": "CANCELED"}),
        "get_position": AsyncMock(return_value={"positionAmt": "0"}),
        "get_commission_rate": AsyncMock(return_value={"maker": 0.0002, "taker": 0.0004}),
    }
    result = _close_check(mocks, service_mocks={"recenter_grid": mock_recenter})
    assert result["triggered"] is None
    mock_recenter.assert_not_awaited()

    # Counter persisted to DB for the next cycle.
    conn = connection.get_sqlite_connection()
    try:
        row = conn.execute("SELECT out_of_range_strikes AS s FROM grids WHERE id = ?", (GRID_ID,)).fetchone()
        assert row["s"] == 1
    finally:
        conn.close()


def test_second_strike_triggers_recenter_when_policy_recenter(monkeypatch):
    """
    With 1 strike already logged, a second decisive departure crosses
    OUT_OF_RANGE_STRIKES_TO_TRIGGER and re-centers instead of closing.
    """
    monkeypatch.setattr("app.services.grid_service.OUT_OF_RANGE_POLICY", "RECENTER")
    _insert_grid(strikes=OUT_OF_RANGE_STRIKES_TO_TRIGGER - 1)

    mock_recenter = AsyncMock(return_value={"new_grid_id": "new-1", "grid_mode": "LONG", "triggered": "RECENTERED"})
    mocks = {
        "get_mark_price": _price_below_buffer(),
        "get_klines": AsyncMock(return_value=make_klines(count=15, base_price=DEFAULT_MARK_PRICE, spread=100)),
        "cancel_grid": AsyncMock(return_value={"id": GRID_ID, "status": "CANCELED"}),
        "get_position": AsyncMock(return_value={"positionAmt": "0"}),
        "get_commission_rate": AsyncMock(return_value={"maker": 0.0002, "taker": 0.0004}),
    }
    mocks["get_mark_price"].return_value = {"symbol": SYMBOL, "price": "39800"}
    result = _close_check(mocks, service_mocks={"recenter_grid": mock_recenter})
    assert result["triggered"] == "RECENTERED"
    mock_recenter.assert_awaited_once()


def test_in_range_resets_strikes(monkeypatch):
    monkeypatch.setattr("app.services.grid_service.OUT_OF_RANGE_POLICY", "RECENTER")
    _insert_grid(strikes=1)

    mocks = {
        "get_mark_price": AsyncMock(return_value={"symbol": SYMBOL, "price": str(DEFAULT_MARK_PRICE)}),  # inside range
        "get_klines": AsyncMock(return_value=make_klines(count=15, base_price=DEFAULT_MARK_PRICE, spread=100)),
        "cancel_grid": AsyncMock(return_value={"id": GRID_ID, "status": "CANCELED"}),
        "get_position": AsyncMock(return_value={"positionAmt": "0"}),
        "get_commission_rate": AsyncMock(return_value={"maker": 0.0002, "taker": 0.0004}),
    }
    result = _close_check(mocks)
    assert result["triggered"] is None

    conn = connection.get_sqlite_connection()
    try:
        row = conn.execute("SELECT out_of_range_strikes AS s FROM grids WHERE id = ?", (GRID_ID,)).fetchone()
        assert row["s"] == 0
    finally:
        conn.close()


def test_below_atr_buffer_is_treated_as_noise(monkeypatch):
    """
    A price that is outside the grid range but NOT beyond the ATR buffer
    (e.g. 39950 with lower=40000 and buffer=100) must not increment strikes.
    """
    monkeypatch.setattr("app.services.grid_service.OUT_OF_RANGE_POLICY", "RECENTER")
    _insert_grid(strikes=0)

    mocks = {
        "get_mark_price": AsyncMock(return_value={"symbol": SYMBOL, "price": "39950"}),  # within buffer, outside raw range
        "get_klines": AsyncMock(return_value=make_klines(count=15, base_price=DEFAULT_MARK_PRICE, spread=100)),
        "cancel_grid": AsyncMock(return_value={"id": GRID_ID, "status": "CANCELED"}),
        "get_position": AsyncMock(return_value={"positionAmt": "0"}),
        "get_commission_rate": AsyncMock(return_value={"maker": 0.0002, "taker": 0.0004}),
    }
    result = _close_check(mocks)
    assert result["triggered"] is None

    conn = connection.get_sqlite_connection()
    try:
        row = conn.execute("SELECT out_of_range_strikes AS s FROM grids WHERE id = ?", (GRID_ID,)).fetchone()
        assert row["s"] == 0
    finally:
        conn.close()


def test_recenter_endpoint_returns_new_grid(client, monkeypatch):
    """
    POST /api/v1/grids/{grid_id}/recenter delegates to grid_service.recenter_grid
    and returns the re-centred grid (a real re-run is covered at the service level;
    here the service call is stubbed to a RECENTERED result).
    """
    _insert_grid(status="RUNNING")

    async def fake_recenter(grid_id):
        return {"new_grid_id": "new-1", "old_grid_id": GRID_ID, "symbol": SYMBOL,
                "grid_mode": "LONG", "reason": "test", "triggered": "RECENTERED"}

    grid_service_real = main_grid_service.recenter_grid
    main_grid_service.recenter_grid = fake_recenter
    try:
        # The endpoint returns get_grid(new_grid_id); seed a grid for that id.
        conn = connection.get_sqlite_connection()
        try:
            created = datetime.now(timezone.utc) - timedelta(hours=1)
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO grids
                   (id, symbol, lower_price, upper_price, levels, grid_type, status,
                    stop_loss, take_profit, leverage, quantity_per_order, grid_mode,
                    created_at, recenter_count, out_of_range_strikes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                ("new-1", "ETHUSDT", "40000", "45000", 10, "GEOMETRIC", "RUNNING",
                 "100", "300", 3, "0.002", "LONG",
                 created.strftime("%Y-%m-%d %H:%M:%S"), 1, 0),
            )
            conn.commit()
        finally:
            conn.close()

        response = client.post(f"/api/v1/grids/{GRID_ID}/recenter")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "new-1"
        assert data["grid_mode"] == "LONG"
    finally:
        main_grid_service.recenter_grid = grid_service_real
