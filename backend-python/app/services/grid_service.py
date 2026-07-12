"""
Grid service
Orchestrates grid calculation, order execution on Binance, and local persistence
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from decimal import ROUND_DOWN, Decimal
from typing import Any, Dict, List, Optional

from app.config_auto_params import GRID_LEVERAGE_DEFAULT
from app.core.config import settings
from app.database.connection import get_sqlite_connection, SessionLocal
from app.database.models import HistoricalGridLog
from app.services.binance_client import BinanceClient
from app.services.grid_engine import GridEngine, GridType
from app.services.indicators import calculate_atr, calculate_grid_bounds, calculate_grid_pnl, check_sl_tp, validate_grid_step

logger = logging.getLogger(__name__)

_BATCH_SIZE = 5
_INTER_BATCH_DELAY_SECONDS = 0.5
_TERMINAL_ORDER_STATUSES = {"FILLED", "CANCELED", "REJECTED", "EXPIRED"}
_MAX_REFRESH_FAILURES = 3  # consecutive unreconciled refresh cycles before auto-cancel


class GridService:
    """Coordinates GridEngine, BinanceClient and SQLite persistence"""

    def __init__(self):
        self.binance = BinanceClient()
        # Consecutive refresh cycles (n8n polls every 5 min) where Binance
        # state could not be fully reconciled for a grid — either the whole
        # openOrders call failed, or an individual order could be confirmed
        # neither open nor closed. Resets to 0 on any clean refresh.
        # _MAX_REFRESH_FAILURES=3 -> auto-cancel window is ~15 minutes.
        self._refresh_fail_counters: Dict[str, int] = {}

    @staticmethod
    def _snap_down(value: Decimal, step: Decimal) -> Decimal:
        """Floor value to the nearest multiple of step (Binance tickSize/stepSize)"""
        if step <= 0:
            return value
        return (value / step).to_integral_value(rounding=ROUND_DOWN) * step

    @staticmethod
    def _grid_age_hours(grid: Dict[str, Any]) -> Optional[float]:
        """
        Calculate how many hours have passed since the grid was created.

        Args:
            grid: Grid dict with created_at timestamp (SQLite format: YYYY-MM-DD HH:MM:SS UTC)

        Returns:
            Age in hours, or None if timestamp cannot be parsed
        """
        raw = grid.get("created_at")
        if not raw:
            return None
        try:
            # SQLite CURRENT_TIMESTAMP is UTC
            opened = datetime.strptime(str(raw), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
        return (datetime.now(timezone.utc) - opened).total_seconds() / 3600.0

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

    _VALID_GRID_MODES = {"NEUTRAL", "LONG", "SHORT"}

    async def create_grid(self, symbol: str, levels: int, grid_type: str, quantity_per_order: float,
                           lower_price: Optional[float] = None, upper_price: Optional[float] = None,
                           atr_period: int = 14, atr_multiplier: float = 2.0,
                           klines_interval: str = "4h",
                           stop_loss: Optional[float] = None,
                           take_profit: Optional[float] = None,
                           max_duration_hours: Optional[float] = None,
                           leverage: Optional[int] = None,
                           grid_mode: str = "NEUTRAL") -> Dict[str, Any]:
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

        grid_mode: NEUTRAL (default) requires the account to have no open
                   position on `symbol` before creating the grid, and blocks
                   replenishment while a position drifts away from zero —
                   guards against a grid unintentionally stacking on top of
                   directional exposure. LONG/SHORT skip that guard.

        Raises:
            ValueError: if prices/bounds are invalid, grid_mode is unknown,
                        a NEUTRAL grid is requested with an existing position,
                        or current price/klines cannot be fetched
        """
        grid_mode = grid_mode.upper()
        if grid_mode not in self._VALID_GRID_MODES:
            raise ValueError(f"grid_mode must be one of {sorted(self._VALID_GRID_MODES)}, got {grid_mode!r}")

        manual_bounds_given = lower_price is not None or upper_price is not None
        manual_bounds_complete = lower_price is not None and upper_price is not None
        if manual_bounds_given and not manual_bounds_complete:
            raise ValueError(
                "Provide lower_price and upper_price together, or omit both so "
                "they are calculated automatically from ATR"
            )

        # Fail fast (before any pricing/klines calls) if NEUTRAL mode would
        # stack on top of an existing position from outside this bot.
        if grid_mode == "NEUTRAL":
            position = await self.binance.get_position(symbol)
            position_amt = Decimal(position["positionAmt"]) if position else Decimal("0")
            if position_amt != 0:
                raise ValueError(
                    f"Cannot create NEUTRAL grid for {symbol}: existing position {position_amt} != 0. "
                    "Close the position first, or use grid_mode=LONG/SHORT."
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
        # And global exposure limit (Paso 10): max concurrent grids
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

            # Check global exposure limit
            cursor_check.execute(
                "SELECT COUNT(*) AS c FROM grids WHERE status = 'RUNNING'"
            )
            count = cursor_check.fetchone()["c"]
            if count >= settings.MAX_CONCURRENT_GRIDS:
                raise ValueError(
                    f"Max concurrent grids ({settings.MAX_CONCURRENT_GRIDS}) reached. "
                    f"Cancel an existing grid before creating a new one."
                )
        finally:
            conn_check.close()

        # Validate account position mode and set leverage/margin before placing orders
        one_way = await self.binance.is_one_way_mode()
        if one_way is False:
            raise ValueError(
                "Account is in hedge (dual) mode — switch to one-way mode before running grids"
            )

        # Set leverage explicitly BEFORE placing any order (dynamic per grid)
        effective_leverage = leverage if leverage is not None else GRID_LEVERAGE_DEFAULT
        lev_result = await self.binance.set_leverage(symbol, effective_leverage)
        if lev_result is None:
            raise ValueError(f"Could not set leverage {effective_leverage}x for {symbol}")
        print(f"set_leverage({symbol}, {effective_leverage}) OK before placing orders: {lev_result}")

        if not await self.binance.ensure_symbol_settings(
            symbol,
            leverage=effective_leverage,
            margin_type=settings.DEFAULT_MARGIN_TYPE
        ):
            raise ValueError(f"Could not set leverage/margin type for {symbol}")

        # Validate grid step is large enough to cover fees and be profitable
        fees = await self.binance.get_commission_rate(symbol)
        maker_fee = fees["maker"] if fees else Decimal("0.0002")  # fallback: 0.02%
        validate_grid_step(
            Decimal(str(lower_price)),
            Decimal(str(upper_price)),
            levels,
            maker_fee,
            Decimal(str(settings.MIN_STEP_FEE_MULTIPLE))
        )

        # Build order specs for every grid level, keeping track of level_index
        order_specs = []
        for level_idx, level_price in enumerate(price_levels):
            quantized_price = self._snap_down(level_price, filters["tick_size"])
            side = "BUY" if quantized_price < current_price else "SELL"
            order_specs.append({
                "symbol": symbol,
                "side": side,
                "quantity": quantized_qty,
                "price": quantized_price,
                "level_index": level_idx,  # Track index for replenishment
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
            for column_def in (
                "leverage INTEGER DEFAULT 3",
                "quantity_per_order NUMERIC",
                "grid_mode TEXT DEFAULT 'NEUTRAL'",
            ):
                try:
                    cursor.execute(f"ALTER TABLE grids ADD COLUMN {column_def}")
                except Exception:
                    pass  # column already exists
            cursor.execute(
                """INSERT INTO grids (id, symbol, lower_price, upper_price, levels, grid_type, status, stop_loss, take_profit, max_duration_hours, leverage, quantity_per_order, grid_mode)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (grid_id, symbol, str(engine.lower_price), str(engine.upper_price), levels, grid_type, "RUNNING",
                 str(stop_loss) if stop_loss is not None else None,
                 str(take_profit) if take_profit is not None else None,
                 str(max_duration_hours) if max_duration_hours is not None else None,
                 effective_leverage, str(quantized_qty), grid_mode)
            )
            orders_placed = 0
            for spec, order in order_results:
                if not order or "orderId" not in order:
                    print(f"Order skipped — Binance response: {order} | spec: price={spec['price']} side={spec['side']}")
                    continue
                cursor.execute(
                    """INSERT INTO grid_orders (id, grid_id, price, quantity, side, type, status, level_index, cycle)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (str(order["orderId"]), grid_id, str(spec["price"]), str(spec["quantity"]),
                     spec["side"], "LIMIT", "NEW", spec.get("level_index"), 0)
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

        Optimization (Paso 9): uses GET /fapi/v1/openOrders (1 call) to get
        all open orders, then only queries individual orders that have closed
        (not in the open set). Reduces N calls to 1 + (closed orders).

        Dead-order / reconciliation safety net: if this grid's state cannot
        be fully confirmed against Binance (the openOrders call itself fails,
        or an individual order comes back neither open nor resolvable) for
        _MAX_REFRESH_FAILURES consecutive cycles, the grid is auto-canceled
        rather than left silently drifting between local and remote state.
        The result carries `refresh_status` / `unconfirmed_order_ids` /
        `extra_order_ids` (not persisted columns — added to the in-memory
        dict) so the caller can alert on partial mismatches even when the
        grid isn't bad enough to auto-cancel yet.

        Returns:
            Updated grid (with orders) or None if grid_id does not exist.
        """
        grid = self.get_grid(grid_id)
        if not grid:
            return None

        open_orders = [o for o in grid["orders"] if o["status"] not in _TERMINAL_ORDER_STATUSES]
        if not open_orders:
            self._refresh_fail_counters.pop(grid_id, None)
            grid["refresh_status"] = "ok"
            return grid

        # Fetch all open orders on Binance for this symbol (1 call)
        binance_open = await self.binance.get_open_orders(grid["symbol"])
        if binance_open is None:
            return await self._handle_refresh_failure(
                grid_id, grid, reason="openOrders call failed (network/API error)"
            )

        # Build set of orderIds that are still open on Binance
        open_order_ids = set(str(o["orderId"]) for o in binance_open)
        unconfirmed_ids: List[str] = []
        external_cancellations: List[Dict[str, Any]] = []

        conn = get_sqlite_connection()
        try:
            cursor = conn.cursor()

            for order in open_orders:
                order_id_str = str(order["id"])

                if order_id_str in open_order_ids:
                    # Order is still open on Binance - find and update from the fetched list
                    for binance_order in binance_open:
                        if str(binance_order["orderId"]) == order_id_str:
                            new_status = binance_order["status"]
                            executed_qty = binance_order.get("executedQty", "0")
                            avg_price = binance_order.get("avgPrice", "0")
                            cursor.execute(
                                "UPDATE grid_orders SET status = ?, executed_qty = ?, avg_fill_price = ? WHERE id = ?",
                                (new_status, executed_qty, avg_price, order["id"])
                            )
                            break
                else:
                    # Order is not in open list - must have closed, query individually to know status
                    remote = await self.binance.get_order_status(grid["symbol"], int(order["id"]))
                    if not remote or "status" not in remote:
                        # Dead/orphaned order: neither open on Binance nor
                        # resolvable via direct lookup. Leave local status
                        # untouched but flag it — this is exactly the
                        # "phantom order" drift scenario.
                        unconfirmed_ids.append(order_id_str)
                        continue
                    new_status = remote["status"]
                    executed_qty = remote.get("executedQty", "0")
                    avg_price = remote.get("avgPrice", "0")

                    # Reconciliation succeeded (we got a confirmed answer) but
                    # the answer is "someone/something canceled this outside
                    # the bot" — worth telling the operator even though local
                    # state is about to become consistent again.
                    if new_status == "CANCELED" and order["status"] != "CANCELED":
                        logger.warning(
                            f"Grid {grid_id}: external cancellation detected for order "
                            f"{order['id']} (was {order['status']}, price={order.get('price')}, "
                            f"qty={order.get('quantity')}, executed={executed_qty})"
                        )
                        external_cancellations.append({
                            "order_id": order_id_str,
                            "price": str(order.get("price", "0")),
                            "quantity": str(order.get("quantity", "0")),
                            "executed_qty": str(executed_qty),
                            "status_was": order["status"],
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        })

                    cursor.execute(
                        "UPDATE grid_orders SET status = ?, executed_qty = ?, avg_fill_price = ? WHERE id = ?",
                        (new_status, executed_qty, avg_price, order["id"])
                    )

            conn.commit()
        finally:
            conn.close()

        if unconfirmed_ids:
            failure_result = await self._handle_refresh_failure(
                grid_id, self.get_grid(grid_id),
                reason=f"{len(unconfirmed_ids)} order(s) unconfirmed on Binance",
                unconfirmed_ids=unconfirmed_ids,
            )
            if external_cancellations:
                failure_result["external_cancellations"] = external_cancellations
            return failure_result

        # Clean reconciliation this cycle
        self._refresh_fail_counters.pop(grid_id, None)
        result = self.get_grid(grid_id)
        result["refresh_status"] = "ok"
        if external_cancellations:
            result["external_cancellations"] = external_cancellations
        # Extra visibility: orders open on Binance but not tracked locally
        # (e.g. manual intervention on the exchange UI, or a replenish race).
        local_open_ids = {str(o["id"]) for o in result["orders"] if o["status"] not in _TERMINAL_ORDER_STATUSES}
        extra_ids = sorted(open_order_ids - local_open_ids)
        if extra_ids:
            result["extra_order_ids"] = extra_ids
            logger.warning(f"Grid {grid_id}: {len(extra_ids)} order(s) open on Binance but untracked locally: {extra_ids}")
        return result

    async def _handle_refresh_failure(
        self, grid_id: str, grid: Dict[str, Any], reason: str,
        unconfirmed_ids: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Bump the per-grid failure counter; auto-cancel once it reaches
        _MAX_REFRESH_FAILURES instead of letting local/remote state drift
        indefinitely. Never raises — cancellation failures are logged and
        the grid is still reported back with its (unreconciled) local state.
        """
        count = self._refresh_fail_counters.get(grid_id, 0) + 1
        self._refresh_fail_counters[grid_id] = count
        logger.warning(f"Grid {grid_id}: refresh failure {count}/{_MAX_REFRESH_FAILURES} ({reason})")

        if count < _MAX_REFRESH_FAILURES:
            grid["refresh_status"] = "unreconciled"
            grid["refresh_failure_count"] = count
            if unconfirmed_ids:
                grid["unconfirmed_order_ids"] = unconfirmed_ids
            return grid

        logger.critical(
            f"Grid {grid_id}: {count} consecutive unreconciled refresh cycles — auto-canceling"
        )
        self._refresh_fail_counters.pop(grid_id, None)
        try:
            closed = await self.cancel_grid(grid_id, trigger_condition="RECONCILIATION_FAILED")
            if closed:
                closed["refresh_status"] = "auto_canceled"
                return closed
        except Exception as e:
            logger.critical(f"Grid {grid_id}: auto-cancel after reconciliation failure ALSO failed: {e}")

        grid["refresh_status"] = "auto_cancel_failed"
        return grid

    async def replenish_filled_orders(self, grid_id: str) -> int:
        """
        Reposición de órdenes: por cada orden FILLED (o con executed_qty > 0 y no replenida),
        coloca la orden opuesta en el nivel adyacente.

        FIX 1A: Claim atómico en SQLite — reclamar replenish ANTES de colocar orden.
        FIX 1B: clientOrderId determinístico para idempotencia en Binance.

        Rules:
        - BUY llenada en nivel i  → SELL en nivel i+1
        - SELL llenada en nivel i → BUY en nivel i-1
        - Si no hay nivel adyacente (fill en el borde), skip
        - Idempotente (dos capas): claim atómico en DB + clientOrderId determinístico

        Returns:
            Número de órdenes nuevas colocadas. 0 si sin fills o error.
        """
        grid = self.get_grid(grid_id)
        if not grid or grid["status"] != "RUNNING":
            return 0

        # NEUTRAL mode: pause replenishment while the account carries a
        # position on this symbol beyond a small dust tolerance. Replenishing
        # while unbalanced would keep adding to the same directional
        # exposure a NEUTRAL grid is meant to avoid.
        if (grid.get("grid_mode") or "NEUTRAL").upper() == "NEUTRAL":
            position = await self.binance.get_position(grid["symbol"])
            position_amt = Decimal(position["positionAmt"]) if position else Decimal("0")
            qty_per_order = Decimal(grid.get("quantity_per_order") or 0)
            tolerance = qty_per_order * Decimal("0.05") if qty_per_order > 0 else Decimal("0")
            if abs(position_amt) > tolerance:
                logger.warning(
                    f"Grid {grid_id} ({grid['symbol']}) NEUTRAL mode: position {position_amt} "
                    f"outside tolerance {tolerance} — blocking replenish this cycle"
                )
                return 0

        # Recalculate grid levels using stored params
        engine = GridEngine(
            grid["symbol"],
            float(grid["lower_price"]),
            float(grid["upper_price"]),
            int(grid["levels"]),
            GridType(grid.get("grid_type") or "GEOMETRIC")
        )
        price_levels = engine.calculate_grid_levels()

        filters = await self.binance.get_symbol_filters(grid["symbol"])
        if not filters:
            return 0

        # Find candidates for replenishment (filled but not yet replenished)
        conn = get_sqlite_connection()
        placed = 0
        try:
            cursor = conn.cursor()
            grid_orders = self.get_grid(grid_id)["orders"]

            for o in grid_orders:
                executed = Decimal(o.get("executed_qty") or 0)
                if executed <= 0:
                    continue  # Not filled

                # CAPA A: Claim atómico — reclamar derecho a reponer ANTES de colocar orden
                cursor.execute(
                    "UPDATE grid_orders SET replenished = 1 "
                    "WHERE id = ? AND replenished = 0",
                    (o["id"],)
                )
                conn.commit()

                if cursor.rowcount != 1:
                    continue  # Otro ciclo ya reclamó esta orden — skip

                # Solo llegamos aquí si reclamamos exitosamente
                idx = o.get("level_index")
                if idx is None:
                    continue  # No level info, revert claim
                    # (en la práctica es muy raro, pero si ocurre, la próxima iteración lo verá como replenished)

                # Determine opposite order position
                if o["side"] == "BUY" and idx + 1 < len(price_levels):
                    new_idx, new_side = idx + 1, "SELL"
                elif o["side"] == "SELL" and idx - 1 >= 0:
                    new_idx, new_side = idx - 1, "BUY"
                else:
                    continue  # Fill at grid edge, no adjacent level

                new_price = self._snap_down(price_levels[new_idx], filters["tick_size"])

                # CAPA B: clientOrderId determinístico para idempotencia en Binance
                # Formato: g{grid_id:8}-l{level:05d}-r{source_order:8}
                grid_id_short = grid_id[:8] if len(grid_id) >= 8 else grid_id
                source_order_short = str(o["id"])[:8] if str(o["id"]) else "unknown"
                client_order_id = f"g{grid_id_short}-l{new_idx:05d}-r{source_order_short}"[:36]

                # Colocar orden individual (no en batch por simplicidad y claridad atómica)
                try:
                    order_result = await self.binance.place_batch_orders(
                        [{
                            "symbol": grid["symbol"],
                            "side": new_side,
                            "quantity": Decimal(str(o["quantity"])),
                            "price": new_price,
                        }],
                        client_order_ids_map={0: client_order_id}
                    )

                    if order_result and order_result[0] and "orderId" in order_result[0]:
                        # Éxito: insertar nueva orden en DB
                        order = order_result[0]
                        cursor.execute(
                            """INSERT INTO grid_orders
                               (id, grid_id, price, quantity, side, type, status, level_index, cycle)
                               VALUES (?, ?, ?, ?, ?, ?, 'NEW', ?, ?)""",
                            (str(order["orderId"]), grid_id, str(new_price),
                             str(o["quantity"]), new_side, "LIMIT",
                             new_idx, int(o.get("cycle") or 0) + 1)
                        )
                        conn.commit()
                        placed += 1
                    else:
                        # Fallo en Binance: si es clientOrderId duplicado (benigno), marcar como ya replenida y loguear
                        # Si es error real, revertir el claim para reintentar
                        error_msg = str(order_result[0]) if (order_result and order_result[0]) else "No response"
                        if "duplicate" in error_msg.lower() or "already" in error_msg.lower():
                            print(f"Replenish ya colocada (clientOrderId duplicado): {client_order_id}")
                            # Flag ya está 1, no revertir — se considera éxito benigno
                            placed += 1
                        else:
                            # Error real: revertir claim para próximo intento
                            print(f"Replenish falló ({error_msg}), revertiendo claim para {o['id']}")
                            cursor.execute(
                                "UPDATE grid_orders SET replenished = 0 WHERE id = ?",
                                (o["id"],)
                            )
                            conn.commit()

                except Exception as e:
                    print(f"Exception en replenish para {o['id']}: {e}")
                    # Revertir claim para reintentar
                    cursor.execute(
                        "UPDATE grid_orders SET replenished = 0 WHERE id = ?",
                        (o["id"],)
                    )
                    conn.commit()

        finally:
            conn.close()

        return placed

    async def get_grid_pnl(self, grid_id: str, current_price: Optional[Decimal] = None) -> Optional[Dict[str, Any]]:
        """
        Fetch a grid's current orders + mark price and compute PnL via the
        pure calculate_grid_pnl(). Does not call refresh_order_status() -
        call that first if you need PnL based on up to date fill status.

        Args:
            current_price: Reuse an already-fetched mark price (e.g. from
                close_grid_if_triggered's OUT_OF_RANGE check) instead of
                hitting Binance again in the same evaluation cycle.

        Raises:
            ValueError: if current price cannot be fetched
        """
        grid = self.get_grid(grid_id)
        if not grid:
            return None

        if current_price is None:
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

    async def cancel_grid(self, grid_id: str, trigger_condition: str = "MANUAL",
                         close_position: bool = True) -> Optional[Dict[str, Any]]:
        """
        Cancel all open orders for a grid and close the net position.

        Step 1: Cancel ALL open orders on the symbol (atomic /fapi/v1/allOpenOrders)
        Step 2: Close the net position with MARKET + reduceOnly (no orphaned position)
        Step 3: Update SQLite to mark all orders and grid as CANCELED
        Step 4: Log closure in historical_grid_logs (Postgres) if available

        With rule R-07 (1 RUNNING grid per symbol), canceling by symbol is safe
        and simpler than canceling by orderId.

        Args:
            close_position: If True, place a MARKET order to reduce any open position to 0.
                          Set to False only for testing.

        Raises:
            ValueError: if cancel_all_open_orders or place_market_close fails
        """
        grid = self.get_grid(grid_id)
        if not grid:
            return None

        final_pnl = None
        try:
            final_pnl = await self.get_grid_pnl(grid_id)
        except ValueError:
            pass  # current price unavailable - log without PnL rather than failing the cancel

        # 1) Cancel ALL open orders on the symbol (LIMIT + PARTIALLY_FILLED)
        ok = await self.binance.cancel_all_open_orders(grid["symbol"])
        if not ok:
            raise ValueError(
                f"Could not cancel open orders for {grid['symbol']} — grid NOT closed"
            )

        # 2) Close the net position with MARKET reduceOnly
        if close_position:
            position = await self.binance.get_position(grid["symbol"])
            position_amt = Decimal(position["positionAmt"]) if position else Decimal("0")
            if position_amt != 0:
                result = await self.binance.place_market_close(grid["symbol"], position_amt)
                if not result:
                    raise ValueError(
                        f"Orders canceled but position {position_amt} {grid['symbol']} "
                        "could NOT be closed — manual intervention required"
                    )

        # 3) Persist state change locally + FIX 3: log to grid_closures
        position_amt_at_close = None
        if close_position:
            position = await self.binance.get_position(grid["symbol"])
            position_amt_at_close = str(position.get("positionAmt", "0")) if position else "0"

        total_pnl_str = str(final_pnl.get("total_pnl", "0")) if final_pnl else "0"

        conn = get_sqlite_connection()
        try:
            cursor = conn.cursor()
            non_terminal = [o for o in grid["orders"] if o["status"] not in _TERMINAL_ORDER_STATUSES]
            for order in non_terminal:
                cursor.execute("UPDATE grid_orders SET status = 'CANCELED' WHERE id = ?", (order["id"],))
            cursor.execute("UPDATE grids SET status = 'CANCELED' WHERE id = ?", (grid_id,))

            # FIX 3: Insert closure audit log to grid_closures (never fails — best effort)
            try:
                cursor.execute(
                    """INSERT INTO grid_closures
                       (grid_id, symbol, trigger_condition, total_pnl, position_amt_at_close)
                       VALUES (?, ?, ?, ?, ?)""",
                    (grid_id, grid["symbol"], trigger_condition, total_pnl_str, position_amt_at_close)
                )
            except Exception as e:
                print(f"Warning: could not insert grid_closures for {grid_id}: {e}")

            conn.commit()
        finally:
            conn.close()

        # 4) Log closure (PostgreSQL)
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
        Evaluate whether a grid should be closed based on five conditions:
        1. EXPIRED: grid age >= max_duration_hours
        2. OUT_OF_RANGE: mark price outside [lower_price, upper_price]
        3. MAX_POSITION: net position exceeds MAX_NET_POSITION_LEVELS * quantity_per_order (FIX 2)
        4. STOP_LOSS: total PnL <= stop_loss threshold
        5. TAKE_PROFIT: total PnL >= take_profit threshold

        Does not call refresh_order_status() first - call that beforehand
        if the decision needs up to date fills.

        Returns:
            {"grid": <grid dict>, "triggered": "EXPIRED" | "OUT_OF_RANGE" | "MAX_POSITION" |
             "STOP_LOSS" | "TAKE_PROFIT" | None}
            or None if grid_id does not exist.
        """
        grid = self.get_grid(grid_id)
        if not grid:
            return None

        if grid["status"] != "RUNNING":
            return {"grid": grid, "triggered": None}

        # Check 1: Expiration (age vs max_duration_hours)
        max_duration = grid.get("max_duration_hours")
        if max_duration is not None:
            age = self._grid_age_hours(grid)
            if age is not None and age >= float(max_duration):
                closed_grid = await self.cancel_grid(grid_id, trigger_condition="EXPIRED")
                return {"grid": closed_grid, "triggered": "EXPIRED"}

        # Fetch mark price once and reuse it for OUT_OF_RANGE + SL/TP below,
        # instead of hitting Binance twice in the same evaluation cycle.
        current_price: Optional[Decimal] = None
        price_data = await self.binance.get_mark_price(grid["symbol"])
        if price_data and "price" in price_data:
            current_price = Decimal(str(price_data["price"]))

        # Check 2: Price left the grid's range entirely. A strong trend that
        # blows through the range stops earning from oscillation and just
        # accumulates one-sided exposure — MAX_POSITION (below) is the
        # position-based backstop for that, this is the price-based one.
        if current_price is not None:
            lower_price = Decimal(str(grid["lower_price"]))
            upper_price = Decimal(str(grid["upper_price"]))
            if current_price < lower_price or current_price > upper_price:
                closed_grid = await self.cancel_grid(grid_id, trigger_condition="OUT_OF_RANGE")
                logger.warning(
                    f"Grid {grid_id} ({grid['symbol']}) closed: "
                    f"price {current_price} outside range [{lower_price}, {upper_price}]"
                )
                return {"grid": closed_grid, "triggered": "OUT_OF_RANGE"}

        # Check 3: Max net position accumulated (FIX 2)
        qty_per_order = Decimal(grid.get("quantity_per_order") or 0)
        if qty_per_order > 0:
            position = await self.binance.get_position(grid["symbol"])
            position_amt = Decimal(position["positionAmt"]) if position else Decimal("0")
            max_position = settings.MAX_NET_POSITION_LEVELS * qty_per_order * Decimal("1.05")  # 5% tolerance
            if abs(position_amt) > max_position:
                closed_grid = await self.cancel_grid(grid_id, trigger_condition="MAX_POSITION")
                return {"grid": closed_grid, "triggered": "MAX_POSITION"}

        # Check 4 & 5: SL/TP
        pnl = await self.get_grid_pnl(grid_id, current_price=current_price)

        stop_loss = Decimal(str(grid["stop_loss"])) if grid.get("stop_loss") is not None else None
        take_profit = Decimal(str(grid["take_profit"])) if grid.get("take_profit") is not None else None

        trigger = check_sl_tp(pnl["total_pnl"], stop_loss, take_profit)
        if trigger is None:
            return {"grid": grid, "triggered": None}

        closed_grid = await self.cancel_grid(grid_id, trigger_condition=trigger)
        return {"grid": closed_grid, "triggered": trigger}