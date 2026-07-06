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

Llama Backend:
```
POST /market-analysis
{
  "symbol": "BTCUSDT",
  "interval": "4h",
  "atr_period": 14,
  "sma_period": 50
}
```

Backend responde:
```json
{
  "symbol": "BTCUSDT",
  "current_price": 63500.50,
  "atr": 450.25,
  "sma": 62800.00,
  "trend": "bullish",
  "volatility": "medium"
}
```

### 3. AI Decision (OpenAI/Gemini)

**Prompt:** "Is BTC bullish right now? Current: {price}, ATR: {atr}, SMA: {sma}, Trend: {trend}. Answer YES or NO."

**IA responde:** `YES` (bullish) o `NO` (bearish)

**Lógica:**
- Si YES → Continúa a step 4
- Si NO → Envía notificación "Market not bullish, skipping" y termina

### 4. Calculate Grid Parameters

Si YES:

```
lower_price = current_price - (2.5 × atr)
upper_price = current_price + (2.5 × atr)
levels = 15
risk_pct = 0.02
```

### 5. Create Grid

Llama Backend:
```
POST /create-grid
{
  "symbol": "BTCUSDT",
  "lower_price": <calculated>,
  "upper_price": <calculated>,
  "levels": 15,
  "risk_pct": 0.02
}
```

Backend responde:
```json
{
  "grid_id": "GRID_20260705_001",
  "status": "ACTIVE",
  "orders_created": 15
}
```

### 6. Set Stop Loss

Llama Backend:
```
POST /set-stop-loss/GRID_20260705_001
{
  "stop_loss_pct": 0.02
}
```

Backend responde:
```json
{
  "grid_id": "GRID_20260705_001",
  "stop_loss_price": <calculated>
}
```

### 7. Send Telegram Notification

```
✅ Grid GRID_20260705_001 created
   Symbol: BTCUSDT
   Range: 60000 - 66000
   Levels: 15
   Stop Loss: 58500
   Status: ACTIVE ✅
```

---

## Variables Importantes

| Variable | Ejemplo | Descripción |
|----------|---------|-------------|
| symbol | BTCUSDT | Símbolo a tradear |
| current_price | 63500 | Precio actual |
| atr | 450 | Volatilidad |
| sma | 62800 | Promedio móvil |
| trend | bullish | Tendencia |
| lower_price | 61275 | Precio mínimo del grid |
| upper_price | 65725 | Precio máximo del grid |
| levels | 15 | Cantidad de órdenes |
| risk_pct | 0.02 | 2% del balance |
| grid_id | GRID_... | ID único |

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
TELEGRAM_CHAT_ID=<tu-chat-id>
OPENAI_API_KEY=<tu-api-key>  (opcional, si usas OpenAI)
```

---

## Error Handling

| Error | Causa | Solución |
|-------|-------|----------|
| 400: Step too small | Rango muy pequeño | Aumentar upper-lower |
| 409: Max grids exceeded | Ya hay 2 activos | Cerrar una grid |
| 503: Binance unreachable | API caída | Esperar o reintentar |
| IA says NO | Mercado bearish | Esperar próxima ejecución |

---

## Success Metrics

**Workflow 1 debe:**
- ✅ Ejecutarse sin errores
- ✅ Crear grid si IA dice YES
- ✅ Setear SL automáticamente
- ✅ Enviar notificación a Telegram
- ✅ Completarse en < 60 segundos

---

## Testing Workflow 1

### Manual Execution

```
1. n8n UI → Workflow 1 → Execute
2. Espera ~30 seg
3. Revisa output final
4. Verifica grid creada: curl http://localhost:8000/grids?status=ACTIVE
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
