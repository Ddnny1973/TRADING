"""
FastAPI Application - Grid Trading Hybrid Backend
Main entry point for the trading engine microservice
"""

from typing import List, Optional
import logging
import time

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

# Import configuration and services
from app.core.config import settings
from app.database.connection import init_db
from app.schemas.grid_schema import GridRequest, GridResponse, GridDetailResponse, GridPnlResponse, GridCloseCheckResponse, MarketAnalysisResponse, AutoParamsResponse, AutoParamsParams
from app.auto_params import auto_derive_params
from app.config_auto_params import MAX_RISK_PCT, LEVELS_BOUNDS, LEVERAGE_BOUNDS, SYMBOL_CACHE_TTL_SECONDS
from app.pair_selector import select_best_pair_cached, _balance_bucket
from app.services.grid_service import GridService
from app.services.indicators import calculate_atr, calculate_grid_bounds, calculate_position_size
from decimal import Decimal, ROUND_UP


class GridRequestWithLeverage(GridRequest):
    """GridRequest + dynamic leverage derived by /auto-params"""
    leverage: Optional[int] = None


class AutoParamsParamsV2(AutoParamsParams):
    """AutoParamsParams + volatility-derived leverage + authoritative qty/bounds"""
    leverage: int
    quantity_per_order: float = 0.0
    lower_price: float = 0.0
    upper_price: float = 0.0


class AutoParamsResponseV2(AutoParamsResponse):
    """AutoParamsResponse + automatic symbol selection metadata"""
    params: Optional[AutoParamsParamsV2] = None
    symbol_selection: dict = {}
    warnings: List[str] = []
    code_version: str = ""

# Configure logging (Paso 13)
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("grid_trading")

grid_service = GridService()

# Marcador de versión del código: visible en /health y /auto-params para
# verificar remotamente qué build está corriendo (sin acceso a logs)
CODE_VERSION = "v1.3.0-frozen-grid-bounds"

# Cache de respuestas completas de /auto-params: (balance_bucket, symbol) → (ts, result)
_auto_params_cache: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events
    """
    # Startup
    logger.info("🚀 Starting Grid Trading Backend...")
    init_db()
    server_time = await grid_service.binance.time_sync.sync_time()
    if server_time:
        logger.info(f"✅ Time synced with Binance. Offset: {grid_service.binance.time_sync.time_offset}ms")
    else:
        logger.warning("⚠️  Could not sync time with Binance. Using local clock.")
    logger.info(f"Config: MAX_CONCURRENT_GRIDS={settings.MAX_CONCURRENT_GRIDS}, "
                f"DEFAULT_RISK_PCT={settings.DEFAULT_RISK_PCT}, "
                f"DEFAULT_LEVERAGE={settings.DEFAULT_LEVERAGE}")
    yield
    # Shutdown
    logger.info("🛑 Shutting down Grid Trading Backend...")
    await grid_service.binance.close_session()


app = FastAPI(
    title="Grid Trading Hybrid API",
    description="Backend microservice for autonomous grid trading execution",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    lifespan=lifespan,
    servers=[{"url": "/", "description": "Current server"}]
)


# ==========================================
# HEALTH CHECK ENDPOINTS
# ==========================================

@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint for Docker container"""
    # Quick status check
    binance_ok = grid_service.binance.time_sync.time_offset is not None
    return {
        "status": "healthy",
        "service": "grid-trading-backend",
        "version": "0.1.0",
        "code_version": CODE_VERSION,
        "binance_synced": binance_ok,
        "time_offset_ms": grid_service.binance.time_sync.time_offset or "unknown"
    }


@app.get("/", tags=["Info"])
async def root():
    """Root endpoint with API information and system status"""
    running_grids = grid_service.list_grids(status="RUNNING")
    return {
        "service": "Grid Trading Hybrid - Backend",
        "status": "ready",
        "api_version": "v1",
        "docs": "/api/docs",
        "running_grids": len(running_grids),
        "max_concurrent_grids": settings.MAX_CONCURRENT_GRIDS,
        "default_risk_pct": settings.DEFAULT_RISK_PCT,
        "default_leverage": settings.DEFAULT_LEVERAGE,
    }


# ==========================================
# MARKET ANALYSIS ENDPOINTS (read-only)
# ==========================================

