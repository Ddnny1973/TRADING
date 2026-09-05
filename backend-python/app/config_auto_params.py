"""
Configuration policy for auto-derivation of grid parameters.
All constants and bounds are defined here for easy tuning.
"""

from decimal import Decimal

# Fee parameters (Binance Futures maker/taker ~0.02% each)
FEE_ROUNDTRIP = Decimal("0.002")        # 0.1% (0.02% maker + 0.02% taker per side)
FEE_MARGIN_FACTOR = Decimal("2.5")      # step must cover 2.5x round-trip fees

# Risk and viability constraints
MAX_RISK_PCT = Decimal("0.15")          # Never commit more than 15% of balance per grid
CAPITAL_BUFFER = Decimal("1.1")         # 10% margin above min_notional

# Tope de pérdida / objetivo de ganancia por grid, como fracción del balance.
# auto_derive_params() los traduce a stop_loss/take_profit en USDT para que
# check_close tenga un freno expresado en dinero (y no solo en inventario
# acumulado vía MAX_NET_POSITION_LEVELS). 0 deshabilita el umbral.
GRID_STOP_LOSS_PCT_OF_BALANCE = Decimal("0.010")     # 1.0% del balance
GRID_TAKE_PROFIT_PCT_OF_BALANCE = Decimal("0.030")   # 3.0% del balance

# Kill-switch (T15): fracción del balance que, como pérdida diaria agregada
# (cierres del día + PnL no realizado de grids RUNNING), dispara el cierre de
# todos los grids, bloquea create_grid y exige reactivación manual. 0 deshabilita.
MAX_DAILY_DRAWDOWN_PCT = Decimal("0.030")            # 3.0% del balance en un día

# Leverage por volatilidad del par (ATR% = ATR / precio)
GRID_LEVERAGE_DEFAULT = 3
LEVERAGE_BY_VOLATILITY = [
    {"max_atr_pct": 0.01, "leverage": 5},   # ATR% < 1%  → 5x
    {"max_atr_pct": 0.03, "leverage": 3},   # ATR% 1-3%  → 3x
    {"max_atr_pct": 999,  "leverage": 2},   # ATR% > 3%  → 2x
]
LEVERAGE_BOUNDS = (2, 10)

# Selección automática de par
SYMBOL_SELECTION_WEIGHTS = {
    "er":      0.40,
    "volume":  0.30,
    "atr_pct": 0.20,
    "funding": 0.10,
}
MIN_VOLUME_24H_USDT = 50_000_000
MAX_SPREAD_PCT      = 0.0005
SYMBOL_CACHE_TTL_SECONDS = 900
SYMBOL_BLACKLIST    = []
MAX_CANDIDATES_TO_SCORE = 20            # cap de candidatos a puntuar (limita llamadas a klines)
MAX_ATR_PCT_TRADEABLE = 0.10            # descartar pares con ATR > 10% del precio (no aptos para grid)

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

# Check-close grace period: OUT_OF_RANGE is not evaluated until the grid
# has been alive for at least this many minutes, giving orders time to fill
# and cycles to complete before the first price-bound check.
CHECK_CLOSE_GRACE_MINUTES = 30

# Fracción de MAX_NET_POSITION_LEVELS hasta la que un grid NEUTRAL puede
# acumular inventario sin dejar de reponer órdenes. Un grid funciona
# acumulando inventario: pausar la reposición al primer fill lo deja inerte.
# Solo se pausa al acercarse al límite duro que evaluará MAX_POSITION.
REPLENISH_POSITION_TOLERANCE_RATIO = Decimal("0.80")

# Cap de inventario proporcional al tamaño del grid: un grid de N niveles
# puede sostener aproximadamente N * ratio niveles de inventario de un solo
# lado. Un tope fijo (3 niveles) mataba grids de 10-13 niveles con solo 3
# fills, justo cuando debían estar acumulando.
MAX_NET_POSITION_RATIO = Decimal("0.6")

# Múltiplo del cap suave a partir del cual el inventario se considera
# descontrolado y el grid sí se cierra. Es una red de seguridad, no el
# mecanismo normal: el freno en dinero es stop_loss (ver auto_params).
MAX_POSITION_HARD_MULTIPLE = Decimal("2.0")

# Política ante OUT_OF_RANGE (T2): "CLOSE" (comportamiento histórico, vender a
# mercado y cristalizar la pérdida) o "RECENTER" (cancelar órdenes, conservar
# el inventario y reconstruir el grid alrededor del precio actual en modo
# LONG/SHORT, de modo que el inventario se descargue en la reversión en vez de
# liquidarse en el mínimo).
OUT_OF_RANGE_POLICY = "RECENTER"
# Nº máximo de re-centrados por grid antes de forzar el cierre real.
MAX_RECENTERS_PER_GRID = 2
# Margen (en múltiplos de ATR) que el precio debe superar fuera del rango antes
# de considerar el grid realmente "fuera", para no re-centrar por ruido.
OUT_OF_RANGE_ATR_BUFFER = Decimal("0.5")
# Nº de ciclos consecutivos de WF2 en los que el precio debe mantenerse fuera
# del rango (con buffer) antes de disparar RECENTER/CLOSE.
OUT_OF_RANGE_STRIKES_TO_TRIGGER = 2
