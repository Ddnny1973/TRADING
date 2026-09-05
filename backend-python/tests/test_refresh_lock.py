"""
Unit tests for T16: per-grid refresh+replenish serialization.

Covers:
- get_refresh_lock() returns the SAME lock for the same grid_id
- Different grids get DIFFERENT locks (no cross-blocking)
- cancel_grid() pops the lock once the grid is terminal
"""

import asyncio
import sqlite3

import pytest

from app.services.grid_service import GridService


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
    conn.execute(
        "INSERT INTO grids (id, symbol, status, created_at) VALUES ('g1', 'BTCUSDT', 'RUNNING', 'now')")
    conn.commit()

    def fake_conn():
        return sqlite3.connect(str(db_path))

    monkeypatch.setattr("app.services.grid_service.get_sqlite_connection", fake_conn)
    return db_path


def make_service(monkeypatch):
    service = GridService()
    monkeypatch.setattr(service.binance, "cancel_all_open_orders", None)
    monkeypatch.setattr(service.binance, "get_position", None)
    monkeypatch.setattr(service.binance, "place_market_close", None)
    return service


def test_get_refresh_lock_same_grid_returns_same_lock(memory_db, monkeypatch):
    service = make_service(monkeypatch)
    lock_a = service.get_refresh_lock("grid-1")
    lock_b = service.get_refresh_lock("grid-1")
    assert lock_a is lock_b


def test_get_refresh_lock_different_grids_different_locks(memory_db, monkeypatch):
    service = make_service(monkeypatch)
    lock_1 = service.get_refresh_lock("grid-1")
    lock_2 = service.get_refresh_lock("grid-2")
    assert lock_1 is not lock_2


def test_lock_serializes_same_grid_concurrent(memory_db, monkeypatch):
    service = make_service(monkeypatch)
    lock = service.get_refresh_lock("grid-1")
    in_critical = []

    async def enter():
        async with lock:
            in_critical.append("enter")
            await asyncio.sleep(0.05)
            in_critical.append("exit")

    async def main():
        await asyncio.gather(enter(), enter())

    asyncio.run(main())
    # No interleaving: each enter is immediately followed by its exit
    assert in_critical == ["enter", "exit", "enter", "exit"]


def test_cancel_grid_pops_lock_when_dormant(memory_db, monkeypatch):
    service = make_service(monkeypatch)
    lock = service.get_refresh_lock("g1")
    assert service._refresh_locks.get("g1") is lock

    # cancel_grid with no grid orders and empty position closes and pops the lock
    async def fake_cancel_all(symbol):
        return True
    async def fake_get_position(symbol):
        return {"positionAmt": "0"}
    async def fake_place_close(symbol, qty):
        return {"orderId": "x"}
    monkeypatch.setattr(service.binance, "cancel_all_open_orders", fake_cancel_all)
    monkeypatch.setattr(service.binance, "get_position", fake_get_position)
    monkeypatch.setattr(service.binance, "place_market_close", fake_place_close)

    asyncio.run(service.cancel_grid("g1", trigger_condition="MANUAL"))
    assert "g1" not in service._refresh_locks