@app.get("/api/v1/market-analysis/{symbol}", response_model=MarketAnalysisResponse, tags=["Analysis"])
async def analyze_market(symbol: str, atr_period: int = 14, atr_multiplier: float = 2.0,
                        klines_interval: str = "4h", risk_pct: float = None, levels: int = None):
    """
    Analyze market conditions for a symbol without placing any orders.

    Returns current price, ATR, and suggested grid bounds. If risk_pct and levels
    are provided, also calculates suggested_quantity_per_order based on account balance.

    Args:
        symbol: Trading pair (e.g., BTCUSDT)
        atr_period: Number of True Range periods for ATR (default 14)
        atr_multiplier: ATR multiplier for grid width (default 2.0)
        klines_interval: Kline interval for ATR calculation (default "4h")
        risk_pct: Risk as fraction (0.01 = 1%). If provided with levels,
                 calculates quantity_per_order. Omit to skip.
        levels: Number of grid levels. Required if risk_pct is provided.

    Returns:
        MarketAnalysisResponse with current price, ATR, bounds,
        and optionally suggested_quantity_per_order.

    Raises:
        ValueError (400): if current price/klines cannot be fetched, or if
                         risk_pct provided without levels (or vice versa)
    """
    price_data = await grid_service.binance.get_mark_price(symbol)
    if not price_data or "price" not in price_data:
        raise ValueError(f"Could not fetch current price for {symbol}")
    current_price = Decimal(str(price_data["price"]))

    klines = await grid_service.binance.get_klines(symbol, interval=klines_interval, limit=atr_period + 1)
    if not klines:
        raise ValueError(f"Could not fetch klines for {symbol} to compute ATR")

    atr = calculate_atr(klines, period=atr_period)
    bounds = calculate_grid_bounds(current_price, atr, Decimal(str(atr_multiplier)))

    response = {
        "symbol": symbol,
        "current_price": float(current_price),
        "atr": float(atr),
        "atr_period": atr_period,
        "atr_multiplier": atr_multiplier,
        "klines_interval": klines_interval,
        "suggested_lower_price": float(bounds["lower_price"]),
        "suggested_upper_price": float(bounds["upper_price"]),
        "suggested_range": float(bounds["upper_price"] - bounds["lower_price"]),
    }

    # Calculate suggested quantity if levels provided (risk_pct has default)
    if levels is not None:
        effective_risk_pct = risk_pct if risk_pct is not None else settings.DEFAULT_RISK_PCT

        balance_data = await grid_service.binance.get_account_balance()
        if not balance_data or "balances" not in balance_data:
            raise ValueError(f"Could not fetch account balance for {symbol}")

        # Find USDT balance
        usdt_balance = None
        for balance_item in balance_data["balances"]:
            if balance_item.get("asset") == "USDT":
                usdt_balance = Decimal(str(balance_item.get("availableBalance", 0)))
                break

        if usdt_balance is None or usdt_balance <= 0:
            raise ValueError("No available USDT balance in account")

        # Calculate allocated capital and suggested SL
        capital_asignado = usdt_balance * Decimal(str(effective_risk_pct))
        suggested_sl = capital_asignado * Decimal("0.5")  # SL at 50% of allocated capital

        quantity = calculate_position_size(
            usdt_balance,
            Decimal(str(effective_risk_pct)),
            levels,
            Decimal(str(bounds["lower_price"])),
            Decimal(str(bounds["upper_price"]))
        )
        response["suggested_quantity_per_order"] = float(quantity)
        response["allocated_capital"] = float(capital_asignado)
        response["suggested_stop_loss"] = float(suggested_sl)

        # Viability check against exchange minimums (min_notional + step_size).
        # Deterministic and transparent: the endpoint never inflates the
        # suggested quantity; it reports the minimum viable one so the
        # orchestrator (WF1) can decide/notify explicitly.
        filters = await grid_service.binance.get_symbol_filters(symbol)
        # Fallback to known Binance Futures minimums if exchange info unavailable.
        min_notional = filters["min_notional"] if filters else Decimal("50")
        step = filters["step_size"] if filters else Decimal("0.001")

        lower_bound = Decimal(str(bounds["lower_price"]))
        upper_bound = Decimal(str(bounds["upper_price"]))
        # Smallest step-multiple whose notional at the lowest grid level
        # still clears min_notional (worst case = lower bound).
        steps_needed = (min_notional / lower_bound / step).to_integral_value(rounding=ROUND_UP)
        min_viable_qty = max(steps_needed * step, step)
        avg_price = (lower_bound + upper_bound) / 2
        required_risk_pct = (min_viable_qty * Decimal(levels) * avg_price) / usdt_balance
        response["min_viable_quantity"] = float(min_viable_qty)
        response["grid_viable"] = quantity >= min_viable_qty
        response["required_risk_pct"] = float(required_risk_pct)

    return response


