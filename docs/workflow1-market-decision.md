# Workflow 1: Market Decision (Decisión automática de lanzar grid)

**Propósito:** Automatizar la decisión de si lanzar un grid y con qué parámetros, basado en análisis de mercado.

**Trigger:** Manual o periódico (cron cada 4 horas, aligned con `klines_interval: "4h"`)

---

## Flujo paso a paso

### Nodo 1: Input manual o parámetros

```json
{
  "symbol": "BTCUSDT"
}
```

O si es cron, valores fijos:
```json
{
  "symbol": "BTCUSDT",
  "atr_period": 14,
  "atr_multiplier": 2.0,
  "klines_interval": "4h"
}
```

---

### Nodo 2: Consultar análisis de mercado (HTTP GET)

**Endpoint:** `GET http://backend:8000/api/v1/market-analysis/{symbol}`

**Query params:**
```
atr_period=14
atr_multiplier=2.0
klines_interval=4h
```

**Response (entrada al nodo de IA):**
```json
{
  "symbol": "BTCUSDT",
  "current_price": 42500.0,
  "atr": 200.0,
  "atr_period": 14,
  "klines_interval": "4h",
  "suggested_lower_price": 42100.0,
  "suggested_upper_price": 42900.0,
  "suggested_range": 800.0
}
```

---

### Nodo 3: AI Decision Node (Claude / LLM)

**Tipo:** `Call Tool` → `AI` node en n8n (Claude, OpenAI, etc.)

**System Prompt:**
```
Eres el módulo de decisión de un bot de grid trading en Binance Futures.
Recibes datos de mercado ya calculados (no los recalcules). Tu única
tarea es decidir si conviene lanzar un grid ahora y con qué parámetros.

Reglas de criterio:
- Si atr_pct (ATR/current_price) es muy bajo (<0.3%), el rango será demasiado
  angosto para capturar movimiento → considera no lanzar.
- Si atr_pct es muy alto (>2%), el mercado puede estar en tendencia fuerte,
  no lateral → grids funcionan peor → considera no lanzar o reducir gridCount.
- gridCount razonable: entre 5 y 20 según el ATR.
  Ejemplo: si atr_pct ~0.5%, usa 10-15 levels.
  Si atr_pct ~1.5%, usa 8-12 levels (menos levels en mercados volátiles).
- Siempre explica tu razonamiento en el campo "reasoning" ANTES de
  fijar "launch".
- lowerLimit/upperLimit: puedes ajustar los suggested_* si tienes razón
  fundamental, pero generalmente respeta los sugeridos.

Responde ÚNICAMENTE en JSON válido, sin texto adicional.
```

**Input al nodo:**

Pasa directamente el response del Nodo 2:
```json
{
  "symbol": "BTCUSDT",
  "current_price": 42500.0,
  "atr": 200.0,
  "atr_period": 14,
  "klines_interval": "4h",
  "suggested_lower_price": 42100.0,
  "suggested_upper_price": 42900.0,
  "suggested_range": 800.0
}
```

**Output esperado (JSON Schema estructurado):**

```json
{
  "type": "object",
  "properties": {
    "reasoning": {
      "type": "string",
      "description": "Explicación del razonamiento (atr_pct, volatilidad, decisión)"
    },
    "launch": {
      "type": "boolean",
      "description": "True si recomienda lanzar, false si no"
    },
    "lowerLimit": {
      "type": "number",
      "description": "Precio inferior del grid (generalmente suggested_lower_price)"
    },
    "upperLimit": {
      "type": "number",
      "description": "Precio superior del grid (generalmente suggested_upper_price)"
    },
    "gridCount": {
      "type": "integer",
      "minimum": 2,
      "maximum": 30,
      "description": "Número de levels del grid (recomendación: 5-20)"
    }
  },
  "required": ["reasoning", "launch", "lowerLimit", "upperLimit", "gridCount"]
}
```

**Ejemplo de respuesta del IA:**

```json
{
  "reasoning": "ATR/price = 200/42500 = 0.47%, dentro del rango óptimo (0.3%-2%). Mercado en rango lateral según los 4h. Recomiendo lanzar con 12 levels para capturar oscilación sin sobreexposición.",
  "launch": true,
  "lowerLimit": 42100.0,
  "upperLimit": 42900.0,
  "gridCount": 12
}
```

**Ejemplo de respuesta negativa:**

```json
{
  "reasoning": "ATR/price = 50/42500 = 0.12%, demasiado bajo. El rango sugerido (42450-42550) es muy angosto para capturar movimiento real. Mercado sin volatilidad, esperar.",
  "launch": false,
  "lowerLimit": null,
  "upperLimit": null,
  "gridCount": null
}
```

---

### Nodo 4: Condicional (Switch)

**Condición:**
```
$json.launch === true
```

**True branch:** ir a Nodo 5 (crear grid)
**False branch:** ir a Nodo 6 (log/notificación "no lanzar")

---

### Nodo 5: Crear Grid (HTTP POST - condicional)

**Endpoint:** `POST http://backend:8000/api/v1/grids`

**Request body:**
```json
{
  "symbol": "{{ $json.symbol }}",
  "lower_price": {{ $json.lowerLimit }},
  "upper_price": {{ $json.upperLimit }},
  "levels": {{ $json.gridCount }},
  "grid_type": "GEOMETRIC",
  "quantity_per_order": 0.001,
  "stop_loss": null,
  "take_profit": null
}
```

