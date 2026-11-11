"""
Backtester offline del grid (N6, docs/analisis-bot/05 §5).

Reproduce con velas reales de mainnet el ciclo completo del bot: selección de
par y derivación de parámetros (se reusa `auto_derive_params` tal cual, con un
cliente histórico), fills de órdenes límite, reposición, cierres
(EXPIRED / OUT_OF_RANGE→RECENTER / MAX_POSITION / SL / TP) y kill-switch.

No toca Binance testnet, SQLite ni Postgres: solo lee velas públicas de
`fapi.binance.com` (cacheadas en disco) y escribe un reporte.

Uso: `python -m app.backtest --help` (desde `backend-python/`).
"""
