"""
Endpoint-level tests for the grid trading API, mirroring
docs/manual-test-plan-swagger.md but with Binance fully mocked (see
tests/conftest.py) so they run offline and deterministically.
"""

from decimal import Decimal

import pytest

from app.database import connection
from app.services.indicators import calculate_grid_pnl
from tests.conftest import make_klines

DEFAULT_PRICE = "42500.00"


def create_grid(client, **overrides):
    payload = {
        "symbol": "BTCUSDT",
        "lower_price": 40000.0,
        "upper_price": 45000.0,
        "levels": 10,
        "grid_type": "GEOMETRIC",
        "quantity_per_order": 0.001,
    }
    payload.update(overrides)
    return client.post("/api/v1/grids", json=payload)


def _mark_order_filled(order_id: str) -> None:
    conn = connection.get_sqlite_connection()
    try:
        conn.execute("UPDATE grid_orders SET status = 'FILLED' WHERE id = ?", (str(order_id),))
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 1. Sanity check
# ---------------------------------------------------------------------------

def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "service": "grid-trading-backend",
        "version": "0.1.0",
    }


def test_root(client):
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["api_version"] == "v1"
    assert body["docs"] == "/api/docs"


# ---------------------------------------------------------------------------
# 2. Creación de grids
# ---------------------------------------------------------------------------

def test_create_grid_manual_bounds(client):
    response = create_grid(client)
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "RUNNING"
    assert data["lower_price"] == 40000.0
    assert data["upper_price"] == 45000.0
    assert data["stop_loss"] is None
    assert data["take_profit"] is None
    assert len(data["orders"]) == 10


def test_create_grid_auto_atr_bounds(client, mock_binance):
    # spread=100 -> constant true range of 200 per candle -> ATR(14)=200
    mock_binance["get_klines"].return_value = make_klines(base_price=Decimal(DEFAULT_PRICE), spread=Decimal("100"))

    response = create_grid(
        client,
        symbol="ETHUSDT",
        levels=6,
        quantity_per_order=0.01,
        lower_price=None,
        upper_price=None,
    )
    assert response.status_code == 200

    data = response.json()
    # current_price=42500, atr=200, multiplier=2.0 -> bounds = 42500 +/- 400
    assert data["lower_price"] == 42100.0
    assert data["upper_price"] == 42900.0
    assert len(data["orders"]) == 6
    mock_binance["get_klines"].assert_awaited_once()


def test_create_grid_with_sl_tp(client):
    response = create_grid(
        client,
        symbol="SOLUSDT",
        lower_price=100.0,
        upper_price=150.0,
        quantity_per_order=1.0,
        stop_loss=5.0,
        take_profit=10.0,
    )
    assert response.status_code == 200

    data = response.json()
    assert data["stop_loss"] == 5.0
    assert data["take_profit"] == 10.0


def test_create_grid_rejects_incomplete_bounds(client):
    response = create_grid(client, lower_price=40000.0, upper_price=None)
    assert response.status_code == 400
    assert "lower_price" in response.json()["detail"]


def test_create_grid_rejects_negative_quantity(client):
    response = create_grid(client, quantity_per_order=-1)
    assert response.status_code == 400


def test_create_grid_levels_zero_returns_two_level_grid(client):
    """
    Documented quirk (see docs/manual-test-plan-swagger.md 2.5b): GridEngine
    treats levels<2 as a special case and still returns a valid 2-level
    grid - it does not reject levels=0.
    """
    response = create_grid(client, symbol="ADAUSDT", lower_price=0.30, upper_price=0.50,
                            levels=0, quantity_per_order=10)
    assert response.status_code == 200

    data = response.json()
    assert len(data["orders"]) == 2


def test_create_grid_duplicate_symbol_rejected(client):
    first = create_grid(client)
    assert first.status_code == 200

    second = create_grid(client)
    assert second.status_code == 400
    assert "already exists" in second.json()["detail"]


# ---------------------------------------------------------------------------
# 3. Lectura
# ---------------------------------------------------------------------------

def test_list_grids_returns_created_grids(client):
    a = create_grid(client, symbol="BTCUSDT").json()
    b = create_grid(client, symbol="ETHUSDT").json()

    listed_ids = {g["id"] for g in client.get("/api/v1/grids").json()}
    assert {a["id"], b["id"]} <= listed_ids


def test_get_grid_detail_includes_orders(client):
    grid = create_grid(client).json()

    response = client.get(f"/api/v1/grids/{grid['id']}")
    assert response.status_code == 200
    orders = response.json()["orders"]
    assert len(orders) == 10
    for order in orders:
        assert {"price", "quantity", "side", "status"} <= order.keys()


def test_get_grid_not_found(client):
    response = client.get("/api/v1/grids/does-not-exist")
    assert response.status_code == 404
    assert response.json()["detail"] == "Grid not found"


# ---------------------------------------------------------------------------
# 4. Refresh de estado
# ---------------------------------------------------------------------------

def test_refresh_grid_updates_order_status(client, mock_binance):
    grid = create_grid(client).json()
    mock_binance["get_order_status"].return_value = {"status": "FILLED"}

    response = client.post(f"/api/v1/grids/{grid['id']}/refresh")
    assert response.status_code == 200
    assert all(o["status"] == "FILLED" for o in response.json()["orders"])


def test_refresh_grid_not_found(client):
    response = client.post("/api/v1/grids/does-not-exist/refresh")
    assert response.status_code == 404


