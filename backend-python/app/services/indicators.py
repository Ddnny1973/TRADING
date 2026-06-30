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

    Only orders with status == "FILLED" count toward realized PnL. Any other
    status (NEW, PARTIALLY_FILLED, CANCELED, REJECTED, EXPIRED) is ignored.

    Known, deliberate limitation: grid_orders stores each order's full
    requested quantity, not Binance's executedQty, so a PARTIALLY_FILLED
    order contributes nothing until Binance reports it as fully FILLED.

    Method: filled BUY and SELL quantities are matched against each other.
        avg_buy_price  = total buy cost   / total filled buy qty
        avg_sell_price = total sell value / total filled sell qty
        matched_qty    = min(filled buy qty, filled sell qty)
        realized_pnl   = matched_qty * (avg_sell_price - avg_buy_price)
    Any unmatched (leftover) quantity is valued against current_price as
    unrealized_pnl - positive net_position_qty means leftover bought
    inventory (long), negative means leftover sold inventory (short).

    Args:
        orders: order dicts with at least "side", "price", "quantity", "status"
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
        if order.get("status") != "FILLED":
            continue
        qty = _as_decimal(order["quantity"])
        price = _as_decimal(order["price"])
        if order["side"] == "BUY":
            buy_qty += qty
            buy_cost += qty * price
        elif order["side"] == "SELL":
            sell_qty += qty
            sell_proceeds += qty * price

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
