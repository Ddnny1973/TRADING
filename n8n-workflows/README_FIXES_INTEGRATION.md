# 🚀 Guía Maestra: Integración de Fixes en n8n + Backend

**Última actualización:** 2026-07-07

---

## 📌 Resumen de los 4 Fixes

| Fix | Problema | Solución | Ubicación |
|-----|----------|----------|-----------|
| **FIX 1A** | Race condition en replenish (órdenes duplicadas) | UPDATE condicional atómico en SQLite | backend-python/app/services/grid_service.py |
| **FIX 1B** | Duplicación en Binance por timeout | clientOrderId determinístico + parámetro en place_batch_orders() | backend-python/app/services/binance_client.py |
| **FIX 2** | Acumulación ilimitada de posición neta | MAX_NET_POSITION_LEVELS check en close_grid_if_triggered() | backend-python/app/core/config.py + grid_service.py |
| **FIX 3** | Trazabilidad solo en PostgreSQL | Tabla grid_closures local en SQLite | backend-python/app/database/connection.py + grid_service.py |
| **FIX 4** | Grid se crea sin validar viabilidad | Endpoint /auto-params + gate en n8n | app/auto_params.py + n8n/auto_params_gate.json |

---

## 🔗 Flujo Completo End-to-End

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          N8N WORKFLOW 1 (4h)                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Config (symbol, balance)                                              │
│       ↓                                                                 │
│  GET /auto-params?symbol=BTCUSDT&balance=5000  ← FIX 4                 │
│       ↓                                                                 │
│  IF grid_viable?                                                       │
│       ├─ TRUE → Gemini (recibe parámetros pre-validados)               │
│       │        → Create Grid                                           │
│       │        → POST /api/v1/grids                                    │
│       │           Backend (FIX 1A+1B+2+3 activados)                   │
│       │           ├─ Crear grid con niveles                            │
│       │           ├─ Colocar órdenes LIMIT en Binance                  │
│       │           ├─ Guardar en grids + grid_orders                    │
│       │           └─ Validar min_notional                              │
│       │                                                                 │
│       └─ FALSE → Notify "No Viable" (razón)                             │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                              ⏱️ 4 horas
                              
┌─────────────────────────────────────────────────────────────────────────┐
│                       N8N WORKFLOW 2 (5 min) [LOOP]                     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  GET /api/v1/grids?status=RUNNING                                      │
│       ↓                                                                 │
│  FOR EACH RUNNING GRID:                                                │
│       │                                                                 │
│       ├─ POST /api/v1/grids/{id}/refresh                               │
│       │  Backend:                                                       │
│       │    1. refresh_order_status() ← Sincroniza fills                │
│       │    2. replenish_filled_orders() ← FIX 1A: Claim atómico        │
│       │       • UPDATE grid_orders SET replenished=1                    │
│       │         WHERE id=? AND replenished=0 (atomic)                  │
│       │       • Generate clientOrderId determinístico (FIX 1B)          │
│       │       • Colocar orden de reposición                            │
│       │         - Si duplicate en Binance: OK (idempotente)            │
│       │         - Si error de red: Revertir claim (retry próxima vez)  │
│       │                                                                 │
│       ├─ POST /api/v1/grids/{id}/check-close                           │
│       │  Backend:                                                       │
│       │    1. Check EXPIRED: age >= max_duration_hours?                │
│       │    2. Check MAX_POSITION: abs(position) > limit? ← FIX 2       │
│       │    3. Check SL/TP: total_pnl vs thresholds?                   │
│       │    4. Si trigger:                                              │
│       │       cancel_grid() {                                          │
│       │         • Cancel open orders en Binance                         │
│       │         • Close position (MARKET reduceOnly)                    │
│       │         • UPDATE grids SET status=CANCELED                      │
│       │         • INSERT INTO grid_closures ← FIX 3 (auditoría)         │
│       │           (grid_id, trigger_condition, total_pnl, position_amt)│
│       │       }                                                          │
│       │                                                                 │
│       └─ Notify Telegram:                                              │
│          • "Grid Closed" con trigger (❌ SL, ✅ TP, ⏰ EXPIRED,        │
│            🚫 MAX_POSITION, 🤷 MANUAL) ← FIX 2                         │
│          • PnL, cycles completados                                     │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 📁 Archivos Generados/Modificados

### Backend Python (4 archivos modificados)