def test_refresh_with_no_open_orders_skips_binance_call(client, mock_binance):
    grid = create_grid(client).json()
    for order in grid["orders"]:
        _mark_order_filled(order["id"])

    response = client.post(f"/api/v1/grids/{grid['id']}/refresh")
    assert response.status_code == 200
    mock_binance["get_order_status"].assert_not_awaited()


# ---------------------------------------------------------------------------
# 5. PnL
# ---------------------------------------------------------------------------

def test_pnl_with_no_fills_is_zero(client):
    grid = create_grid(client).json()

    response = client.get(f"/api/v1/grids/{grid['id']}/pnl")
    assert response.status_code == 200
    data = response.json()
    assert data["realized_pnl"] == 0
    assert data["unrealized_pnl"] == 0
    assert data["total_pnl"] == 0
    assert data["net_position_qty"] == 0
    assert data["current_price"] == 42500.0


def test_pnl_after_fills_reflects_orders(client):
    grid = create_grid(client).json()
    buy = next(o for o in grid["orders"] if o["side"] == "BUY")
    sell = next(o for o in grid["orders"] if o["side"] == "SELL")
    _mark_order_filled(buy["id"])
    _mark_order_filled(sell["id"])

    expected = calculate_grid_pnl(
        [
            {"side": "BUY", "price": buy["price"], "quantity": buy["quantity"], "status": "FILLED"},
            {"side": "SELL", "price": sell["price"], "quantity": sell["quantity"], "status": "FILLED"},
        ],
        current_price=Decimal(DEFAULT_PRICE),
    )

    data = client.get(f"/api/v1/grids/{grid['id']}/pnl").json()
    assert data["total_pnl"] == pytest.approx(float(expected["total_pnl"]), abs=1e-8)
    assert data["realized_pnl"] == pytest.approx(float(expected["realized_pnl"]), abs=1e-8)


def test_pnl_not_found(client):
    response = client.get("/api/v1/grids/does-not-exist/pnl")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# 6. Check-close
# ---------------------------------------------------------------------------

def test_check_close_no_trigger_within_thresholds(client):
    grid = create_grid(client, stop_loss=50, take_profit=100).json()

    response = client.post(f"/api/v1/grids/{grid['id']}/check-close")
    assert response.status_code == 200
    data = response.json()
    assert data["triggered"] is None
    assert data["grid"]["status"] == "RUNNING"


def test_check_close_triggers_take_profit(client):
    grid = create_grid(client, take_profit=0.01).json()
    buy = next(o for o in grid["orders"] if o["side"] == "BUY")
    sell = next(o for o in grid["orders"] if o["side"] == "SELL")
    _mark_order_filled(buy["id"])
    _mark_order_filled(sell["id"])

    # Sanity: the manufactured fills really do clear the tiny take_profit threshold
    pnl = calculate_grid_pnl(
        [
            {"side": "BUY", "price": buy["price"], "quantity": buy["quantity"], "status": "FILLED"},
            {"side": "SELL", "price": sell["price"], "quantity": sell["quantity"], "status": "FILLED"},
        ],
        current_price=Decimal(DEFAULT_PRICE),
    )
    assert pnl["total_pnl"] >= Decimal("0.01")

    response = client.post(f"/api/v1/grids/{grid['id']}/check-close")
    assert response.status_code == 200
    data = response.json()
    assert data["triggered"] == "TAKE_PROFIT"
    assert data["grid"]["status"] == "CANCELED"


def test_check_close_not_found(client):
    response = client.post("/api/v1/grids/does-not-exist/check-close")
    assert response.status_code == 404


def test_check_close_short_circuits_when_not_running(client, mock_binance):
    grid = create_grid(client, take_profit=0.01).json()
    buy = next(o for o in grid["orders"] if o["side"] == "BUY")
    sell = next(o for o in grid["orders"] if o["side"] == "SELL")
    _mark_order_filled(buy["id"])
    _mark_order_filled(sell["id"])

    first = client.post(f"/api/v1/grids/{grid['id']}/check-close").json()
    assert first["triggered"] == "TAKE_PROFIT"

    calls_before = mock_binance["get_mark_price"].await_count
    second = client.post(f"/api/v1/grids/{grid['id']}/check-close").json()
    assert second["triggered"] is None
    assert second["grid"]["status"] == "CANCELED"
    # already CANCELED -> close_grid_if_triggered returns early, no PnL recompute
    assert mock_binance["get_mark_price"].await_count == calls_before


# ---------------------------------------------------------------------------
# 7. Cancelación manual
# ---------------------------------------------------------------------------

def test_cancel_grid_cancels_open_orders(client, mock_binance):
    grid = create_grid(client).json()

    response = client.delete(f"/api/v1/grids/{grid['id']}")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CANCELED"
    assert all(o["status"] == "CANCELED" for o in data["orders"])
    assert mock_binance["cancel_order"].await_count == 10


def test_cancel_grid_not_found(client):
    response = client.delete("/api/v1/grids/does-not-exist")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# 9. Idempotencia
# ---------------------------------------------------------------------------

def test_repeated_cancel_is_idempotent(client, mock_binance):
    grid = create_grid(client).json()

    first = client.delete(f"/api/v1/grids/{grid['id']}")
    assert first.status_code == 200
    calls_after_first = mock_binance["cancel_order"].await_count

    second = client.delete(f"/api/v1/grids/{grid['id']}")
    assert second.status_code == 200
    assert second.json()["status"] == "CANCELED"
    # no NEW orders left -> no further cancel_order calls
    assert mock_binance["cancel_order"].await_count == calls_after_first
