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
    """Fake SQLite that get_sqlite_connection() returns."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""CREATE TABLE grids (
        id TEXT PRIMARY KEY, symbol TEXT NOT NULL, status TEXT NOT NULL,
        created_at TEXT)""")
    conn.execute("""CREATE TABLE grid_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT, grid_id TEXT NOT NULL,
        symbol TEXT NOT NULL, status TEXT NOT NULL,
        executed_qty TEXT DEFAULT '0', avg_fill_price TEXT DEFAULT '0',
        price TEXT, quantity TEXT)""")
    conn.execute("""CREATE TABLE grid_closures (
        id INTEGER PRIMARY KEY AUTOINCREMENT, grid_id TEXT NOT NULL,
        symbol TEXT NOT NULL, trigger_condition TEXT NOT NULL,
        failure_reason TEXT DEFAULT NULL, total_pnl TEXT,
        position_amt_at_close TEXT, parent_grid_id TEXT,
        closed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    conn.commit()

    def fake_conn():
        return sqlite3.connect(str(db_path))

    monkeypatch.setattr("app.services.grid_service.get_sqlite_connection", fake_conn)
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
