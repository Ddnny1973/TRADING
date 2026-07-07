# Verificación - Tests de Integración

## Pre-requisitos

- ✅ Backend corriendo (`docker-compose ps`)
- ✅ n8n corriendo
- ✅ `/health` devuelve OK
- ✅ API key/secret configurados

---

## Test 1: Health Check

Verifica que el sistema está vivo.

```bash
curl http://localhost:8000/health
```

**Respuesta esperada:**
```json
{
  "status": "healthy",
  "service": "grid-trading-backend",
  "version": "0.1.0",
  "binance_synced": true,
  "time_offset_ms": 15
}
```

**Si falla:**
- Backend no está corriendo: `docker-compose up -d`
- API key inválida: revisa `.env`
- Binance API caída: espera

---

## Test 2: Market Analysis

Obtiene datos de mercado (ATR, precios sugeridos, capital + SL automático, viabilidad).

```bash
# GET (no POST), con query params — incluir levels para obtener campos de viabilidad
curl "http://localhost:8000/api/v1/market-analysis/BTCUSDT?atr_period=14&atr_multiplier=2.0&klines_interval=4h&risk_pct=0.05&levels=4"
```

**Respuesta esperada (con levels pasado):**
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

**Si falla:**
- Endpoint incorrecto: debe ser `/api/v1/market-analysis/BTCUSDT` (GET, no POST)
- Symbol no encontrado: usa "BTCUSDT" o "ETHUSDT"
- Klines no disponibles: Binance API error, revisa logs

---

## Test 3: Create Grid

Crea una grid (conjunto de órdenes).

```bash
curl -X POST http://localhost:8000/api/v1/grids \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTCUSDT",
    "lower_price": 62500,
    "upper_price": 65000,
    "levels": 4,
    "quantity_per_order": 0.002,
    "grid_type": "GEOMETRIC",
    "stop_loss": 100.0
  }'
```

**Respuesta esperada:**
```json
{
  "id": "uuid-grid-001",
  "symbol": "BTCUSDT",
  "status": "RUNNING",
  "lower_price": 62500,
  "upper_price": 65000,
  "levels": 4,
  "stop_loss": 100.0,
  "orders": [...],
  "created_at": "2026-07-05T20:22:00Z"
}
```

**Si falla:**
- `"error": "Step size 0.1% is less than minimum 0.2%"` → aumenta range
- `"error": "Max concurrent grids reached"` → cierra una grid
- `"error": "Notional too small"` → aumenta capital/cantidad
- Revisa logs

**Guarda el grid_id para tests posteriores.**

---

## Test 4: List Grids

Lista las grids activas.

```bash
curl "http://localhost:8000/api/v1/grids"
curl "http://localhost:8000/api/v1/grids?status=RUNNING"
```

**Respuesta esperada:**
```json
[
  {
    "id": "uuid-grid-001",
    "symbol": "BTCUSDT",
    "status": "RUNNING",
    "lower_price": 62500,
    "upper_price": 65000,
    "levels": 4,
    "created_at": "2026-07-05T20:22:00Z"
  }
]
```

---

## Test 5: Get Grid Detail

Obtiene detalle de una grid con órdenes.

```bash
# Reemplaza GRID_ID con el id del Test 3
curl "http://localhost:8000/api/v1/grids/GRID_ID"
```

**Respuesta esperada:** GridDetailResponse con array `orders[]`, cada orden con `status: "NEW"` o `"FILLED"`.

---

## Test 6: Refresh Grid

Sincroniza órdenes con Binance (sync + replenish en un solo endpoint).

```bash
curl -X POST "http://localhost:8000/api/v1/grids/GRID_ID/refresh"
```

**Respuesta esperada:** GridDetailResponse actualizado. Si no hay fills aún, `executed_qty: 0` en todas las órdenes.

---

## Test 7: Get PnL

Obtiene ganancias/pérdidas (neto, ya deducidas fees 0.02%).

```bash
curl "http://localhost:8000/api/v1/grids/GRID_ID/pnl"
```

**Respuesta esperada:**
```json
{
  "grid_id": "uuid-grid-001",
  "realized_pnl": 0.0,
  "unrealized_pnl": 0.0,
  "total_pnl": 0.0,
  "net_position_qty": 0.0,
  "filled_buy_qty": 0.0,
  "filled_sell_qty": 0.0,
  "current_price": 63500.0
}
```

---

## Test 8: Check Close

