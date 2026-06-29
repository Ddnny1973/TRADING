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
from app.schemas.grid_schema import GridRequest, GridResponse, GridDetailResponse
from app.services.grid_service import GridService

grid_service = GridService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events
    """
    # Startup
    print("🚀 Starting Grid Trading Backend...")
    init_db()
    yield
    # Shutdown
    print("🛑 Shutting down Grid Trading Backend...")


app = FastAPI(
    title="Grid Trading Hybrid API",
    description="Backend microservice for autonomous grid trading execution",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    lifespan=lifespan
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
# GRID TRADING ENDPOINTS
# ==========================================

@app.post("/api/v1/grids", response_model=GridDetailResponse, tags=["Grids"])
async def create_grid(request: GridRequest):
    """Calculate grid levels, place orders on Binance and persist the grid"""
    grid = await grid_service.create_grid(
        symbol=request.symbol,
        lower_price=request.lower_price,
        upper_price=request.upper_price,
        levels=request.levels,
        grid_type=request.grid_type,
        quantity_per_order=request.quantity_per_order
    )
    return grid


@app.get("/api/v1/grids", response_model=List[GridResponse], tags=["Grids"])
async def list_grids():
    """List all grids"""
    return grid_service.list_grids()


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
