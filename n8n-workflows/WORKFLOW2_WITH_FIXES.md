# Workflow 2: Grid Monitor — Integración con Fixes Backend

**Archivo:** `workflow2-monitor.json` (ya actualizado)

**Estado:** ✅ Compatible con FIX 1, 2, 3, 4

---

## 🔄 Flujo de Monitoreo

```
┌─────────────────────┐
│ Cron: Every 5 min   │  ← Ejecuta 288 veces/día
└──────────┬──────────┘
           │
           ▼
┌─────────────────────────────────────────┐
│ GET /api/v1/grids?status=RUNNING        │
│ Obtiene todas las grids en ejecución    │
└──────────┬──────────────────────────────┘
           │
           ▼
    ┌──────────────────┐
    │ IF: Hay grids?   │
    └────────┬──────┬──┘
             │      │
          Sí │      │ No
             ▼      ▼
        Loop    Notify "Sin grids"
             
        ┌─────────────────────────────┐
        │ Para cada grid:             │
        │ 1. POST /refresh            │  ← FIX 1A+1B: Replenish idempotente
        │ 2. POST /check-close        │  ← FIX 2: Chequea MAX_POSITION
        │ 3. Procesa resultado        │
        └────────┬────────────────────┘
                 │
        ┌────────┴────────────────────┐
        │                             │
     triggered=null          triggered=STOP_LOSS/
        │                    TAKE_PROFIT/EXPIRED/
        │                    MAX_POSITION/MANUAL
        │                             │
        ▼                             ▼
    Continua              Notify: Grid Closed (FIX 3)
    siguiente grid        con trigger_condition
```

---

## 🔧 Cambios a aplicar en workflow2.json

### 1. **Actualizar mensaje de "Grid Closed" para incluir MAX_POSITION (FIX 2)**

**Ubicación:** Nodo "Notify: Grid Closed" (línea ~45)

**Cambio:**
```javascript
// ANTES:
'📌 Motivo: ' + ($json.triggered === 'STOP_LOSS' ? '❌ Stop Loss' : 
                 $json.triggered === 'TAKE_PROFIT' ? '✅ Take Profit' : 
                 $json.triggered === 'EXPIRED' ? '⏰ Expiración' : 
                 '🤷 Manual')

// DESPUÉS (agregar MAX_POSITION):
'📌 Motivo: ' + (
  $json.triggered === 'STOP_LOSS' ? '❌ Stop Loss' : 
  $json.triggered === 'TAKE_PROFIT' ? '✅ Take Profit' : 
  $json.triggered === 'EXPIRED' ? '⏰ Expiración' :
  $json.triggered === 'MAX_POSITION' ? '🚫 Posición Máxima' :
  '🤷 Manual'
)
```

### 2. **Agregar notificación de Check-Close Error (FIX 1: retry logic)**

El workflow ya tiene:
- "Notify: Check-close Error" node (línea ~114)
- Intenta reintentar cada ciclo si check-close falla

**Verificar:** El mensaje dice "Se reintentará en próximo ciclo (5 min)" — esto está correcto.

### 3. **Agregar logs de grid_closures consultables (FIX 3)**

**Opcional:** Agregar un nodo al final que consulte grid_closures para auditoría:

```json
{
  "name": "Log Closure (optional FIX 3 audit)",
  "type": "n8n-nodes-base.httpRequest",
  "parameters": {
    "method": "GET",
    "url": "{{ $env.BACKEND_URL }}/audit/grid-closures?limit=10"
  }
}
```

(Requiere endpoint adicional en backend para consultar grid_closures)

---

## 🎯 Triggers soportados (Nuevos + Existentes)

