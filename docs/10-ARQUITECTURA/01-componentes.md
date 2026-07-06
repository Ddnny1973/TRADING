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
**Función:** Analizar mercado, calcular capital + SL, decidir si crear un grid

**Fases Implementadas:**
- ✅ **Fase 1 (Correctitud):** Real closure, leverage, expiration triggers
- ✅ **Fase 2 (Rentabilidad):** Fee deduction en PnL, min-step validation
- ✅ **Fase 3 (Estrategia):** Replenishment y refresh automático
- ✅ **Fase 4 (Robustez):** Limits concurrentes, HTTP hygiene

**Pasos:**
1. Fetch market data (ATR, SMA, current price)
2. Call `/api/v1/market-analysis` → obtiene:
   - `suggested_lower_price`, `suggested_upper_price` (basados en ATR)
   - `suggested_quantity_per_order` (tamaño dinámico por risk%)
   - `allocated_capital` (capital en riesgo calculado)
   - `suggested_stop_loss` (SL automático basado en PnL)
3. Analyze market trend con IA (Gemini)
4. Si bullish → Call `/api/v1/grids` con:
   - `stop_loss: $json.suggested_stop_loss` (SL real, no null)
   - `quantity_per_order: $json.suggested_quantity_per_order` (sin Math.max inflation)
5. Notify a Telegram con capital y SL

**Input (desde n8n):**
```json
{
  "symbol": "BTCUSDT",
  "klines_interval": "4h",
  "atr_period": 14,
  "atr_multiplier": 2.0
}
```

**Output (Backend Market Analysis):**
```json
{
  "symbol": "BTCUSDT",
  "current_price": 42500.0,
  "atr": 200.0,
  "suggested_lower_price": 42100.0,
  "suggested_upper_price": 42900.0,
  "suggested_quantity_per_order": 0.002,
  "allocated_capital": 85.0,
  "suggested_stop_loss": 4250.0
}
```

**Output (Grid Creado):**
```json
{
  "id": "grid_20260705_001",
  "symbol": "BTCUSDT",
  "status": "RUNNING",
  "lower_price": 42100.0,
  "upper_price": 42900.0,
  "stop_loss": 4250.0,
  "levels": 10,
  "orders": [...]
}
```

---

### Workflow 2: Grid Monitor
**Trigger:** Cron cada 5 minutos (**MEJORADO de 15 min**)  
**Duración:** ~3-5 segundos  
**Función:** Sincronizar estado, replenish fills, evaluar SL/TP/EXPIRED con visibilidad mejorada

**Pasos:**
1. Fetch active grids
2. Call `/api/v1/grids/{id}/refresh` → Sync orders con Binance
3. Call `/api/v1/grids/{id}/pnl` → Calcula PnL (con deducción de fees)
4. Replenish órdenes ejecutadas (ciclos BUY → SELL → BUY)
5. Call `/api/v1/grids/{id}/check-close` → Evalúa triggers:
   - **STOP_LOSS:** Pérdida > threshold (mostrado como ❌)
   - **TAKE_PROFIT:** Ganancia > threshold (mostrado como ✅)
   - **EXPIRED:** Grid vencido (mostrado como ⏰)
   - **Manual:** Cerrado manualmente (mostrado como 🤷)
6. Update DB y notify a Telegram con razón de cierre

**Input:** None (automático)  
**Output:**
```json
{
  "grids_monitored": 2,
  "orders_synced": 45,
  "orders_replenished": 3,
  "grids_closed": 1,
  "close_reason": "TAKE_PROFIT",
  "notifications_sent": 2
}
```

**Mejoras en WF2:**
- ⏱️ Intervalo: 15 min → **5 min** (fills detectados más rápido)
- 📊 Triggers: raw value → **interpretados con emojis** (mejor UX)
- 💰 PnL: bruto → **neto (deduce fees 0.02% default)**
- 🔄 Replenish: más ciclos por grid en el mismo tiempo

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
  - `calculate_atr()` — Average True Range (para definir grid bounds)
  - `calculate_sma()` — Simple Moving Average
  - `calculate_grid_pnl(orders, current_price, fee_rate=0.0002)` — Calcula PnL **neto** (deduce comisiones Binance 0.02%)

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

### Binance Futures REST API (Base para Backend)

**Auth:** API Key en Header + HMAC-SHA256 en Query

#### Market Data
```
GET /dapi/v1/klines              — Klines históricos (para ATR/SMA)
GET /dapi/v1/ticker/24hr         — Precio actual
GET /dapi/v1/premium/index       — Mark price (precio actual)
```

#### Trading
```
POST /dapi/v1/order              — Coloca orden LIMIT (batch)
DELETE /dapi/v1/order            — Cancela orden
GET /dapi/v1/allOrders           — Lista órdenes
GET /dapi/v1/openOrders          — Órdenes abiertas
GET /dapi/v1/positionRisk        — Posición actual
```

