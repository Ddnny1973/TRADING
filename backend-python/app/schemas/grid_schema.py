"""
Pydantic schemas for request/response validation
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class GridRequest(BaseModel):
    """Schema for grid creation request"""

    symbol: str = Field(..., description="Trading pair (e.g., BTCUSDT)")
    lower_price: Optional[float] = Field(
        default=None,
        description="Grid lower price limit. Omit together with upper_price to "
                     "calculate both automatically from ATR."
    )
    upper_price: Optional[float] = Field(
        default=None,
        description="Grid upper price limit. Omit together with lower_price to "
                     "calculate both automatically from ATR."
    )
    levels: int = Field(default=10, description="Number of grid levels")
    grid_type: str = Field(default="GEOMETRIC", description="Grid type: GEOMETRIC or ARITHMETIC")
    quantity_per_order: float = Field(..., description="Order quantity placed at each grid level")
    stop_loss: Optional[float] = Field(
        default=None,
        description="Quote-currency PnL threshold (positive number) - grid auto-closes when "
                     "total_pnl <= -stop_loss. Omit to disable."
    )
    take_profit: Optional[float] = Field(
        default=None,
        description="Quote-currency PnL threshold (positive number) - grid auto-closes when "
                     "total_pnl >= take_profit. Omit to disable."
    )
    atr_period: int = Field(
        default=14,
        description="Number of True Range values used for ATR when bounds are calculated automatically"
    )
    atr_multiplier: float = Field(
        default=2.0,
        description="ATR multiplier controlling the width of automatically-calculated bounds"
    )
    klines_interval: str = Field(
        default="4h",
        description="Kline interval used for automatic ATR calculation (e.g. 4h, 1h, 1d)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "symbol": "BTCUSDT",
                "lower_price": 40000.0,
                "upper_price": 45000.0,
                "levels": 10,
                "grid_type": "GEOMETRIC",
                "quantity_per_order": 0.001
            }
        }


class GridResponse(BaseModel):
    """Schema for grid response"""
    
    id: str
    symbol: str
    lower_price: float
    upper_price: float
    levels: int
    status: str
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


class OrderResponse(BaseModel):
    """Schema for order response"""

    id: str
    grid_id: str
    price: float
    quantity: float
    side: str
    type: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class GridDetailResponse(GridResponse):
    """Schema for grid response including its orders"""

    orders: list[OrderResponse] = []


class GridPnlResponse(BaseModel):
    """Schema for grid PnL response (output of calculate_grid_pnl)"""

    grid_id: str
    symbol: str
    current_price: float
    realized_pnl: float
    unrealized_pnl: float
    total_pnl: float
    net_position_qty: float
    filled_buy_qty: float
    filled_sell_qty: float


class GridCloseCheckResponse(BaseModel):
    """Schema for the response of check_sl_tp / close_grid_if_triggered"""

    triggered: Optional[str] = None
    grid: GridDetailResponse
