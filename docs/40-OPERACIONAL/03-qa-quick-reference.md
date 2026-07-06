# QA Quick Reference - Tests Rápidos

## Resumen de 10 Tests

| # | Test | Duración | Pass Criteria |
|---|------|----------|---------------|
| 1 | Market Analysis | 1s | Devuelve ATR, SMA, trend |
| 2 | Create Grid | 2s | Grid status = ACTIVE, 15 órdenes |
| 3 | Sync Orders | 1s | Órdenes sincronizadas con Binance |
| 4 | Replenish (Fills) | 2s | SELL creado después BUY |
| 5 | Stop Loss | 2s | Grid cierra con SL |
| 6 | Expiration | 3s | Grid cierra por edad |
| 7 | Min Notional | 1s | Órdenes >= 10 USDT |
| 8 | Min Step | 1s | Step >= 0.2% |
| 9 | Max Grids | 1s | 3ª grid rechazada |
| 10 | Health Check | 1s | Status = healthy |

**Total: ~20 minutos**

---

## TEST 1: Market Analysis

```bash
curl -X POST http://localhost:8000/market-analysis \
  -H "Content-Type: application/json" \
  -d '{"symbol": "BTCUSDT", "interval": "4h"}'
```

**Pass:** 
- Status 200
- Tiene: current_price, atr, sma, trend
- trend = "bullish" o "bearish"

**Fail:**
- Status != 200
- Falta ATR/SMA
- Binance API error

---

## TEST 2: Create Grid

```bash
GRID_ID=$(curl -s -X POST http://localhost:8000/create-grid \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTCUSDT",
    "lower_price": 62500,
    "upper_price": 65000,
    "levels": 15,
    "risk_pct": 0.02
  }' | jq -r '.grid_id')

echo "Grid ID: $GRID_ID"
```

**Pass:**
- grid_id creado (formato: GRID_YYYYMMDD_XXX)
- status = "ACTIVE"
- orders_created = 15
- Órdenes en Binance (verificar en https://testnet.binancefuture.com)

**Fail:**
- Step too small
- Max grids exceeded
- Notional too small

**Guarda $GRID_ID para tests posteriores.**

---

## TEST 3: Sync Orders

```bash
curl -X POST http://localhost:8000/refresh-grid/$GRID_ID
```

**Pass:**
- Status 200
- orders_synced = 15
- orders_filled >= 0

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

# Luego replenish:
curl -X POST http://localhost:8000/replenish-grid/$GRID_ID
```

**Pass:**
- Status 200
- orders_replenished >= 1
- BD tiene SELL nuevas (verificar con sqlite3)

**Fail:**
- 0 replenished (sin fills)
- Backend error

---

## TEST 5: Stop Loss

```bash
curl -X POST http://localhost:8000/set-stop-loss/$GRID_ID \
  -H "Content-Type: application/json" \
  -d '{"stop_loss_pct": 0.02}'
```

**Pass:**
- status = "ACTIVE" (aún)
- stop_loss_price calculado correctamente

Luego simula SL:
```bash
# En Binance, baja precio por debajo de stop_loss_price
# Workflow 2 debe detectar y cerrar grid

# Verifica (después 15 min):
curl http://localhost:8000/grids/$GRID_ID
# status debe cambiar a CLOSED
```

**Fail:**
- Grid no cierra
- Status != "CLOSED"

---

## TEST 6: Expiration (Max Duration)

```bash
# Crea grid nuevo
GRID2=$(curl -s -X POST http://localhost:8000/create-grid \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTCUSDT",
    "lower_price": 62500,
    "upper_price": 65000,
    "levels": 15,
    "risk_pct": 0.02
  }' | jq -r '.grid_id')

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
# Intenta crear grid con cantidad muy pequeña
curl -X POST http://localhost:8000/create-grid \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTCUSDT",
    "lower_price": 62500,
    "upper_price": 62550,  # Rango muy pequeño
    "levels": 15,
    "risk_pct": 0.001       # Risk muy bajo
  }'
```

**Pass:**
- Status 400
- error_code = "NOTIONAL_TOO_SMALL"

**Fail:**
- Grid se crea (notional no validado)
- Status = 200

---

## TEST 8: Min Step

```bash
curl -X POST http://localhost:8000/create-grid \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTCUSDT",
    "lower_price": 62500,
    "upper_price": 62510,  # Step = 0.08% < 0.2%
    "levels": 15,
    "risk_pct": 0.02
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
# Crea grid 1
GRID1=$(curl -s -X POST http://localhost:8000/create-grid -H "Content-Type: application/json" -d '{...}' | jq -r '.grid_id')

# Crea grid 2
GRID2=$(curl -s -X POST http://localhost:8000/create-grid -H "Content-Type: application/json" -d '{...}' | jq -r '.grid_id')

# Intenta crear grid 3
curl -X POST http://localhost:8000/create-grid -H "Content-Type: application/json" -d '{...}'
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
3. Monitorea Workflow 2 cada 15 min
4. Revisa logs cada 4h
```

### Monitorear

```bash
# Cada 4 horas:
curl http://localhost:8000/grids?status=ACTIVE | jq '.[] | {grid_id, pnl_realized, orders_total}'

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
  "SELECT grid_id, status, pnl_realized FROM grids;"
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
3. **Check API key:** `curl http://localhost:8000/account`
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
