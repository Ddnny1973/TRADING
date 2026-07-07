# Workflow 2: Grid Monitor - Especificación Detallada

## Resumen Ejecutivo

**ID n8n:** `96qAStQwfrHAVXRd`  
**Trigger:** Cron cada 5 minutos (`minutesInterval: 5`, nodo: "Cron: Every 5 min")  
**Duración:** ~3-5 segundos por ejecución  
**Función:** Refresh órdenes + evaluar SL/TP/EXPIRED — el replenish lo hace el backend dentro de `/refresh`

---

## Flujo Completo (según JSON real)

```
Cron / Manual / WF-Monitoreo-Trading
         ↓
  List Running Grids
  GET /api/v1/grids?status=RUNNING
         ↓
  IF: Hay grids running?
    ├── FALSE → Notify: No Running Grids → Monitor cycle complete
    └── TRUE  → Split in Batches (Sequential)
                    ↓ (por cada grid)
              Refresh Orders (POST)
              POST /api/v1/grids/{id}/refresh
                    ↓
              Interpret Refresh Result
                    ↓
              IF: Refresh failed?
                ├── TRUE  → Notify: Refresh Error → Wait 1.5s → siguiente grid
                └── FALSE → Check Close (POST)
                            POST /api/v1/grids/{id}/check-close
                                  ↓
                            Interpret Check-Close Result
                                  ↓
                            IF: Check-close failed?
                              ├── TRUE  → Notify: Check-close Error → Wait 1.5s → siguiente grid
                              └── FALSE → IF: Grid closed?
                                            ├── TRUE  → Notify: Grid Closed → Wait 1.5s → siguiente grid
                                            └── FALSE → Wait 1.5s → siguiente grid
                    ↓ (todos los grids procesados)
              Split done → Monitor cycle complete
```

---

## Nodos Detallados

### Triggers (3 modos de entrada)

| Nodo | Tipo | Cuándo |
|------|------|--------|
| `Cron: Every 5 min` | scheduleTrigger | Automático, 288 veces/día |
| `Start (Manual)` | manualTrigger | Test/debug en n8n UI |
| `WF-Monitoreo-Trading` | executeWorkflowTrigger | Llamado por otro workflow |

---

### List Running Grids

```
GET $env.BACKEND_URL/api/v1/grids?status=RUNNING
```

- Usa `alwaysOutputData: true` → siempre pasa aunque array esté vacío

---

### IF: Hay grids running?

**Condición:** `!!$json.id === true`

- **TRUE** → `Split in Batches (Sequential)` → procesa cada grid
- **FALSE** → `Notify: No Running Grids`
  - Mensaje Telegram: `"ℹ️ Sin grids en ejecución\n⏳ Próximo monitoreo: en 5 minutos"`

---

### Refresh Orders (POST)

```
POST $env.BACKEND_URL/api/v1/grids/{id}/refresh
```

- `fullResponse: true`, `neverError: true` (nunca lanza excepción, siempre retorna)
- El backend ejecuta el **replenish automáticamente** dentro de este endpoint

**Interpret Refresh Result** extrae:
```javascript
{
  gridId, symbol,
  isError: statusCode !== 200,
  errorMessage,  // si isError
  grid           // body completo si ok
}
```

**IF: Refresh failed?** → `isError === true`
- **TRUE** → `Notify: Refresh Error` (Telegram) → `Wait 1.5s`
- **FALSE** → continúa a `Check Close`

---

### Check Close (POST)

```
POST $env.BACKEND_URL/api/v1/grids/{gridId}/check-close
```

- `fullResponse: true`, `neverError: true`

**Interpret Check-Close Result** extrae:
```javascript
{
  gridId, symbol,
  isError: statusCode !== 200,
  triggered,  // "STOP_LOSS" | "TAKE_PROFIT" | "EXPIRED" | null
  grid        // GridDetailResponse si ok
}
```

**IF: Check-close failed?** → `isError === true`
- **TRUE** → `Notify: Check-close Error` (Telegram) → `Wait 1.5s`
- **FALSE** → `IF: Grid closed?`

---

### IF: Grid closed?

**Condición:** `$json.triggered` is not empty

- **TRUE** → `Notify: Grid Closed`
- **FALSE** → `Wait 1.5s` → siguiente grid

**Notify: Grid Closed** (Telegram):
```
🔒 GRID CERRADO - {symbol}

📌 Motivo:
  STOP_LOSS   → ❌ Stop Loss
  TAKE_PROFIT → ✅ Take Profit
  EXPIRED     → ⏰ Expiración
  otro        → 🤷 Manual

📊 PnL Total: {grid.total_pnl} USDT
🆔 Grid ID: {grid.id}
✨ Ciclos: {grid.cycles_completed}
```

---

### Wait (1.5s between items) + Loop

Espera 1.5s → vuelve a `Split in Batches` → siguiente grid.  
Cuando todos los grids están procesados → `Monitor cycle complete` (noOp).

---

## Variables de Entorno Requeridas

```
BACKEND_URL=http://backend-python:8000
N8N_BLOCK_ENV_ACCESS_IN_NODE=false
TELEGRAM_CHAT_ID=1060878323
```

---

## Ejemplo de Ejecución

### Ciclo sin fills
```
Cron (00:05) → List Running Grids → 1 grid RUNNING
→ Refresh Orders → OK, 0 fills
→ Check Close → triggered: null
→ Wait 1.5s → Monitor cycle complete
```

### Ciclo con fill + cierre por TP
```
Cron (00:10) → List Running Grids → 1 grid RUNNING
→ Refresh Orders → OK (backend detecta fill, crea orden opuesta)
→ Check Close → triggered: "TAKE_PROFIT"
→ Notify: Grid Closed "✅ Take Profit | PnL: +12.5 USDT"
→ Wait 1.5s → Monitor cycle complete
```

### Sin grids activos
```
Cron (00:15) → List Running Grids → [] vacío
→ IF: Hay grids running? → FALSE
→ Notify: "ℹ️ Sin grids en ejecución"
→ Monitor cycle complete
```

---

## Manejo de Errores

| Fallo | Nodo que lo detecta | Acción |
|-------|-------------------|--------|
| `/refresh` HTTP ≠ 200 | IF: Refresh failed? | Telegram error + skip check-close |
| `/check-close` HTTP ≠ 200 | IF: Check-close failed? | Telegram error + skip cierre |
| Sin grids RUNNING | IF: Hay grids running? | Telegram info + fin normal |

Todos los errores son **no fatales**: el workflow continúa con el siguiente grid.

---

## Métricas

- **Frecuencia:** cada 5 min → 288 ejecuciones/día
- **Latencia esperada:** < 5 segundos por ejecución
- **Rate limiting:** Wait 1.5s entre grids para respetar Binance API
- **Errores tolerables:** hasta 3 fallos/día manteniendo > 99% uptime

---

## Próximas Secciones

- [Workflow 1: Market Decision](02-workflow1.md)
- [Visión General de Workflows](01-vision-general.md)
- [Setup de n8n](../20-SETUP/01-setup-n8n.md)
- [Troubleshooting](../40-OPERACIONAL/01-troubleshooting.md)
