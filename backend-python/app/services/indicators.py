"""
Indicators module
Pure, deterministic market calculations (no I/O, no external calls, no LLM).
Inputs in -> outputs out, same result every time given the same data.

These functions are the analysis building blocks consumed by grid_service.py
(and, later, by an external AI orchestrator that decides *when* and *with what
parameters* to call them). They must never embed qualitative/contextual
judgment (sentiment, news, discretionary overrides) - that belongs to the
orchestration layer described in roadmap_grid_trading_bot.md.
"""

from decimal import Decimal
from typing import List, Dict, Any, Optional


def calculate_atr(klines: List[Dict[str, Any]], period: int = 14) -> Decimal:
    """
    Calculate Average True Range (ATR) using a simple moving average of
    True Range values (Wilder's original formula, unsmoothed variant).

    True Range for candle i:
        TR_i = max(high_i - low_i, |high_i - prevClose|, |low_i - prevClose|)

    ATR(period) = average of the last `period` TR values.

    Requires period + 1 klines because the first candle in the window is
    only used to supply the "previous close" for the second candle's TR.
    binance_client.get_klines() defaults to limit=15 for this reason
    (period=14 -> 14 TR values -> 15 candles).

    Args:
        klines: Ordered oldest->newest list of dicts as returned by
                BinanceClient.get_klines() / _parse_kline() (Decimal values).
        period: Number of True Range values to average. Default 14.

    Returns:
        ATR as Decimal.

    Raises:
        ValueError: if there are not enough klines for the requested period.
    """
    if period < 1:
        raise ValueError("period debe ser >= 1")

    required = period + 1
    if len(klines) < required:
        raise ValueError(
            f"Se requieren al menos {required} velas para period={period}, "
            f"llegaron {len(klines)}"
        )

    # Use the most recent `required` candles in case more were passed in
    window = klines[-required:]

    true_ranges: List[Decimal] = []
    for i in range(1, len(window)):
        high = window[i]["high"]
        low = window[i]["low"]
        prev_close = window[i - 1]["close"]

        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close),
        )
        true_ranges.append(tr)

    return sum(true_ranges) / Decimal(len(true_ranges))


def calculate_grid_bounds(
    current_price: Decimal,
    atr: Decimal,
    multiplier: Decimal = Decimal("2"),
) -> Dict[str, Decimal]:
    """
    Fixed (non-learned) rule that derives grid lower/upper bounds from
    volatility. Wider ATR or multiplier -> wider grid range.

        lower_price = current_price - (atr * multiplier)
        upper_price = current_price + (atr * multiplier)

    `multiplier` is a tunable parameter, not a hardcoded constant - the
    caller (eventually the AI orchestrator) decides its value per call.
    Default of 2 is a reasonable, commonly-used starting point for grid
    trading ranges sized off ATR(14).

    Args:
        current_price: Anchor price (e.g. mark price) as Decimal.
        atr: Average True Range as Decimal (output of calculate_atr).
        multiplier: ATR multiplier controlling range width. Default 2.

    Returns:
        {"lower_price": Decimal, "upper_price": Decimal}

    Raises:
        ValueError: if current_price or atr is not positive, or the
                    resulting lower_price would be <= 0.
    """
    if current_price <= 0:
        raise ValueError("current_price debe ser > 0")
    if atr <= 0:
        raise ValueError("atr debe ser > 0")
    if multiplier <= 0:
        raise ValueError("multiplier debe ser > 0")

    offset = atr * multiplier
    lower_price = current_price - offset
    upper_price = current_price + offset

    if lower_price <= 0:
        raise ValueError(
            f"lower_price calculado ({lower_price}) es <= 0; "
            f"reduce el multiplier o revisa el ATR de entrada"
        )

    return {"lower_price": lower_price, "upper_price": upper_price}


