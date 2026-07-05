# Fixes Applied — Production Audit (2026-07-05)

**Veredicto anterior:** NO-GO (1 bug crítico de runtime, 23 tests fallando)  
**Veredicto después de fixes:** READY FOR SOAK & QA (bloqueantes de código resueltos)

---

## Problemas Críticos Arreglados

### N1 — Bug de runtime en /refresh (CRITICAL)
**Problema:** Línea 270 de `main.py` hace `await grid_service.get_grid(grid_id)` pero `get_grid()` es síncrona.
- **Síntoma:** TypeError → HTTP 500 exactamente cuando la reposición de órdenes funciona
- **Impacto:** WF2 falla en check-close ese ciclo; grid se queda RUNNING indefinidamente

**Fix aplicado:** ✅
```python
# ANTES:
grid = await grid_service.get_grid(grid_id)

# DESPUÉS:
grid = grid_service.get_grid(grid_id)
```
**Archivo:** `backend-python/app/main.py:270`

---

### N2 — Math.max inflando posicionamiento (CRITICAL)
**Problema:** WF1 tenía `Math.max($json.suggested_qty, 65/avgPrice)` en Create Grid POST.
- **Síntoma:** Si cantidad sugerida < 65/avgPrice, usa el piso de 65 USDT (ignora risk_pct)
- **Impacto:** Sobre-exposición en órdenes pequeñas, bypass de risk management

**Fix aplicado:** ✅
```javascript
// ANTES:
quantity_per_order: Math.max($json.suggested_quantity_per_order || 0, (65 / (($json.lowerLimit + $json.upperLimit) / 2)))

// DESPUÉS:
quantity_per_order: $json.suggested_quantity_per_order
```
**Archivo:** `n8n-workflows/workflow1-market-decision.json` (nodo "Create Grid (POST)")

**Nota:** El backend ya valida min-notional en `validate_grid_step()` usando comisiones reales.

---

### N3 — PnL sin deducción de fees (CRITICAL)
**Problema:** `calculate_grid_pnl()` calculaba PnL bruto; SL/TP decidía sobre ganancias infladas.
- **Síntoma:** Grid con PnL bruto +$10 y comisiones -$8 se cierra por SL cuando PnL neto = +$2
- **Impacto:** SL/TP inapropiados; decisiones basadas en PnL falso

**Fix aplicado:** ✅
```python
# Firma actualizada:
def calculate_grid_pnl(orders, current_price, fee_rate=Decimal("0.0002"))

# Cálculo de fees en realized_pnl:
buy_fees = matched_qty * avg_buy_price * fee_rate
sell_fees = matched_qty * avg_sell_price * fee_rate
realized_pnl = matched_qty * (avg_sell_price - avg_buy_price) - buy_fees - sell_fees
```
**Archivo:** `backend-python/app/services/indicators.py:121`

**Fee rate por defecto:** 0.02% (0.0002) — blend maker/taker de Binance Futures

---

### N4 — Workflows duplicados y desincronizados (CRITICAL)
**Problema:** `workflow1-updated.json` (obsoleto, tiene `stop_loss: null`) convivía con versión correcta.
- **Síntoma:** Importar el archivo equivocado en n8n reintroduce el deadlock de Fase 0
- **Impacto:** Workflow no propaga suggested_stop_loss

**Fix aplicado:** ✅
- ✅ Borrado: `n8n-workflows/workflow1-updated.json`
- ✅ Vigente: `n8n-workflows/workflow1-market-decision.json` (con todos los fixes)

---

## Datos Cruciales Para El Equipo QA

### Base de Datos: Migración requerida (si no se resetea)
**Archivo:** `backend-python/app/database/migration_001_executed_qty.py`

**Problema:** Órdenes FILLED creadas antes del campo `executed_qty` reportan PnL = 0.

**Solución:**
```bash
cd backend-python
python -m app.database.migration_001_executed_qty
# O ejecutar directamente en SQLite:
UPDATE grid_orders SET executed_qty = quantity WHERE status = 'FILLED' AND executed_qty = 0;
```