Evalúa si el grid debe cerrarse (SL/TP/EXPIRED).

```bash
curl -X POST "http://localhost:8000/api/v1/grids/GRID_ID/check-close"
```

**Respuesta esperada (sin trigger):**
```json
{
  "triggered": null,
  "grid": { "status": "RUNNING", ... }
}
```

---

## Test 9: Cancel Grid (Manual Close)

Cierra el grid manualmente (cancela todas las órdenes).

```bash
curl -X DELETE "http://localhost:8000/api/v1/grids/GRID_ID"
```

**Respuesta esperada:**
```json
{
  "id": "uuid-grid-001",
  "status": "CANCELED",
  "orders": [...],
  "created_at": "2026-07-05T20:22:00Z"
}
```

---

## Test 10: n8n Workflow 1

Prueba el workflow de Market Decision.

**Paso a paso:**
1. Abre http://localhost:5678
2. Busca "Workflow 1" (Market Decision)
3. Click **Execute** (▶️ button)
4. Espera a que termine (~30 seg)
5. Revisa el output:
   - ✅ Market analysis devuelve datos (incluyendo grid_viable)
   - ✅ IF: Grid viable? → TRUE pasa a Gemini
   - ✅ Gemini devuelve decisión (launch: true/false)
   - ✅ Si launch=true: grid creada

**Resultado esperado:**
- Grid creada en backend
- Telegram notificación recibida
- Status RUNNING (no ACTIVE)

---

## Test 11: n8n Workflow 2

Prueba el workflow de Monitoring.

**Paso a paso:**
1. Abre http://localhost:5678
2. Busca "Workflow 2 - Grid Monitor & Close"
3. Click **Execute**
4. Espera a que termine (~5 seg)
5. Revisa el output:
   - ✅ GET /api/v1/grids?status=RUNNING devuelve grids
   - ✅ POST /refresh actualiza órdenes (+ replenish si hay fills)
   - ✅ POST /check-close evalúa SL/TP/EXPIRED

**Resultado esperado:**
- Sin errores
- Si hay grids RUNNING: se procesan todas
- Si no hay grids RUNNING: Telegram "Sin grids en ejecución"

---

## Test 12: BD Persistence

Verifica que datos se guardan.

```bash
docker-compose exec backend-python sqlite3 grid_trading.db "SELECT COUNT(*) FROM grids;"
```

Deberías ver: `1` (la grid que creaste)

```bash
docker-compose exec backend-python sqlite3 grid_trading.db "SELECT COUNT(*) FROM orders;"
```

Deberías ver el número de órdenes del grid (= levels configurados)

---

## Test 13: Rate Limiting

Verifica que el sistema respeta rate limits de Binance.

```bash
# Ejecuta 50 requests rápidos (debe manejar sin 429)
for i in {1..50}; do
  curl http://localhost:8000/health
done
```

Esperado: Todos 200 OK (no 429 errors)

---

## Checklist de Verificación

- [ ] Test 1: Health OK
- [ ] Test 2: Market Analysis OK (con grid_viable)
- [ ] Test 3: Grid creada con status RUNNING
- [ ] Test 4: Grids listadas por status=RUNNING
- [ ] Test 5: Grid detail con órdenes
- [ ] Test 6: Refresh sin errores
- [ ] Test 7: PnL consultas OK
- [ ] Test 8: Check-close devuelve triggered: null
- [ ] Test 9: Grid cancela sin errores
- [ ] Test 10: Workflow 1 ejecuta (manual)
- [ ] Test 11: Workflow 2 ejecuta (manual)
- [ ] Test 12: BD tiene datos
- [ ] Test 13: Rate limiting OK

---

## Si Falla Algo

1. **Backend issues:**
   - `docker-compose logs backend-python`
   - Reinicia: `docker-compose restart backend-python`

2. **API key issues:**
   - Verifica `.env` BINANCE_API_KEY/SECRET
   - En Binance: API Management → Regenerate key

3. **Binance API issues:**
   - Espera (rate limit temporal)
   - Verifica internet
   - Verifica IP whitelist

4. **n8n issues:**
   - Revisa Environment Variables
   - Reinicia n8n: `docker-compose restart n8n`
   - Verifica URLs en HTTP nodes

---

## Próximos Pasos

✅ Verificación completada → Listo para QA manual

Lee: [QA Quick Reference](../40-OPERACIONAL/03-qa-quick-reference.md)
