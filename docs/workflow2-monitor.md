# Workflow 2 â€” Monitoreo y Cierre de Grids

**PropÃ³sito:** Monitorear grids activos cada 5 minutos, sincronizar estado con Binance, evaluar condiciones de cierre (SL/TP), y notificar.

**Requisitos previos:** Workflow 1 ha lanzado al menos un grid (`status: RUNNING`).

---

## Diagrama de flujo

```
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚ Nodo 1: Cron Trigger        â”‚
â”‚ Cada 5 minutos             â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
               â”‚
               â–¼
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚ Nodo 2: GET /grids?status=RUNNING   â”‚
â”‚ Listar todos los grids activos      â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
               â”‚
               â–¼
         â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
         â”‚  Nodo 3: IF â”‚
         â”‚ Â¿hay grids? â”‚
         â””â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
      SÃ­ /                \ No
        /                  â””â”€â”€â†’ End (no-op)
       â–¼
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚ Nodo 4: Split in Batches     â”‚
â”‚ batchSize=1 (secuencial)     â”‚
â”‚ Itera: for each grid RUNNING â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
               â”‚
      â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â–¼â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
      â”‚ LOOP PARA GRID N â”‚
      â””â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
               â”‚
               â–¼
    â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
    â”‚ Nodo 5: POST /refresh      â”‚
    â”‚ Sincroniza Ã³rdenes         â”‚
    â”‚ Continue on Fail: true     â”‚
    â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                 â”‚
                 â–¼
           â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
           â”‚ Nodo 6: IF   â”‚
           â”‚ Â¿error?      â”‚
           â””â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
        SÃ­ /               \ No
          /                 â””â”€â”€â†’ Nodo 7
         â–¼
    â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
    â”‚ Nodo 6a: Notify  â”‚
    â”‚ âš ï¸ Fallo refresh â”‚
    â””â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
           â”‚
           â””â”€â”€â†’ [Siguiente grid]
               
               
               â–¼ (desde Nodo 6 No)
    â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
    â”‚ Nodo 7: POST /check-close  â”‚
    â”‚ EvalÃºa SL/TP               â”‚
    â”‚ Continue on Fail: true     â”‚
    â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                 â”‚
                 â–¼
           â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
           â”‚ Nodo 8: IF   â”‚
           â”‚ Â¿error?      â”‚
           â””â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
        SÃ­ /               \ No
          /                 â””â”€â”€â†’ Nodo 9
         â–¼
    â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
    â”‚ Nodo 8a: Notify  â”‚
    â”‚ âš ï¸ Fallo close   â”‚
    â””â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
           â”‚
           â””â”€â”€â†’ [Siguiente grid]
           
           
               â–¼ (desde Nodo 8 No)
           â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
           â”‚ Nodo 9: IF   â”‚
           â”‚ triggered?   â”‚
           â””â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
        SÃ­ /               \ No
          /                 â””â”€â”€â†’ Nodo 10
         â–¼
    â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
    â”‚ Nodo 9a: Notify  â”‚
    â”‚ ðŸ”’ Grid cerrado  â”‚
    â””â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
           â”‚
           â–¼
    â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
    â”‚ Nodo 10: Wait    â”‚
    â”‚ 1-2 segundos     â”‚
    â””â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
           â”‚
           â–¼
    â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
    â”‚ Fin del loop         â”‚
    â”‚ (vuelve al Nodo 5    â”‚
    â”‚  para siguiente grid) â”‚
    â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

---

## Detalle de nodos

### **Nodo 1: Cron Trigger**

**Tipo:** Trigger

**ConfiguraciÃ³n:**
```
Interval: 5 minutes
Recurring: Yes
```

**Output:** SeÃ±al de inicio (sin payload)

---

### **Nodo 2: HTTP Request â€” Listar grids activos**

**Tipo:** HTTP Request

**ConfiguraciÃ³n:**
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

### **Nodo 3: IF â€” Â¿hay grids activos?**

**Tipo:** IF

**CondiciÃ³n:**
```
{{ $json.length }} > 0
```

**Branches:**
- **True:** ContinÃºa a Nodo 4 (procesar grids)
- **False:** Termina workflow (no hay nada que monitorear)

---

### **Nodo 4: Split in Batches**

**Tipo:** Split in Batches

**ConfiguraciÃ³n:**
```
Batch Size: 1
Split Field: (raÃ­z, es decir, el array de grids)
Max Iterations: (auto, procesa todos)
```

**PropÃ³sito:** Itera sobre cada grid RUNNING de una en una, evitando rÃ¡fagas de llamadas a Binance.

**Output por iteraciÃ³n:** Un solo grid (objeto, no array)

```json
{
  "id": "grid-123",
  "symbol": "BTCUSDT",
  ...
}
```

---

### **Nodo 5: HTTP Request â€” Refresh**

**Tipo:** HTTP Request

**ConfiguraciÃ³n:**
```
Method: POST
URL: {{ $env.BACKEND_URL }}/api/v1/grids/{{ $json.id }}/refresh
Headers:
  Content-Type: application/json
