"""
Automatic trading pair selection for grid trading.

Fetches the USDT-M perpetual universe from Binance (public endpoints, no API
key), filters by capital viability / volume / spread, scores candidates by
Efficiency Ratio, volume, ATR%% and funding rate, and returns the best pair.
"""

import asyncio
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional
import logging

import aiohttp

from app.config_auto_params import (
    ATR_PERIOD, ER_MAX_TRADEABLE, CAPITAL_BUFFER,
    SYMBOL_SELECTION_WEIGHTS, MIN_VOLUME_24H_USDT, MAX_SPREAD_PCT,
    SYMBOL_CACHE_TTL_SECONDS, SYMBOL_BLACKLIST, MAX_CANDIDATES_TO_SCORE,
    MIN_NOTIONAL_FALLBACK
)
from app.services.binance_client import BinanceClient
from app.services.indicators import calculate_atr

logger = logging.getLogger(__name__)

_FAPI_BASE = "https://fapi.binance.com"
_TIMEOUT = aiohttp.ClientTimeout(total=15)


async def _get_json(path: str) -> Any:
    """GET a public fapi endpoint and return parsed JSON. Raises on failure."""
    url = f"{_FAPI_BASE}{path}"
    async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
        async with session.get(url) as r:
            if r.status != 200:
                text = await r.text()
                raise ValueError(f"GET {path} failed: HTTP {r.status} {text[:200]}")
            return await r.json()


async def fetch_universe() -> List[Dict[str, Any]]:
    """
    Fetch all tradeable USDT-M perpetual symbols from exchangeInfo.

    Returns:
        List of dicts with symbol + full filters, excluding SYMBOL_BLACKLIST.
    """
    info = await _get_json("/fapi/v1/exchangeInfo")
    universe = []
    for s in info.get("symbols", []):
        if (
            s.get("status") == "TRADING"
            and s.get("contractType") == "PERPETUAL"
            and s.get("quoteAsset") == "USDT"
            and s.get("symbol") not in SYMBOL_BLACKLIST
        ):
            universe.append({"symbol": s["symbol"], "filters": s.get("filters", [])})
    return universe


async def fetch_tickers_24h() -> Dict[str, Dict[str, float]]:
    """
    Fetch 24h ticker stats for all symbols.

    Returns:
        Dict keyed by symbol → {quoteVolume, lastPrice, bidPrice, askPrice}.
    """
    tickers = await _get_json("/fapi/v1/ticker/24hr")
    result = {}
    for t in tickers:
        try:
            result[t["symbol"]] = {
                "quoteVolume": float(t.get("quoteVolume", 0)),
                "lastPrice": float(t.get("lastPrice", 0)),
                "bidPrice": float(t.get("bidPrice", 0)),
                "askPrice": float(t.get("askPrice", 0)),
            }
        except (TypeError, ValueError):
            continue
    return result


async def fetch_funding_rates() -> Dict[str, float]:
    """
    Fetch current funding rates from premiumIndex.

    Returns:
        Dict keyed by symbol → lastFundingRate as float.
    """
    data = await _get_json("/fapi/v1/premiumIndex")
    result = {}
    for entry in data:
        try:
            result[entry["symbol"]] = float(entry.get("lastFundingRate") or 0)
        except (TypeError, ValueError):
            result[entry["symbol"]] = 0.0
    return result


def _min_notional_from_filters(filters: List[Dict[str, Any]]) -> float:
    """Extract min notional from a symbol's filters (NOTIONAL or MIN_NOTIONAL)."""
    for f in filters:
        if f.get("filterType") in ("NOTIONAL", "MIN_NOTIONAL"):
            raw = f.get("notional", f.get("minNotional"))
            if raw is not None:
                try:
                    return float(raw)
                except (TypeError, ValueError):
                    pass
    return float(MIN_NOTIONAL_FALLBACK)


