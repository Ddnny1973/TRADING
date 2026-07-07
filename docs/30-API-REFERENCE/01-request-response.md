# API Reference - Request/Response

## Base URL

```
http://localhost:8000/api/v1
```

---

## Health Check

### GET `/health`
Estado del backend.

**Response:**
```json
{
  "status": "healthy",
  "service": "grid-trading-backend",
  "version": "0.1.0",
  "binance_synced": true,
  "time_offset_ms": 15
}
```

**Status codes:**
- `200` — Healthy
- `503` — Unhealthy (DB, Binance API, etc.)

---

## Market Analysis (Fase 2: Rentabilidad)

### GET `/market-analysis/{symbol}`
Analiza mercado: ATR, precios sugeridos, capital y SL automático.

**Path params:**
- `symbol` — Trading pair (e.g., BTCUSDT, ETHUSDT)

**Query params (opcionales):**
- `atr_period` — Default: 14
- `atr_multiplier` — Default: 2.0
- `klines_interval` — Default: "4h" (4h, 1h, 15m, etc.)
- `risk_pct` — Opcional; si se omite, usa `DEFAULT_RISK_PCT` del servidor (default 0.02). WF1 usa 0.05.
- `levels` — Opcional; si se omite, no se calculan campos de viabilidad. WF1 usa 4.

**Example request (con levels, para obtener campos de viabilidad):**
```bash
GET /api/v1/market-analysis/BTCUSDT?atr_period=14&atr_multiplier=2.0&klines_interval=4h&risk_pct=0.05&levels=4
```

**Response (con `levels` pasado):**
```json
{
  "symbol": "BTCUSDT",
  "current_price": 42500.0,
  "atr": 200.0,
  "atr_period": 14,
  "atr_multiplier": 2.0,
  "suggested_lower_price": 42100.0,
  "suggested_upper_price": 42900.0,
  "suggested_range": 800.0,
  "suggested_quantity_per_order": 0.001,
  "allocated_capital": 500.0,
  "suggested_stop_loss": 250.0,
  "min_viable_quantity": 0.001,
  "grid_viable": true,
  "required_risk_pct": 0.042,
  "klines_interval": "4h"
}
```

**Field explanations:**
- `suggested_lower_price/upper_price` — Grid bounds based on ATR
- `suggested_quantity_per_order` — Per-order qty calculated from risk_pct (solo si se pasa `levels`)
- `allocated_capital` — Capital asignado = balance × risk_pct (solo si se pasa `levels`)
- `suggested_stop_loss` — SL sugerido = allocated_capital × 0.5 (solo si se pasa `levels`)
- `min_viable_quantity` — Cantidad mínima para cumplir min_notional 50 USDT + step_size (solo si se pasa `levels`)
- `grid_viable` — true si suggested_quantity_per_order >= min_viable_quantity (solo si se pasa `levels`)
- `required_risk_pct` — risk_pct necesario para que el grid sea viable (solo si se pasa `levels`)

**Status codes:**
- `200` — Market data available
- `400` — Missing current price or klines

---

## Grid Operations

### POST `/grids`
Crea una nueva grid con órdenes en Binance.

**Request:**
```json
{
  "symbol": "BTCUSDT",
  "lower_price": 42100.0,
  "upper_price": 42900.0,
  "levels": 10,
  "quantity_per_order": 0.002,
  "grid_type": "GEOMETRIC",
  "stop_loss": 4250.0,
  "take_profit": null
}
```

**Field notes:**
- `lower_price`/`upper_price` — Optional; if null, uses market-analysis bounds
- `quantity_per_order` — Must be >= min_notional (50 USDT for Binance Futures)
- `stop_loss`/`take_profit` — Optional; can be null
- `grid_type` — "GEOMETRIC" or "ARITHMETIC"

**Response (201 Created):**
```json
{
  "id": "grid_20260705_abc123",
  "symbol": "BTCUSDT",
  "status": "RUNNING",
  "lower_price": 42100.0,
  "upper_price": 42900.0,
  "levels": 10,
  "stop_loss": 4250.0,
  "take_profit": null,
  "orders": [
    {
      "id": "order_1",
      "side": "BUY",
      "price": 42100.0,
      "quantity": 0.002,
      "status": "NEW"
    },
    {
      "id": "order_2",
      "side": "BUY",
      "price": 42233.0,
      "quantity": 0.002,
      "status": "NEW"
    }
  ],
  "created_at": "2026-07-05T20:22:00Z"
}
```

**Status codes:**
- `200` — Grid created successfully
- `400` — Invalid parameters (min_notional, quantity, etc.)
- `409` — Duplicate symbol (only one active grid per symbol)

---

### GET `/grids`
Lista todas las grids.

**Query params (opcionales):**
- `status` — Filter by RUNNING, CANCELED, EXPIRED
- `symbol` — Filter by symbol (BTCUSDT, etc.)

**Response:**
```json
[
  {
    "id": "grid_20260705_abc123",
    "symbol": "BTCUSDT",
    "status": "RUNNING",
    "lower_price": 42100.0,
    "upper_price": 42900.0,
    "levels": 10,
    "stop_loss": 4250.0,
    "created_at": "2026-07-05T20:22:00Z"
  }
]
```

