"""
Grid service
Orchestrates grid calculation, order execution on Binance, and local persistence
"""

import asyncio
import uuid
from datetime import datetime
from decimal import ROUND_DOWN, Decimal
from typing import Any, Dict, List, Optional

from app.database.connection import get_sqlite_connection, SessionLocal
from app.database.models import HistoricalGridLog
from app.services.binance_client import BinanceClient
from app.services.grid_engine import GridEngine, GridType
from app.services.indicators import calculate_atr, calculate_grid_bounds, calculate_grid_pnl, check_sl_tp

_BATCH_SIZE = 5
_INTER_BATCH_DELAY_SECONDS = 0.5
_TERMINAL_ORDER_STATUSES = {"FILLED", "CANCELED", "REJECTED", "EXPIRED"}


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

    @staticmethod
    def _calculate_max_duration_hours(klines_interval: str, atr_period: int) -> float:
        """
        Calculate max grid duration deterministically from klines_interval and atr_period.

        Rule: max_duration = 4x (klines_interval * atr_period)
        - klines_interval → hours
        - atr_period (e.g., 14) → number of candles, each interval-wide
        - Product → total hours in ATR calculation window
        - 4x → assume that after 4x the ATR window, market has evolved enough
          to warrant recalculation

        Examples:
          - "4h" + atr(14) → 56h window → 224h max_duration (~9 days)
          - "1h" + atr(14) → 14h window → 56h max_duration (~2.3 days)
          - "1d" + atr(14) → 14d window → 56d max_duration (~2 months)
        """
        interval_to_hours = {
            "1m": 1 / 60,
            "3m": 3 / 60,
            "5m": 5 / 60,
            "15m": 15 / 60,
            "30m": 30 / 60,
            "1h": 1,
            "2h": 2,
            "4h": 4,
            "6h": 6,
            "8h": 8,
            "12h": 12,
            "1d": 24,
            "3d": 24 * 3,
            "1w": 24 * 7,
        }
        interval_hours = interval_to_hours.get(klines_interval, 4.0)  # default 4h if unknown
        atr_window_hours = interval_hours * atr_period
        max_duration_hours = atr_window_hours * 4
        return max_duration_hours

    async def create_grid(self, symbol: str, levels: int, grid_type: str, quantity_per_order: float,
                           lower_price: Optional[float] = None, upper_price: Optional[float] = None,
                           atr_period: int = 14, atr_multiplier: float = 2.0,
                           klines_interval: str = "4h",
                           stop_loss: Optional[float] = None,
                           take_profit: Optional[float] = None,
                           max_duration_hours: Optional[float] = None) -> Dict[str, Any]:
        """
        Calculate grid levels, place LIMIT orders on Binance and persist the grid.

        Bounds can be supplied manually (lower_price + upper_price together) or
        left out entirely so they are derived deterministically from ATR
        (calculate_atr + calculate_grid_bounds). Mixing the two (only one of the
        two prices given) is rejected. This is what lets an external orchestrator
        create a grid by sending only {symbol, levels, grid_type, quantity_per_order}.

        max_duration_hours: If omitted, calculated automatically from
                           klines_interval and atr_period as 4x the ATR window.
                           Represents the maximum hours the grid should run before
                           reevaluation is recommended.

        Raises:
            ValueError: if prices/bounds are invalid, or current price/klines
                        cannot be fetched
        """
        manual_bounds_given = lower_price is not None or upper_price is not None
        manual_bounds_complete = lower_price is not None and upper_price is not None
        if manual_bounds_given and not manual_bounds_complete:
            raise ValueError(
                "Provide lower_price and upper_price together, or omit both so "
                "they are calculated automatically from ATR"
            )

        price_data = await self.binance.get_mark_price(symbol)
        if not price_data or "price" not in price_data:
            raise ValueError(f"Could not fetch current price for {symbol}")
        current_price = Decimal(str(price_data["price"]))

        if not manual_bounds_complete:
            klines = await self.binance.get_klines(symbol, interval=klines_interval, limit=atr_period + 1)
            if not klines:
                raise ValueError(f"Could not fetch klines for {symbol} to compute ATR-based bounds")
            atr = calculate_atr(klines, period=atr_period)
            bounds = calculate_grid_bounds(current_price, atr, Decimal(str(atr_multiplier)))
            lower_price = float(bounds["lower_price"])
            upper_price = float(bounds["upper_price"])

        if lower_price >= upper_price:
            raise ValueError("lower_price must be less than upper_price")

        engine = GridEngine(symbol, lower_price, upper_price, levels, GridType(grid_type))
        price_levels = engine.calculate_grid_levels()

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

        # Anti-duplicate guard (R-07): one RUNNING grid per symbol at a time
        conn_check = get_sqlite_connection()
        try:
            cursor_check = conn_check.cursor()
            cursor_check.execute(
                "SELECT id FROM grids WHERE symbol = ? AND status = 'RUNNING'", (symbol,)
            )
            existing = cursor_check.fetchone()
            if existing:
                raise ValueError(
                    f"A RUNNING grid for {symbol} already exists (id: {existing['id']}). "
                    "Cancel it before creating a new one."
                )
        finally:
            conn_check.close()

        # Build order specs for every grid level
        order_specs = []
        for level_price in price_levels:
            quantized_price = self._snap_down(level_price, filters["tick_size"])
            side = "BUY" if quantized_price < current_price else "SELL"
            order_specs.append({
                "symbol": symbol,
                "side": side,
                "quantity": quantized_qty,
                "price": quantized_price,
            })

        # Place orders in batches of _BATCH_SIZE
        order_results: List[tuple] = []
        for batch_start in range(0, len(order_specs), _BATCH_SIZE):
            if batch_start > 0:
                await asyncio.sleep(_INTER_BATCH_DELAY_SECONDS)
            batch = order_specs[batch_start:batch_start + _BATCH_SIZE]
            results = await self.binance.place_batch_orders(batch)
            if results:
                order_results.extend(zip(batch, results))
            else:
                order_results.extend((spec, None) for spec in batch)

        # Calculate max_duration_hours if not provided (Opción A: rule-based)
        if max_duration_hours is None:
            max_duration_hours = self._calculate_max_duration_hours(klines_interval, atr_period)

        # Persist grid and all placed orders in a single DB transaction
        grid_id = str(uuid.uuid4())
        conn = get_sqlite_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO grids (id, symbol, lower_price, upper_price, levels, status, stop_loss, take_profit, max_duration_hours)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (grid_id, symbol, str(engine.lower_price), str(engine.upper_price), levels, "RUNNING",
                 str(stop_loss) if stop_loss is not None else None,
                 str(take_profit) if take_profit is not None else None,
                 str(max_duration_hours) if max_duration_hours is not None else None)
            )
            orders_placed = 0
            for spec, order in order_results:
                if not order or "orderId" not in order:
                    print(f"Order skipped — Binance response: {order} | spec: price={spec['price']} side={spec['side']}")
                    continue
                cursor.execute(
                    """INSERT INTO grid_orders (id, grid_id, price, quantity, side, type, status)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (str(order["orderId"]), grid_id, str(spec["price"]), str(spec["quantity"]),
                     spec["side"], "LIMIT", "NEW")
                )
                orders_placed += 1

            if orders_placed == 0:
                # Transaction is not committed — the grids INSERT above will be
                # rolled back automatically when conn.close() runs in the finally block.
                raise ValueError(
                    f"No orders were placed on Binance — all {len(order_results)} levels were rejected. "
                    "Common causes: insufficient margin (-2019, reduce quantity_per_order or add funds "
                    "to your Futures account), invalid price/quantity filters, or exchange connectivity issues. "
                    "Check container logs for the per-order Binance error codes."
                )

            conn.commit()
        finally:
            conn.close()

        return self.get_grid(grid_id)

    async def refresh_order_status(self, grid_id: str) -> Optional[Dict[str, Any]]:
        """
        Query Binance for the current status of every non-terminal order in
        a grid and update grid_orders in SQLite to match (NEW,
        PARTIALLY_FILLED, FILLED, CANCELED, REJECTED, EXPIRED - Binance's
        own status values, stored as-is).

        Pure pass-through of Binance's reported state: it does not interpret
        or act on the result (no PnL, no SL/TP check, no cancellation). Meant
        to be called periodically by the external orchestrator before
        get_grid_pnl / a future check_sl_tp run (see roadmap Fase 3.3: the
        polling trigger itself lives outside this service, not in an
        internal loop).

        Returns:
            Updated grid (with orders) or None if grid_id does not exist.
        """
        grid = self.get_grid(grid_id)
        if not grid:
            return None

        open_orders = [o for o in grid["orders"] if o["status"] not in _TERMINAL_ORDER_STATUSES]
        if not open_orders:
            return grid

        conn = get_sqlite_connection()
        try:
            cursor = conn.cursor()
            for order in open_orders:
                remote = await self.binance.get_order_status(grid["symbol"], int(order["id"]))
                if not remote or "status" not in remote:
                    continue  # Binance unreachable/unknown - leave local status untouched
                new_status = remote["status"]
                if new_status != order["status"]:
                    cursor.execute(
                        "UPDATE grid_orders SET status = ? WHERE id = ?",
                        (new_status, order["id"])
                    )
            conn.commit()
        finally:
            conn.close()

        return self.get_grid(grid_id)

    async def get_grid_pnl(self, grid_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch a grid's current orders + mark price and compute PnL via the
        pure calculate_grid_pnl(). Does not call refresh_order_status() -
        call that first if you need PnL based on up to date fill status.

        Raises:
            ValueError: if current price cannot be fetched
        """
        grid = self.get_grid(grid_id)
        if not grid:
            return None

        price_data = await self.binance.get_mark_price(grid["symbol"])
        if not price_data or "price" not in price_data:
            raise ValueError(f"Could not fetch current price for {grid['symbol']}")
        current_price = Decimal(str(price_data["price"]))

        pnl = calculate_grid_pnl(grid["orders"], current_price)
        return {
            "grid_id": grid_id,
            "symbol": grid["symbol"],
            "current_price": current_price,
            **pnl,
        }

    def list_grids(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List grids, optionally filtered by status.

        Args:
            status: Filter by status (RUNNING, CANCELED, etc.). None = all grids.

        Returns:
            List of grid dicts ordered by creation date (newest first).
        """
        conn = get_sqlite_connection()
        try:
            cursor = conn.cursor()
            if status:
                cursor.execute("SELECT * FROM grids WHERE status = ? ORDER BY created_at DESC", (status,))
            else:
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

    async def cancel_grid(self, grid_id: str, trigger_condition: str = "MANUAL") -> Optional[Dict[str, Any]]:
        """
        Cancel all open orders for a grid and mark it as canceled.

        Also records the closure in the Postgres historical_grid_logs table
        (Fase 4.4) with the grid's final PnL and trigger_condition
        ("MANUAL" by default, or "STOP_LOSS"/"TAKE_PROFIT" when called from
        close_grid_if_triggered). Logging failures are non-fatal: the grid
        is still canceled on Binance/SQLite even if Postgres is unreachable.
        """
        grid = self.get_grid(grid_id)
        if not grid:
            return None

        final_pnl = None
        try:
            final_pnl = await self.get_grid_pnl(grid_id)
        except ValueError:
            pass  # current price unavailable - log without PnL rather than failing the cancel

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

        closed_grid = self.get_grid(grid_id)
        self._log_grid_closure(closed_grid, final_pnl, trigger_condition)
        return closed_grid

    def _log_grid_closure(self, grid: Dict[str, Any], pnl: Optional[Dict[str, Any]],
                           trigger_condition: str) -> None:
        """
        Best-effort write to historical_grid_logs (Postgres). Never raises -
        a logging failure must not block a cancellation that already
        happened on Binance/SQLite.
        """
        if SessionLocal is None:
            print("Warning: PostgreSQL not available, skipping historical_grid_logs write")
            return

        opened_at_raw = grid.get("created_at")
        opened_at = None
        if isinstance(opened_at_raw, datetime):
            opened_at = opened_at_raw
        elif opened_at_raw:
            try:
                opened_at = datetime.strptime(str(opened_at_raw), "%Y-%m-%d %H:%M:%S")
            except ValueError:
                opened_at = None

        total_pnl = pnl["total_pnl"] if pnl else Decimal("0")

        session = SessionLocal()
        try:
            existing = session.query(HistoricalGridLog).filter_by(grid_id=grid["id"]).first()
            if existing:
                # Grid was already logged (e.g. cancelled twice) - update in place
                existing.closed_at = datetime.utcnow()
                existing.trigger_condition = trigger_condition
                existing.total_pnl = total_pnl
            else:
                log_entry = HistoricalGridLog(
                    grid_id=grid["id"],
                    symbol=grid["symbol"],
                    total_pnl=total_pnl,
                    trigger_condition=trigger_condition,
                    opened_at=opened_at,
                    closed_at=datetime.utcnow(),
                )
                session.add(log_entry)
            session.commit()
        except Exception as e:
            print(f"Warning: could not write historical_grid_logs for grid {grid['id']}: {e}")
            session.rollback()
        finally:
            session.close()

    async def close_grid_if_triggered(self, grid_id: str) -> Optional[Dict[str, Any]]:
        """
        Compare the grid's current PnL against its configured stop_loss/
        take_profit (check_sl_tp) and, if triggered, cancel it and log the
        closure. Does not call refresh_order_status() first - call that
        beforehand if the decision needs up to date fills.

        Returns:
            {"grid": <grid dict>, "triggered": "STOP_LOSS" | "TAKE_PROFIT" | None}
            or None if grid_id does not exist.
        """
        grid = self.get_grid(grid_id)
        if not grid:
            return None

        if grid["status"] != "RUNNING":
            return {"grid": grid, "triggered": None}

        pnl = await self.get_grid_pnl(grid_id)

        stop_loss = Decimal(str(grid["stop_loss"])) if grid.get("stop_loss") is not None else None
        take_profit = Decimal(str(grid["take_profit"])) if grid.get("take_profit") is not None else None

        trigger = check_sl_tp(pnl["total_pnl"], stop_loss, take_profit)
        if trigger is None:
            return {"grid": grid, "triggered": None}

        closed_grid = await self.cancel_grid(grid_id, trigger_condition=trigger)
        return {"grid": closed_grid, "triggered": trigger}