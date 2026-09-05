"""
Unit tests for T15: kill-switch + guardia de drawdown diario.

Covers:
- _get_system_state / _set_system_state: persistencia básica.
- get_kill_switch_state: inactivo por defecto; activo tras engage.
- engage_kill_switch: cierra grids RUNNING y persiste estado.
- disarm_kill_switch: desactiva sin reabrir grids.
- create_grid: rechaza creación cuando kill-switch está activo.
- check_daily_drawdown: auto-dispara cuando el umbral se cruza.
"""

import asyncio
import sqlite3
from decimal import Decimal
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from app.services.grid_service import GridService


@pytest.fixture
def memory_db(monkeypatch, tmp_path):
    """Fake SQLite with grids + grid_closures + system_state tables."""
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
    conn.execute("""CREATE TABLE system_state (
        key TEXT PRIMARY KEY, value TEXT NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    conn.execute(
        "INSERT INTO grids (id, symbol, status, created_at) "
        "VALUES ('g1', 'BTCUSDT', 'RUNNING', 'now')")
    conn.commit()
    conn.close()

    def fake_conn():
        return sqlite3.connect(str(db_path))

    monkeypatch.setattr("app.services.grid_service.get_sqlite_connection", fake_conn)
    return db_path


def make_service(monkeypatch):
    service = GridService()
    monkeypatch.setattr(service.binance, "cancel_all_open_orders", AsyncMock(return_value=True))
    monkeypatch.setattr(service.binance, "get_position", AsyncMock(return_value={"positionAmt": "0"}))
    monkeypatch.setattr(service.binance, "place_market_close", AsyncMock(return_value={"orderId": "x"}))
    monkeypatch.setattr(service.binance, "get_mark_price", AsyncMock(return_value={"price": "50000"}))
    monkeypatch.setattr(service.binance, "get_symbol_filters", AsyncMock(
        return_value={"step_size": Decimal("0.001"), "tick_size": Decimal("0.1"), "min_notional": Decimal("5")}))
    return service


# ------------------------------------------------------------------ #

def test_system_state_empty_initially(memory_db, monkeypatch):
    svc = make_service(monkeypatch)
    assert svc._get_system_state("kill_switch") is None


def test_set_system_state_persists(memory_db, monkeypatch):
    svc = make_service(monkeypatch)
    svc._set_system_state("kill_switch", "1")
    assert svc._get_system_state("kill_switch") == "1"


def test_get_kill_switch_state_default_inactive(memory_db, monkeypatch):
    svc = make_service(monkeypatch)
    state = svc.get_kill_switch_state()
    assert state == {"active": False, "reason": None, "triggered_at": None}


def test_engage_and_disarm(memory_db, monkeypatch):
    svc = make_service(monkeypatch)
    result = asyncio.run(svc.engage_kill_switch("TEST"))
    assert result["active"] is True
    assert result["reason"] == "TEST"
    assert "g1" in result["closed_grids"]
    # grid now CANCELED after engage
    conn = sqlite3.connect(memory_db)
    row = conn.execute("SELECT status FROM grids WHERE id='g1'").fetchone()
    conn.close()
    assert row[0] == "CANCELED"

    state = svc.get_kill_switch_state()
    assert state["active"] is True
    assert state["reason"] == "TEST"

    disarm = asyncio.run(svc.disarm_kill_switch())
    assert disarm["active"] is False
    state2 = svc.get_kill_switch_state()
    assert state2["active"] is False


def test_create_grid_blocked_when_kill_switch_active(memory_db, monkeypatch):
    svc = make_service(monkeypatch)
    asyncio.run(svc.engage_kill_switch("BLOCK_TEST"))
    with pytest.raises(ValueError, match="Kill-switch ENGAGED"):
        asyncio.run(svc.create_grid(
            symbol="BTCUSDT", levels=5, grid_type="SPOT", quantity_per_order=0.001))


def test_check_daily_drawdown_triggers(memory_db, monkeypatch):
    """When realized PnL is below -3% balance, check_daily_drawdown engages."""
    svc = make_service(monkeypatch)
    # Fake balance = 1000 USDT
    monkeypatch.setattr(svc.binance, "get_account_balance", AsyncMock(
        return_value={"balances": [{"asset": "USDT", "balance": "1000"}]}))
    # insert a closure with total_pnl = -40 (4% of 1000)
    conn = sqlite3.connect(memory_db)
    conn.execute(
        "INSERT INTO grid_closures (grid_id, symbol, trigger_condition, total_pnl) "
        "VALUES ('g1', 'BTCUSDT', 'SL', '-40')")
    conn.commit()
    conn.close()

    result = asyncio.run(svc.check_daily_drawdown())
    assert result is not None
    assert result["active"] is True
    assert result["auto"] is True
    assert "g1" in result["closed_grids"]


def test_check_daily_drawdown_no_trigger(memory_db, monkeypatch):
    """When realized PnL is above -3% balance, no trigger."""
    svc = make_service(monkeypatch)
    monkeypatch.setattr(svc.binance, "get_account_balance", AsyncMock(
        return_value={"balances": [{"asset": "USDT", "balance": "1000"}]}))
    conn = sqlite3.connect(memory_db)
    conn.execute(
        "INSERT INTO grid_closures (grid_id, symbol, trigger_condition, total_pnl) "
        "VALUES ('g1', 'BTCUSDT', 'SL', '-20')")
    conn.commit()
    conn.close()
    result = asyncio.run(svc.check_daily_drawdown())
    assert result is None


def test_check_daily_drawdown_short_circuits_when_already_active(memory_db, monkeypatch):
    """No balance call or closure query when kill-switch is already active."""
    svc = make_service(monkeypatch)
    asyncio.run(svc.engage_kill_switch("EARLY"))
    bal_mock = AsyncMock(return_value={"balances": [{"asset": "USDT", "balance": "1000"}]})
    monkeypatch.setattr(svc.binance, "get_account_balance", bal_mock)
    result = asyncio.run(svc.check_daily_drawdown())
    assert result is None
    bal_mock.assert_not_called()
