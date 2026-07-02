"""
FastAPI Application - Grid Trading Hybrid Backend
Main entry point for the trading engine microservice
"""

from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

# Import configuration and services
from app.core.config import settings
from app.database.connection import init_db
from app.schemas.grid_schema import GridRequest, GridResponse, GridDetailResponse, GridPnlResponse, GridCloseCheckResponse, MarketAnalysisResponse
from app.services.grid_service import GridService
from app.services.indicators import calculate_atr, calculate_grid_bounds, calculate_position_size
from decimal import Decimal

grid_service = GridService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events
    """
    # Startup
    print("🚀 Starting Grid Trading Backend...")
    init_db()
    server_time = await grid_service.binance.time_sync.sync_time()
    if server_time:
        print(f"✅ Time synced with Binance. Offset: {grid_service.binance.time_sync.time_offset}ms")
    else:
        print("⚠️  Could not sync time with Binance. Using local clock.")
    yield
    # Shutdown
    print("🛑 Shutting down Grid Trading Backend...")


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
    return {
        "status": "healthy",
        "service": "grid-trading-backend",
        "version": "0.1.0"
    }


@app.get("/", tags=["Info"])
async def root():
    """Root endpoint with API information"""
    return {
        "service": "Grid Trading Hybrid - Backend",
        "status": "ready",
        "api_version": "v1",
        "docs": "/api/docs"
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

        quantity = calculate_position_size(
            usdt_balance,
            Decimal(str(effective_risk_pct)),
            levels,
            Decimal(str(bounds["lower_price"])),
            Decimal(str(bounds["upper_price"]))
        )
        response["suggested_quantity_per_order"] = float(quantity)

    return response


# ==========================================
# GRID TRADING ENDPOINTS
# ==========================================

@app.post("/api/v1/grids", response_model=GridDetailResponse, tags=["Grids"])
async def create_grid(request: GridRequest):
    """
    Calculate grid levels, place orders on Binance and persist the grid.

    Omit lower_price and upper_price together to have them calculated
    automatically from ATR (atr_period / atr_multiplier / klines_interval).
    """
    grid = await grid_service.create_grid(
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
    Pull the latest order status from Binance for this grid's open orders
    and update local state. Intended to be called periodically by the
    external orchestrator (cron/workflow), not on an internal timer.
    """
    grid = await grid_service.refresh_order_status(grid_id)
    if not grid:
        raise HTTPException(status_code=404, detail="Grid not found")
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
