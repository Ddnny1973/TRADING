# Componentes del Sistema - Grid Trading TRADING

## Visión General

```
┌─────────────────────────────────────────────────────────┐
│                   USUARIO / MANEJO MANUAL               │
└────────────────────────┬────────────────────────────────┘
                         │
         ┌───────────────┴───────────────┐
         │                               │
    ┌────▼─────────────┐          ┌─────▼──────────────┐
    │ Workflow 1       │          │ Workflow 2         │
    │ Market Decision  │          │ Grid Monitor       │
    │ (Trigger: Cron/  │          │ (Trigger: Cron     │
    │  Manual, 4h)     │          │  15min)            │
    └────┬─────────────┘          └─────┬──────────────┘
         │                               │
         └───────────────┬───────────────┘
                         │
         ┌───────────────▼───────────────────────┐
         │   Backend FastAPI (Python)            │
         │   - Market Analysis (ATR, SMA)        │
         │   - Grid CRUD Operations              │
         │   - Order Refresh & Replenish         │
         │   - Stop Loss / Take Profit Checks    │
         │   - Health & Monitoring               │
         └───────────────┬───────────────────────┘
                         │
         ┌───────────────▼────────────┐
         │  Base de Datos Local       │
         │  - SQLite (grids, orders)  │
         │  - PostgreSQL opcional     │
         └────────────────────────────┘
                         │
         ┌───────────────▼───────────────┐
         │   Binance Futures API (REST)  │
         │   - Place/Cancel Orders       │
         │   - Query Position Data       │
         │   - Fetch Account Balance     │
         │   - Market Data (Klines)      │
         └───────────────────────────────┘
```

---

## 1. FRONTEND (n8n Workflows)

### Workflow 1: Market Decision
**Trigger:** Manual o Cron cada 4 horas  
**Duración:** ~15-30 segundos  
**Función:** Analizar mercado y decidir si crear un grid

**Pasos:**
1. Fetch market data (ATR, SMA)
2. Analyzemarket trend con IA (OpenAI/Gemini)
3. Si bullish → Call `/create-grid` con parámetros dinámicos
4. Set Stop Loss automático
5. Notify a Telegram

**Input:**
```json
{
  "symbol": "BTCUSDT",
  "klines_interval": "4h",
  "grid_levels": 15,
  "risk_pct": 0.02
}
```

**Output:**
```json
{
  "grid_id": "GRID_20260705_001",
  "status": "ACTIVE",
  "lower_price": 62500,
  "upper_price": 65000,
  "orders_created": 15
}
```

---

### Workflow 2: Grid Monitor
**Trigger:** Cron cada 15 minutos  
**Duración:** ~3-5 segundos  
**Función:** Sincronizar estado de órdenes, replenish fills, evaluar SL/TP

**Pasos:**
1. Fetch active grids
2. Sync orders con Binance
3. Replenish órdenes ejecutadas (ciclos)
4. Check Stop Loss / Take Profit / EXPIRED
5. Update DB y notify a Telegram

**Input:** None (automático)  
**Output:**
```json
{
  "grids_monitored": 2,
  "orders_synced": 45,
  "orders_replenished": 3,
  "grids_closed": 0,
  "notifications_sent": 2
}
```

---

## 2. BACKEND (FastAPI en Python)

**Ubicación:** `backend-python/app/`

### Módulos Principales

#### `main.py`
- Inicialización de FastAPI
- Endpoints principales
- Lifespan (startup/shutdown)
- Logging

#### `core/config.py`
- Configuración centralizada (.env)
- Parámetros por defecto
- Validación de config

#### `core/security.py`
- Firma HMAC-SHA256 para Binance
- Validación de requests

#### `core/time_sync.py`
- Sincronización de reloj con Binance
- Importante para órdenes (timestamp validation)

#### `services/binance_client.py`
- Wrapper de API REST de Binance Futures
- Métodos:
  - `place_order()` — Coloca una orden LIMIT
  - `cancel_order()` — Cancela una orden
  - `get_position()` — Consulta posición abierta
  - `get_account_balance()` — Saldo disponible
  - `get_klines()` — Datos históricos
  - `get_mark_price()` — Precio actual

#### `services/grid_service.py`
- Orquestación de grids
- Métodos:
  - `create_grid()` — Crea nuevas órdenes
  - `refresh_grid()` — Sincroniza órdenes existentes
  - `replenish_grid()` — Crea órdenes nuevas en fills
  - `close_grid()` — Cierra todas las órdenes
  - `evaluate_closures()` — Chequea SL/TP/EXPIRED

#### `services/grid_engine.py`
- Cálculos de grid
- Métodos:
  - `calculate_grid_levels()` — Genera precios de órdenes
  - `calculate_grid_orders()` — Cantidad y precio de cada orden
  - Soporta GEOMETRIC y ARITHMETIC

#### `services/indicators.py`
- Indicadores técnicos
- Métodos:
  - `calculate_atr()` — Average True Range
  - `calculate_sma()` — Simple Moving Average
  - `calculate_pnl()` — Ganancias/pérdidas realizadas

#### `database/`
- Modelos SQLite/PostgreSQL
- Tablas:
  - `grids` — Información de grids activos
  - `orders` — Todas las órdenes (BUY, SELL)
  - `pnl_history` — Histórico de ganancias
  - `market_data` — Caché de datos de mercado

