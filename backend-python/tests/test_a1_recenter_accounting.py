"""
A1a: contabilidad de la cadena de re-centrado.

- El grid hijo usa el inventario heredado como costo base (orden sintética al
  precio de marca del re-centrado), así PnL(padre) + PnL(hijo) = PnL real.
- recenter_grid registra el PnL marcado del padre en grid_closures (antes "0")
  y lo loguea en historical_grid_logs con trigger RECENTERED.
- El dashboard solo cuenta como "vivo" el snapshot de grids RUNNING.
"""

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from app.database import connection
from app.services.dashboard_data import split_live_snapshots
from app.services.grid_service import GridService
from app.services.indicators import calculate_grid_pnl

PARENT_ID = "grid-parent"
SYMBOL = "BTCUSDT"


def _fill(side, price, qty):
    return {"side": side, "price": str(price), "quantity": str(qty),
            "executed_qty": str(qty), "avg_fill_price": str(price), "status": "FILLED"}


def test_inherited_inventory_makes_chain_add_up():
    """
    Padre compra 2 @100 y re-centra con el precio en 90 (marca). El hijo
    hereda +2 y las vende @95; luego el precio cae a 80.
    Resultado real: 2 × (95 − 100) = −10.
    """
    fee = Decimal("0")
    parent_orders = [_fill("BUY", 100, 1), _fill("BUY", 100, 1)]
    parent = calculate_grid_pnl(parent_orders, Decimal("90"), fee_rate=fee)
    assert parent["total_pnl"] == Decimal("-20")

    child_grid = {"orders": [_fill("SELL", 95, 1), _fill("SELL", 95, 1)],
                  "inherited_qty": "2", "inherited_price": "90"}
    child = calculate_grid_pnl(GridService._orders_for_pnl(child_grid), Decimal("80"), fee_rate=fee)
    assert child["total_pnl"] == Decimal("10")
    assert child["net_position_qty"] == Decimal("0")
    assert parent["total_pnl"] + child["total_pnl"] == Decimal("-10")

    # Sin costo base (comportamiento anterior) el hijo se ve como un short
    # valorado contra el precio actual y la cadena no cuadra.
    legacy = calculate_grid_pnl(child_grid["orders"], Decimal("80"), fee_rate=fee)
    assert legacy["total_pnl"] == Decimal("30")


def test_orders_for_pnl_short_inheritance_and_no_inheritance():
    short_grid = {"orders": [], "inherited_qty": "-0.5", "inherited_price": "200"}
    synthetic = GridService._orders_for_pnl(short_grid)[0]
    assert synthetic["side"] == "SELL"
    assert synthetic["executed_qty"] == Decimal("0.5")

    plain = {"orders": [_fill("BUY", 1, 1)], "inherited_qty": None, "inherited_price": None}
    assert GridService._orders_for_pnl(plain) == plain["orders"]


def _insert_parent_grid():
    conn = connection.get_sqlite_connection()
    try:
        cursor = conn.cursor()
        for column_def in ("leverage INTEGER DEFAULT 3", "quantity_per_order NUMERIC",
                           "grid_mode TEXT DEFAULT 'NEUTRAL'"):
            try:
                cursor.execute(f"ALTER TABLE grids ADD COLUMN {column_def}")
            except Exception:
                pass
        cursor.execute(
            """INSERT INTO grids (id, symbol, lower_price, upper_price, levels, grid_type, status,
                                  stop_loss, take_profit, leverage, quantity_per_order, grid_mode, recenter_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (PARENT_ID, SYMBOL, "40000", "45000", 10, "GEOMETRIC", "RUNNING",
             "100", "300", 3, "0.001", "NEUTRAL", 0),
        )
        for i in range(2):
            cursor.execute(
                """INSERT INTO grid_orders (id, grid_id, price, quantity, side, type, status,
                                            executed_qty, avg_fill_price)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (f"o{i}", PARENT_ID, "42000", "0.001", "BUY", "LIMIT", "FILLED", "0.001", "42000"),
            )
        conn.commit()
    finally:
        conn.close()


def test_recenter_logs_marked_parent_pnl_and_passes_cost_basis():
    _insert_parent_grid()
    svc = GridService()
    svc.binance.cancel_all_open_orders = AsyncMock(return_value=True)
    svc.binance.get_position = AsyncMock(return_value={"positionAmt": "0.002"})
    svc.binance.get_mark_price = AsyncMock(return_value={"symbol": SYMBOL, "price": "41000"})
    svc.binance.get_commission_rate = AsyncMock(return_value={"maker": Decimal("0"), "taker": Decimal("0")})
    svc.create_grid = AsyncMock(return_value={"id": "grid-child"})
    svc._log_grid_closure = MagicMock()

    result = asyncio.run(svc.recenter_grid(PARENT_ID))

    assert result["triggered"] == "RECENTERED"
    kwargs = svc.create_grid.await_args.kwargs
    assert kwargs["inherited_qty"] == Decimal("0.002")
    assert kwargs["inherited_price"] == Decimal("41000")
    assert kwargs["grid_mode"] == "LONG"

    # 0.002 × (41000 − 42000) = −2, sin fees.
    conn = connection.get_sqlite_connection()
    try:
        row = conn.execute(
            "SELECT trigger_condition, total_pnl, parent_grid_id FROM grid_closures WHERE grid_id = ?",
            (PARENT_ID,)).fetchone()
    finally:
        conn.close()
    assert row["trigger_condition"] == "RECENTERED"
    assert Decimal(row["total_pnl"]) == Decimal("-2")
    assert row["parent_grid_id"] == "grid-child"

    logged_grid, logged_pnl, logged_trigger = svc._log_grid_closure.call_args.args
    assert logged_grid["id"] == PARENT_ID
    assert logged_pnl["total_pnl"] == Decimal("-2")
    assert logged_trigger == "RECENTERED"


def test_create_grid_persists_inherited_columns(mock_binance):
    svc = GridService()
    for name, mock in mock_binance.items():
        setattr(svc.binance, name, mock)
    grid = asyncio.run(svc.create_grid(
        symbol=SYMBOL, levels=6, grid_type="GEOMETRIC", quantity_per_order=0.002,
        grid_mode="LONG", parent_grid_id=PARENT_ID, recenter_count=1,
        inherited_qty=Decimal("0.002"), inherited_price=Decimal("41000"),
    ))
    assert Decimal(grid["inherited_qty"]) == Decimal("0.002")
    assert Decimal(grid["inherited_price"]) == Decimal("41000")


def test_split_live_snapshots():
    snaps = [{"grid_id": "a", "total_pnl": 1.0}, {"grid_id": "b", "total_pnl": -5.0}]
    live, orphans = split_live_snapshots(snaps, {"a"})
    assert [r["grid_id"] for r in live] == ["a"]
    assert [r["grid_id"] for r in orphans] == ["b"]

    live, orphans = split_live_snapshots(snaps, None)
    assert len(live) == 2 and orphans == []
