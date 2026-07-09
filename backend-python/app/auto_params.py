"""
Auto-derivation of grid parameters from symbol and balance only.
Pure trading logic with exact formulas from specification.
"""

from decimal import Decimal, ROUND_DOWN, ROUND_UP
from typing import Dict, List, Optional, Tuple, Any
import logging

from app.config_auto_params import (
    FEE_ROUNDTRIP, FEE_MARGIN_FACTOR, MAX_RISK_PCT, CAPITAL_BUFFER,
    MULTIPLIER_BOUNDS, LEVELS_BOUNDS, ATR_PERIOD,
    CANDIDATE_INTERVALS, ER_LOOKBACK, ER_MAX_TRADEABLE, RANGE_LOOKBACK,
    MIN_NOTIONAL_FALLBACK, LEVERAGE_BY_VOLATILITY, LEVERAGE_BOUNDS
)
from app.services.binance_client import BinanceClient
from app.services.indicators import calculate_atr

logger = logging.getLogger(__name__)


async def fetch_klines(
    client: BinanceClient,
    symbol: str,
    interval: str,
    limit: int = 100
) -> Optional[List[Dict[str, Any]]]:
    """
    Fetch klines from Binance public API.

    Args:
        client: BinanceClient instance
        symbol: Trading pair (e.g., BTCUSDT)
        interval: Kline interval (1m, 5m, 1h, 4h, 1d, etc.)
        limit: Number of candles to fetch

    Returns:
        List of klines with Decimal values, or None if request fails
    """
    try:
        klines = await client.get_klines(symbol, interval, limit)
        if klines is None:
            logger.warning(f"fetch_klines failed for {symbol} {interval}")
            return None
        return klines
    except Exception as e:
        logger.error(f"fetch_klines exception: {e}")
        return None


async def fetch_min_notional(
    client: BinanceClient,
    symbol: str
) -> Decimal:
    """
    Fetch min_notional from exchangeInfo.
    Falls back to MIN_NOTIONAL_FALLBACK if not found or error.

    Args:
        client: BinanceClient instance
        symbol: Trading pair

    Returns:
        Minimum notional as Decimal (USDT)
    """
    try:
        filters = await client.get_symbol_filters(symbol)
        if filters and "min_notional" in filters:
            return filters["min_notional"]
    except Exception as e:
        logger.warning(f"fetch_min_notional exception for {symbol}: {e}")

    logger.info(f"Using fallback min_notional for {symbol}: {MIN_NOTIONAL_FALLBACK}")
    return MIN_NOTIONAL_FALLBACK


async def derive_interval(
    client: BinanceClient,
    symbol: str
) -> Tuple[str, Dict[str, Decimal], bool, str]:
    """
    Select the flattest interval (lowest Efficiency Ratio).

    For each interval in CANDIDATE_INTERVALS:
        ER = abs(close[-1] - close[0]) / sum(abs(close[i] - close[i-1]))

    Returns:
        (selected_interval, er_per_interval_dict, grid_viable, reason)

    If ER_min > ER_MAX_TRADEABLE, returns grid_viable=False.
    """
    ers = {}
    detailed_reasons = []

    for interval in CANDIDATE_INTERVALS:
        klines = await fetch_klines(client, symbol, interval, limit=ER_LOOKBACK + 1)
        if not klines or len(klines) < 2:
            logger.warning(f"Not enough klines for {symbol} {interval}")
            ers[interval] = Decimal("1.0")  # Default to "trending"
            continue

        closes = [k["close"] for k in klines]

        # ER = abs(first - last) / sum(abs changes)
        price_change = abs(closes[-1] - closes[0])
        total_change = sum(abs(closes[i] - closes[i-1]) for i in range(1, len(closes)))

        if total_change == 0:
            er = Decimal("1.0")
        else:
            er = price_change / total_change

        ers[interval] = er
        detailed_reasons.append(f"{interval}={er:.4f}")

    selected = min(ers.items(), key=lambda x: x[1])
    selected_interval = selected[0]
    min_er = selected[1]

    reason = f"ER {selected_interval}={min_er:.4f} (selected, lowest) vs " + ", ".join(detailed_reasons)

    # Check if all timeframes are too trendy
    if min_er > ER_MAX_TRADEABLE:
        logger.info(f"Market in trend on all timeframes: min ER={min_er:.4f} > {ER_MAX_TRADEABLE}")
        return selected_interval, ers, False, f"Market trending: all ER > {ER_MAX_TRADEABLE}"

    return selected_interval, ers, True, reason