#### `schemas/`
- Validación de Pydantic
- Models:
  - `CreateGridRequest` — Input para crear grid
  - `GridResponse` — Output de grid
  - `OrderResponse` — Información de orden

---

## 3. BASE DE DATOS

### SQLite (Desarrollo/Testnet)
**Archivo:** `grid_trading.db`

```sql
CREATE TABLE grids (
  id TEXT PRIMARY KEY,
  symbol TEXT NOT NULL,
  status TEXT (ACTIVE, CLOSED, REFRESHING),
  lower_price REAL,
  upper_price REAL,
  levels INTEGER,
  created_at TIMESTAMP,
  closed_at TIMESTAMP,
  pnl_realized REAL
);

CREATE TABLE orders (
  id TEXT PRIMARY KEY,
  grid_id TEXT FOREIGN KEY,
  order_type TEXT (BUY, SELL),
  status TEXT (OPEN, FILLED, CANCELED, EXPIRED),
  quantity REAL,
  price REAL,
  executed_qty REAL,
  avg_price REAL,
  created_at TIMESTAMP,
  executed_at TIMESTAMP
);

CREATE TABLE pnl_history (
  id INTEGER PRIMARY KEY,
  grid_id TEXT,
  pnl_realized REAL,
  pnl_unrealized REAL,
  timestamp TIMESTAMP
);
```

### PostgreSQL (Producción Opcional)
- Mejor para escala
- Mismo esquema que SQLite
- Se activa con env var `DATABASE_URL`

---

## 4. BINANCE FUTURES API

### REST Endpoints Utilizados

**Auth:** API Key en Header + HMAC-SHA256 en Query

#### Market Data
```
GET /dapi/v1/klines              — Klines históricos
GET /dapi/v1/ticker/24hr         — Precio actual
GET /dapi/v1/premium/index       — Mark price
```

#### Trading
```
POST /dapi/v1/order              — Coloca orden
DELETE /dapi/v1/order            — Cancela orden
GET /dapi/v1/allOrders           — Lista órdenes
GET /dapi/v1/openOrders          — Órdenes abiertas
GET /dapi/v1/positionRisk        — Posición actual
```

#### Account
```
GET /dapi/v1/account             — Balance, max leverage, etc.
```

### Limitaciones Importantes

- **Rate limit:** 1200 requests/min (20 requests/sec)
- **Min notional:** ~10 USDT (~0.0001 BTC para BTCUSDT)
- **Min step:** Depende de instrumento (ej. 0.1 USDT)
- **Order timeout:** 60 segundos (cancela si no se ejecuta)

---

## 5. FLUJO COMPLETO

### Escenario: Usuario ejecuta Workflow 1 manualmente

1. **n8n Workflow 1**
   - Fetch BTCUSDT data (ATR, SMA, mark price)
   - Call IA: "¿Es bullish?"
   - → Sí

2. **n8n llama `/create-grid` (Backend)**
   ```json
   {
     "symbol": "BTCUSDT",
     "lower_price": 62500,
     "upper_price": 65000,
     "levels": 15,
     "risk_pct": 0.02
   }
   ```

3. **Backend: create_grid()**
   - Valida risk, notional, step
   - Calcula 15 órdenes (BUY LIMIT a 0.33% intervals)
   - Coloca órdenes en Binance
   - Guarda en DB
   - Devuelve grid_id

4. **Backend coloca en Binance:**
   ```
   BUY 0.01 BTC @ 62500
   BUY 0.01 BTC @ 62710
   ...
   BUY 0.01 BTC @ 64500
   ```

5. **Workflow 1 setea SL:**
   - Call `/set-stop-loss` con grid_id
   - Grid cierra si precio baja 2% (ejemplo)

6. **Workflow 2 (cada 15 min):**
   - Sync órdenes actuales
   - Si BUY se ejecutó → Crea SELL a precio + 0.33%
   - Repite indefinidamente
   - Monitorea SL/TP/EXPIRED

---

## 6. INTERACCIONES CLAVE

### Grid Lifecycle

```
CREATE (Workflow 1)
  ↓
ACTIVE (Órdenes BUY/SELL en Binance)
  ↓
REPLENISHING (Workflow 2 crea órdenes nuevas)
  ├─ Ciclos: BUY → SELL → BUY → ...
  ├─ Si SL hit → CLOSED (pérdida)
  ├─ Si TP hit → CLOSED (ganancia)
  └─ Si EXPIRED → CLOSED (por edad)
  ↓
CLOSED (Sin órdenes, sin posición)
  ↓
FIN
```

### Seguridad

- ✅ API Key + Secret en .env (nunca en código)
- ✅ Firma HMAC-SHA256 en cada request
- ✅ IP whitelist en Binance (recomendado)
- ✅ Testnet para desarrollo (no capital real)

---

## 7. DEPLOYMENT

### Desarrollo
- `docker-compose up` — Todo local
- Backend en `http://localhost:8000`
- n8n en `http://localhost:5678`
- SQLite en disco

### Producción
- Cambiar `.env` a mainnet Binance
- Usar PostgreSQL en la nube
- Usar Redis para rate limiting
- SSL/TLS en endpoints
- Backups automáticos

---

## Próximas Secciones

- [Code Structure](../70-DEVELOPMENT/01-code-structure.md) — Archivos específicos
- [API Reference](../30-API-REFERENCE/01-request-response.md) — Endpoints detallados
- [Risk Management](../60-TRADING-LOGIC/02-risk-management.md) — SL/TP/Límites
