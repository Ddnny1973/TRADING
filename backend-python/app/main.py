"""
FastAPI Application - Grid Trading Hybrid Backend
Main entry point for the trading engine microservice
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

# Import configuration and services
from app.core.config import settings
from app.database.connection import init_db

# Create FastAPI app
app = FastAPI(
    title="Grid Trading Hybrid API",
    description="Backend microservice for autonomous grid trading execution",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)


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
# GRID TRADING ENDPOINTS (TO BE IMPLEMENTED)
# ==========================================

# TODO: Implement grid creation endpoint
# TODO: Implement grid status endpoint
# TODO: Implement grid execution endpoint
# TODO: Implement order management endpoints


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