def calculate_grid_pnl(orders: List[Dict[str, Any]], current_price: Decimal) -> Dict[str, Decimal]:
    """
    Pure PnL calculation over a grid's orders. No I/O, no DB access - the
    caller is responsible for fetching `orders` (e.g. via GridService) and
    an up to date `current_price` beforehand.

    Now uses executed_qty (actual fills) instead of status == "FILLED". This way:
    - FILLED orders: executed_qty = full quantity
    - PARTIALLY_FILLED orders: executed_qty = partial amount (counts proportionally)
    - NEW, CANCELED, REJECTED, EXPIRED: executed_qty = 0 (ignored)

    Method: filled BUY and SELL quantities (by executed_qty) are matched.
        avg_buy_price  = total buy cost   / total filled buy qty
        avg_sell_price = total sell value / total filled sell qty
        matched_qty    = min(filled buy qty, filled sell qty)
        realized_pnl   = matched_qty * (avg_sell_price - avg_buy_price)
    Any unmatched quantity is valued against current_price as unrealized_pnl.

    Args:
        orders: order dicts with "side", "price", "quantity", "executed_qty", "avg_fill_price"
                (price/quantity accepted as str or Decimal).
        current_price: anchor price used to value unmatched inventory.

    Returns:
        dict with realized_pnl, unrealized_pnl, total_pnl, net_position_qty,
        filled_buy_qty, filled_sell_qty - all Decimal.
    """

    def _as_decimal(value: Any) -> Decimal:
        return value if isinstance(value, Decimal) else Decimal(str(value))

    buy_qty = Decimal("0")
    buy_cost = Decimal("0")
    sell_qty = Decimal("0")
    sell_proceeds = Decimal("0")

    for order in orders:
        # Use executed_qty instead of status: accounts for partial fills
        executed = _as_decimal(order.get("executed_qty") or 0)
        if executed <= 0:
            continue  # No fills, skip
        # Use avg_fill_price if available (Binance reports the filled average)
        # otherwise fall back to order's limit price
        price = _as_decimal(order.get("avg_fill_price") or 0) or _as_decimal(order["price"])
        if order["side"] == "BUY":
            buy_qty += executed
            buy_cost += executed * price
        elif order["side"] == "SELL":
            sell_qty += executed
            sell_proceeds += executed * price

    avg_buy_price = (buy_cost / buy_qty) if buy_qty > 0 else Decimal("0")
    avg_sell_price = (sell_proceeds / sell_qty) if sell_qty > 0 else Decimal("0")

    matched_qty = min(buy_qty, sell_qty)
    realized_pnl = matched_qty * (avg_sell_price - avg_buy_price) if matched_qty > 0 else Decimal("0")

    net_position_qty = buy_qty - sell_qty
    if net_position_qty > 0:
        unrealized_pnl = net_position_qty * (current_price - avg_buy_price)
    elif net_position_qty < 0:
        unrealized_pnl = abs(net_position_qty) * (avg_sell_price - current_price)
    else:
        unrealized_pnl = Decimal("0")

    return {
        "realized_pnl": realized_pnl,
        "unrealized_pnl": unrealized_pnl,
        "total_pnl": realized_pnl + unrealized_pnl,
        "net_position_qty": net_position_qty,
        "filled_buy_qty": buy_qty,
        "filled_sell_qty": sell_qty,
    }


def check_sl_tp(
    total_pnl: Decimal,
    stop_loss: Optional[Decimal],
    take_profit: Optional[Decimal],
) -> Optional[str]:
    """
    Fixed comparison rule (no judgment, no context) over an already-computed
    total_pnl (see calculate_grid_pnl):

        total_pnl <= -stop_loss   -> "STOP_LOSS"
        total_pnl >= take_profit  -> "TAKE_PROFIT"
        otherwise                 -> None

    stop_loss/take_profit are optional quote-currency thresholds; a None
    threshold simply can never trigger. If both would trigger at once
    (degenerate/misconfigured input, e.g. stop_loss=0 and take_profit=0),
    STOP_LOSS takes priority - a fixed, explicit tie-break, not a judgment
    call.

    Args:
        total_pnl: current total PnL (output of calculate_grid_pnl).
        stop_loss: positive quote-currency loss threshold, or None to disable.
        take_profit: positive quote-currency gain threshold, or None to disable.

    Returns:
        "STOP_LOSS", "TAKE_PROFIT", or None.
    """
    if stop_loss is not None and total_pnl <= -stop_loss:
        return "STOP_LOSS"
    if take_profit is not None and total_pnl >= take_profit:
        return "TAKE_PROFIT"
    return None


