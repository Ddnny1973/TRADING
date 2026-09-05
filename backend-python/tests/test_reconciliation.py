"""
Unit tests for T14: reconciliation failure handling.

Covers:
- _MAX_REFRESH_FAILURES threshold (6)
- _handle_refresh_failure storing failure_reason on auto-cancel
- State reconstruction from allOrders
"""

import asyncio
import sqlite3

import pytest

from app.services.grid_service import GridService, _MAX_REFRESH_FAILURES


@pytest.fixture
def memory_db(monkeypatch, tmp_path):
    """SQLite con el schema real (init_sqlite_tables) + grid g1 RUNNING."""
    import app.database.connection as connection
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(connection, "SQLITE_DB_PATH", str(db_path))
    connection.init_sqlite_tables()
    conn = connection.get_sqlite_connection()
    try:
        conn.execute(
            "INSERT INTO grids (id, symbol, lower_price, upper_price, levels, status, created_at) "
            "VALUES ('g1', 'BTCUSDT', 40000, 45000, 10, 'RUNNING', '2026-01-01 00:00:00')"
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def make_service(monkeypatch):
    service = GridService()
    return service


def test_max_refresh_failures_is_6():
    assert _MAX_REFRESH_FAILURES == 6


def test_handle_refresh_failure_below_threshold(memory_db, monkeypatch):
    service = make_service(monkeypatch)
    grid = {"id": "g1", "orders": [], "symbol": "BTCUSDT"}

    for i in range(1, _MAX_REFRESH_FAILURES):
        result = asyncio.run(service._handle_refresh_failure("g1", grid, "test reason"))
        assert result["refresh_status"] == "unreconciled"
        assert result["refresh_failure_count"] == i


def test_handle_refresh_failure_auto_cancels_with_reason(memory_db, monkeypatch):
    service = make_service(monkeypatch)
    grid = {"id": "g1", "orders": [], "symbol": "BTCUSDT"}

    # allOrders returns None -> reconstruction fails -> must auto-cancel
    async def fake_all_orders(symbol):
        return None
    monkeypatch.setattr(service.binance, "get_all_orders", fake_all_orders)

    captured = {}

    async def fake_cancel(grid_id, trigger_condition="MANUAL", close_position=True,
                          failure_reason=None):
        captured["trigger_condition"] = trigger_condition
        captured["failure_reason"] = failure_reason
        return {"id": grid_id, "orders": [], "symbol": "BTCUSDT", "status": "CANCELED"}

    monkeypatch.setattr(service, "cancel_grid", fake_cancel)

    result = None
    for _ in range(_MAX_REFRESH_FAILURES):
        result = asyncio.run(service._handle_refresh_failure(
            "g1", grid, "openOrders call failed (network/API error)"))

    assert result["refresh_status"] == "auto_canceled"
    assert captured["trigger_condition"] == "RECONCILIATION_FAILED"
    assert captured["failure_reason"] == "openOrders call failed (network/API error)"


def test_handle_refresh_failure_reconstructs_state(memory_db, monkeypatch):
    service = make_service(monkeypatch)
    grid = {"id": "g1",
            "orders": [{"id": 1, "status": "NEW", "price": "60000", "quantity": "0.1"}],
            "symbol": "BTCUSDT"}

    # allOrders resolves the open order -> reconstruction succeeds -> survives
    async def fake_all_orders(symbol):
        return [{"orderId": 1, "status": "FILLED",
                 "executedQty": "0.5", "avgPrice": "60000"}]
    monkeypatch.setattr(service.binance, "get_all_orders", fake_all_orders)

    def fake_cancel(*args, **kwargs):
        raise AssertionError("cancel_grid should NOT be called when reconstruction succeeds")
    monkeypatch.setattr(service, "cancel_grid", fake_cancel)

    result = None
    for _ in range(_MAX_REFRESH_FAILURES):
        result = asyncio.run(service._handle_refresh_failure(
            "g1", grid, "1 order(s) unconfirmed on Binance"))

    assert result["refresh_status"] == "reconstructed"
