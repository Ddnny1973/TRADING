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
  "uptime_seconds": 1234,
  "database": "connected",
  "binance_api": "reachable"
}
```

**Si falla:**
- Backend no está corriendo: `docker-compose up -d`
- API key inválida: revisa `.env`
- Binance API caída: espera

---

## Test 2: Market Analysis

Obtiene datos de mercado (ATR, SMA, precio actual).

```bash
curl -X POST http://localhost:8000/market-analysis \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTCUSDT",
    "interval": "4h",
    "atr_period": 14,
    "sma_period": 50
  }'
```

**Respuesta esperada:**
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

**Si falla:**
- Symbol incorrecto: usa "BTCUSDT" (con testnet)
- Binance API error: revisa logs

---

## Test 3: Account

Obtiene balance y posiciones.

```bash
curl http://localhost:8000/account
```

**Respuesta esperada:**
```json
{
  "balance_usdt": 10000.00,
  "available_usdt": 9800.00,
  "max_leverage": 125,
  "current_leverage": 1,
  "total_positions": 0,
  "positions": []
}
```

**Si falla:**
- API key inválida: Binance devuelve 401
- Sin fondos: balance_usdt = 0 (carga saldo en testnet)
- Revisa logs: `docker logs backend-python`

---

## Test 4: Create Grid

Crea una grid (conjunto de órdenes).

```bash
curl -X POST http://localhost:8000/create-grid \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTCUSDT",
    "lower_price": 62500,
    "upper_price": 65000,
    "levels": 15,
    "risk_pct": 0.02
  }'
```

**Respuesta esperada:**
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

**Si falla:**
- `"error": "Step size 0.1% is less than minimum 0.2%"` → aumenta range
- `"error": "Max concurrent grids reached"` → cierra una grid
- `"error": "Notional too small"` → aumenta capital/cantidad
- Revisa logs

**Guarda el grid_id para tests posteriores.**

---

## Test 5: List Grids

Lista las grids activas.

```bash
curl http://localhost:8000/grids
curl http://localhost:8000/grids?status=ACTIVE
```

**Respuesta esperada:**
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
      "pnl_realized": 0.00,
      "created_at": "2026-07-05T20:22:00Z"
    }
  ],
  "total": 1
}
```

---

## Test 6: Get Orders

Lista las órdenes de una grid.

```bash
# Reemplaza GRID_ID con tu grid_id del Test 4
curl http://localhost:8000/grids/GRID_20260705_001/orders
```

**Respuesta esperada:**
```json
{
  "grid_id": "GRID_20260705_001",
  "orders": [
    {
      "order_id": "123456789",
      "symbol": "BTCUSDT",
      "type": "BUY",
      "status": "OPEN",
      "quantity": 0.01,
      "price": 62500.00,
      "created_at": "2026-07-05T20:22:00Z"
    },
    ...15 órdenes totales
  ],
  "total": 15
}
```

---

## Test 7: Refresh Grid

Sincroniza órdenes con Binance (revisa cuáles se ejecutaron).

```bash
curl -X POST http://localhost:8000/refresh-grid/GRID_20260705_001
```

**Respuesta esperada:**
```json
{
  "grid_id": "GRID_20260705_001",
  "status": "ACTIVE",
  "orders_synced": 15,
  "orders_filled": 0,
  "timestamp": "2026-07-05T20:25:00Z"
}
```

(Si no hay fills aún, orders_filled = 0, es normal)

---

## Test 8: Set Stop Loss

Configura stop loss para la grid.

```bash
curl -X POST http://localhost:8000/set-stop-loss/GRID_20260705_001 \
  -H "Content-Type: application/json" \
  -d '{"stop_loss_pct": 0.02}'
```

**Respuesta esperada:**
```json
{
  "grid_id": "GRID_20260705_001",
  "stop_loss_pct": 0.02,
  "stop_loss_price": 61250.00,
  "status": "ACTIVE"
}
```

---

## Test 9: Get PnL

Obtiene ganancias/pérdidas.

```bash
curl http://localhost:8000/pnl/GRID_20260705_001
```

**Respuesta esperada:**
```json
{
  "grid_id": "GRID_20260705_001",
  "pnl_realized": 0.00,
  "pnl_unrealized": 0.00,
  "pnl_total": 0.00,
  "pnl_pct": 0.00,
  "fees_paid": 0.00,
  "timestamp": "2026-07-05T20:25:00Z"
}
```

---

## Test 10: Close Grid

Cierra la grid (cancela todas las órdenes).

```bash
curl -X POST http://localhost:8000/close-grid/GRID_20260705_001
```

**Respuesta esperada:**
```json
{
  "grid_id": "GRID_20260705_001",
  "status": "CLOSED",
  "orders_canceled": 15,
  "pnl_realized": 0.00,
  "closed_at": "2026-07-05T20:30:00Z"
}
```

---

## Test 11: n8n Workflow 1

Prueba el workflow de Market Decision.

**Paso a paso:**
1. Abre http://localhost:5678
2. Busca "Workflow 1" (Market Decision)
3. Click **Execute** (▶️ button)
4. Espera a que termine (~30 seg)
5. Revisa el output:
   - ✅ Market analysis devuelve datos
   - ✅ IA devuelve decisión (bullish/bearish)
   - ✅ Si bullish: grid creada

**Resultado esperado:**
- Grid creada en backend
- Telegram notificación recibida
- Status ACTIVE

---

## Test 12: n8n Workflow 2

Prueba el workflow de Monitoring.

**Paso a paso:**
1. Abre http://localhost:5678
2. Busca "Workflow 2" (Monitor)
3. Click **Execute**
4. Espera a que termine (~5 seg)
5. Revisa el output:
   - ✅ Grids monitoreadas
   - ✅ Órdenes sincronizadas
   - ✅ (Si hay fills) Órdenes replenished

**Resultado esperado:**
- Sin errores
- Telegram notificación con resumen

---

## Test 13: BD Persistence

Verifica que datos se guardan.

```bash
docker-compose exec backend-python sqlite3 grid_trading.db "SELECT COUNT(*) FROM grids;"
```

Deberías ver: `1` (la grid que creaste)

```bash
docker-compose exec backend-python sqlite3 grid_trading.db "SELECT COUNT(*) FROM orders;"
```

Deberías ver: `15` (las 15 órdenes)

---

## Test 14: Rate Limiting

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
- [ ] Test 2: Market Analysis OK
- [ ] Test 3: Account balance > 0
- [ ] Test 4: Grid creada
- [ ] Test 5: Grids listadas
- [ ] Test 6: Órdenes listadas (15)
- [ ] Test 7: Refresh sin errores
- [ ] Test 8: SL setado
- [ ] Test 9: PnL consultas OK
- [ ] Test 10: Grid cierra sin errores
- [ ] Test 11: Workflow 1 ejecuta (manual)
- [ ] Test 12: Workflow 2 ejecuta (manual)
- [ ] Test 13: BD tiene datos
- [ ] Test 14: Rate limiting OK

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