#### Account
```
GET /dapi/v1/account             — Balance, max leverage, commission rates
GET /dapi/v1/commissionRates     — Comisiones (maker/taker 0.02%-0.04%)
```

### Nuestros Endpoints (FastAPI Backend)

**Base:** `http://localhost:8000/api/v1`

#### Market Analysis (Soporte para decisiones inteligentes)
```
GET /market-analysis/{symbol}
  Params: atr_period=14, atr_multiplier=2.0, klines_interval=4h
  Return: {
    current_price, atr, 
    suggested_lower_price, suggested_upper_price,
    suggested_quantity_per_order,    ← NUEVO (Fase 2)
    allocated_capital,                ← NUEVO (Fase 2)
    suggested_stop_loss               ← NUEVO (Fase 2)
  }
```

#### Grid Operations
```
POST /grids
  Create grid con params dinámicos (bounds, levels, risk%)
  
GET /grids
  List all grids
  
GET /grids/{id}
  Get grid detail + orders
  
POST /grids/{id}/refresh
  Sync órdenes con Binance
  
GET /grids/{id}/pnl
  Calculate PnL (neto = bruto - fees)  ← ACTUALIZADO (Fase 2)
  
POST /grids/{id}/check-close
  Evaluate SL/TP/EXPIRED triggers
  
DELETE /grids/{id}
  Cancel all orders (manual close)
```

### Limitaciones Importantes (Binance Futures)

- **Rate limit:** 1200 requests/min (20 requests/sec)
- **Min notional:** **50 USDT** (Binance Futures, no Spot)
- **Min step:** Depende de instrumento (ej. 0.01 USDT para BTCUSDT)
- **Min qty step:** Depende de instrumento (ej. 0.001 BTC)
- **Order timeout:** 60 segundos (cancela si no se ejecuta)
- **Commission rate:** 0.02% maker, 0.04% taker (deducido en PnL calculations)

---

## 5. FLUJO COMPLETO (CON MEJORAS FASE 1-4)

### Escenario: Usuario ejecuta Workflow 1 manualmente

1. **n8n Workflow 1 (Market Decision)**
   ```
   → Call /api/v1/market-analysis/BTCUSDT
      ↓ (Backend calcula)
   ← {
       current_price: 42500,
       atr: 200,
       suggested_lower_price: 42100,
       suggested_upper_price: 42900,
       suggested_quantity_per_order: 0.002,
       allocated_capital: 85,            ← NUEVO
       suggested_stop_loss: 4250         ← NUEVO
     }
   ```

2. **n8n Workflow 1 (Decision Logic)**
   - Build Gemini Request con datos del backend
   - Call Gemini API: "¿Es bullish?"
   - → Sí, procede

3. **n8n llama POST /api/v1/grids (Backend)**
   ```json
   {
     "symbol": "BTCUSDT",
     "lower_price": 42100,
     "upper_price": 42900,
     "quantity_per_order": 0.002,        ← Sin Math.max inflation
     "levels": 10,
     "stop_loss": 4250,                   ← Valor real (no null)
     "grid_type": "GEOMETRIC"
   }
   ```

4. **Backend: create_grid()**
   - ✅ Valida min_notional (50 USDT, no 5)
   - ✅ Calcula 10 órdenes (BUY LIMIT a 0.33% intervals)
   - ✅ Valida min_step dinámico por instrumento
   - ✅ Coloca órdenes en Binance (batch)
   - ✅ Guarda en DB (SQLite/PostgreSQL)
   - ✅ Devuelve grid_id + status

5. **Backend crea en Binance:**
   ```
   BUY 0.002 BTC @ 42100
   BUY 0.002 BTC @ 42233
   ...
   BUY 0.002 BTC @ 42900
   (+ SELL orders por encima del precio actual)
   ```

6. **n8n Workflow 1 notifica (con valores reales):**
   ```
   📊 GRID CREADO
   Capital en riesgo: 85 USDT
   Stop Loss: 4250 USDT (si PnL < SL, cierra TODO)
   Niveles: 10 | Rango: 42100-42900
   ```

7. **n8n Workflow 2 (Grid Monitor) - cada 5 min**
   ```
   → GET /api/v1/grids (obtiene activos)
   → POST /api/v1/grids/{id}/refresh
      (Sync órdenes con Binance)
   → GET /api/v1/grids/{id}/pnl
      (Calcula PnL neto = bruto - fees 0.02%)
   → POST /api/v1/grids/{id}/check-close
      (Evalúa triggers)
   ```

8. **Si BUY se ejecutó:**
   - Backend crea SELL a precio + spread
   - Ciclo continúa (replenishment)