```
backend-python/app/
├── core/config.py                    (+1)  MAX_NET_POSITION_LEVELS=3
├── database/connection.py           (+12)  CREATE TABLE grid_closures
├── services/
│   ├── binance_client.py            (+14) client_order_ids_map param
│   └── grid_service.py            (+188)  replenish (FIX 1), MAX_POSITION (FIX 2), 
                                           grid_closures INSERT (FIX 3)
└── auto_params.py                    (NEW) FIX 4 derivación de parámetros

Total: +215 líneas backend
```

### n8n Workflows (4 archivos)

```
n8n-workflows/
├── workflow1-market-decision.json           (ACTUALIZADO) Versión con FIX 4 integrado
│   └── Auto params gate + Gemini + Create Grid con params derivados
│   └── Nombre estándar para compatibilidad con CI/CD
├── workflow2-monitor.json                   (EXISTENTE) Compatible con todos los fixes
│   └─ Triggers: STOP_LOSS, TAKE_PROFIT, EXPIRED, MAX_POSITION, MANUAL
├── WORKFLOW1_COMPLETE_GUIDE.md              (NEW) Documentación de WF1 completo
├── WORKFLOW2_WITH_FIXES.md                  (NEW) Integración de FIX 2+3 en WF2
└── README_FIXES_INTEGRATION.md              (THIS) Guía maestra
```

---

## 🚀 Instalación Paso a Paso

### Paso 1: Backend (Python)

```bash
cd backend-python/

# Verificar que los archivos están modificados
git diff --stat

# Debe mostrar:
# app/core/config.py             | +1
# app/database/connection.py     | +12
# app/services/binance_client.py | +14 -1
# app/services/grid_service.py   | +188 -63

# Levantar con Docker (o uvicorn si local)
docker-compose up -d backend

# Verificar que esté UP
curl http://localhost:8000/health

# Esperar a que se inicialice la DB con grid_closures
# Verifica en logs: "✅ Databases initialized successfully"
```

### Paso 2: n8n Workflows

```bash
cd n8n-workflows/

# OPCIÓN A: Reemplazar workflow1 original (cuidado, back up primero)
cp workflow1-market-decision.json workflow1-market-decision.backup.json
cp workflow1-market-decision-complete.json workflow1-market-decision.json

# OPCIÓN B: Importar como nuevo (mantener ambos)
# En n8n UI:
# 1. Menu → Import → seleccionar workflow1-market-decision-complete.json
# 2. Dar nuevo nombre (ej: "WF1 - Market Decision v2")
```

### Paso 3: Verificar credenciales n8n

En n8n UI → Credentials & Settings:

- ✅ **Telegram Bot API**: Existe credential named "TRADING"?
- ✅ **Gemini HTTP Header Auth**: Configurado con Authorization header?
- ✅ **Environment Variables**: Presentes BACKEND_URL, TELEGRAM_CHAT_ID?

### Paso 4: Test Manual

```bash
# En n8n UI, click "Manual" en WF1
# Debe:
# 1. Llamar GET /auto-params
# 2. Mostrar grid_viable=true/false
# 3. Si true: llamar Gemini, crear grid
# 4. Notificar Telegram con resultado
```

---

## ✅ Checklist de Validación

### Backend

- [ ] `MAX_NET_POSITION_LEVELS = 3` en config.py
- [ ] `grid_closures` table creada en DB
- [ ] `replenish_filled_orders()` usa UPDATE condicional atómico
- [ ] `place_batch_orders()` acepta `client_order_ids_map` parámetro
- [ ] `close_grid_if_triggered()` checkea MAX_POSITION antes de SL/TP
- [ ] `cancel_grid()` inserta en `grid_closures` con `trigger_condition`

### n8n

- [ ] WF1 tiene nodo "Get Auto Params (FIX 4)"
- [ ] WF1 tiene nodo "IF: Grid Viable? (FIX 4)"
- [ ] WF1 rama FALSE notifica con razón de no viable
- [ ] WF2 nodo "Notify: Grid Closed" soporta "MAX_POSITION" emoji
- [ ] Ambos workflows usan `$env.BACKEND_URL` y `$env.TELEGRAM_CHAT_ID`

---

## 🔍 Verificar que Fixes Funcionan

### FIX 1A+1B: Idempotencia de replenish

