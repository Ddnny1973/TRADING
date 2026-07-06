# API Reference - Request/Response

## Base URL

```
http://localhost:8000
```

---

## Health Check

### GET `/health`
Estado del backend.

**Response:**
```json
{
  "status": "healthy",
  "uptime_seconds": 3600,
  "database": "connected",
  "binance_api": "reachable"
}
```

**Status codes:**
- `200` — Healthy
- `503` — Unhealthy (DB, Binance API, etc.)

---

## Market Analysis

### POST `/market-analysis`
Analiza mercado: ATR, SMA, mark price.

**Request:**
```json
{
  "symbol": "BTCUSDT",
  "interval": "4h",
  "atr_period": 14,
  "sma_period": 50
}
```

**Response:**
```json
{
  "symbol": "BTCUSDT",
  "interval": "4h",
  "current_price": 63500.50,
  "atr": 450.25,
  "sma": 62800.00,
  "trend": "bullish",
  "volatility": "medium"
}
```

---

## Grid Operations

### POST `/create-grid`
Crea una nueva grid.

**Request:**
```json
{
  "symbol": "BTCUSDT",
  "lower_price": 62500,
  "upper_price": 65000,
  "levels": 15,
  "risk_pct": 0.02
}
```

**Response:**
```json
{
  "grid_id": "GRID_20260705_001",
  "symbol": "BTCUSDT",
  "status": "ACTIVE",
  "lower_price": 62500,
  "upper_price": 65000,
  "levels": 15,
  "orders_created": 15,
  "total_quantity": 0.15,
  "created_at": "2026-07-05T20:22:00Z"
}
```

**Errors:**
- `400` — Invalid parameters (risk too high, step too small, etc.)
- `409` — Max grids reached (máx 2 simultáneamente)

---

### GET `/grids`
Lista todas las grids.

**Query params:**
- `status` — (ACTIVE, CLOSED, REFRESHING) — Opcional
- `symbol` — (BTCUSDT, etc.) — Opcional

**Response:**
```json
{
  "grids": [
    {
      "grid_id": "GRID_20260705_001",
      "symbol": "BTCUSDT",
      "status": "ACTIVE",
      "lower_price": 62500,
      "upper_price": 65000,
      "levels": 15,
      "pnl_realized": 12.50,
      "created_at": "2026-07-05T20:22:00Z"
    }
  ],
  "total": 1
}
```

---

### POST `/refresh-grid/{grid_id}`
Sincroniza una grid con Binance (revisa órdenes ejecutadas).

**Response:**
```json
{
  "grid_id": "GRID_20260705_001",
  "status": "ACTIVE",
  "orders_synced": 15,
  "orders_filled": 3,
  "timestamp": "2026-07-05T20:30:00Z"
}
```

---

### POST `/replenish-grid/{grid_id}`
Crea órdenes nuevas en órdenes ejecutadas (ciclos).

**Response:**
```json
{
  "grid_id": "GRID_20260705_001",
  "orders_replenished": 3,
  "total_orders_now": 15,
  "timestamp": "2026-07-05T20:30:00Z"
}
```

---

### POST `/close-grid/{grid_id}`
Cierra una grid (cancela todas las órdenes).

**Response:**
```json
{
  "grid_id": "GRID_20260705_001",
  "status": "CLOSED",
  "orders_canceled": 15,
  "pnl_realized": 45.75,
  "closed_at": "2026-07-05T20:35:00Z"
}
```

---

## Stop Loss & Take Profit

### POST `/set-stop-loss/{grid_id}`
Setea un stop loss para una grid.

**Request:**
```json
{
  "stop_loss_pct": 0.02
}
```

**Response:**
```json
{
  "grid_id": "GRID_20260705_001",
  "stop_loss_pct": 0.02,
  "stop_loss_price": 62250,
  "status": "ACTIVE"
}
```

---

### POST `/set-take-profit/{grid_id}`
Setea un take profit para una grid.

**Request:**
```json
{
  "take_profit_pct": 0.05
}
```

**Response:**
```json
{
  "grid_id": "GRID_20260705_001",
  "take_profit_pct": 0.05,
  "take_profit_price": 65625,
  "status": "ACTIVE"
}
```

---

## Orders

### GET `/grids/{grid_id}/orders`
Lista las órdenes de una grid.

**Query params:**
- `status` — (OPEN, FILLED, CANCELED, EXPIRED)

**Response:**
```json
{
  "grid_id": "GRID_20260705_001",
  "orders": [
    {
      "order_id": "ORDER_001",
      "symbol": "BTCUSDT",
      "type": "BUY",
      "status": "OPEN",
      "quantity": 0.01,
      "price": 62500,
      "created_at": "2026-07-05T20:22:00Z"
    },
    {
      "order_id": "ORDER_002",
      "symbol": "BTCUSDT",
      "type": "BUY",
      "status": "FILLED",
      "quantity": 0.01,
      "price": 62500,
      "executed_qty": 0.01,
      "avg_price": 62500,
      "executed_at": "2026-07-05T20:25:00Z"
    }
  ],
  "total": 15
}
```

---

## Account & Position

### GET `/account`
Info de la cuenta (balance, max leverage, etc.).

**Response:**
```json
{
  "balance_usdt": 10000,
  "available_usdt": 9500,
  "max_leverage": 125,
  "current_leverage": 1,
  "total_positions": 1,
  "positions": [
    {
      "symbol": "BTCUSDT",
      "quantity": 0.05,
      "mark_price": 63500,
      "unrealized_pnl": 75
    }
  ]
}
```

---

## PnL & History

### GET `/pnl/{grid_id}`
Ganancias/pérdidas de una grid.

**Response:**
```json
{
  "grid_id": "GRID_20260705_001",
  "pnl_realized": 45.75,
  "pnl_unrealized": 12.50,
  "pnl_total": 58.25,
  "pnl_pct": 0.58,
  "fees_paid": 5.25,
  "timestamp": "2026-07-05T20:35:00Z"
}
```

---

## Error Handling

Ver [Error Handling](02-error-handling.md)

---

## Webhooks (n8n)

Los workflows llaman a los endpoints arriba.

**Ejemplo de Workflow 1:**
```
→ POST /market-analysis
← {market data}
→ POST /create-grid (si bullish)
← {grid_id}
```

**Ejemplo de Workflow 2:**
```
→ GET /grids?status=ACTIVE
← {all active grids}
→ POST /refresh-grid/{grid_id} (para cada grid)
← {sync result}
→ POST /replenish-grid/{grid_id}
← {replenish result}
```

---

## Rate Limits

- **n8n to Backend:** Sin límite (misma red)
- **Backend to Binance:** 1200 req/min (20 req/sec)
  - El backend respeta esto automáticamente

---

## Autenticación

**No hay autenticación en backend** (asume red privada).

Si necesitas agregar:
- Pasa a `core/security.py`
- Agrega decorador `@require_api_key` en endpoints