Continue on Fail: true  // IMPORTANTE: continÃºa incluso si falla
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

### **Nodo 6: IF â€” Â¿fallÃ³ el refresh?**

**Tipo:** IF

**CondiciÃ³n:**
```
{{ $json.error !== undefined }}
```

o alternativamente (segÃºn cÃ³mo n8n exponga errores):
```
{{ $json.statusCode !== 200 && $json.statusCode !== undefined }}
```

**Branches:**
- **True:** Nodo 6a (notificaciÃ³n de error), luego salta al siguiente grid
- **False:** ContinÃºa a Nodo 7 (check-close)

---

### **Nodo 6a: NotificaciÃ³n â€” Fallo en refresh**

**Tipo:** Send Slack Message / Send Email / Custom HTTP (POST a Telegram, etc.)

**Mensaje:**
```
âš ï¸ Fallo de red/Binance en refresh â€” grid {{ $json.id }} ({{ $json.symbol }})

Error: {{ $json.error }}

Se reintentarÃ¡ en el prÃ³ximo ciclo (5 min).
```

**Destino:** Slack / Email / Telegram (segÃºn configuraciÃ³n)

**DespuÃ©s de este nodo:** Salta al siguiente grid en el loop (Nodo 10 â†’ siguiente iteraciÃ³n)

---

### **Nodo 7: HTTP Request â€” Check-close**

**Tipo:** HTTP Request

**ConfiguraciÃ³n:**
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
    "status": "RUNNING",  // o "CANCELED" si se cerrÃ³
    "total_pnl": 45.67
  }
}
```

---

### **Nodo 8: IF â€” Â¿fallÃ³ el check-close?**

**Tipo:** IF

**CondiciÃ³n:**
```
{{ $json.error !== undefined }}
```

**Branches:**
- **True:** Nodo 8a (notificaciÃ³n de error), luego salta al siguiente grid
- **False:** ContinÃºa a Nodo 9 (evalÃºa cierre)

---

### **Nodo 8a: NotificaciÃ³n â€” Fallo en check-close**

**Tipo:** Send Slack / Email / HTTP

**Mensaje:**
```
âš ï¸ Fallo de red/Binance en check-close â€” grid {{ $json.id }} ({{ $json.symbol }})

Error: {{ $json.error }}

El grid continuarÃ¡ running. Se reintentarÃ¡ en el prÃ³ximo ciclo.
```

**DespuÃ©s de este nodo:** Salta al siguiente grid en el loop

---

### **Nodo 9: IF â€” Â¿se disparÃ³ un cierre?**

**Tipo:** IF

**CondiciÃ³n:**
```
{{ $json.triggered !== null }}
```

**Branches:**
- **True:** Nodo 9a (notificaciÃ³n de cierre)
- **False:** Nodo 10 (wait, sin notificaciÃ³n)

---

### **Nodo 9a: NotificaciÃ³n â€” Grid cerrado**

**Tipo:** Send Slack / Email / HTTP

**Mensaje:**
```
ðŸ”’ GRID CERRADO

SÃ­mbolo: {{ $json.grid.symbol }}
Motivo: {{ $json.triggered }}  // "STOP_LOSS" o "TAKE_PROFIT"
PnL Total: {{ $json.grid.total_pnl }} USDT
Grid ID: {{ $json.grid.id }}