# ==========================================
# GRID TRADING ENDPOINTS
# ==========================================

@app.post("/api/v1/grids", response_model=GridDetailResponse, tags=["Grids"])
async def create_grid(request: GridRequestWithLeverage):
    """
    Calculate grid levels, place orders on Binance and persist the grid.

    Omit lower_price and upper_price together to have them calculated
    automatically from ATR (atr_period / atr_multiplier / klines_interval).
    """
    grid = await grid_service.create_grid(
        leverage=request.leverage,
        symbol=request.symbol,
        levels=request.levels,
        grid_type=request.grid_type,
        quantity_per_order=request.quantity_per_order,
        lower_price=request.lower_price,
        upper_price=request.upper_price,
        atr_period=request.atr_period,
        atr_multiplier=request.atr_multiplier,
        klines_interval=request.klines_interval,
        stop_loss=request.stop_loss,
        take_profit=request.take_profit,
        max_duration_hours=request.max_duration_hours,
    )
    return grid


@app.get("/api/v1/grids", response_model=List[GridResponse], tags=["Grids"])
async def list_grids(status: str = None):
    """
    List all grids, optionally filtered by status.

    Query params:
        status (optional): Filter by status — RUNNING, CANCELED, etc.
                          Omit to list all grids regardless of status.

    Returns:
        List of GridResponse (grid info without orders).
    """
    return grid_service.list_grids(status=status)


@app.get("/api/v1/grids/{grid_id}", response_model=GridDetailResponse, tags=["Grids"])
async def get_grid(grid_id: str):
    """Get grid details including its orders"""
    grid = grid_service.get_grid(grid_id)
    if not grid:
        raise HTTPException(status_code=404, detail="Grid not found")
    return grid


@app.delete("/api/v1/grids/{grid_id}", response_model=GridDetailResponse, tags=["Grids"])
async def cancel_grid(grid_id: str):
    """Cancel all open orders for a grid and stop it"""
    grid = await grid_service.cancel_grid(grid_id)
    if not grid:
        raise HTTPException(status_code=404, detail="Grid not found")
    return grid


@app.post("/api/v1/grids/{grid_id}/refresh", response_model=GridDetailResponse, tags=["Grids"])
async def refresh_grid_orders(grid_id: str):
    """
    Refresh grid order status from Binance and replenish filled orders.

    Steps:
    1. Sync order status with Binance (fills, cancellations, etc.)
    2. Replenish filled orders: for each FILLED order, place the opposite
       order at the adjacent grid level (if available)

    Intended to be called periodically by the external orchestrator
    (Workflow 2 every 15 min). Handles Fase 3 grid cycling.
    """
    grid = await grid_service.refresh_order_status(grid_id)
    if not grid:
        raise HTTPException(status_code=404, detail="Grid not found")

    # Replenish filled orders to create continuous grid cycles
    replenished = await grid_service.replenish_filled_orders(grid_id)
    if replenished > 0:
        grid = grid_service.get_grid(grid_id)

    return grid


@app.get("/api/v1/grids/{grid_id}/pnl", response_model=GridPnlResponse, tags=["Grids"])
async def get_grid_pnl(grid_id: str):
    """
    Compute realized/unrealized PnL for a grid from its current local order
    state. Call POST /api/v1/grids/{grid_id}/refresh first to make sure
    fills are up to date.
    """
    pnl = await grid_service.get_grid_pnl(grid_id)
    if not pnl:
        raise HTTPException(status_code=404, detail="Grid not found")
    return pnl


@app.post("/api/v1/grids/{grid_id}/check-close", response_model=GridCloseCheckResponse, tags=["Grids"])
async def check_close_grid(grid_id: str):
    """
    Compare current PnL against the grid's stop_loss/take_profit and cancel
    it automatically if triggered. Call POST .../refresh first if the
    decision needs up to date fills - this endpoint does not refresh on its
    own. Intended to be polled periodically by the external orchestrator,
    same as .../refresh (see roadmap Fase 3.3).
    """
    result = await grid_service.close_grid_if_triggered(grid_id)
    if not result:
        raise HTTPException(status_code=404, detail="Grid not found")
    return result


