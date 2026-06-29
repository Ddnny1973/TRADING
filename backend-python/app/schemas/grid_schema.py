"""
Pydantic schemas for request/response validation
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class GridRequest(BaseModel):
    """Schema for grid creation request"""

    symbol: str = Field(..., description="Trading pair (e.g., BTCUSDT)")
    lower_price: float = Field(..., description="Grid lower price limit")
    upper_price: float = Field(..., description="Grid upper price limit")
    levels: int = Field(default=10, description="Number of grid levels")
    grid_type: str = Field(default="GEOMETRIC", description="Grid type: GEOMETRIC or ARITHMETIC")
    quantity_per_order: float = Field(..., description="Order quantity placed at each grid level")

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