**Notas:**
- `quantity_per_order: 0.001` = 1 miliBTC ≈ $42.50 notional (escalable después)
- `grid_type: GEOMETRIC` — espaciado logarítmico (recomendado)
- `stop_loss`, `take_profit` → null por ahora (agregar después si se necesita)

**Expected Response (200):**
```json
{
  "id": "a1b2c3d4-...",
  "symbol": "BTCUSDT",
  "lower_price": 42100.0,
  "upper_price": 42900.0,
  "levels": 12,
  "status": "RUNNING",
  "stop_loss": null,
  "take_profit": null,
  "created_at": "2026-07-02T14:30:00",
  "orders": [
    { "id": "123456", "price": 42100.0, "quantity": 0.001, "side": "BUY", "status": "NEW" },
    ...
  ]
}
```

**Error handling:**
- **400** `"already exists"` → No error, grid ya existe del intento anterior (ver [n8n-integration-strategy.md](./n8n-integration-strategy.md))
- **400** (otro) → Error de validación (margen insuficiente, filtros), notificar
- **500** → Error del servidor, reintentar o escalar

---

### Nodo 6: Notificación / Log

**Si launch = true:**
```
✅ Grid BTCUSDT lanzado (id: {grid_id}, levels: 12, rango: 42100-42900)
Reasoning: {reasoning}
```

**Si launch = false:**
```
⏭️ No lanzar grid BTCUSDT
Reasoning: {reasoning}
```

**Medio:** Slack, Email, o solo log (según preferencia)

---

## Decisión: quantity_per_order

**Propuesta:** Fijar `quantity_per_order: 0.001` BTC por ahora (≈ $42.50 notional a precio actual).

**Razones:**
1. **Simple:** no necesita lógica de sizing
2. **Seguro:** es un volumen pequeño, manejable incluso con margen bajo
3. **Funcional:** es suficiente para probar el flujo end-to-end
4. **Escalable:** cambiar a valor dinámico después (% del balance, Kelly criterion, etc.)

**Futuro (Workflow 2 o mejora):**
- Consultar balance de cuenta via `/fapi/v1/account`
- Calcular quantity basado en % de riesgo (ej. 1% del balance)
- Ajustar según apalancamiento disponible

---

## Variables de configuración (recomendadas)

Almacena estos valores en n8n environment variables o en un Config node:

```
BACKEND_URL = "http://backend:8000"
SYMBOL = "BTCUSDT"
ATR_PERIOD = 14
ATR_MULTIPLIER = 2.0
KLINES_INTERVAL = "4h"
GRID_QUANTITY_PER_ORDER = 0.001
GRID_TYPE = "GEOMETRIC"
```

---

## Diagrama del flujo

```
┌─────────────────────┐
│ 1. Input Symbol     │
│ (manual o cron)     │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────────────────────┐
│ 2. GET /market-analysis/{symbol}    │
│ (fetch price, ATR, bounds)          │
└──────────┬──────────────────────────┘
           │
           ▼
┌──────────────────────────────────────┐
│ 3. AI Decision Node                  │
│ (Claude analiza ATR%, decide launch) │
└──────────┬───────────────────────────┘
           │
           ▼
    ┌──────────────┐
    │ launch = ?   │
    └──┬───────┬──┘
       │ true  │ false
       ▼       ▼
    ┌──────┐ ┌──────────┐
    │ 4a   │ │ 4b       │
    │POST  │ │Log:      │
    │grid  │ │"Skip"    │
    └──┬───┘ └──┬───────┘
       │        │
       ├────┬───┘
       │    │
       ▼    ▼
    ┌─────────────┐
    │ 5. Notify   │
    │ (Slack/log) │
    └─────────────┘
```

---

## Caso de uso: Workflow 1 en loop

Si quieres que corra periódicamente:

**Trigger:** Cron, cada 4 horas (aligned con klines_interval)
```
0 */4 * * *   (0:00, 4:00, 8:00, ... UTC)
```

**Comportamiento:**
- Cada 4h: analiza mercado
- Si ATR/price está en rango óptimo → lanza un grid nuevo
- Si ya hay un grid RUNNING para el símbolo → 400 "already exists", capturado como OK (no duplo)
- Notifica estado (lanzado o skipped)

---

## Testing del workflow (manual)

1. Abre Swagger UI: `http://localhost:8043/api/docs`
2. GET `/api/v1/market-analysis/BTCUSDT` → copia respuesta
3. En el nodo de IA de n8n, pega la respuesta como input directo
4. Verifica que el IA devuelve JSON válido con `launch: true/false`
5. Si `launch: true`, verifica que POST `/api/v1/grids` devuelve 200
6. Checks: grid aparece en `GET /api/v1/grids?status=RUNNING`

---

## Integración con Workflow 2 (Monitor)

Workflow 1 **lanza** grids.
[Workflow 2](./workflow2-monitor.md) **monitorea** grids (refresh órdenes, calcula PnL, evalúa SL/TP).

Recomendación: ambos corren en paralelo (1 lanza cada 4h, 2 monitorea cada 5 min).