El grid ha sido cancelado automÃ¡ticamente.
PrÃ³xima reevaluaciÃ³n: el grid ya no aparecerÃ¡ en RUNNING.
```

**Destino:** Slack con emoji ðŸ”’ / Email urgente / Telegram

---

### **Nodo 10: Wait**

**Tipo:** Wait

**ConfiguraciÃ³n:**
```
Duration: 1-2 seconds
```

**PropÃ³sito:** Espaciar las llamadas a Binance, evitar rate-limiting

---

### **Nodo 11: Fin del loop**

El **Split in Batches** automÃ¡ticamente vuelve a Nodo 5 para el siguiente grid, hasta agotar todos.

Cuando se acabun los grids, el workflow termina.

---

## Flujo de variables en n8n

Para referencia, aquÃ­ estÃ¡n las variables principales en cada paso:

| Nodo | Variable clave | Ejemplo |
|---|---|---|
| Nodo 2 | `$json` (array) | `[{id: "g1", symbol: "BTC"}, ...]` |
| Nodo 3 | `$json.length` | `2` (dos grids) |
| Nodo 4 | `$json` (objeto, 1 grid) | `{id: "g1", symbol: "BTC", ...}` |
| Nodo 5 (respuesta) | `$json.orders` | array de Ã³rdenes |
| Nodo 6 | `$json.error` | `undefined` (Ã©xito) o error string |
| Nodo 7 (respuesta) | `$json.triggered` | `null` (running) o `"STOP_LOSS"` / `"TAKE_PROFIT"` |
| Nodo 9 | `$json.triggered` | `"STOP_LOSS"` (cierre disparado) |

---

## Casos de uso y decisiones

### **Caso 1: Grid RUNNING, sin cambios, sin cierre**

```
Nodo 5 âœ“ â†’ Nodo 7 âœ“ â†’ Nodo 9 (false) â†’ Nodo 10 Wait â†’ siguiente grid
```

**Outcome:** Sin notificaciones, grid continÃºa RUNNING.

---

### **Caso 2: Fallo de red en refresh**

```
Nodo 5 âœ— (error) â†’ Nodo 6 (true) â†’ Nodo 6a (Notify) â†’ siguiente grid
```

**Outcome:** NotificaciÃ³n âš ï¸, grid no evaluado en este ciclo, se reintenta en 5 min.

**Por quÃ© no continuar:** Los datos de Ã³rdenes pueden estar desactualizados. No evaluamos SL/TP sin datos frescos.

---

### **Caso 3: Grid en liquidaciÃ³n â€” TP disparado**

```
Nodo 5 âœ“ â†’ Nodo 7 âœ“ (triggered: "TAKE_PROFIT") â†’ Nodo 9 (true) â†’ Nodo 9a (Notify ðŸ”’) â†’ siguiente grid
```

**Outcome:** NotificaciÃ³n ðŸ”’, grid ya estÃ¡ CANCELED en el backend (cancel_grid() escribiÃ³ en historical_grid_logs).

**PrÃ³ximo ciclo:** Grid NO aparecerÃ¡ en `?status=RUNNING`, asÃ­ que Nodo 3 tampoco lo procesa.

---

### **Caso 4: MÃºltiples grids activos**

```
Grid 1 RUNNING, sin cierre
  â†’ Grid 2 RUNNING, cierre por SL ðŸ”’
    â†’ Grid 3 RUNNING, error en refresh âš ï¸
      â†’ (fin del loop)
```

**Outcome:** Nodo 4 procesÃ³ 3 grids secuencialmente (batchSize=1), 3 notificaciones en total (1 cierre, 1 error).

---

## ConfiguraciÃ³n recomendada de notificaciones

### **Slack (si disponible)**

```
Nodo 6a, 8a: Color naranja (warning), emoji âš ï¸
Nodo 9a: Color verde (success), emoji ðŸ”’
```

### **Email (fallback)**

```
Asunto: [TRADING GRID] <tipo de evento>
Cuerpo: mensaje con detalles
```

### **Telegram (crÃ­tico)**

```
Nodo 9a solamente: enviar a chat de telegram (solo cierres de grids)
```

---

## Checklist de implementaciÃ³n

- [ ] Nodo 1: Cron configurado a 5 minutos
- [ ] Nodo 2: URL correcta al backend (`/grids?status=RUNNING`)
- [ ] Nodo 3: CondiciÃ³n comprobada (`$json.length > 0`)
- [ ] Nodo 4: Split in Batches con batchSize=1
- [ ] Nodo 5: POST a `/refresh` con `Continue on Fail: true`
- [ ] Nodo 6: CondiciÃ³n de error correcta (`$json.error !== undefined`)
- [ ] Nodo 6a: NotificaciÃ³n de error implementada
- [ ] Nodo 7: POST a `/check-close` con `Continue on Fail: true`
- [ ] Nodo 8: CondiciÃ³n de error correcta
- [ ] Nodo 8a: NotificaciÃ³n de error implementada
- [ ] Nodo 9: CondiciÃ³n de cierre correcta (`$json.triggered !== null`)
- [ ] Nodo 9a: NotificaciÃ³n de cierre implementada
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

## PrÃ³xima mejora (Phase 3)

- Agregar Nodo 12: **Historial de monitoreo** â€” LOG en una tabla de audit (Postgres) cada ciclo (sin Nodo HTTP, solo funciÃ³n local)
  - Timestamp, grid_id, status_antes, status_despuÃ©s, error (si aplica)
  - Ãštil para troubleshooting retroactivo

---

## RelaciÃ³n con Workflow 1

| Workflow | Trigger | Frecuencia | AcciÃ³n |
|---|---|---|---|
| **Workflow 1** | Manual o Cron (4h) | Cada 4 horas | Crea grids nuevos |
| **Workflow 2** | Cron | Cada 5 min | Monitorea y cierra grids |

**Coexisten:** Workflow 1 lanza, Workflow 2 mantiene vivo y evalÃºa salida.


