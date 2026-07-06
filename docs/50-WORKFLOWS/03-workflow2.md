# Workflow 2: Grid Monitor - Especificación Detallada

**Referencia completa:** Ver `docs/workflow2-monitor.md` (archivo original)

---

## Resumen Ejecutivo

**Trigger:** Cron cada 15 minutos (automático)  
**Duración:** ~3-5 segundos  
**Función:** Sincronizar grids + replenish fills + evaluar closures

---

## Flujo Step-by-Step

### 1. Trigger

```
Cron: Cada 15 minutos automáticamente
00:00, 00:15, 00:30, ... 23:45 (every day, 24/7)
```

### 2. Fetch Active Grids

Llama Backend:
```
GET /grids?status=ACTIVE
```

Backend responde:
```json
{
  "grids": [
    {
      "grid_id": "GRID_20260705_001",
      "symbol": "BTCUSDT",
      "status": "ACTIVE",
      "lower_price": 61275,
      "upper_price": 65725,
      "levels": 15,
      "pnl_realized": 0.00
    },
    {
      "grid_id": "GRID_20260705_002",
      "symbol": "ETHUSDT",
      "status": "ACTIVE",
      ...
    }
  ],
  "total": 2
}
```

### 3. Para Cada Grid: Refresh

Llama Backend:
```
POST /refresh-grid/GRID_20260705_001
```

Qué hace:
- Fetch órdenes OPEN/FILLED de Binance
- Sincroniza estado en BD
- Detecta fills nuevas

Backend responde:
```json
{
  "grid_id": "GRID_20260705_001",
  "status": "ACTIVE",
  "orders_synced": 15,
  "orders_filled": 3,
  "timestamp": "2026-07-05T20:35:00Z"
}
```

### 4. Para Cada Grid: Replenish

Llama Backend:
```
POST /replenish-grid/GRID_20260705_001
```

Qué hace:
- Busca órdenes FILLED sin su "par"
- Si BUY ejecutado → Crea SELL a precio + 0.4%
- Si SELL ejecutado → Crea BUY a precio - 0.4%
- **Crea ciclos automáticos**

Backend responde:
```json
{
  "grid_id": "GRID_20260705_001",
  "orders_replenished": 2,
  "total_orders_now": 14,
  "timestamp": "2026-07-05T20:35:00Z"
}
```

### 5. Evaluate Closures

Para cada grid, chequea:
- **Stop Loss hit?** Si precio < SL → Cierra
- **Take Profit hit?** Si precio > TP → Cierra
- **EXPIRED?** Si edad > 224h → Cierra

Si aplica alguno:
```
POST /close-grid/GRID_ID
```

Backend responde:
```json
{
  "grid_id": "GRID_20260705_001",
  "status": "CLOSED",
  "reason": "STOP_LOSS",
  "pnl_realized": -2.50
}
```

### 6. Aggregate Results

Sumario:
```
Grids monitored: 2
Orders synced: 30
Orders filled: 3
Orders replenished: 2
Grids closed: 0
Uptime: 100%
```

### 7. Send Telegram Notification

```
📊 Monitoring Report (15:35 UTC)

Grids checked: 2 ✅
- GRID_001 (BTC): 15 orders, 0 filled
- GRID_002 (ETH): 15 orders, 2 filled

Orders synced: 30
Orders replenished: 2
Grids closed: 0

Status: ✅ HEALTHY
```

---

## Variables Importantes

| Variable | Ejemplo | Descripción |
|----------|---------|-------------|
| grids_active | 2 | Cuántos grids están activos |
| orders_synced | 30 | Total de órdenes sincronizadas |
| orders_filled | 3 | Órdenes ejecutadas en este ciclo |
| orders_replenished | 2 | Órdenes nuevas creadas |
| grids_closed | 0 | Grids cerradas (SL/TP/EXP) |
| pnl_total | +5.50 | PnL acumulado |
| errors | 0 | Errores detectados |

---

## Configuración

### Cron (Automático)

En n8n UI:
```
Trigger Node → Type: "Cron"
Interval: Minutes
Minutes: 15
```

### Environment Variables

```
BACKEND_URL=http://backend-python:8000
N8N_BLOCK_ENV_ACCESS_IN_NODE=false
TELEGRAM_CHAT_ID=<tu-chat-id>
```

---

## Ciclo Completo Ejemplo

### Hour 0: Workflow 1 Ejecuta
```
✅ GRID_001 creada (BTC)
   15 órdenes BUY en rango 61275-65725
   Status: ACTIVE
```

### Hour 0:15: Workflow 2 Ejecuta #1
```
Grids checked: 1
Orders synced: 15
Orders filled: 0
Orders replenished: 0
Status: ✅ No fills yet (esperando mercado)
```

### Hour 0:30: Workflow 2 Ejecuta #2
```
Grids checked: 1
Orders synced: 15
Orders filled: 1 (BUY @ 63500)
Orders replenished: 1 (SELL @ 63710)
Status: ✅ Ciclo iniciado
```

### Hour 0:45: Workflow 2 Ejecuta #3
```
Grids checked: 1
Orders synced: 15
Orders filled: 2 (SELL @ 63710 ejecutado)
Orders replenished: 1 (BUY @ 63500)
Status: ✅ Ciclo completado, ganancia realizada
```

### Hour 1:00: Workflow 2 Ejecuta #4 - 96 (96 veces / 24 horas)
```
Ciclos continuos: BUY → SELL → BUY → ...
PnL acumulado: +0.38% × N ciclos
```

---

## Error Handling & Retry Logic

| Escenario | Acción |
|-----------|--------|
| Backend timeout | Reintentar 3x con backoff |
| Binance API 429 | Esperar 60 seg, reintentar |
| Grid not found | Log error, continuar siguiente |
| Order cancel fail | Log, marcador para revisión |

---

## Monitoreo Continuo (24/7)

**Workflow 2 se ejecuta 96 veces/día** (cada 15 min):
```
Uptime esperado: > 99% (1 falla/día = aceptable)
Grids procesadas: 1-2 simultáneamente
Latencia: < 5 seg por ejecución
```

---

## Métricas de Salud

Cada ejecución de Workflow 2 debe:
- ✅ Completarse en < 10 segundos
- ✅ Sincronizar 15-30 órdenes
- ✅ Replenish fills sin errores
- ✅ Enviar notificación
- ✅ 0 crashes/errores críticos

---

## Testing Workflow 2

### Manual Execution (Desarrollo)

```
1. n8n UI → Workflow 2 → Execute
2. Espera ~5 seg
3. Revisa output final
4. Verifica órdenes sincronizadas: curl http://localhost:8000/grids/GRID_ID/orders
```

### Automated (Cron 24/7)

```
1. Workflow 2 → Activate (switch ON)
2. Monitorea "Executions" tab cada hora
3. Revisa logs de n8n
4. Verifica PnL acumulado (curl /grids)
```

### 48-Hour Test

```
Duración: 48 horas
Objetivo: Validar ciclos continuos
Success: >= 10 ciclos sin errores
```

---

## Performance Optimization

Si Workflow 2 es lento:

1. **Reducir sync frequency:** De 15 min → 30 min
2. **Batch grids:** Procesar múltiples grids en paralelo
3. **Cache market data:** Evitar redundantes calls
4. **Async HTTP:** Non-blocking requests

---

## Próximas Secciones

- [Workflow 1: Market Decision](02-workflow1.md)
- [Visión General](01-vision-general.md)
- [Setup de n8n](../20-SETUP/01-setup-n8n.md)

---

## Referencia Técnica

Para detalles completos, ver: `/docs/workflow2-monitor.md`
