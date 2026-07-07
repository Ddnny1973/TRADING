# QA Quick Reference - Tests Rápidos

## Resumen de 10 Tests

| # | Test | Duración | Pass Criteria |
|---|------|----------|---------------|
| 1 | Market Analysis | 1s | Devuelve ATR, SMA, trend |
| 2 | Create Grid | 2s | Grid status = RUNNING, 4 órdenes (config default) |
| 3 | Sync Orders | 1s | Órdenes sincronizadas con Binance |
| 4 | Replenish (Fills) | 2s | SELL creado después BUY |
| 5 | Stop Loss | 2s | Grid cierra con SL |
| 6 | Expiration | 3s | Grid cierra por edad |
| 7 | Min Notional | 1s | Órdenes >= 50 USDT notional |
| 8 | Min Step | 1s | Step >= 0.2% |
| 9 | Max Grids | 1s | 3ª grid rechazada |
| 10 | Health Check | 1s | Status = healthy |

**Total: ~20 minutos**

---

## TEST 1: Market Analysis

```bash
curl "http://localhost:8000/api/v1/market-analysis/BTCUSDT?atr_period=14&atr_multiplier=2.0&klines_interval=4h&risk_pct=0.05&levels=4"
```

**Pass:** 
- Status 200
- Tiene: current_price, atr, suggested_lower_price, suggested_upper_price
- Con levels pasado: suggested_quantity_per_order, allocated_capital, suggested_stop_loss, min_viable_quantity, grid_viable, required_risk_pct

**Fail:**
- Status != 200
- Falta ATR o precios sugeridos
- Binance API error

---

## TEST 2: Create Grid

```bash
GRID_ID=$(curl -s -X POST http://localhost:8000/api/v1/grids \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTCUSDT",
    "lower_price": 62500,
    "upper_price": 65000,
    "levels": 4,
    "quantity_per_order": 0.002,
    "grid_type": "GEOMETRIC",
    "stop_loss": 100.0
  }' | jq -r '.id')

echo "Grid ID: $GRID_ID"
```