async def derive_multiplier(
    client: BinanceClient,
    symbol: str,
    selected_interval: str,
    atr: Decimal
) -> Tuple[Decimal, str]:
    """
    Calculate multiplier from real price range vs ATR.

    multiplier = range_real / (2 * atr)

    Clamp to MULTIPLIER_BOUNDS and round to 1 decimal.

    Returns:
        (multiplier, reason)
    """
    klines = await fetch_klines(client, symbol, selected_interval, limit=RANGE_LOOKBACK + 1)
    if not klines or len(klines) < 2:
        # Fallback to 2.0 if can't compute
        logger.warning(f"Not enough klines for multiplier calculation, using 2.0")
        return Decimal("2.0"), "Fallback (insufficient data)"

    highs = [k["high"] for k in klines]
    lows = [k["low"] for k in klines]

    range_real = max(highs) - min(lows)
    multiplier_raw = range_real / (Decimal("2") * atr) if atr > 0 else Decimal("2.0")

    # Clamp to bounds
    min_mult, max_mult = MULTIPLIER_BOUNDS
    multiplier = max(min_mult, min(max_mult, multiplier_raw))

    # Round to 1 decimal
    multiplier = multiplier.quantize(Decimal("0.1"), rounding=ROUND_DOWN)

    reason = f"Range {range_real:.2f} / (2*ATR) = {multiplier_raw:.2f}, clamped to {multiplier}"
    return multiplier, reason


async def derive_levels(
    price: Decimal,
    atr: Decimal,
    multiplier: Decimal
) -> Tuple[int, str]:
    """
    Calculate number of levels based on grid range and fee coverage.

    range_grid = 2 * multiplier * atr
    step_min_pct = FEE_ROUNDTRIP * FEE_MARGIN_FACTOR
    levels = floor(range_grid / (price * step_min_pct))

    Clamp to LEVELS_BOUNDS.

    Returns:
        (levels, reason)
    """
    range_grid = Decimal("2") * multiplier * atr
    step_min_pct = FEE_ROUNDTRIP * FEE_MARGIN_FACTOR

    denominator = price * step_min_pct
    if denominator <= 0:
        logger.warning(f"Invalid denominator for levels calculation")
        levels = LEVELS_BOUNDS[0]
        return levels, f"Fallback to min levels due to invalid calculation"

    levels_raw = int(range_grid / denominator)

    # Clamp
    min_lvl, max_lvl = LEVELS_BOUNDS
    levels = max(min_lvl, min(max_lvl, levels_raw))

    reason = f"Range {range_grid:.2f} / (price {price:.2f} * step_min {step_min_pct}) = {levels_raw} levels, clamped to {levels}"
    return levels, reason


def derive_leverage(atr_pct: float) -> int:
    """
    Derive leverage from the pair's volatility (ATR as fraction of price).

    Walks LEVERAGE_BY_VOLATILITY tiers (ordered by max_atr_pct ascending)
    and clamps the result to LEVERAGE_BOUNDS.
    """
    for tier in LEVERAGE_BY_VOLATILITY:
        if atr_pct <= tier["max_atr_pct"]:
            lev = tier["leverage"]
            return max(LEVERAGE_BOUNDS[0], min(lev, LEVERAGE_BOUNDS[1]))
    return LEVERAGE_BOUNDS[0]


def derive_quantity_per_order(
    min_notional: Decimal,
    lower_price: Decimal,
    step_size: Decimal
) -> Tuple[Decimal, str]:
    """
    Derive the exact order quantity so that its notional clears min_notional
    at the LOWEST grid level, rounded UP to the symbol's step_size.

    This is computed here (not in the orchestrator/workflow) because rounding
    to step_size can silently halve the notional on symbols with coarse steps
    (e.g. UNIUSDT step=1) — the quantity must be authoritative.
    """
    qty_raw = (min_notional * CAPITAL_BUFFER) / lower_price
    if step_size > 0:
        qty = (qty_raw / step_size).to_integral_value(rounding=ROUND_UP) * step_size
    else:
        qty = qty_raw
    reason = (f"min_notional {min_notional} * {CAPITAL_BUFFER} buffer / lower {lower_price:.6f} "
              f"= {qty_raw:.6f}, redondeado ARRIBA a step {step_size} -> {qty}")
    return qty, reason