```sql
-- En DB mientras WF2 corre:
SELECT COUNT(*) FROM grid_orders WHERE cycle > 0 AND replenished = 1;

-- Debe haber reposiciones sin duplicación
-- (Si había race condition antes: verías 2 órdenes del mismo nivel)
```

### FIX 2: MAX_POSITION

```bash
# Crear grid deliberadamente con 4+ fills
# Esperar a que workflow2 corra
# Debe cerrar automáticamente con trigger_condition="MAX_POSITION"
curl http://localhost:8000/api/v1/grids?status=CANCELED | grep MAX_POSITION
```

### FIX 3: grid_closures

```sql
-- En SQLite:
SELECT * FROM grid_closures ORDER BY closed_at DESC LIMIT 5;

-- Debe mostrar: grid_id, symbol, trigger_condition, total_pnl, position_amt_at_close, closed_at
```

### FIX 4: /auto-params

```bash
curl "http://localhost:8000/auto-params?symbol=BTCUSDT&balance=5000"

# Respuesta debe incluir:
# {
#   "grid_viable": true/false,
#   "params": {
#     "levels": <int>,
#     "risk_pct": <float>,
#     "atr_multiplier": <float>,
#     "klines_interval": "<str>",
#     "atr_period": 14
#   },
#   "reasoning": {...}
# }
```

---

## 📊 Datos Esperados Post-Fix

### Grid Lifecycle (antes vs después)

**ANTES:**
```
Hora    Evento
09:00   Create Grid: levels=4, risk_pct=0.05 (hardcoded)
09:30   Replenish: 1 orden placed
10:00   Replenish: DUPLICADA (race condition) ❌ BUG
10:05   Grid cierra por SL (acumula posición, PnL negativo)
```

**DESPUÉS:**
```
Hora    Evento
09:00   Create Grid: levels=8, risk_pct=0.0111 (auto-derivado, viable)
09:05   Replenish: 1 orden placed (claim atómico + deterministic ID)
09:10   Replenish: 1 orden placed (reintento de timeout = OK, no duplica)
09:15   MAX_POSITION check: position = -2 qty, límite = 3 qty → SAFE
10:00   Grid cierra por EXPIRED (completa ciclos normalmente)
        → INSERT grid_closures(grid_id, "EXPIRED", total_pnl=45.32, position=-0.001, closed_at)
```

---

## 🎯 Resultados Esperados

### Antes de Fixes (AUDITORIA_GRID.md evidencia)

- ❌ Órdenes de reposición duplicadas (nocional doble 124.5 vs 62 USDT)
- ❌ Posición corta acumulada sin límite (3 shorts contra tendencia)
- ❌ Sin trazabilidad local de por qué cerró un grid
- ❌ Grid se crea sin validación de viabilidad

### Después de Fixes

- ✅ Replenish atómico: máximo 1 reposición por fill, sin duplicación
- ✅ Límite automático: grid se cierra si posición > 3×qty (MAX_POSITION)
- ✅ Auditoría local: `grid_closures` registra TODOS los cierres con razón
- ✅ Viabilidad pre-validada: /auto-params checkea antes de Gemini

---

## 📞 Soporte & Debugging

### "Grid creation is taking too long"
- Check: ¿GET /auto-params responde?
- Fix: Verificar backend listening, red connectivity

### "Replenish never places new orders"
- Check: ¿FIX 1A claim UPDATE ejecutándose?
- Debug:
  ```sql
  SELECT * FROM grid_orders WHERE replenished = 0 AND executed_qty > 0;
  -- Si hay filas: problema en replenish
  ```

### "MAX_POSITION check no cierra grid"
- Check: ¿MAX_NET_POSITION_LEVELS = 3 en config.py?
- Debug: ¿Grid tiene position_amt >= 3 × qty_per_order?

### "grid_closures tabla no existe"
- Fix: Reiniciar backend (init_db() recrea tabla)
- o: Manualmente en SQLite: `CREATE TABLE IF NOT EXISTS grid_closures (...)`

---

## 📝 Resumen

Los 4 fixes transforman un sistema con:
- Race conditions en órdenes
- Acumulación ilimitada de riesgo
- Sin trazabilidad local
- Creación de grids sin validación

En un sistema robusto con:
- Idempotencia garantizada (dos capas: DB + Binance)
- Protección de límite de posición automática
- Auditoría completa local (grid_closures)
- Validación pre-creación (/auto-params gate)

**Listo para producción testnet. Escalable a mainnet con ajustes de limits.**

