"""
Grid service
Orchestrates grid calculation, order execution on Binance, and local persistence
"""

import asyncio
import uuid
from decimal import ROUND_DOWN, Decimal
from typing import Any, Dict, List, Optional

from app.database.connection import get_sqlite_connection
from app.services.binance_client import BinanceClient
from app.services.grid_engine import GridEngine, GridType

ORDER_PLACEMENT_DELAY_SECONDS = 0.3


class GridService:
    """Coordinates GridEngine, BinanceClient and SQLite persistence"""

    def __init__(self):
        self.binance = BinanceClient()

    @staticmethod
    def _snap_down(value: Decimal, step: Decimal) -> Decimal:
        """Floor value to the nearest multiple of step (Binance tickSize/stepSize)"""
        if step <= 0:
            return value
        return (value / step).to_integral_value(rounding=ROUND_DOWN) * step

    async def create_grid(self, symbol: str, lower_price: float, upper_price: float,
                           levels: int, grid_type: str, quantity_per_order: float) -> Dict[str, Any]:
        """
        Calculate grid levels, place LIMIT orders on Binance and persist the grid

        Raises:
            ValueError: if prices are invalid or current price cannot be fetched
        """
        if lower_price >= upper_price:
            raise ValueError("lower_price must be less than upper_price")

        engine = GridEngine(symbol, lower_price, upper_price, levels, GridType(grid_type))
        price_levels = engine.calculate_grid_levels()

        price_data = await self.binance.get_mark_price(symbol)
        if not price_data or "price" not in price_data:
            raise ValueError(f"Could not fetch current price for {symbol}")
        current_price = Decimal(str(price_data["price"]))

        filters = await self.binance.get_symbol_filters(symbol)
        if not filters:
            raise ValueError(f"Could not fetch exchange filters for {symbol}")

        quantized_qty = self._snap_down(Decimal(str(quantity_per_order)), filters["step_size"])
        if quantized_qty <= 0:
            raise ValueError("quantity_per_order is smaller than the minimum step size for this symbol")

        min_notional_price = min(price_levels)
        if min_notional_price * quantized_qty < filters["min_notional"]:
            raise ValueError(
                f"quantity_per_order too small: order notional must be at least "
                f"{filters['min_notional']} (got {min_notional_price * quantized_qty})"
            )

        grid_id = str(uuid.uuid4())
        conn = get_sqlite_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO grids (id, symbol, lower_price, upper_price, levels, status)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (grid_id, symbol, str(engine.lower_price), str(engine.upper_price), levels, "RUNNING")
            )

            for i, level_price in enumerate(price_levels):
                quantized_price = self._snap_down(level_price, filters["tick_size"])
                side = "BUY" if quantized_price < current_price else "SELL"

                if i > 0:
                    await asyncio.sleep(ORDER_PLACEMENT_DELAY_SECONDS)

                order = await self.binance.place_limit_order(
                    symbol=symbol, side=side, quantity=quantized_qty, price=quantized_price
                )
                if not order or "orderId" not in order:
                    continue
                cursor.execute(
                    """INSERT INTO grid_orders (id, grid_id, price, quantity, side, type, status)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (str(order["orderId"]), grid_id, str(quantized_price), str(quantized_qty), side, "LIMIT", "NEW")
                )

            conn.commit()
        finally:
            conn.close()

        return self.get_grid(grid_id)

    def list_grids(self) -> List[Dict[str, Any]]:
        """List all grids"""
        conn = get_sqlite_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM grids ORDER BY created_at DESC")
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_grid(self, grid_id: str) -> Optional[Dict[str, Any]]:
        """Get a single grid with its orders"""
        conn = get_sqlite_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM grids WHERE id = ?", (grid_id,))
            grid_row = cursor.fetchone()
            if not grid_row:
                return None

            cursor.execute("SELECT * FROM grid_orders WHERE grid_id = ? ORDER BY created_at", (grid_id,))
            orders = [dict(row) for row in cursor.fetchall()]

            grid = dict(grid_row)
            grid["orders"] = orders
            return grid
        finally:
            conn.close()

    async def cancel_grid(self, grid_id: str) -> Optional[Dict[str, Any]]:
        """Cancel all open orders for a grid and mark it as canceled"""
        grid = self.get_grid(grid_id)
        if not grid:
            return None

        conn = get_sqlite_connection()
        try:
            cursor = conn.cursor()
            open_orders = [o for o in grid["orders"] if o["status"] == "NEW"]

            for order in open_orders:
                await self.binance.cancel_order(grid["symbol"], int(order["id"]))
                cursor.execute("UPDATE grid_orders SET status = 'CANCELED' WHERE id = ?", (order["id"],))

            cursor.execute("UPDATE grids SET status = 'CANCELED' WHERE id = ?", (grid_id,))
            conn.commit()
        finally:
            conn.close()

        return self.get_grid(grid_id)