9. **Si se dispara SL/TP/EXPIRED:**
   ```
   → DELETE /api/v1/grids/{id}
      (Cancela todas las órdenes)
   → Workflow 2 notifica:
      "❌ Stop Loss" o "✅ Take Profit" o "⏰ Expiración"
      con PnL final neto (ya deducidas comisiones)
   ```

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

## 7. FASES DE MEJORA IMPLEMENTADAS (2026-07-05)

### ✅ Fase 1: CORRECTITUD (Grid Real)
- Real closure triggers (SL, TP, EXPIRED)
- Leverage control (1-125x)
- Proper order lifecycle (NEW → FILLED → REPLENISHED → CLOSED)

**Cambios Backend:**
- ✅ Fixed: `await grid_service.get_grid()` removed (was sync, not async) - Line 270, main.py
- ✅ Grid status lifecycle: RUNNING → CLOSED (no ACTIVE)

---

### ✅ Fase 2: RENTABILIDAD (Fee Deduction + Min-Step)
- Commission rates deducted from PnL (0.02% maker, 0.04% taker)
- Dynamic min_notional validation (50 USDT for Binance Futures)
- Min_step respecting per-instrument constraints

**Cambios Backend:**
- ✅ `calculate_grid_pnl()` now deducts fees: `pnl_net = pnl_gross - (qty * price * fee_rate)` - indicators.py:121
- ✅ Conftest min_notional: 5 → 50 USDT
- ✅ Removed `Math.max()` inflation bug in workflow1 - was forcing qty >= 65 USDT unnecessarily

**Cambios Workflows:**
- ✅ WF1: Create Grid uses `quantity_per_order` directly (no Math.max)
- ✅ WF1: `stop_loss` = `$json.suggested_stop_loss` (real value, not null)
- ✅ WF2: Displays fee-deducted PnL in notifications

---

### ✅ Fase 3: ESTRATEGIA (Replenishment + Faster Monitoring)
- Automatic order replenishment on fills (BUY → SELL → BUY cycles)
- Faster monitoring interval (15 min → 5 min)
- Better trigger visibility (SL ❌, TP ✅, EXPIRED ⏰, Manual 🤷)

**Cambios Workflows:**
- ✅ WF2: Cron interval reduced: 15 min → **5 min**
- ✅ WF2: Trigger display: raw value → conditional emojis
- ✅ WF1: Propagates `allocated_capital` and `suggested_stop_loss` from market-analysis
- ✅ WF1: Notifications display capital at risk and SL threshold

---

### ✅ Fase 4: ROBUSTEZ (Concurrency Limits + HTTP Hygiene)
- Concurrent grid limits per symbol
- Request timeout handling (60s)
- Proper error codes (400 invalid, 404 not found, 500 server error)
- Rate limiting awareness (1200 req/min on Binance)

**Cambios Backend:**
- ✅ GridService validates symbol uniqueness (one active grid per symbol)
- ✅ Binance wrapper respects rate limits
- ✅ HTTP status codes properly mapped

---

### 📊 Critical Production Blockers Fixed (2026-07-05)

| N° | Bug | Impact | Fix | File |
|----|-----|--------|-----|------|
| N1 | `await` on sync function | HTTP 500 on replenish | Remove await | main.py:270 |
| N2 | Math.max inflation | 2x qty if < 65 USDT | Use suggested qty directly | workflow1 |
| N3 | PnL ignores fees | Wrong SL/TP decisions | Deduct 0.02% fees | indicators.py:121 |
| N4 | Duplicate workflow files | Confusion | Delete workflow1-updated.json | git rm |

---

## 7. DEPLOYMENT

### Desarrollo
- `docker-compose up` — Todo local
- Backend en `http://localhost:8000`
- n8n en `http://localhost:5678`
- SQLite en disco
- **Reqiere:** `BACKEND_URL=http://localhost:8000` en n8n environment

### Producción
- Cambiar `.env` a mainnet Binance
- Usar PostgreSQL en la nube
- Usar Redis para rate limiting
- SSL/TLS en endpoints
- Backups automáticos
- **Requiere:** `BACKEND_URL=http://backend-python:8000` (Docker) en n8n
- **Requiere:** `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` para acceso a variables

---

## Próximas Secciones

- [Code Structure](../70-DEVELOPMENT/01-code-structure.md) — Archivos específicos y layout
- [API Reference](../30-API-REFERENCE/01-request-response.md) — Todos los endpoints
- [Risk Management](../60-TRADING-LOGIC/02-risk-management.md) — SL/TP/Cálculos
- [Workflows](../50-WORKFLOWS/01-vision-general.md) — Explicación detallada de WF1 y WF2
- [Troubleshooting](../40-OPERACIONAL/01-troubleshooting.md) — Problemas comunes
