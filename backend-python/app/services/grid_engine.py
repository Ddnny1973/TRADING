"""
Grid engine module
Implements the mathematical calculations for grid trading strategies
"""

from decimal import Decimal, ROUND_DOWN
from typing import List, Dict, Any
from enum import Enum


class GridType(str, Enum):
    """Supported grid types"""
    GEOMETRIC = "GEOMETRIC"
    ARITHMETIC = "ARITHMETIC"


class GridEngine:
    """
    Grid trading engine with strict mathematical precision
    Uses Decimal for exact calculations without floating point errors
    """
    
    def __init__(self, symbol: str, lower_price: float, upper_price: float, 
                 levels: int, grid_type: GridType = GridType.GEOMETRIC):
        """
        Initialize grid engine
        
        Args:
            symbol: Trading pair (e.g., BTCUSDT)
            lower_price: Grid lower boundary
            upper_price: Grid upper boundary
            levels: Number of levels in the grid
            grid_type: Type of grid distribution
        """
        self.symbol = symbol
        self.lower_price = Decimal(str(lower_price))
        self.upper_price = Decimal(str(upper_price))
        self.levels = levels
        self.grid_type = grid_type
        self.grid_levels = []
    
    def calculate_grid_levels(self) -> List[Decimal]:
        """
        Calculate grid price levels based on grid type
        
        Returns:
            List of Decimal price levels
        """
        if self.grid_type == GridType.GEOMETRIC:
            self.grid_levels = self._calculate_geometric_grid()
        elif self.grid_type == GridType.ARITHMETIC:
            self.grid_levels = self._calculate_arithmetic_grid()
        
        return self.grid_levels
    
    def _calculate_geometric_grid(self) -> List[Decimal]:
        """
        Calculate geometric progression grid levels
        Used for exponential price spacing
        
        Returns:
            Sorted list of Decimal price levels
        """
        if self.levels < 2:
            return [self.lower_price, self.upper_price]
        
        # Calculate geometric ratio
        ratio = (self.upper_price / self.lower_price) ** (Decimal(1) / Decimal(self.levels - 1))
        
        levels = []
        for i in range(self.levels):
            level = self.lower_price * (ratio ** i)
            # Truncate down to avoid precision issues
            level = level.quantize(Decimal('0.00000001'), rounding=ROUND_DOWN)
            levels.append(level)
        
        return sorted(set(levels))  # Remove duplicates and sort
    
    def _calculate_arithmetic_grid(self) -> List[Decimal]:
        """
        Calculate arithmetic progression grid levels
        Used for linear price spacing
        
        Returns:
            Sorted list of Decimal price levels
        """
        if self.levels < 2:
            return [self.lower_price, self.upper_price]
        
        step = (self.upper_price - self.lower_price) / Decimal(self.levels - 1)
        
        levels = []
        for i in range(self.levels):
            level = self.lower_price + (step * i)
            # Truncate down to avoid precision issues
            level = level.quantize(Decimal('0.00000001'), rounding=ROUND_DOWN)
            levels.append(level)
        
        return sorted(set(levels))  # Remove duplicates and sort
    
    def get_grid_info(self) -> Dict[str, Any]:
        """Get grid information"""
        return {
            "symbol": self.symbol,
            "lower_price": str(self.lower_price),
            "upper_price": str(self.upper_price),
            "levels": self.levels,
            "grid_type": self.grid_type.value,
            "calculated_levels": [str(level) for level in self.grid_levels]
        }
