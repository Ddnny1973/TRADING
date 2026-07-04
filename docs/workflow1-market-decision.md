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
risk_pct=0.02
levels=10
```

(Nota: `risk_pct` y `levels` son opcionales. Si se omiten, no se calcula `suggested_quantity_per_order`. Si se proporcionan juntos, el backend consulta el balance y calcula la cantidad.)

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
  "suggested_range": 800.0,
  "suggested_quantity_per_order": 0.001
}
```

**Nota:** El endpoint ahora calcula `suggested_quantity_per_order` automáticamente si proporcionas `risk_pct` y `levels`. Esto es útil porque evita que la IA tenga que hacer cálculos de sizing — puede reutilizar el valor sugerido o ajustarlo según su criterio.

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

### ⚠️ IMPORTANTE: `levels` (Config) vs `gridCount` (IA) — NO son lo mismo

Son dos parámetros con nombres parecidos pero **totalmente independientes**, y esto ha causado confusión real durante las pruebas:

- **`levels`** (nodo Config / query param de `/market-analysis`) → solo se usa para calcular `suggested_quantity_per_order` (el sizing por orden). La IA **nunca ve este valor como restricción**.
- **`gridCount`** (campo de la respuesta de la IA) → es una decisión **autónoma** de la IA, basada únicamente en las reglas del `atr_pct` del system prompt (rango 5-20). Es este valor — no `levels` — el que efectivamente se envía como `"levels"` en el `POST /api/v1/grids` (Nodo 5).

**Consecuencia real observada:** configurar `levels=5` en el nodo Config para limitar la exposición **NO limita nada** — la IA puede seguir decidiendo `gridCount=12` y esa es la cantidad de órdenes que realmente se colocan.

**Decisión tomada (fase de pruebas):** se agregó un tope duro en el nodo `Parse AI Decision` de `n8n-workflows/workflow1-market-decision.json`:
```javascript
const cappedGridCount = decision.gridCount != null
  ? Math.min(decision.gridCount, configLevels)  // configLevels = $('Config').item.json.levels
  : decision.gridCount;
```
Es decir: **la IA decide, pero `levels` de Config actúa como techo/cap de seguridad** — nunca se ejecutan más niveles que los configurados manualmente, aunque la IA sugiera más.

**Pendiente de alinear (no resuelto aún):** el system prompt de la IA (`Build Gemini Request`) sigue sin mencionar `levels`/el cap — la IA sigue "pensando" que puede elegir libremente entre 5-20, sin saber que su sugerencia puede ser recortada después. Esto puede llevar a razonamientos inconsistentes (ej. la IA explica por qué eligió 12 niveles para cierta volatilidad, pero el grid real termina con 5). Dos opciones a futuro, sin resolver todavía:
1. Pasarle `levels` de Config a la IA como techo explícito en el prompt (ej. "el máximo permitido es {{ levels }}, nunca sugieras más"), para que su razonamiento sea coherente con lo que realmente se ejecuta.
2. Quitarle a la IA la decisión de `gridCount` por completo y dejar que siempre sea un valor fijo controlado por Config (menos "inteligente", pero 100% predecible).

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
  "atr_period": 14,
  "atr_multiplier": 2.0,
  "klines_interval": "4h",
  "stop_loss": null,
  "take_profit": null,
  "max_duration_hours": null
}
```

**Notas:**
- `quantity_per_order: 0.001` = 1 miliBTC ≈ $42.50 notional (escalable después)
- `grid_type: GEOMETRIC` — espaciado logarítmico (recomendado)
- `atr_period`, `atr_multiplier`, `klines_interval` — parámetros usados por el AI node, repetir aquí para que el backend recalcule bounds/duration si es necesario
- `max_duration_hours: null` — se calcula automáticamente como 4× (klines_interval × atr_period). Ver [grid-expiration-strategy.md](./grid-expiration-strategy.md) para detalles
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

## Decisión: quantity_per_order — Ahora con Sizing Dinámico ✅

**Status actual:** El endpoint `/api/v1/market-analysis` ahora calcula automáticamente `suggested_quantity_per_order` si proporcionas `risk_pct` y `levels`.

### Fórmula de sizing (sin leverage, 1-2% riesgo):

```
capital_a_arriesgar = balance_disponible * risk_pct
precio_promedio = (lower_price + upper_price) / 2
quantity_per_order = capital_a_arriesgar / (levels * precio_promedio)
```

### Flujo en n8n:

**Nodo 2 (Market Analysis):**
```
GET /api/v1/market-analysis/BTCUSDT?risk_pct=0.02&levels=10
```

**Response incluye:**
```json
{
  "suggested_lower_price": 42100.0,
  "suggested_upper_price": 42900.0,
  "suggested_quantity_per_order": 0.00047
}
```

**Nodo 3 (AI Decision):**
La IA recibe `suggested_quantity_per_order` ya calculado. Puede:
- Reutilizarlo tal cual (confianza en el algoritmo)
- Ajustarlo según su criterio (ej. si la volatilidad es extrema, reduce un 50%)

### Beneficios:
- ✅ **Sizing seguro:** basado en % del balance, no en volumen fijo
- ✅ **Sin apalancamiento:** 1× notional, riesgo controlado en 1-2% por grid
- ✅ **Adaptativo:** si el balance crece, quantity crece automáticamente
- ✅ **Simple:** la IA no necesita hacer cálculos, solo evaluar si la sugerencia es razonable

### Rango recomendado de risk_pct:
- **Conservative (1%):** `risk_pct=0.01` — cantidad pequeña, bajo riesgo
- **Normal (2%):** `risk_pct=0.02` — balance entre riesgo y oportunidad (recomendado)
- **Aggressive (3-5%):** `risk_pct=0.03+` — mayor exposición, solo si tienes experiencia

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
