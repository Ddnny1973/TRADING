"""
Shared pytest fixtures for the grid trading backend test suite.

Design choices:
- All Binance network calls are mocked (AsyncMock) - no real HTTP traffic,
  no dependency on testnet availability or credentials.
- Each test gets its own throwaway SQLite file (via monkeypatching
  app.database.connection.SQLITE_DB_PATH) so tests never share or pollute
  state, and never touch a real grid_trading.db.
- Postgres (historical_grid_logs) is skipped by default (SessionLocal=None)
  since no real Postgres is available in this environment; the logging
  behavior itself is covered separately in test_grid_service_logging.py
  with a fake session.
- The required-but-irrelevant-for-tests Settings fields (Binance/Postgres
  credentials) are stubbed via os.environ *before* app.core.config is
  imported anywhere, since pydantic-settings validates them eagerly at
  import time.
"""

import itertools
import os
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

os.environ.setdefault("BINANCE_API_KEY", "test-api-key")
os.environ.setdefault("BINANCE_API_SECRET", "test-api-secret")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")

from fastapi.testclient import TestClient

from app.database import connection
from app.main import app, grid_service

DEFAULT_FILTERS = {
    "tick_size": Decimal("0.10"),
    "step_size": Decimal("0.001"),
    "min_notional": Decimal("50"),  # Binance Futures minimum order size in USDT
}

DEFAULT_MARK_PRICE = Decimal("42500.00")


def make_order_response(order_id: int, status: str = "NEW") -> dict:
    """A minimal Binance order response, shaped like place_batch_orders/place_limit_order output."""
    return {
        "orderId": order_id,
        "status": status,
        "clientOrderId": f"test-{order_id}",
    }


def make_klines(count: int = 15, base_price: Decimal = DEFAULT_MARK_PRICE,
                 spread: Decimal = Decimal("100")) -> list:
    """
    Synthetic, oldest->newest candles with a constant true range, so
    calculate_atr() returns a deterministic, non-zero value:
    TR = max(high-low, |high-prev_close|, |low-prev_close|) = 2*spread per candle.
    """
    klines = []
    for i in range(count):
        klines.append({
            "open_time": i,
            "open": base_price,
            "high": base_price + spread,
            "low": base_price - spread,
            "close": base_price,
            "volume": Decimal("10"),
            "close_time": i + 1,
            "quote_volume": Decimal("1000"),
            "num_trades": 5,
        })
    return klines


@pytest.fixture(autouse=True)
def isolated_sqlite_db(tmp_path, monkeypatch):
    """Point grid storage at a throwaway SQLite file, fresh for every test."""
    db_path = tmp_path / "grid_trading_test.db"
    monkeypatch.setattr(connection, "SQLITE_DB_PATH", str(db_path))
    connection.init_sqlite_tables()
    yield db_path


@pytest.fixture(autouse=True)
def skip_postgres_logging(monkeypatch):
    """No real Postgres in this environment - _log_grid_closure() takes its early-return path."""
    monkeypatch.setattr("app.services.grid_service.SessionLocal", None)


@pytest.fixture
def order_id_counter():
    return itertools.count(1000)


@pytest.fixture
def mock_binance(monkeypatch, order_id_counter):
    """
    Replaces every network-calling method on the app's singleton
    GridService.binance with an AsyncMock carrying sane defaults for a
    ~42500 mark price. Tests override return_value/side_effect on the
    returned dict as needed (e.g. mocks["get_mark_price"].return_value = ...).
    """
    binance = grid_service.binance

    def batch_side_effect(orders, max_retries=3):
        return [make_order_response(next(order_id_counter)) for _ in orders]

    mocks = {
        "get_mark_price": AsyncMock(return_value={"symbol": "BTCUSDT", "price": str(DEFAULT_MARK_PRICE)}),
        "get_symbol_filters": AsyncMock(return_value=dict(DEFAULT_FILTERS)),
        "get_klines": AsyncMock(return_value=make_klines(count=15, base_price=DEFAULT_MARK_PRICE, spread=Decimal("100"))),
        "place_batch_orders": AsyncMock(side_effect=batch_side_effect),
        "place_limit_order": AsyncMock(side_effect=lambda *a, **k: make_order_response(next(order_id_counter))),
        "cancel_order": AsyncMock(return_value={"status": "CANCELED"}),
        "get_order_status": AsyncMock(return_value=None),
        "is_one_way_mode": AsyncMock(return_value=True),
        "ensure_symbol_settings": AsyncMock(return_value=None),
        "get_open_orders": AsyncMock(return_value=[]),
        "get_position": AsyncMock(return_value={"positionAmt": "0"}),
        "get_commission_rate": AsyncMock(return_value={"makerCommission": 0.0002, "takerCommission": 0.0004}),
    }
    for name, mock in mocks.items():
        monkeypatch.setattr(binance, name, mock)
    return mocks


@pytest.fixture
def client(mock_binance):
    """
    FastAPI TestClient *without* entering it as a context manager, so the
    app's lifespan (init_db() + Binance time sync) never runs - tests do
    their own DB setup via isolated_sqlite_db and never need a network
    time-sync call.
    """
    return TestClient(app)
