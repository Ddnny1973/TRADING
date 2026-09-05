"""
Unit tests for T16: per-grid refresh+replenish serialization.

Covers:
- get_refresh_lock() returns the SAME lock for the same grid_id
- Different grids get DIFFERENT locks (no cross-blocking)
- cancel_grid() pops the lock once the grid is terminal
"""

import asyncio
import sqlite3
from unittest.mock import AsyncMock

import pytest

from app.services.grid_service import GridService


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
    monkeypatch.setattr(service.binance, "cancel_all_open_orders", None)
    monkeypatch.setattr(service.binance, "get_position", None)
    monkeypatch.setattr(service.binance, "place_market_close", None)
    monkeypatch.setattr(service.binance, "get_mark_price", AsyncMock(return_value={"price": "50000"}))
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