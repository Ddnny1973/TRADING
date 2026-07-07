"""
Configuration policy for auto-derivation of grid parameters.
All constants and bounds are defined here for easy tuning.
"""

from decimal import Decimal

# Fee parameters (Binance Futures maker/taker ~0.02% each)
FEE_ROUNDTRIP = Decimal("0.002")        # 0.1% (0.02% maker + 0.02% taker per side)
FEE_MARGIN_FACTOR = Decimal("2.5")      # step must cover 2.5x round-trip fees

# Risk and viability constraints
MAX_RISK_PCT = Decimal("0.05")          # Never commit more than 5% of balance per grid
CAPITAL_BUFFER = Decimal("1.2")         # 20% margin above min_notional

# Parameter bounds (will be applied after derivation)
MULTIPLIER_BOUNDS = (Decimal("1.5"), Decimal("3.5"))
LEVELS_BOUNDS = (4, 20)

# ATR and market analysis
ATR_PERIOD = 14

# Interval selection via Efficiency Ratio
CANDIDATE_INTERVALS = ["1h", "4h", "1d"]
ER_LOOKBACK = 48                        # candles for ER calculation
ER_MAX_TRADEABLE = Decimal("0.35")      # if all timeframes exceed this, don't trade

# Range calculation (for deriving multiplier)
RANGE_LOOKBACK = 50                     # candles for real range

# Fallback if exchangeInfo doesn't provide minNotional
MIN_NOTIONAL_FALLBACK = Decimal("5.0")  # USDT