*Nota: La respuesta es un array directo (no un objeto con `grids`).*

---

### GET `/grids/{id}`
Detalle de una grid con todas sus órdenes.

**Response:**
```json
{
  "id": "grid_20260705_abc123",
  "symbol": "BTCUSDT",
  "status": "RUNNING",
  "lower_price": 42100.0,
  "upper_price": 42900.0,
  "stop_loss": 4250.0,
  "take_profit": null,
  "orders": [
    {
      "id": "order_1",
      "side": "BUY",
      "price": 42100.0,
      "quantity": 0.002,
      "status": "NEW",
      "executed_qty": 0.0,
      "avg_price": null
    },
    {
      "id": "order_2",
      "side": "BUY",
      "price": 42233.0,
      "quantity": 0.002,
      "status": "FILLED",
      "executed_qty": 0.002,
      "avg_price": 42233.0
    }
  ],
  "created_at": "2026-07-05T20:22:00Z"
}
```

---

### POST `/grids/{id}/refresh`
Sincroniza estado de órdenes con Binance (Fase 3: Estrategia).

**Response:**
```json
{
  "id": "grid_20260705_abc123",
  "status": "RUNNING",
  "orders_synced": 10,
  "orders_filled": 2,
  "timestamp": "2026-07-05T20:30:00Z"
}
```

**Use case:** Called by Workflow 2 every 5 minutes to detect fills.

---

### GET `/grids/{id}/pnl`
Calcula PnL (neto = gross - fees 0.02%) (Fase 2: Rentabilidad).

**Response:**
```json
{
  "grid_id": "grid_20260705_abc123",
  "realized_pnl": 45.75,
  "unrealized_pnl": 12.50,
  "total_pnl": 58.25,
  "fees_paid": 5.25,
  "net_position_qty": 0.01,
  "current_price": 42500.0,
  "timestamp": "2026-07-05T20:35:00Z"
}
```

**Important:**
- `realized_pnl` already deducts 0.02% Binance commission (Fase 2)
- Used by Workflow 2 to decide SL/TP closure
- If no fills: all fields are 0

---

### POST `/grids/{id}/check-close`
Evalúa triggers: SL, TP, EXPIRED (Fase 1: Correctitud).

**Response (trigger not hit):**
```json
{
  "triggered": null,
  "grid": {
    "status": "RUNNING"
  }
}
```

**Response (trigger hit):**
```json
{
  "triggered": "TAKE_PROFIT",
  "grid": {
    "id": "grid_20260705_abc123",
    "status": "CANCELED",
    "realized_pnl": 45.75,
    "closed_at": "2026-07-05T20:35:00Z"
  }
}
```

**Trigger values:**
- `"STOP_LOSS"` — PnL dropped below threshold
- `"TAKE_PROFIT"` — PnL exceeded threshold
- `"EXPIRED"` — Grid exceeded max age
- `null` — No trigger hit, grid still running

**Use case:** Called by Workflow 2 every 5 minutes.

---

### DELETE `/grids/{id}`
Cancela grid (cierra todas las órdenes, manual close).

**Response:**
```json
{
  "id": "grid_20260705_abc123",
  "status": "CANCELED",
  "orders_canceled": 10,
  "realized_pnl": 35.50,
  "closed_at": "2026-07-05T20:35:00Z"
}
```

**Status codes:**
- `200` — Grid closed
- `404` — Grid not found

---

## Error Handling

Ver [Error Handling](02-error-handling.md)

---

## Workflow Integration

### Workflow 1: Market Decision (n8n)

```
1. GET /market-analysis/BTCUSDT
   → Gets: current_price, ATR, bounds, allocated_capital, suggested_stop_loss

2. (Build Gemini prompt with above data)

3. POST /grids
   → Params: lower_price, upper_price, quantity_per_order, stop_loss
   → Response: grid_id
```

### Workflow 2: Grid Monitor (n8n, every 5 minutes)

```
1. GET /grids?status=RUNNING
   → Gets: list of active grids

2. For each grid:
   a. POST /grids/{id}/refresh
      → Sync orders with Binance
   
   b. GET /grids/{id}/pnl
      → Calculate PnL (net of fees)
   
   c. POST /grids/{id}/check-close
      → Evaluate SL/TP/EXPIRED
      
   d. If triggered: DELETE /grids/{id}
      → Close all orders
      → Notify Telegram (reason: SL ❌, TP ✅, EXPIRED ⏰)
```

---

## Rate Limits

- **n8n → Backend:** No limit (same network)
- **Backend → Binance:** 1200 req/min (20 req/sec)
  - Automatically enforced by BinanceClient wrapper

---

## Authentication

**Currently:** No authentication (assumes private network)

**For production:** Add to `core/security.py`
- API Key validation
- Request signing
- Rate limiting by key

---

## Implementation Phases

| Phase | Name | Status |
|-------|------|--------|
| **1** | Correctitud (Real closure) | ✅ Implemented |
| **2** | Rentabilidad (Fee deduction) | ✅ Implemented |
| **3** | Estrategia (Replenishment) | ✅ Implemented |
| **4** | Robustez (Concurrency limits) | ✅ Implemented |

See [Arquitectura](../10-ARQUITECTURA/01-componentes.md#7-fases-de-mejora-implementadas) for details.