def calculate_position_size(
    available_balance: Decimal,
    risk_pct: Decimal,
    levels: int,
    lower_price: Decimal,
    upper_price: Decimal,
) -> Decimal:
    """
    Calculate position size (quantity per order) based on available balance and risk tolerance.

    Pure function, no I/O, deterministic sizing rule. No leverage assumed (1× notional).

    Formula:
        capital_a_arriesgar = available_balance * risk_pct
        precio_promedio = (lower_price + upper_price) / 2
        quantity_per_order = capital_a_arriesgar / (levels * precio_promedio)

    This allocates risk_pct of your balance across all grid levels at the average price
    (midpoint between lower and upper bounds).

    Real-world example:
      - available_balance = $10,000 USDT
      - risk_pct = 0.02 (2% risk per grid)
      - levels = 10
      - lower_price = $42,100
      - upper_price = $42,900
      - Calculation:
        - capital_a_arriesgar = 10000 * 0.02 = $200
        - precio_promedio = (42100 + 42900) / 2 = $42,500
        - quantity_per_order = 200 / (10 * 42500) = 200 / 425000 ≈ 0.00047 BTC

    Args:
        available_balance: USDT balance available for trading (Decimal).
        risk_pct: Fraction of balance to risk per grid (0.01 = 1%, 0.02 = 2%).
                  Recommended range: 0.01 to 0.02 (1-2% per grid for safety).
        levels: Number of grid levels (buy orders).
        lower_price: Lower bound of the grid in quote currency (Decimal).
        upper_price: Upper bound of the grid in quote currency (Decimal).

    Returns:
        Quantity per order (Decimal), represents how much base asset per grid level.

    Raises:
        ValueError: if inputs are non-positive or invalid.
    """
    if available_balance <= 0:
        raise ValueError("available_balance debe ser > 0")
    if risk_pct <= 0 or risk_pct > 1:
        raise ValueError("risk_pct debe estar entre 0 y 1")
    if levels < 1:
        raise ValueError("levels debe ser >= 1")
    if lower_price <= 0 or upper_price <= 0:
        raise ValueError("lower_price y upper_price deben ser > 0")
    if lower_price >= upper_price:
        raise ValueError("lower_price debe ser < upper_price")

    capital_a_arriesgar = available_balance * risk_pct
    precio_promedio = (lower_price + upper_price) / Decimal(2)
    quantity = capital_a_arriesgar / (Decimal(levels) * precio_promedio)

    return quantity


def validate_grid_step(lower_price: Decimal, upper_price: Decimal, levels: int,
                       maker_fee: Decimal, min_fee_multiple: Decimal = Decimal("5")) -> None:
    """
    Validate that grid step size is large enough to cover fees and make profit.

    The benefit of a single cycle (buy at level i, sell at i+1) is approximately
    the step percentage. The cost is 2 × maker_fee (entry + exit). We require:

        step_pct >= min_fee_multiple * 2 * maker_fee

    With maker_fee = 0.02% (0.0002) and min_fee_multiple = 5:
        Required step_pct >= 5 * 2 * 0.02% = 0.2%

    Args:
        lower_price: Lower bound of grid (Decimal).
        upper_price: Upper bound of grid (Decimal).
        levels: Number of grid levels.
        maker_fee: Maker commission rate as decimal (0.0002 = 0.02%).
        min_fee_multiple: Multiplier of (2 * maker_fee) that defines minimum step.
                         Default 5 means step_pct must be at least 5× the round-trip fee.

    Raises:
        ValueError: if step_pct < min_fee_multiple * 2 * maker_fee.
    """
    if levels < 2:
        # Only 1 level: no cycles possible, skip validation
        return

    avg_price = (lower_price + upper_price) / Decimal(2)
    step_size = (upper_price - lower_price) / Decimal(max(levels - 1, 1))
    step_pct = step_size / avg_price

    min_step_pct = min_fee_multiple * Decimal(2) * maker_fee

    if step_pct < min_step_pct:
        raise ValueError(
            f"Grid step {step_pct:.4%} is below minimum {min_step_pct:.4%} "
            f"(= {min_fee_multiple}x round-trip fees of 2 × {maker_fee:.4%}). "
            f"Reduce levels or widen the range to make cycles profitable."
        )