def derive_risk_pct_and_levels(
    levels: int,
    quantity_per_order: Decimal,
    current_price: Decimal,
    balance: Decimal,
    leverage: int = 1
) -> Tuple[Decimal, int, bool, str]:
    """
    Calculate risk_pct (margin committed as fraction of balance) from the
    ACTUAL quantity per order. If it exceeds MAX_RISK_PCT, reduce levels
    until it fits.

    margin_per_level = quantity * current_price / leverage
    risk_pct = levels * margin_per_level / balance

    If risk_pct > MAX_RISK_PCT: reduce levels by 1, recalculate, repeat.
    If no valid levels: return viable=False.

    Returns:
        (risk_pct, levels_final, viable, reason)
    """
    min_lvl, max_lvl = LEVELS_BOUNDS
    current_levels = levels
    lev = Decimal(max(leverage, 1))
    margin_per_level = quantity_per_order * current_price / lev

    while current_levels >= min_lvl:
        risk_pct = Decimal(current_levels) * margin_per_level / balance

        if risk_pct <= MAX_RISK_PCT:
            # Fits
            risk_pct_rounded = risk_pct.quantize(Decimal("0.0001"), rounding=ROUND_DOWN)
            reason = (f"{current_levels} levels * (qty {quantity_per_order} * price {current_price:.6f} "
                      f"/ {lev}x leverage) / {balance} balance = {risk_pct_rounded}")
            return risk_pct_rounded, current_levels, True, reason

        # Doesn't fit, reduce
        current_levels -= 1

    # Even min levels doesn't fit
    reason = (f"Balance {balance} too low: even {min_lvl} levels * (qty {quantity_per_order} * "
              f"price {current_price:.6f} / {lev}x leverage) exceeds {MAX_RISK_PCT} risk limit")
    return Decimal("0"), 0, False, reason


