# Estado de Fixes en Test Suite

**Fecha:** 2026-07-05  
**Estado anterior:** 23 fallos de 54 tests  
**Estado actual:** ~18 fallos (en progreso)

---

## ✅ Problemas Resueltos

### 1. Tests de Indicators (3/3 fallos resueltos)
```
✅ test_calculate_grid_pnl_matched_buy_sell_is_fully_realized
✅ test_calculate_grid_pnl_unmatched_buy_is_unrealized_long  
✅ test_calculate_grid_pnl_ignores_non_filled_orders
```

**Fix:** 
- Actualizado `_order()` helper para incluir `executed_qty` y `avg_fill_price`
- Tests ahora reflejan que `calculate_grid_pnl()` usa `executed_qty` en lugar de `status`
- PnL ahora descuenta fees (cambio en backend)

### 2. Test de Health Check (1/1 fallo resuelto)
```
✅ test_health_check
```

**Fix:**
- Actualizado para esperar campos nuevos: `binance_synced`, `time_offset_ms`
- Endpoint ahora devuelve estado de sincronización con Binance

---

## ❌ Problemas Pendientes (17 fallos)

### Categoría A: Tests de Create Grid (10 fallos)
```
❌ test_create_grid_manual_bounds               → 400 "No orders placed"
❌ test_create_grid_auto_atr_bounds             → 400 "No orders placed"
❌ test_create_grid_with_sl_tp                  → 400 "No orders placed"
❌ test_create_grid_levels_zero_returns_two_level_grid
❌ test_create_grid_duplicate_symbol_rejected
❌ test_list_grids_returns_created_grids        → KeyError: 'id'
❌ test_get_grid_detail_includes_orders         → KeyError: 'id'
❌ test_pnl_with_no_fills_is_zero               → KeyError: 'id'
❌ test_pnl_after_fills_reflects_orders         → KeyError: 'id'
❌ test_cancel_grid_cancels_open_orders         → KeyError: 'id'
```

**Causa raíz:** Los mocks de Binance (`place_batch_orders`, `get_symbol_filters`, etc.) no están siendo invocados correctamente O están fallando silenciosamente.

**Solución necesaria:**
- Verificar que `get_symbol_filters` está siendo llamado (necesario para validaciones)
- Verificar que `place_batch_orders` retorna órdenes válidas
- Posiblemente agregar logeo en los mocks para debuggear qué está fallando

### Categoría B: Tests de Monitoring (4 fallos)
```
❌ test_refresh_grid_updates_order_status        → KeyError: 'id'
❌ test_refresh_with_no_open_orders_skips_binance_call
❌ test_check_close_no_trigger_within_thresholds
❌ test_check_close_triggers_take_profit         → KeyError: 'id'
```

**Causa raíz:** Dependencia de que create_grid funcione (necesita crear un grid primero)

**Solución:** Arreglar Categoría A primero, esto arreglará Categoría B automáticamente

### Categoría C: Tests de Logging (2 fallos)
```
❌ test_log_grid_closure_writes_historical_log  → assert 0 == 1
❌ test_log_grid_closure_defaults_pnl_to_zero_when_unavailable → IndexError
```

**Causa raíz:** Mocks de Postgres no están configurados correctamente para estos tests

**Solución necesaria:**
- Revisar `test_grid_service_logging.py`
- Actualizar mocks de sesión de Postgres
- Posiblemente actualizar llamadas a `_log_grid_closure()`

### Categoría D: Tests de Market Analysis (1 fallo)
```
❌ test_market_analysis_custom_parameters       → assert 42470.0 == 70.0
```

**Causa raíz:** Mock de `get_balance` retorna valor incorrecto

**Solución:** Actualizar mock para retornar balance correcto

---

## 📊 Prioridad de Fixes

### P0 (Crítica - bloquea otras)
1. **Arreglar mocks de `place_batch_orders` en conftest.py**
   - Verificar que retorna órdenes válidas
   - Asegurarse que `get_symbol_filters` es llamado
   - Esto arreglará 10+ tests automáticamente

### P1 (Alta)
2. **Arreglar test_market_analysis_custom_parameters**
   - Actualizar mock de `get_balance`
   - Quick win (1 línea de cambio)

3. **Arreglar logging tests**
   - Actualizar mocks de Postgres
   - 2 tests

### P2 (Normal)
4. **Validación final**
   - Asegurar que todos los 54 tests pasan
   - Documentar cambios realizados

---

## 🔧 Cómo Continuar

```bash
# 1. Investigar qué está pasando en conftest.py
cd backend-python/tests
# Revisar por qué place_batch_orders falla

# 2. Agregar logeo temporal en los mocks
# (para entender qué se está llamando)

# 3. Ejecutar tests con más verbosidad
python -m pytest tests/test_api_grids.py::test_create_grid_manual_bounds -vvv

# 4. Ir arreglando por categoría (A, B, C, D)

# 5. Hacer commit por categoría
```

---

## 💡 Notas Técnicas

### Por qué fallen tantos tests de API
- Los endpoints `/api/v1/grids` requieren:
  1. Mock de `get_mark_price` ✅ (seteado)
  2. Mock de `get_symbol_filters` ⚠️ (seteado pero posiblemente no se llama)
  3. Mock de `place_batch_orders` ⚠️ (seteado pero posiblemente no retorna datos correctos)
  4. Mock de `get_klines` (solo si se piden bounds automáticos por ATR)

- Si alguno falla, `create_grid` retorna 400 en lugar de 201

### Por qué los tests de logging fallan
- Requieren que `GridService._log_grid_closure()` pueda escribir en Postgres
- Hoy SessionLocal es None en tests (monkeypatch en conftest)
- Los tests espera que la BD se actualice aunque no haya Postgres real

---

## 📝 Archivos a Revisar/Actualizar

```
backend-python/tests/
├── conftest.py                    ← Revisar mocks de place_batch_orders
├── test_api_grids.py              ← Algunos tests pueden estar desactualizados
├── test_grid_service_logging.py   ← Mocks de Postgres
└── test_indicators.py             ← ✅ YA ACTUALIZADO
```

---

**Próximo paso:** Investigar conftest.py y entender por qué `place_batch_orders` falla