def filter_by_capital(
    universe: List[Dict[str, Any]],
    tickers: Dict[str, Dict[str, float]],
    balance: float,
    max_risk_pct: float,
    leverage_max: int,
    min_levels: int,
) -> List[str]:
    """
    Filter pairs the account can actually trade with this balance.

    Includes a pair if:
    - minNotional <= balance * max_risk_pct * leverage_max / min_levels
    - quoteVolume >= MIN_VOLUME_24H_USDT
    - spread (ask - bid) / lastPrice <= MAX_SPREAD_PCT
    """
    capital_disponible = balance * max_risk_pct * leverage_max / min_levels
    passed = []
    for pair in universe:
        symbol = pair["symbol"]
        ticker = tickers.get(symbol)
        if not ticker or ticker["lastPrice"] <= 0:
            continue

        min_notional = _min_notional_from_filters(pair["filters"])
        if min_notional > capital_disponible:
            continue
        if ticker["quoteVolume"] < MIN_VOLUME_24H_USDT:
            continue

        spread_pct = (ticker["askPrice"] - ticker["bidPrice"]) / ticker["lastPrice"]
        if spread_pct > MAX_SPREAD_PCT:
            continue

        passed.append(symbol)
    return passed


def score_candidate(
    symbol: str,
    er: float,
    atr_pct: float,
    volume_24h: float,
    funding_rate: float,
    max_volume: float,
) -> float:
    """
    Score a candidate: higher = better for grid trading.

    Rewards low ER (ranging market), high volume, moderate ATR%% and
    near-zero funding rate, weighted by SYMBOL_SELECTION_WEIGHTS.
    """
    volume_norm = volume_24h / max_volume if max_volume > 0 else 0.0
    atr_norm = min(atr_pct / 0.05, 1.0)
    funding_norm = 1 - min(abs(funding_rate) / 0.001, 1.0)

    return (
        SYMBOL_SELECTION_WEIGHTS["er"] * (1 - er)
        + SYMBOL_SELECTION_WEIGHTS["volume"] * volume_norm
        + SYMBOL_SELECTION_WEIGHTS["atr_pct"] * atr_norm
        + SYMBOL_SELECTION_WEIGHTS["funding"] * funding_norm
    )


async def _evaluate_candidate(
    client: BinanceClient, symbol: str
) -> Optional[Dict[str, Any]]:
    """
    Compute ER (flattest interval) and ATR for one candidate.

    Reuses derive_interval / fetch_klines from auto_params so the metrics
    match exactly what /auto-params will derive later.
    Returns None if the pair is trending on all timeframes or data fails.
    """
    from app.auto_params import derive_interval, fetch_klines  # circular-safe

    try:
        interval, ers, viable, _reason = await derive_interval(client, symbol)
        min_er = min(ers.values())
        if min_er > ER_MAX_TRADEABLE:
            return None  # trending on every timeframe

        klines = await fetch_klines(client, symbol, interval, limit=ATR_PERIOD + 1)
        if not klines:
            return None
        atr = calculate_atr(klines, ATR_PERIOD)
        last_close = klines[-1]["close"]
        atr_pct = float(atr / last_close) if last_close > 0 else 0.0

        return {
            "symbol": symbol,
            "er": float(min_er),
            "best_interval": interval,
            "atr": float(atr),
            "atr_pct": atr_pct,
        }
    except Exception as e:
        logger.warning(f"pair_selector: evaluation failed for {symbol}: {e}")
        return None


