# API Endpoints Reference

## Base URL
```
http://localhost:8000
```
(o el puerto mapeado en `docker-compose.yml`, p. ej. `8043` en despliegue)

## Health & Status

### Health Check
```
GET /health
```
**Descripción:** Estado del servicio para el healthcheck de Docker.

**Respuesta:**
```json
{
  "status": "healthy",
  "service": "grid-trading-backend",
  "version": "0.1.0"
}
```

### API Information
```
GET /
```
**Descripción:** Metadata del servicio y enlace a documentación.

**Respuesta:**
```json
{
  "service": "Grid Trading Hybrid - Backend",
  "status": "ready",
  "api_version": "v1",
  "docs": "/api/docs"
}
```

---

## Market Analysis (read-only, implementado)

### Analizar condiciones de mercado
```
GET /api/v1/market-analysis/{symbol}
```
Consulta el precio actual, calcula ATR, y sugiere bounds para un grid sin crear órdenes. Pensado para que orquestadores (n8n, agentes IA) evalúen condiciones antes de decidir si lanzar un grid. No toca Binance más que para leer datos públicos.

**Parámetros query:**
- `atr_period` (int, default 14): períodos de True Range para ATR
- `atr_multiplier` (float, default 2.0): multiplicador del ATR para ancho del grid
- `klines_interval` (str, default "4h"): intervalo de velas para ATR

**Respuesta:** `200` — `MarketAnalysisResponse`:
```json
{
  "symbol": "BTCUSDT",
  "current_price": 42500.0,
  "atr": 200.0,
  "atr_period": 14,
  "atr_multiplier": 2.0,
  "klines_interval": "4h",
  "suggested_lower_price": 42100.0,
  "suggested_upper_price": 42900.0,
  "suggested_range": 800.0
}
```

---

## Grid Trading Endpoints (implementados)

### Crear Grid
```
POST /api/v1/grids
```
Calcula los niveles, coloca las órdenes LIMIT en Binance (en lotes de hasta 5) y persiste el grid en SQLite.

**Body:**
```json
{
  "symbol": "BTCUSDT",
  "lower_price": 40000.0,
  "upper_price": 45000.0,
  "levels": 10,
  "grid_type": "GEOMETRIC",
  "quantity_per_order": 0.001,
  "stop_loss": null,
  "take_profit": null,
  "atr_period": 14,
  "atr_multiplier": 2.0,
  "klines_interval": "4h"
}
```
- `lower_price`/`upper_price` son opcionales: si se omiten **ambos**, se calculan automáticamente a partir del ATR(`atr_period`) de las velas `klines_interval`. Enviar solo uno de los dos → `400`.
- `stop_loss`/`take_profit`: umbral de PnL (en moneda de cotización) para auto-cierre vía `/check-close`. Opcionales.
- Solo puede existir **un grid `RUNNING` por símbolo a la vez** — crear otro mientras el anterior sigue activo devuelve `400`.

**Respuesta:** `200` — `GridDetailResponse` (grid + `orders[]`). Errores de validación de negocio (bounds incompletos, cantidad/levels inválidos, símbolo no encontrado en Binance, grid duplicado) devuelven `400` con `detail`.

### Listar Grids
```
GET /api/v1/grids
```

**Query params:**
- `status` (optional): Filtrar por estado — `RUNNING`, `CANCELED`, etc. Omitir para listar todos.

**Respuesta:** `200` — array de `GridResponse` (sin `orders[]`). Ejemplo:
```json
[
  {
    "id": "grid-123",
    "symbol": "BTCUSDT",
    "lower_price": 40000.0,
    "upper_price": 45000.0,
    "levels": 10,
    "status": "RUNNING",
    "stop_loss": null,
    "take_profit": null,
    "created_at": "2026-07-02T10:30:00"
  }
]
```

**Ejemplos:**
- `GET /api/v1/grids` → todos los grids
- `GET /api/v1/grids?status=RUNNING` → solo grids activos (para monitoreo)
- `GET /api/v1/grids?status=CANCELED` → grids cerrados

### Detalle de Grid
```
GET /api/v1/grids/{grid_id}
```
**Respuesta:** `200` — `GridDetailResponse` (incluye `orders[]`). `404` si no existe.

### Cancelar Grid
```
DELETE /api/v1/grids/{grid_id}
```
Cancela en Binance todas las órdenes del grid en estado `NEW` y marca el grid como `CANCELED`. Registra el cierre en `historical_grid_logs` (Postgres) con `trigger_condition = "MANUAL"`; el fallo al escribir en Postgres no bloquea la cancelación. Idempotente: repetir la llamada sobre un grid ya `CANCELED` devuelve `200` sin error.

**Respuesta:** `200` — `GridDetailResponse`. `404` si no existe.

### Refrescar estado de órdenes
```
POST /api/v1/grids/{grid_id}/refresh
```
Consulta en Binance el estado actual de cada orden no terminal del grid y actualiza SQLite. No interpreta el resultado (no calcula PnL ni evalúa SL/TP). Pensado para ser invocado periódicamente por un orquestador externo — no hay scheduler interno.

**Respuesta:** `200` — `GridDetailResponse`. `404` si no existe.

### PnL del Grid
```
GET /api/v1/grids/{grid_id}/pnl
```
Calcula PnL realizado/no realizado a partir del estado local de las órdenes (solo cuentan las `FILLED`) y el mark price actual. No llama a `/refresh` automáticamente.

**Respuesta:** `200` — `GridPnlResponse` (`realized_pnl`, `unrealized_pnl`, `total_pnl`, `net_position_qty`, `filled_buy_qty`, `filled_sell_qty`, `current_price`). `404` si no existe.

### Chequear cierre por SL/TP
```
POST /api/v1/grids/{grid_id}/check-close
```
Compara el PnL actual contra `stop_loss`/`take_profit` del grid; si se dispara, cancela el grid (mismo efecto que `DELETE`, con `trigger_condition = "STOP_LOSS"` o `"TAKE_PROFIT"`). Si el grid ya no está `RUNNING`, responde `triggered: null` sin recalcular PnL. No llama a `/refresh` automáticamente.

**Respuesta:** `200` — `{"triggered": "STOP_LOSS" | "TAKE_PROFIT" | null, "grid": GridDetailResponse}`. `404` si no existe.

---

## Documentación

- **Swagger UI:** `/api/docs`
- **ReDoc:** `/api/redoc`
- **Plan de pruebas manual (Swagger):** [`manual-test-plan-swagger.md`](./manual-test-plan-swagger.md)