async def auto_derive_params(
    symbol: str,
    balance: Decimal,
    client: Optional[BinanceClient] = None
) -> Dict[str, Any]:
    """
    Main orchestration function: derive all grid parameters from symbol + balance.

    Returns dict with:
    - symbol, current_price, grid_viable
    - params (if viable): levels, risk_pct, atr_multiplier, klines_interval, atr_period
    - reasoning (detailed for each derivation)
    - policy (the config constants used)

    If grid_viable=False, params is None and reasoning includes "no_viable".
    """
    if balance <= 0:
        raise ValueError("balance must be > 0")

    # Initialize client if not provided
    if client is None:
        from app.services.grid_service import GridService
        grid_service = GridService()
        client = grid_service.binance

    reasoning = {}

    # Step 1: Get market data and min_notional
    klines = await fetch_klines(client, symbol, "4h", limit=ATR_PERIOD + 1)
    if not klines:
        raise ValueError(f"Symbol {symbol} not found or network error")

    current_price = klines[-1]["close"]
    min_notional = await fetch_min_notional(client, symbol)

    # Step 2: Calculate ATR
    try:
        atr = calculate_atr(klines, ATR_PERIOD)
    except Exception as e:
        logger.error(f"calculate_atr failed: {e}")
        raise ValueError(f"Could not calculate ATR for {symbol}")

    # Step 2b: Derive leverage from volatility (ATR as % of price)
    atr_pct = float(atr / current_price) if current_price > 0 else 0.0
    leverage = derive_leverage(atr_pct)
    reasoning["leverage"] = (
        f"ATR%={atr_pct * 100:.2f}% -> tier "
        f"{next((t['max_atr_pct'] for t in LEVERAGE_BY_VOLATILITY if atr_pct <= t['max_atr_pct']), 'min')} "
        f"-> leverage {leverage}x, dentro de bounds [{LEVERAGE_BOUNDS[0]},{LEVERAGE_BOUNDS[1]}]"
    )

    # Step 3: Derive interval (flattest timeframe)
    interval, ers_dict, interval_viable, interval_reason = await derive_interval(client, symbol)
    reasoning["klines_interval"] = interval_reason

    if not interval_viable:
        # Market is trending on all timeframes
        return {
            "symbol": symbol,
            "current_price": float(current_price),
            "grid_viable": False,
            "params": None,
            "reasoning": {
                "no_viable": interval_reason,
                "klines_interval": interval_reason
            },
            "policy": {
                "fee_roundtrip": float(FEE_ROUNDTRIP),
                "fee_margin_factor": float(FEE_MARGIN_FACTOR),
                "max_risk_pct": float(MAX_RISK_PCT),
                "multiplier_bounds": [float(MULTIPLIER_BOUNDS[0]), float(MULTIPLIER_BOUNDS[1])]
            }
        }

    # Step 4: Derive multiplier
    multiplier, multiplier_reason = await derive_multiplier(client, symbol, interval, atr)
    reasoning["atr_multiplier"] = multiplier_reason

    # Guard: lower bound (price - multiplier * atr) must stay > 0.
    # With extreme ATR (noisy testnet klines / hypervolatile pairs) the grid
    # would be created with a negative lower_price and rejected downstream.
    if atr > 0 and multiplier * atr >= current_price:
        max_mult_for_price = (current_price / atr) * Decimal("0.95")
        min_mult, _ = MULTIPLIER_BOUNDS
        if max_mult_for_price < min_mult:
            no_viable_reason = (
                f"ATR {atr:.6f} demasiado alto vs precio {current_price:.6f}: "
                f"lower_price <= 0 incluso con multiplier mínimo {min_mult}"
            )
            return {
                "symbol": symbol,
                "current_price": float(current_price),
                "grid_viable": False,
                "params": None,
                "reasoning": {"no_viable": no_viable_reason, **reasoning},
                "policy": {
                    "fee_roundtrip": float(FEE_ROUNDTRIP),
                    "fee_margin_factor": float(FEE_MARGIN_FACTOR),
                    "max_risk_pct": float(MAX_RISK_PCT),
                    "multiplier_bounds": [float(MULTIPLIER_BOUNDS[0]), float(MULTIPLIER_BOUNDS[1])]
                }
            }
        multiplier = max_mult_for_price.quantize(Decimal("0.1"), rounding=ROUND_DOWN)
        reasoning["atr_multiplier"] += (
            f" | ajustado a {multiplier} para mantener lower_price > 0 (ATR alto vs precio)"
        )

    # Step 5: Derive levels (initial)
    levels_initial, levels_reason = await derive_levels(current_price, atr, multiplier)
    reasoning["levels"] = levels_reason

    # Step 6: Freeze the grid bounds NOW and derive the authoritative
    # quantity_per_order against them. grid_service.create_grid() must reuse
    # these exact bounds (passed explicitly) instead of recomputing its own
    # ATR from fresh klines - live data drift between this call and grid
    # creation was silently invalidating the notional-safety margin.
    lower_price = current_price - multiplier * atr
    upper_price = current_price + multiplier * atr
    filters = await client.get_symbol_filters(symbol)
    step_size = filters["step_size"] if filters else Decimal("0.001")
    quantity_per_order, qty_reason = derive_quantity_per_order(
        min_notional, lower_price, step_size
    )
    reasoning["quantity_per_order"] = qty_reason

    # Step 7: Derive risk_pct from the actual qty, reducing levels if necessary
    risk_pct, levels_final, risk_viable, risk_reason = derive_risk_pct_and_levels(
        levels_initial, quantity_per_order, current_price, balance, leverage
    )
    reasoning["risk_pct"] = risk_reason

    if not risk_viable:
        # Balance too low
        return {
            "symbol": symbol,
            "current_price": float(current_price),
            "grid_viable": False,
            "params": None,
            "reasoning": {
                "no_viable": risk_reason,
                **reasoning
            },
            "policy": {
                "fee_roundtrip": float(FEE_ROUNDTRIP),
                "fee_margin_factor": float(FEE_MARGIN_FACTOR),
                "max_risk_pct": float(MAX_RISK_PCT),
                "multiplier_bounds": [float(MULTIPLIER_BOUNDS[0]), float(MULTIPLIER_BOUNDS[1])]
            }
        }

    # All viable
    return {
        "symbol": symbol,
        "current_price": float(current_price),
        "grid_viable": True,
        "params": {
            "levels": levels_final,
            "risk_pct": float(risk_pct),
            "quantity_per_order": float(quantity_per_order),
            "lower_price": float(lower_price),
            "upper_price": float(upper_price),
            "atr_multiplier": float(multiplier),
            "klines_interval": interval,
            "atr_period": ATR_PERIOD,
            "leverage": leverage
        },
        "reasoning": reasoning,
        "policy": {
            "fee_roundtrip": float(FEE_ROUNDTRIP),
            "fee_margin_factor": float(FEE_MARGIN_FACTOR),
            "max_risk_pct": float(MAX_RISK_PCT),
            "multiplier_bounds": [float(MULTIPLIER_BOUNDS[0]), float(MULTIPLIER_BOUNDS[1])]
        }
    }
