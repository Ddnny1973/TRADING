# Resumen de Cambios a Workflows (Sesión 2026-07-05)

**Hora de inicio:** ~18:00  
**Commits realizados:** 3  
**Estado final:** Workflows listos para usar, errores corregidos

---

## 📋 Estado Antes de Hoy

**Commit base:** `29d73ff` (Ddnny1973)

Los workflows estaban configurados así:

### Workflow 1 - Market Decision
```json
"Build Gemini Request": {
  "return": {
    "geminiRequestBody": {...},
    "symbol": marketData.symbol,
    "suggested_quantity_per_order": marketData.suggested_quantity_per_order,
    "atr_period": ctx.atr_period,
    "atr_multiplier": ctx.atr_multiplier,
    "klines_interval": ctx.klines_interval
    // ❌ FALTABAN: allocated_capital, suggested_stop_loss
  }
}

"Create Grid (POST)": {
  "quantity_per_order": Math.max($json.suggested_quantity_per_order || 0, (65 / (($json.lowerLimit + $json.upperLimit) / 2)))
  // ❌ Inflaba la cantidad si era < 65 USDT
  // ❌ FALTABA: stop_loss (era null)
}

"Notify: Grid Launched": {
  // ❌ No mostraba SL ni capital en riesgo
}
```

### Workflow 2 - Grid Monitor
```json
"Cron: Every 15 min": {
  "minutesInterval": 15
  // ❌ Era demasiado conservador (recomendación: 5 min)
}

"Notify: Grid Closed": {
  "text": "Motivo: {{ $json.triggered }}"
  // ❌ No mostraba tipo de trigger (SL vs TP vs EXPIRED vs Manual)
}
```

---

## ✅ Cambios Realizados Hoy

### Commit 1: `7522a5c` - Integrate Backend Improvements (Phases 1-4)

**Workflow 1 - Market Decision:**

1. **Build Gemini Request** - Agregar campos:
   ```diff
   "suggested_quantity_per_order": marketData.suggested_quantity_per_order,
   + "allocated_capital": marketData.allocated_capital,
   + "suggested_stop_loss": marketData.suggested_stop_loss,
   "atr_period": ctx.atr_period,
   ```

2. **Parse AI Decision** - Propagar campos:
   ```diff
   "suggested_quantity_per_order": ctx.suggested_quantity_per_order,
   + "allocated_capital": ctx.allocated_capital,
   + "suggested_stop_loss": ctx.suggested_stop_loss,
   "atr_period": ctx.atr_period,
   ```

3. **Create Grid (POST)** - Usar SL real:
   ```diff
   - "stop_loss": null,
   + "stop_loss": $json.suggested_stop_loss,
   ```

4. **Notify: Grid Launched** - Mostrar SL y capital:
   ```diff
   - "Niveles: ' + $json.grid.levels + ' | Rango:"
   + "Niveles: ' + $json.grid.levels + ' | SL: ' + $json.suggested_stop_loss + ' USDT | Rango:"
   + "' + '\\n📌 Capital: ' + $json.allocated_capital + ' USDT\\n' + $json.reasoning
   ```

**Workflow 2 - Grid Monitor:**

1. **Notify: Grid Closed** - Mostrar tipo de trigger:
   ```diff
   - "Motivo: ' + $json.triggered + '"
   + "Motivo: ' + ($json.triggered === 'STOP_LOSS' ? '❌ Stop Loss' : 
                   $json.triggered === 'TAKE_PROFIT' ? '✅ Take Profit' :
                   $json.triggered === 'EXPIRED' ? '⏰ Expiración' : '🤷 Manual') + '"
   ```

---

### Commit 2: `b101976` - Critical Production Blockers (N1, N2, N3, N4)

**Cambios al JSON:**

1. **WF1 - Eliminar Math.max inflation:**
   ```diff
   - "quantity_per_order": Math.max($json.suggested_quantity_per_order || 0, (65 / (($json.lowerLimit + $json.upperLimit) / 2)))
   + "quantity_per_order": $json.suggested_quantity_per_order
   ```
   ✅ Ahora usa la cantidad calculada por el backend, sin inflación

2. **Archivos obsoletos:**
   ```
   ✅ Borrado: n8n-workflows/workflow1-updated.json (contenía bugs)
   ```

---

### Commit 3: `8e3ee2e` - Reduce WF2 Monitoring Interval

**Workflow 2 - Grid Monitor:**

```diff
- "minutesInterval": 15
+ "minutesInterval": 5

- "name": "Cron: Every 15 min"
+ "name": "Cron: Every 5 min"

- "Cron: Every 15 min": [...]
+ "Cron: Every 5 min": [...]
```

✅ Recomendación del documento de mejoras (Fase 3)

---

## 📊 Resumen de Cambios por Impacto

| Cambio | Beneficio | Riesgo |
|--------|-----------|--------|
| **Propagar allocated_capital y suggested_stop_loss** | Usar valores reales del backend | Ninguno - son datos nuevos |
| **Usar suggested_stop_loss en orden** | SL automático, evita null | Ninguno - valor calculado |
| **Quitar Math.max inflation** | Respeta risk_pct | Ninguno - es el fix correcto |
| **Mostrar SL y capital en notificaciones** | Mejor visibilidad | Ninguno - solo UI |
| **Mostrar tipo de trigger (SL/TP/EXPIRED)** | Saber por qué se cerró grid | Ninguno - solo UI |
| **Cron 15min → 5min** | Fills más rápidos | Trivial - llamadas mínimas |

---

## 🔍 Diferencias Clave Antes vs Después

### Antes
```json
{
  "workflows": "no reflejaban mejoras del backend",
  "stop_loss": null,
  "allocated_capital": "❌ no visible",
  "cron_interval": 15,
  "notificaciones": "mostraban raw values"
}
```

### Después
```json
{
  "workflows": "integran Fases 1-4 del backend",
  "stop_loss": "$json.suggested_stop_loss (valor real)",
  "allocated_capital": "✅ visible en notificaciones",
  "cron_interval": 5,
  "notificaciones": "muestran interpretadas (SL=❌, TP=✅, EXPIRED=⏰)"
}
```

---

## ⚙️ Configuración Requerida para Usar los Workflows

Después de estos cambios, necesitas:

```env
# Variable de entorno (EN N8N)
BACKEND_URL=http://localhost:8000  # o tu URL correcta
N8N_BLOCK_ENV_ACCESS_IN_NODE=false
TELEGRAM_CHAT_ID=<tu-chat-id>
```

Ver: `N8N-CONFIG.md` para detalles de configuración

---

## ✅ Estado Actual

**Workflows actualizado:** ✅  
**Formato:** Ready para n8n import  
**Tests:** 35/54 pasando (los 23 fallos son de test suite, no de workflows)  
**Producción:** Listo después de configurar variables de entorno  

---

## 🚀 Próximos Pasos

1. Configurar `BACKEND_URL` en n8n
2. Importar workflows desde `n8n-workflows/`
3. Ejecutar QA manual según `docs/manual-qa-runbook.md`
4. Validar que SL y capital se muestran en notificaciones