async def select_best_pair(
    balance: float,
    max_risk_pct: float,
    leverage_max: int,
    min_levels: int,
    client: Optional[BinanceClient] = None,
) -> Dict[str, Any]:
    """
    Orchestrate the full selection: universe → filters → ER/ATR → scoring.

    Raises:
        ValueError: if fewer than 3 pairs pass the capital/volume/spread
                    filters, or none survives the ER tradeability check.
    """
    if client is None:
        client = BinanceClient()

    universe, tickers, funding = await asyncio.gather(
        fetch_universe(), fetch_tickers_24h(), fetch_funding_rates()
    )

    candidates = filter_by_capital(
        universe, tickers, balance, max_risk_pct, leverage_max, min_levels
    )
    if len(candidates) < 3:
        raise ValueError(f"Solo {len(candidates)} pares viables para balance={balance}")

    # Cap by 24h volume to bound the number of klines requests
    candidates = sorted(
        candidates, key=lambda s: tickers[s]["quoteVolume"], reverse=True
    )[:MAX_CANDIDATES_TO_SCORE]

    evaluations = await asyncio.gather(
        *[_evaluate_candidate(client, s) for s in candidates]
    )
    evaluated = [e for e in evaluations if e is not None]
    if not evaluated:
        raise ValueError(
            "Ningún candidato en rango lateral: todos con ER > "
            f"{ER_MAX_TRADEABLE} o sin datos"
        )

    max_volume = max(tickers[e["symbol"]]["quoteVolume"] for e in evaluated)
    for e in evaluated:
        e["volume_24h_usdt"] = tickers[e["symbol"]]["quoteVolume"]
        e["funding_rate"] = funding.get(e["symbol"], 0.0)
        e["score"] = score_candidate(
            e["symbol"], e["er"], e["atr_pct"],
            e["volume_24h_usdt"], e["funding_rate"], max_volume
        )

    evaluated.sort(key=lambda e: e["score"], reverse=True)

    # Final viability check: with the pair's ACTUAL derived leverage (2-5x,
    # not leverage_max), does min_levels * min_notional fit in max_risk_pct?
    # Without this, high-volume pairs like BTCUSDT win the score but get
    # rejected downstream by derive_risk_pct_and_levels (grid_viable=false).
    from app.auto_params import derive_leverage  # local import: avoid cycle

    min_notionals = {p["symbol"]: _min_notional_from_filters(p["filters"]) for p in universe}
    for e in evaluated:
        lev = derive_leverage(e["atr_pct"])
        margin_min = (
            min_levels * min_notionals.get(e["symbol"], float(MIN_NOTIONAL_FALLBACK))
            * float(CAPITAL_BUFFER) / lev
        )
        e["leverage"] = lev
        e["viable_for_balance"] = (margin_min / balance) <= max_risk_pct

    viable = [e for e in evaluated if e["viable_for_balance"]]
    if viable:
        evaluated = viable
    else:
        logger.warning(
            f"pair_selector: ningún candidato viable para balance={balance} "
            f"con su leverage derivado — se devuelve el mejor score igualmente"
        )
    best = evaluated[0]

    return {
        "selected": {
            "symbol": best["symbol"],
            "score": round(best["score"], 4),
            "er": round(best["er"], 4),
            "best_interval": best["best_interval"],
            "atr": best["atr"],
            "atr_pct": round(best["atr_pct"], 6),
            "volume_24h_usdt": best["volume_24h_usdt"],
            "funding_rate": best["funding_rate"],
        },
        "top_3": [
            {
                "symbol": e["symbol"],
                "score": round(e["score"], 4),
                "er": round(e["er"], 4),
                "volume_24h_m": round(e["volume_24h_usdt"] / 1e6),
            }
            for e in evaluated[:3]
        ],
        "candidates_evaluated": len(universe),
        "candidates_passed_filters": len(candidates),
    }


# ---------------------------------------------------------------------------
# In-memory cache with TTL, bucketed by balance (nearest 100 USDT)
# ---------------------------------------------------------------------------

_pair_cache: dict = {}  # key: balance_bucket → (timestamp, result)


def _balance_bucket(balance: float) -> int:
    return round(balance / 100) * 100


async def select_best_pair_cached(
    balance: float,
    max_risk_pct: float,
    leverage_max: int,
    min_levels: int,
    client: Optional[BinanceClient] = None,
) -> Dict[str, Any]:
    """Cached wrapper around select_best_pair (TTL = SYMBOL_CACHE_TTL_SECONDS)."""
    key = _balance_bucket(balance)
    if key in _pair_cache:
        ts, result = _pair_cache[key]
        if time.time() - ts < SYMBOL_CACHE_TTL_SECONDS:
            return result
    result = await select_best_pair(balance, max_risk_pct, leverage_max, min_levels, client=client)
    _pair_cache[key] = (time.time(), result)
    return result
