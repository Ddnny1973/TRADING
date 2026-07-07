# Workflow 1: Market Decision - Especificación Detallada

**Referencia completa:** Ver `docs/workflow1-market-decision.md` (archivo original)

---

## Resumen Ejecutivo

**Trigger:** Manual o Cron cada 4 horas  
**Duración:** ~15-30 segundos  
**Función:** Analizar mercado + decisión IA + crear grid

---

## Flujo Step-by-Step

### 1. Trigger

```
Manual: Usuario hace click "Execute" en n8n UI
Automático: Cron cada 4 horas (00:00, 04:00, 08:00, etc. UTC)
```

### 2. Market Analysis

Llama Backend (GET):
```
GET /api/v1/market-analysis/BTCUSDT
  ?risk_pct=0.05&levels=4&atr_period=14&atr_multiplier=2.0&klines_interval=4h
```

Backend responde:
```json
{
  "symbol": "BTCUSDT",
  "current_price": 63500.50,
  "atr": 450.25,
  "suggested_lower_price": 62600.0,
  "suggested_upper_price": 64400.0,
  "suggested_range": 1800.0,
  "suggested_quantity_per_order": 0.002,
  "allocated_capital": 500.0,
  "suggested_stop_loss": 250.0,
  "min_viable_quantity": 0.001,
  "grid_viable": true,
  "required_risk_pct": 0.032,
  "klines_interval": "4h"
}
```

### 3. IF: Grid viable?

**Condición:** `$json.grid_viable === true`

- Si **FALSE** → Telegram notifica "Grid NO viable, se requiere risk_pct >= X" y el workflow **termina**
- Si **TRUE** → continúa al Build Gemini Request

### 4. AI Decision (Gemini 2.5-flash)

**Prompt al modelo:** Datos de mercado + reglas de criterio (ATR%, gridCount razonable, etc.)

**Gemini responde (JSON):**
```json
{
  "launch": true,
  "lowerLimit": 62600.0,
  "upperLimit": 64400.0,
  "gridCount": 4,
  "reasoning": "ATR 0.7% lateral, viable con 4 niveles..."
}
```

**Lógica:**
- Si `launch === false` → Telegram "Grid NO lanzado + reasoning" y termina
- Si `launch === true` → Continúa a crear grid

### 5. Create Grid

Llama Backend (POST):
```
POST /api/v1/grids
{
  "symbol": "BTCUSDT",
  "lower_price": lowerLimit,
  "upper_price": upperLimit,
  "levels": min(gridCount, Config.levels=4),
  "quantity_per_order": suggested_quantity_per_order,
  "grid_type": "GEOMETRIC",
  "stop_loss": suggested_stop_loss,
  "take_profit": null
}
```

Backend responde:
```json
{
  "id": "uuid-grid-001",
  "status": "RUNNING",
  "levels": 4,
  "stop_loss": 250.0,
  "orders": [...]
}
```

### 6. Send Telegram Notification

```
✅ Grid lanzado: BTCUSDT
   ID: uuid-grid-001 | Niveles: 4 | Rango: 62600-64400
   💭 ATR 0.7% lateral, viable con 4 niveles...
```

---

## Variables Importantes

| Variable | Ejemplo | Descripción |
|----------|---------|-------------|
| symbol | BTCUSDT | Símbolo a tradear |
| current_price | 63500 | Precio actual |
| atr | 450 | Volatilidad (ATR) |
| risk_pct | 0.05 | 5% del balance (Config) |
| levels | 4 | Cantidad de órdenes (Config) |
| suggested_lower_price | 62600 | Precio mínimo sugerido por ATR |
| suggested_upper_price | 64400 | Precio máximo sugerido por ATR |
| suggested_quantity_per_order | 0.002 | Cantidad calculada por risk% |
| suggested_stop_loss | 250.0 | SL = allocated_capital × 0.5 |
| min_viable_quantity | 0.001 | Mínimo para cumplir 50 USDT min_notional |
| grid_viable | true | ¿Es viable el grid con este capital? |
| grid_id | uuid | ID único del grid |

---

## Configuración

### Cron (Automatización)

En n8n UI:
```
Trigger Node → Type: "Cron"
Interval: Hours
Hours: 4
Timezone: UTC
```

O manualmente:
```
Click "Execute" button en n8n
```

### Environment Variables

Necesarias en n8n:
```
BACKEND_URL=http://backend-python:8000
N8N_BLOCK_ENV_ACCESS_IN_NODE=false
TELEGRAM_CHAT_ID=<tu-chat-id>  (usado en IF: Chat autorizado? y notificaciones)
# Gemini API key se configura como credencial HTTP Header Auth en n8n
```

---

## Error Handling

| Error | Causa | Solución |
|-------|-------|----------|
| grid_viable = false | Capital insuficiente para min_notional 50 USDT | Aumentar risk_pct o reducir levels |
| 400: Step too small | Rango muy pequeño | Aumentar upper-lower |
| 409: Max grids exceeded | Ya hay 2 activos | Cerrar una grid |
| 503: Binance unreachable | API caída | Esperar o reintentar |
| Gemini launch=false | Mercado no apto para grid | Esperar próxima ejecución |

---

## Success Metrics

**Workflow 1 debe:**
- ✅ Ejecutarse sin errores
- ✅ Verificar viabilidad (IF: Grid viable?) antes de llamar a Gemini
- ✅ Crear grid con status RUNNING si Gemini dice launch=true
- ✅ Propagar stop_loss ($json.suggested_stop_loss) al POST /api/v1/grids (no null)
- ✅ Propagar quantity_per_order ($json.suggested_quantity_per_order, sin Math.max)
- ✅ Enviar notificación a Telegram
- ✅ Completarse en < 60 segundos

---

## Testing Workflow 1

### Manual Execution

```
1. n8n UI → Workflow 1 → Execute
2. Espera ~30 seg
3. Revisa output final
4. Verifica grid creada: curl "http://localhost:8000/api/v1/grids?status=RUNNING"
```

### Automated (Cron)

```
1. Workflow 1 → Activate (switch ON)
2. Espera 4 horas
3. Verifica ejecución en "Executions" tab
4. Revisa logs
```

---

## Próximas Secciones

- [Workflow 2: Monitor](03-workflow2.md)
- [Visión General](01-vision-general.md)
- [Setup de n8n](../20-SETUP/01-setup-n8n.md)

---

## Referencia Técnica

Para detalles completos, ver: `/docs/workflow1-market-decision.md`