**Pass:**
- id creado (UUID)
- status = "RUNNING"
- orders array con 4 órdenes
- Órdenes en Binance (verificar en https://testnet.binancefuture.com)

**Fail:**
- Step too small
- Max grids exceeded
- Notional too small

**Guarda $GRID_ID para tests posteriores.**

---

## TEST 3: Sync Orders (Refresh + Replenish)

```bash
curl -X POST "http://localhost:8000/api/v1/grids/$GRID_ID/refresh"
```

**Pass:**
- Status 200
- Devuelve GridDetailResponse con órdenes actualizadas
- Si hay fills, el backend crea órdenes opuestas automáticamente (replenish)

**Fail:**
- Grid not found
- Backend error

---

## TEST 4: Replenish (Ciclos)

**Prerequisito:** Debe haber al menos 1 BUY ejecutado.

```bash
# Si no hay fills, simula en Binance:
# 1. Abre https://testnet.binancefuture.com
# 2. Busca una orden BUY de tu grid
# 3. (Opcional) Ejecuta manualmente si es posible

# El replenish ocurre automáticamente dentro de /refresh:
curl -X POST "http://localhost:8000/api/v1/grids/$GRID_ID/refresh"
```

**Pass:**
- Status 200
- BD tiene órdenes SELL nuevas (creadas por replenish en backend)
- Verificar con: `curl http://localhost:8000/api/v1/grids/$GRID_ID`

**Fail:**
- Error en refresh
- No se crean órdenes opuestas a pesar de haber fills

---

## TEST 5: Stop Loss

El SL se configura al crear el grid (campo `stop_loss` en POST /api/v1/grids).

```bash
# El grid fue creado con stop_loss=100.0 en TEST 2
# Verifica que el campo existe:
curl "http://localhost:8000/api/v1/grids/$GRID_ID"
# Debe mostrar "stop_loss": 100.0 en la respuesta

# Para simular SL (esperar que PnL <= -100):
# Workflow 2 llama a /check-close y cierra automáticamente
# O manualmente:
curl -X POST "http://localhost:8000/api/v1/grids/$GRID_ID/check-close"
```

**Pass:**
- Grid tiene stop_loss configurado
- Workflow 2 detecta SL y cierra grid (status → CANCELED)
- Telegram notifica con "❌ Stop Loss"

**Fail:**
- Grid no cierra cuando PnL cae
- stop_loss es null

---

## TEST 6: Expiration (Max Duration)

```bash
# Crea grid nuevo
GRID2=$(curl -s -X POST http://localhost:8000/api/v1/grids \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTCUSDT",
    "lower_price": 62500,
    "upper_price": 65000,
    "levels": 4,
    "quantity_per_order": 0.002,
    "grid_type": "GEOMETRIC"
  }' | jq -r '.id')

# Espera 2 minutos (simula tiempo)
# O en BD, actualiza created_at a hace 225 horas:
docker-compose exec backend-python sqlite3 grid_trading.db \
  "UPDATE grids SET created_at = datetime('now', '-225 hours') WHERE id = '$GRID2'"

# Ejecuta Workflow 2 (monitoreo)
# Grid debe cerrarse automáticamente
curl http://localhost:8000/grids/$GRID2
# status = "CLOSED"
```

**Pass:**
- Grid cierra automáticamente
- status = "CLOSED"

**Fail:**
- Grid no cierra
- Status != "CLOSED"

---

## TEST 7: Min Notional

```bash
# Intenta crear grid con quantity_per_order muy pequeña (< 50/62500 = 0.0008 BTC)
curl -X POST http://localhost:8000/api/v1/grids \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTCUSDT",
    "lower_price": 62500,
    "upper_price": 65000,
    "levels": 4,
    "quantity_per_order": 0.0001,
    "grid_type": "GEOMETRIC"
  }'
```

**Pass:**
- Status 400 (rechazado por notional < 50 USDT)
- Error describe el problema

**Fail:**
- Grid se crea (notional no validado)
- Status = 200

---

## TEST 8: Min Step

```bash
curl -X POST http://localhost:8000/api/v1/grids \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTCUSDT",
    "lower_price": 62500,
    "upper_price": 62510,
    "levels": 15,
    "quantity_per_order": 0.01,
    "grid_type": "ARITHMETIC"
  }'
```

**Pass:**
- Status 400
- error_code = "STEP_TOO_SMALL"

**Fail:**
- Grid se crea (step no validado)
- Status = 200

---

## TEST 9: Max Grids (Límite de Concurrencia)

```bash
# Crea grid 1 (BTCUSDT)
GRID1=$(curl -s -X POST http://localhost:8000/api/v1/grids -H "Content-Type: application/json" -d '{"symbol":"BTCUSDT","lower_price":62500,"upper_price":65000,"levels":4,"quantity_per_order":0.002,"grid_type":"GEOMETRIC"}' | jq -r '.id')

# Crea grid 2 (ETHUSDT, diferente símbolo)
GRID2=$(curl -s -X POST http://localhost:8000/api/v1/grids -H "Content-Type: application/json" -d '{"symbol":"ETHUSDT","lower_price":3000,"upper_price":3200,"levels":4,"quantity_per_order":0.05,"grid_type":"GEOMETRIC"}' | jq -r '.id')

# Intenta crear grid 3 (cualquier símbolo - debe ser rechazado)
curl -X POST http://localhost:8000/api/v1/grids -H "Content-Type: application/json" -d '{"symbol":"SOLUSDT","lower_price":150,"upper_price":170,"levels":4,"quantity_per_order":1.0,"grid_type":"GEOMETRIC"}'
```

**Pass:**
- Grid 1 y 2: Status 200 ✅
- Grid 3: Status 409, error = "MAX_GRIDS_EXCEEDED"

**Fail:**
- Grid 3 se crea (límite no respetado)
- Status = 200

---

## TEST 10: Health Check

```bash
curl http://localhost:8000/health
```

**Pass:**
- Status 200
- status = "healthy"
- database = "connected"
- binance_api = "reachable"

**Fail:**
- Status != 200
- Algún componente = "error"

---

## Escenario 48 Horas

**Duración:** 48 horas  
**Objetivo:** Validar estabilidad + PnL positivo

### Setup

```bash
# Día 1
1. Crea grid 1 (BTC)
2. Crea grid 2 (ETH) después 4h
3. Monitorea Workflow 2 cada 5 min (automático)
4. Revisa logs cada 4h
```

### Monitorear

```bash
# Cada 4 horas:
curl "http://localhost:8000/api/v1/grids?status=RUNNING" | jq '.[] | {id, status, levels}'

# Ver última ejecución de Workflow 2:
docker logs n8n | tail -50 | grep "Workflow 2"
```

### Success Criteria (48h)

| Métrica | Pass | Fail |
|---------|------|------|
| Uptime | > 95% | < 95% |
| Crashes | 0 | >= 1 |
| PnL total | > 0 | <= 0 |
| Cycles | >= 5 | < 5 |
| SL triggers | <= 1 | >= 2 |

### Report

Documenta en `qa-results-48h.md`:
```markdown
# QA Results - 48 Hours

**Period:** 2026-07-05 to 2026-07-07

## Summary
- Uptime: 100%
- PnL: +2.5%
- Cycles: 12
- Errors: 0

## Grids
- GRID1 (BTC): PnL +1.2%, cycles 6
- GRID2 (ETH): PnL +1.3%, cycles 6

## Issues
- None

## Conclusion
✅ Ready for production
```

---

## Comandos Útiles

### Ver logs
```bash
docker-compose logs -f backend-python
docker-compose logs -f n8n
```

### Ver BD
```bash
docker-compose exec backend-python sqlite3 grid_trading.db \
  "SELECT id, symbol, status FROM grids;"
```

### Limpiar (nuclear)
```bash
docker-compose down
rm backend-python/grid_trading.db
docker-compose up -d
```

### Health script
```bash
#!/bin/bash
while true; do
  echo "=== $(date) ==="
  curl -s http://localhost:8000/health | jq .
  sleep 60
done
```

---

## Si Falla Test

1. **Revisa logs:** `docker logs backend-python`
2. **Reinicia backend:** `docker-compose restart backend-python`
3. **Check API key:** `curl "http://localhost:8000/api/v1/market-analysis/BTCUSDT?risk_pct=0.05&levels=4"` (si devuelve balance → API key OK)
4. **Limpiar BD:** `rm backend-python/grid_trading.db && docker-compose restart`
5. **Lee [Troubleshooting](01-troubleshooting.md)**

---

## Pass/Fail Decision

| Tests Passed | Decision |
|--------------|----------|
| >= 9/10 + 48h OK | ✅ Ready for production |
| 8/10 | ⚠️ Review issues |
| < 8/10 | ❌ Fix and re-test |

---

Ver también: [Verificación](03-verificacion.md) | [Troubleshooting](01-troubleshooting.md)