| Trigger | Emoji | Significado | Acción |
|---------|-------|-------------|--------|
| `STOP_LOSS` | ❌ | PnL cayó bajo el umbral | Close inmediato |
| `TAKE_PROFIT` | ✅ | PnL subió sobre el umbral | Close inmediato |
| `EXPIRED` | ⏰ | Grid excedió edad máxima | Close programado |
| `MAX_POSITION` | 🚫 | Posición neta > límite (FIX 2) | Close inmediato |
| `MANUAL` | 🤷 | Usuario cerró manualmente | Close inmediato |

**Todos registrados en `grid_closures` (FIX 3)** para auditoría local.

---

## 🔐 Idempotencia (FIX 1A + 1B)

**Cómo afecta a workflow2:**

1. **Refresh → Replenish:**
   - Si dos ciclos concurrentes ven mismo fill:
     - Ambos intentan reponer
     - Backend: Solo 1 gana el UPDATE condicional (rowcount=1)
     - Otro: Ve rowcount=0, skipea (no duplica orden)
   - **Resultado:** El workflow puede ejecutarse simultáneamente sin bugs

2. **clientOrderId determinístico:**
   - Si replenish falla en Binance (network timeout):
     - Siguiente ciclo reintenta con MISMO clientOrderId
     - Binance: "ya existe" (benigno)
     - Backend: Marca como replenido
   - **Resultado:** Recuperación automática sin duplicación

---

## 📊 Performance (FIX 1: concurrencia)

**Antes:** Race condition si Cron=5min y refresh+replenish duraba >5min
**Ahora:** Claim atómico + clientOrderId garantizan no duplicación incluso con:
- Múltiples ciclos concurrentes
- Network timeouts
- Reintentos

**Recomendación:** Mantener Cron en 5 minutos. Backend aguanta concurrencia.

---

## 🚨 Manejo de Errores (FIX 1: retries)

Workflow2 ya tiene:

```
refresh_order_status() falla
    ↓
Reintentar en próximo ciclo (5 min)
    ↓
Si falla 3+ veces: Notificar operador
```

**Con FIX 1:** Si replenish falla en Binance por error temporal:
- Claim se revierte automáticamente
- Siguiente ciclo reintentar (no re-compra duplicado)

---

## 📋 Checklist de Instalación

- [ ] Archivo `workflow2-monitor.json` está en n8n-workflows/
- [ ] Workflow importado/actualizado en n8n UI
- [ ] Cron trigger configurado: "Every 5 minutes"
- [ ] Environment variables presentes:
  - [ ] `BACKEND_URL`
  - [ ] `TELEGRAM_CHAT_ID`
- [ ] Telegram Bot credential active
- [ ] Backend corriendo con FIX 1, 2, 3 activados:
  - [ ] `replenish_filled_orders()` con claim atómico
  - [ ] `close_grid_if_triggered()` con MAX_POSITION check
  - [ ] `grid_closures` tabla creada
- [ ] Test: Crear grid manualmente y ver que se monitorea

---

## 🔍 Debugging

### Replenish duplicado (antes de FIX 1)
**Síntoma:** Dos órdenes de reposición en el mismo segundo
**Solución:** Ya está en FIX 1A+1B, nada que hacer en n8n

### Grid no se monitorea
1. ¿GET /grids retorna datos?
   - Revisa "Fetch Running Grids" nodo
   - ¿Status=RUNNING?

2. ¿Refresh falla?
   - Ver "Refresh Grid (POST)" response
   - ¿HTTP 200?

3. ¿Check-close nunca dispara?
   - Ver logs de backend
   - ¿Max duration hours está configurado?

### MAX_POSITION no cierra grid
1. Verificar backend iniciado con FIX 2
2. ¿`MAX_NET_POSITION_LEVELS = 3` en config.py?
3. ¿Position es realmente > 3×qty?

---

## 📝 Notas

- Workflow2 es **stateless**: cada ejecución es independiente
- No guarda estado entre ciclos → seguro ante crashes
- Los fixes FIX 1, 2, 3 están en el **backend**, no en n8n
- n8n solo orquesta las llamadas
- Todo lo importante se registra en SQLite (`grid_closures`, `grid_orders`)

