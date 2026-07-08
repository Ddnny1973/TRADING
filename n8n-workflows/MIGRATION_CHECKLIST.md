# ✅ Checklist de Migración: Aplicar Fixes a Producción

**Fecha:** 2026-07-07

---

## 📋 FASE 1: Preparación (30 minutos)

- [ ] **Backup de datos**
  ```bash
  cp backend-python/grid_trading.db backend-python/grid_trading.db.backup.$(date +%s)
  cp n8n-workflows/workflow1-market-decision.json workflow1-market-decision.json.backup
  cp n8n-workflows/workflow2-monitor.json workflow2-monitor.json.backup
  ```

- [ ] **Verificar git status limpio**
  ```bash
  git status
  # Debe mostrar solo los 4 archivos backend + 2 nuevos n8n
  ```

- [ ] **Documentación leída**
  - [ ] README_FIXES_INTEGRATION.md
  - [ ] WORKFLOW1_COMPLETE_GUIDE.md
  - [ ] WORKFLOW2_WITH_FIXES.md

---

## 📋 FASE 2: Deployment Backend (15 minutos)

- [ ] **Detener servicios**
  ```bash
  docker-compose down
  ```

- [ ] **Levantar backend con fixes**
  ```bash
  docker-compose up -d backend
  ```

- [ ] **Verificar health check**
  ```bash
  curl http://localhost:8000/health
  # HTTP 200 OK
  ```

- [ ] **Verificar /auto-params activo**
  ```bash
  curl "http://localhost:8000/auto-params?symbol=BTCUSDT&balance=5000"
  # HTTP 200 con grid_viable, params, reasoning
  ```

---

## 📋 FASE 3: Deployment n8n Workflows (30 minutos)

**Nota:** El archivo `workflow1-market-decision.json` ya tiene el nombre correcto para CI/CD.

- [ ] **Si hay CI/CD configurado:**
  - El archivo se importará automáticamente (no requiere acción)

- [ ] **Si es importación manual en n8n:**
  ```
  n8n UI → Import from File → seleccionar workflow1-market-decision.json
  ```

- [ ] **Verificar estructura del nuevo WF1**
  - [ ] "Get Auto Params (FIX 4)" present
  - [ ] "IF: Grid Viable? (FIX 4)" con rama TRUE/FALSE
  - [ ] "Create Grid" usa parámetros auto-derivados

- [ ] **Probar manualmente WF1**
  - [ ] Click "Start" en n8n UI
  - [ ] Esperar ejecución completa
  - [ ] Revisar logs: sin errores?
  - [ ] Revisar Telegram: notificación recibida?

---

## 📋 FASE 4: Validación (20 minutos)

- [ ] **FIX 1: Sin duplicación de órdenes**
  ```bash
  sqlite3 grid_trading.db "SELECT COUNT(*) FROM grid_orders WHERE cycle > 0;"
  # Número bajo, sin duplicación
  ```

- [ ] **FIX 2: MAX_POSITION funciona**
  - [ ] Crear grid con cantidad alta
  - [ ] Esperar 5 min para WF2
  - [ ] Grid cierra con trigger "MAX_POSITION"

- [ ] **FIX 3: grid_closures existe**
  ```bash
  sqlite3 grid_trading.db "SELECT * FROM grid_closures LIMIT 5;"
  # Mostrar cierres registrados
  ```

- [ ] **FIX 4: /auto-params valida viabilidad**
  - [ ] Balance bajo (100 USDT): grid_viable = false
  - [ ] Balance alto (5000 USDT): grid_viable = true

---

## ✅ Criterios de Éxito

- ✅ Backend levanta sin errores
- ✅ /auto-params responde correctamente
- ✅ WF1 completa ejecución con resultado esperado
- ✅ WF2 ejecuta sin errores cada 5 min
- ✅ grid_closures registra cierres
- ✅ Sin duplicación de órdenes
- ✅ MAX_POSITION cierra grids cuando aplica

---

## ⚠️ Rollback

Si algo falla:

```bash
# Backend
docker-compose down
cp grid_trading.db.backup.* grid_trading.db
git checkout HEAD -- backend-python/
docker-compose up -d backend

# n8n: restaurar workflow1-market-decision.json.backup
```

