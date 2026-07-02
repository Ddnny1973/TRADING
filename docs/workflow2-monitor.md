# Workflow 2 — Monitoreo y Cierre de Grids

**Propósito:** Monitorear grids activos cada 15 minutos, sincronizar estado con Binance, evaluar condiciones de cierre (SL/TP), y notificar.

**Requisitos previos:** Workflow 1 ha lanzado al menos un grid (`status: RUNNING`).

---

## Diagrama de flujo

```
┌─────────────────────────────┐
│ Nodo 1: Cron Trigger        │
│ Cada 15 minutos             │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│ Nodo 2: GET /grids?status=RUNNING   │
│ Listar todos los grids activos      │
└──────────────┬──────────────────────┘
               │
               ▼
         ┌─────────────┐
         │  Nodo 3: IF │
         │ ¿hay grids? │
         └┬────────────┘
      Sí /                \ No
        /                  └──→ End (no-op)
       ▼
┌──────────────────────────────┐
│ Nodo 4: Split in Batches     │
│ batchSize=1 (secuencial)     │
│ Itera: for each grid RUNNING │
└──────────────┬───────────────┘
               │
      ┌────────▼─────────┐
      │ LOOP PARA GRID N │
      └────────┬─────────┘
               │
               ▼
    ┌────────────────────────────┐
    │ Nodo 5: POST /refresh      │
    │ Sincroniza órdenes         │
    │ Continue on Fail: true     │
    └────────────┬───────────────┘
                 │
                 ▼
           ┌──────────────┐
           │ Nodo 6: IF   │
           │ ¿error?      │
           └┬─────────────┘
        Sí /               \ No
          /                 └──→ Nodo 7
         ▼
    ┌──────────────────┐
    │ Nodo 6a: Notify  │
    │ ⚠️ Fallo refresh │
    └──────┬───────────┘
           │
           └──→ [Siguiente grid]
               
               
               ▼ (desde Nodo 6 No)
    ┌────────────────────────────┐
    │ Nodo 7: POST /check-close  │
    │ Evalúa SL/TP               │
    │ Continue on Fail: true     │
    └────────────┬───────────────┘
                 │
                 ▼
           ┌──────────────┐
           │ Nodo 8: IF   │
           │ ¿error?      │
           └┬─────────────┘
        Sí /               \ No
          /                 └──→ Nodo 9
         ▼
    ┌──────────────────┐
    │ Nodo 8a: Notify  │
    │ ⚠️ Fallo close   │
    └──────┬───────────┘
           │
           └──→ [Siguiente grid]
           
           
               ▼ (desde Nodo 8 No)
           ┌──────────────┐
           │ Nodo 9: IF   │
           │ triggered?   │
           └┬─────────────┘
        Sí /               \ No
          /                 └──→ Nodo 10
         ▼
    ┌──────────────────┐
    │ Nodo 9a: Notify  │
    │ 🔒 Grid cerrado  │
    └──────┬───────────┘
           │
           ▼
    ┌──────────────────┐
    │ Nodo 10: Wait    │
    │ 1-2 segundos     │
    └──────┬───────────┘
           │
           ▼
    ┌──────────────────────┐
    │ Fin del loop         │
    │ (vuelve al Nodo 5    │
    │  para siguiente grid) │
    └──────────────────────┘
```

---

## Detalle de nodos

### **Nodo 1: Cron Trigger**

**Tipo:** Trigger

**Configuración:**
```
Interval: 15 minutes
Recurring: Yes
```

**Output:** Señal de inicio (sin payload)

---

### **Nodo 2: HTTP Request — Listar grids activos**

**Tipo:** HTTP Request

**Configuración:**
```
Method: GET
URL: {{ $env.BACKEND_URL }}/api/v1/grids?status=RUNNING
Headers:
  Authorization: (si se requiere)
  Content-Type: application/json
```

**Expected Response:**
```json
[
  {
    "id": "grid-123",
    "symbol": "BTCUSDT",
    "status": "RUNNING",
    "lower_price": 42100.0,
    "upper_price": 42900.0,
    "levels": 10,
    "created_at": "2026-07-02T14:30:00"
  },
  ...
]
```

---

### **Nodo 3: IF — ¿hay grids activos?**

**Tipo:** IF

**Condición:**
```
{{ $json.length }} > 0
```

**Branches:**
- **True:** Continúa a Nodo 4 (procesar grids)
- **False:** Termina workflow (no hay nada que monitorear)

---

### **Nodo 4: Split in Batches**

**Tipo:** Split in Batches

**Configuración:**
```
Batch Size: 1
Split Field: (raíz, es decir, el array de grids)
Max Iterations: (auto, procesa todos)
```

**Propósito:** Itera sobre cada grid RUNNING de una en una, evitando ráfagas de llamadas a Binance.

**Output por iteración:** Un solo grid (objeto, no array)

```json
{
  "id": "grid-123",
  "symbol": "BTCUSDT",
  ...
}
```