**Cuándo correr:**
- ✅ Si la BD se resetea antes de producción: NO NECESARIO
- ⚠️ Si se mantiene la BD de testnet: OBLIGATORIO antes del GO
- ✅ Idempotente: Seguro ejecutar múltiples veces

---

## Checklist: Listo Para QA

- [x] N1 fix: Quitar await sobre función síncrona
- [x] N2 fix: Quitar Math.max que infla cantidad
- [x] N3 fix: Descontar fees en PnL
- [x] N4 fix: Borrar workflow obsoleto
- [x] Migration: Script de backfill de executed_qty listo
- [ ] **Próximo:** Suite de tests en verde (23 tests fallando actualmente)
- [ ] **Próximo:** Runbook QA de testnet (2-4 semanas soak)
- [ ] **Próximo:** Verificar que WF2 recibe 200 en /refresh (no 500)

---

## Estatus de Bloqueantes

| Bloqueante | Severidad | Antes | Después | Acción |
|-----------|-----------|-------|---------|--------|
| N1: await sync get_grid | CRÍTICA | ❌ | ✅ | Fixed |
| N2: Math.max inflation | CRÍTICA | ❌ | ✅ | Fixed |
| N3: PnL sin fees | CRÍTICA | ❌ | ✅ | Fixed |
| N4: Duplicate workflows | CRÍTICA | ❌ | ✅ | Fixed |
| Tests en rojo (23/58) | ALTA | ❌ | ⏳ | Próxima iteración |
| Backfill executed_qty | MEDIA | ❌ | ✅ | Script ready |
| Runbook QA completo | MEDIA | ⏳ | ⏳ | En paralelo |

---

## Recomendaciones Para El Siguiente Sprint

### Bloqueante estricto (2–3 días)
1. ✅ Todos los fixes N1–N4 ya aplicados
2. ⏳ **Actualizar suite de tests:**
   - Mock `is_one_way_mode()`, `ensure_symbol_settings()`, `get_commission_rate()`
   - Actualizar `test_calculate_grid_pnl()` para que use `executed_qty`
   - Agregar tests mínimos: replenishment, expiration, position closure

### Muy recomendado (paralelo, 2–4 semanas)
1. **Correr QA manual en testnet** con el runbook (`docs/manual-qa-runbook.md`)
   - Ciclo completo: lanzar → fills → reposición → EXPIRED/SL → cierre → relanzamiento
   - ✅ Verify /refresh devuelve 200 (no 500) después del fix N1
   - Medir PnL neto acumulado en `historical_grid_logs`
   - GO solo si PnL acumulado positivo

2. **Muy recomendado (no bloqueante):**
   - STOP_MARKET de respaldo en Binance (mejora P2, no implementada aún)
   - WF2 a 5 min en lugar de 15 min
   - Hoy sin estos: caída de n8n = posiciones sin stop

### Antes de dinero real
- Capital mínimo ($100–$500)
- `MAX_CONCURRENT_GRIDS=1` la primera semana
- API keys de producción restringidas por IP
- Desactivar retiros en las claves API

---

## Archivos Modificados En Este Commit

```
backend-python/app/main.py
  - Línea 270: Quitar await de get_grid()

backend-python/app/services/indicators.py
  - calculate_grid_pnl(): Agregar fee_rate parameter, descontar fees

n8n-workflows/workflow1-market-decision.json
  - Nodo "Create Grid (POST)": Quitar Math.max inflation

n8n-workflows/ (borrado)
  - workflow1-updated.json (obsoleto)

backend-python/app/database/ (nuevo)
  - migration_001_executed_qty.py (backfill script)
```

---

## Próximos Pasos Inmediatos

```bash
# 1. Si la BD se va a resetear:
# (No hacer nada, migración no es necesaria)

# 2. Si la BD se mantiene:
cd backend-python
python -m app.database.migration_001_executed_qty

# 3. Reiniciar backend
docker-compose restart backend-python

# 4. Verificar:
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/grids

# 5. Correr QA de testnet
# (Seguir manual-qa-runbook.md)
```

---

**Estado General:** Los bloqueantes de código están resueltos.  
**Siguiente fase:** Tests + QA en testnet (2–4 semanas antes del GO a producción).