# ==========================================
# AUTO PARAMETER DERIVATION
# ==========================================

@app.get("/auto-params", response_model=AutoParamsResponseV2, tags=["Auto Derivation"])
async def get_auto_params(balance: float, symbol: Optional[str] = None):
    """
    Auto-derive grid parameters from balance (symbol optional).

    If symbol is omitted, the best pair is selected automatically by scoring
    the USDT-M perpetual universe (ER, volume, ATR%, funding) — see
    app/pair_selector.py. Pass symbol to override manually.

    Derivation process:
    1. Select pair (auto scoring or manual override)
    2. Fetch market data (klines, min_notional)
    3. Calculate ATR(14) and derive leverage from ATR%
    4. Select flattest interval (lowest Efficiency Ratio)
    5. Derive multiplier from real price range
    6. Derive levels based on fee coverage
    7. Derive risk_pct, reducing levels if needed to fit within MAX_RISK_PCT

    Example:
        GET /auto-params?balance=5200            (auto selection)
        GET /auto-params?balance=5200&symbol=BTCUSDT  (manual override)
    """
    if balance <= 0:
        raise HTTPException(status_code=422, detail="balance debe ser mayor a 0")
    if balance < 10:
        raise HTTPException(status_code=422, detail=f"balance mínimo es 10 USDT (recibido: {balance})")
    if balance > 1_000_000:
        raise HTTPException(status_code=422, detail=f"balance máximo es 1,000,000 USDT (recibido: {balance})")

    warnings = []
    if balance < 500:
        warnings.append("Balance < 500 USDT: pares viables pueden ser limitados")

    # Full-response cache (same TTL/bucket as the pair selector) so repeated
    # calls with the same balance skip re-deriving ATR/ER against Binance
    cache_key = (_balance_bucket(balance), symbol or "")
    cached = _auto_params_cache.get(cache_key)
    if cached and time.time() - cached[0] < SYMBOL_CACHE_TTL_SECONDS:
        return cached[1]

    try:
        if symbol:
            chosen_symbol = symbol
            selection = None
            selection_meta = {"method": "manual", "selection_skipped": True}
        else:
            selection = await select_best_pair_cached(
                balance=balance,
                max_risk_pct=float(MAX_RISK_PCT),
                leverage_max=LEVERAGE_BOUNDS[1],
                min_levels=LEVELS_BOUNDS[0],
                client=grid_service.binance
            )
            chosen_symbol = selection["selected"]["symbol"]
            selection_meta = {
                "method": "auto",
                "candidates_evaluated": selection["candidates_evaluated"],
                "candidates_passed_filters": selection["candidates_passed_filters"],
                "top_3": selection["top_3"],
                "selected_reason": (
                    f"Score {selection['selected']['score']:.2f}: "
                    f"ER={selection['selected']['er']:.2f}, "
                    f"vol={selection['selected']['volume_24h_usdt']/1e6:.0f}M USDT"
                )
            }

        result = await auto_derive_params(chosen_symbol, Decimal(str(balance)), client=grid_service.binance)
        result["symbol_selection"] = selection_meta
        result["warnings"] = warnings
        result["code_version"] = CODE_VERSION
        if selection and len(selection["top_3"]) > 1:
            runner_up = selection["top_3"][1]
            result["reasoning"]["symbol"] = (
                f"{chosen_symbol} elegido: score {selection['selected']['score']:.2f} "
                f"vs {runner_up['symbol']} {runner_up['score']:.2f}"
            )
        elif selection:
            result["reasoning"]["symbol"] = (
                f"{chosen_symbol} elegido: score {selection['selected']['score']:.2f} (único candidato puntuado)"
            )
        _auto_params_cache[cache_key] = (time.time(), result)
        return result
    except ValueError as e:
        # Symbol not found or invalid input
        if "not found" in str(e).lower() or "network" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        else:
            raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"auto_derive_params failed: {e}")
        raise HTTPException(status_code=502, detail=f"Binance API error: {str(e)}")


# ==========================================
# ERROR HANDLERS
# ==========================================

@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    """Handle ValueError exceptions"""
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc)}
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Handle unexpected exceptions"""
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=settings.FASTAPI_HOST,
        port=settings.FASTAPI_PORT,
        reload=settings.DEBUG_MODE
    )