---

### **Nodo 5: HTTP Request — Refresh**

**Tipo:** HTTP Request

**Configuración:**
```
Method: POST
URL: {{ $env.BACKEND_URL }}/api/v1/grids/{{ $json.id }}/refresh
Headers:
  Content-Type: application/json
Continue on Fail: true  // IMPORTANTE: continúa incluso si falla
```

**Expected Response (200):**
```json
{
  "id": "grid-123",
  "symbol": "BTCUSDT",
  "status": "RUNNING",
  "orders": [
    {"id": "123456", "status": "FILLED"},
    {"id": "123457", "status": "NEW"},
    ...
  ]
}
```

**En caso de error (Continue on Fail = true):**
```json
{
  "error": "Network error / 503 Service Unavailable",
  "message": "..."
}
```

---

### **Nodo 6: IF — ¿falló el refresh?**

**Tipo:** IF

**Condición:**
```
{{ $json.error !== undefined }}
```

o alternativamente (según cómo n8n exponga errores):
```
{{ $json.statusCode !== 200 && $json.statusCode !== undefined }}
```

**Branches:**
- **True:** Nodo 6a (notificación de error), luego salta al siguiente grid
- **False:** Continúa a Nodo 7 (check-close)

---

### **Nodo 6a: Notificación — Fallo en refresh**

**Tipo:** Send Slack Message / Send Email / Custom HTTP (POST a Telegram, etc.)

**Mensaje:**
```
⚠️ Fallo de red/Binance en refresh — grid {{ $json.id }} ({{ $json.symbol }})

Error: {{ $json.error }}

Se reintentará en el próximo ciclo (15 min).
```

**Destino:** Slack / Email / Telegram (según configuración)

**Después de este nodo:** Salta al siguiente grid en el loop (Nodo 10 → siguiente iteración)

---

### **Nodo 7: HTTP Request — Check-close**

**Tipo:** HTTP Request

**Configuración:**
```
Method: POST
URL: {{ $env.BACKEND_URL }}/api/v1/grids/{{ $json.id }}/check-close
Headers:
  Content-Type: application/json
Continue on Fail: true
```

**Expected Response (200):**
```json
{
  "triggered": null,  // o "STOP_LOSS" / "TAKE_PROFIT"
  "grid": {
    "id": "grid-123",
    "symbol": "BTCUSDT",
    "status": "RUNNING",  // o "CANCELED" si se cerró
    "total_pnl": 45.67
  }
}
```

---

### **Nodo 8: IF — ¿falló el check-close?**

**Tipo:** IF

**Condición:**
```
{{ $json.error !== undefined }}
```

**Branches:**
- **True:** Nodo 8a (notificación de error), luego salta al siguiente grid
- **False:** Continúa a Nodo 9 (evalúa cierre)

---

### **Nodo 8a: Notificación — Fallo en check-close**

**Tipo:** Send Slack / Email / HTTP

**Mensaje:**
```
⚠️ Fallo de red/Binance en check-close — grid {{ $json.id }} ({{ $json.symbol }})

Error: {{ $json.error }}

El grid continuará running. Se reintentará en el próximo ciclo.
```

**Después de este nodo:** Salta al siguiente grid en el loop

---

### **Nodo 9: IF — ¿se disparó un cierre?**

**Tipo:** IF

**Condición:**
```
{{ $json.triggered !== null }}
```

**Branches:**
- **True:** Nodo 9a (notificación de cierre)
- **False:** Nodo 10 (wait, sin notificación)

---

### **Nodo 9a: Notificación — Grid cerrado**

**Tipo:** Send Slack / Email / HTTP

**Mensaje:**
```
🔒 GRID CERRADO

Símbolo: {{ $json.grid.symbol }}
Motivo: {{ $json.triggered }}  // "STOP_LOSS" o "TAKE_PROFIT"
PnL Total: {{ $json.grid.total_pnl }} USDT
Grid ID: {{ $json.grid.id }}

El grid ha sido cancelado automáticamente.
Próxima reevaluación: el grid ya no aparecerá en RUNNING.
```

**Destino:** Slack con emoji 🔒 / Email urgente / Telegram

---

### **Nodo 10: Wait**

**Tipo:** Wait

**Configuración:**
```
Duration: 1-2 seconds
```

**Propósito:** Espaciar las llamadas a Binance, evitar rate-limiting

---

### **Nodo 11: Fin del loop**

El **Split in Batches** automáticamente vuelve a Nodo 5 para el siguiente grid, hasta agotar todos.

Cuando se acabun los grids, el workflow termina.

---

## Flujo de variables en n8n

Para referencia, aquí están las variables principales en cada paso:

| Nodo | Variable clave | Ejemplo |
|---|---|---|
| Nodo 2 | `$json` (array) | `[{id: "g1", symbol: "BTC"}, ...]` |
| Nodo 3 | `$json.length` | `2` (dos grids) |
| Nodo 4 | `$json` (objeto, 1 grid) | `{id: "g1", symbol: "BTC", ...}` |
| Nodo 5 (respuesta) | `$json.orders` | array de órdenes |
| Nodo 6 | `$json.error` | `undefined` (éxito) o error string |
| Nodo 7 (respuesta) | `$json.triggered` | `null` (running) o `"STOP_LOSS"` / `"TAKE_PROFIT"` |
| Nodo 9 | `$json.triggered` | `"STOP_LOSS"` (cierre disparado) |

---

## Casos de uso y decisiones

### **Caso 1: Grid RUNNING, sin cambios, sin cierre**

```
Nodo 5 ✓ → Nodo 7 ✓ → Nodo 9 (false) → Nodo 10 Wait → siguiente grid
```

**Outcome:** Sin notificaciones, grid continúa RUNNING.

---

### **Caso 2: Fallo de red en refresh**

```
Nodo 5 ✗ (error) → Nodo 6 (true) → Nodo 6a (Notify) → siguiente grid
```

**Outcome:** Notificación ⚠️, grid no evaluado en este ciclo, se reintenta en 15 min.

**Por qué no continuar:** Los datos de órdenes pueden estar desactualizados. No evaluamos SL/TP sin datos frescos.

---

### **Caso 3: Grid en liquidación — TP disparado**

```
Nodo 5 ✓ → Nodo 7 ✓ (triggered: "TAKE_PROFIT") → Nodo 9 (true) → Nodo 9a (Notify 🔒) → siguiente grid
```

**Outcome:** Notificación 🔒, grid ya está CANCELED en el backend (cancel_grid() escribió en historical_grid_logs).

**Próximo ciclo:** Grid NO aparecerá en `?status=RUNNING`, así que Nodo 3 tampoco lo procesa.

---

### **Caso 4: Múltiples grids activos**

```
Grid 1 RUNNING, sin cierre
  → Grid 2 RUNNING, cierre por SL 🔒
    → Grid 3 RUNNING, error en refresh ⚠️
      → (fin del loop)
```

**Outcome:** Nodo 4 procesó 3 grids secuencialmente (batchSize=1), 3 notificaciones en total (1 cierre, 1 error).

---

## Configuración recomendada de notificaciones

### **Slack (si disponible)**

```
Nodo 6a, 8a: Color naranja (warning), emoji ⚠️
Nodo 9a: Color verde (success), emoji 🔒
```

### **Email (fallback)**

```
Asunto: [TRADING GRID] <tipo de evento>
Cuerpo: mensaje con detalles
```

### **Telegram (crítico)**

```
Nodo 9a solamente: enviar a chat de telegram (solo cierres de grids)
```

---

## Checklist de implementación

- [ ] Nodo 1: Cron configurado a 15 minutos
- [ ] Nodo 2: URL correcta al backend (`/grids?status=RUNNING`)
- [ ] Nodo 3: Condición comprobada (`$json.length > 0`)
- [ ] Nodo 4: Split in Batches con batchSize=1
- [ ] Nodo 5: POST a `/refresh` con `Continue on Fail: true`
- [ ] Nodo 6: Condición de error correcta (`$json.error !== undefined`)
- [ ] Nodo 6a: Notificación de error implementada
- [ ] Nodo 7: POST a `/check-close` con `Continue on Fail: true`
- [ ] Nodo 8: Condición de error correcta
- [ ] Nodo 8a: Notificación de error implementada
- [ ] Nodo 9: Condición de cierre correcta (`$json.triggered !== null`)
- [ ] Nodo 9a: Notificación de cierre implementada
- [ ] Nodo 10: Wait de 1-2 segundos
- [ ] Tester: hacer un test manual del flujo completo con al menos 1 grid RUNNING

---

## Integraciones sugeridas

**Slack Integration (n8n Slack node):**
- Webhook URL: configurable via .env
- Canales: `#trading-alerts` para cierre, `#trading-errors` para fallos

**Email Integration:**
- SMTP: configurable via .env
- Destinatario: admin@example.com

**Telegram Integration:**
- Bot token: configurable via .env
- Chat ID: configurable via .env
- Solo cierres (Nodo 9a) para no spamear

---

## Próxima mejora (Phase 3)

- Agregar Nodo 12: **Historial de monitoreo** — LOG en una tabla de audit (Postgres) cada ciclo (sin Nodo HTTP, solo función local)
  - Timestamp, grid_id, status_antes, status_después, error (si aplica)
  - Útil para troubleshooting retroactivo

---

## Relación con Workflow 1

| Workflow | Trigger | Frecuencia | Acción |
|---|---|---|---|
| **Workflow 1** | Manual o Cron (4h) | Cada 4 horas | Crea grids nuevos |
| **Workflow 2** | Cron | Cada 15 min | Monitorea y cierra grids |

**Coexisten:** Workflow 1 lanza, Workflow 2 mantiene vivo y evalúa salida.
