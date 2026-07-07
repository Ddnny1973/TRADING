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
    max_duration_hours: Optional[float] = Field(
        default=None,
        description="Maximum duration for the grid in hours. If omitted, calculated automatically "
                     "as 4x (klines_interval * atr_period). E.g., 4h interval + ATR(14) → ~56h history → 224h max_duration."
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
    max_duration_hours: Optional[float] = None
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


class MarketAnalysisResponse(BaseModel):
    """Schema for GET /api/v1/market-analysis/{symbol} - read-only market analysis"""

    symbol: str
    current_price: float
    atr: float
    atr_period: int
    atr_multiplier: float
    klines_interval: str
    suggested_lower_price: float
    suggested_upper_price: float
    suggested_range: float  # upper - lower
    suggested_quantity_per_order: Optional[float] = None  # Included if risk_pct param provided
    allocated_capital: Optional[float] = None  # Total capital assigned to grid (balance * risk_pct)
    suggested_stop_loss: Optional[float] = None  # Recommended SL = 50% of allocated_capital
    min_viable_quantity: Optional[float] = None  # Smallest qty meeting exchange min_notional/step_size
    grid_viable: Optional[bool] = None  # True if suggested_quantity_per_order >= min_viable_quantity
    required_risk_pct: Optional[float] = None  # risk_pct needed for the grid to be viable at current balance

    class Config:
        json_schema_extra = {
            "example": {
                "symbol": "BTCUSDT",
                "current_price": 42500.0,
                "atr": 200.0,
                "atr_period": 14,
                "atr_multiplier": 2.0,
                "klines_interval": "4h",
                "suggested_lower_price": 42100.0,
                "suggested_upper_price": 42900.0,
                "suggested_range": 800.0,
                "suggested_quantity_per_order": 0.001,
                "allocated_capital": 200.0,
                "suggested_stop_loss": 100.0,
            }
        }


class AutoParamsRequest(BaseModel):
    """Schema for GET /auto-params query parameters"""
    symbol: str = Field(..., description="Trading pair (e.g., BTCUSDT)")
    balance: float = Field(..., gt=0, description="Available balance in USDT")


class AutoParamsParams(BaseModel):
    """Derived grid parameters from auto-derivation"""
    levels: int
    risk_pct: float
    atr_multiplier: float
    klines_interval: str
    atr_period: int


class AutoParamsResponse(BaseModel):
    """Schema for GET /auto-params response"""
    symbol: str
    current_price: float
    grid_viable: bool
    params: Optional[AutoParamsParams] = None  # None if grid_viable is False
    reasoning: dict  # Detailed derivation steps
    policy: dict  # Policy constants used

    class Config:
        json_schema_extra = {
            "example": {
                "symbol": "BTCUSDT",
                "current_price": 63515.2,
                "grid_viable": True,
                "params": {
                    "levels": 8,
                    "risk_pct": 0.0111,
                    "atr_multiplier": 2.3,
                    "klines_interval": "4h",
                    "atr_period": 14
                },
                "reasoning": {
                    "klines_interval": "ER 4h=0.18 (selected, lowest) vs 1h=0.34, 1d=0.41",
                    "atr_multiplier": "Range 2828.06 / (2*ATR) = 2.3",
                    "levels": "Range grid / min step = 8 levels",
                    "risk_pct": "8 * 5.0 * 1.2 / 5200 = 0.0111"
                },
                "policy": {
                    "fee_roundtrip": 0.002,
                    "fee_margin_factor": 2.5,
                    "max_risk_pct": 0.05,
                    "multiplier_bounds": [1.5, 3.5]
                }
            }
        }
