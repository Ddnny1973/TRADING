# Quick Reference — Grid Trading QA

## Endpoints Principales

### Health & Info
```bash
curl http://localhost:8000/health
curl http://localhost:8000/
```

### Market Analysis
```bash
curl "http://localhost:8000/api/v1/market-analysis/BTCUSDT?risk_pct=0.02&levels=10"
```

### Listar Grids
```bash
# Todos
curl http://localhost:8000/api/v1/grids

# Solo RUNNING
curl "http://localhost:8000/api/v1/grids?status=RUNNING"

# Un grid específico
curl http://localhost:8000/api/v1/grids/{grid_id}
```

### Crear Grid Manual
```bash
curl -X POST http://localhost:8000/api/v1/grids \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTCUSDT",
    "levels": 10,
    "grid_type": "GEOMETRIC",
    "quantity_per_order": 0.001,
    "lower_price": 42000,
    "upper_price": 43000,
    "stop_loss": 100,
    "take_profit": null,
    "max_duration_hours": null
  }'
```

### Refresh Grid
```bash
curl -X POST http://localhost:8000/api/v1/grids/{grid_id}/refresh
```

### Check Close (SL/TP/EXPIRED)
```bash
curl -X POST http://localhost:8000/api/v1/grids/{grid_id}/check-close
```

### Get PnL
```bash
curl http://localhost:8000/api/v1/grids/{grid_id}/pnl
```

### Cancelar Grid
```bash
curl -X DELETE http://localhost:8000/api/v1/grids/{grid_id}
```

---

## Valores Esperados

### Market Analysis Response (TEST 1)
| Campo | Tipo | Rango | Nota |
|-------|------|-------|------|
| `current_price` | float | > 0 | Precio último |
| `atr` | float | > 0 | Average True Range |
| `suggested_quantity_per_order` | float | > 0 | BTC/order (ej: 0.00047) |
| `allocated_capital` | float | balance × 0.02 | Capital en riesgo |
| `suggested_stop_loss` | float | allocated × 0.5 | 50% de capital asignado |
| `suggested_lower_price` | float | < current_price | Límite inferior |
| `suggested_upper_price` | float | > current_price | Límite superior |

### Grid Response (TEST 2-6)
| Campo | Valor Esperado | Ejemplo |
|-------|-----------------|---------|
| `status` | RUNNING, CANCELED | RUNNING |
| `levels` | 5-20 | 10 |
| `orders` | Array | [{ id, price, quantity, status }] |
| `stop_loss` | float > 0 | 100.0 |
| `max_duration_hours` | float > 0 | 224 |

### Grid Orders
| Campo | Valores | Nota |
|-------|---------|------|
| `status` | NEW, PARTIALLY_FILLED, FILLED, CANCELED | Orden abierta o cerrada |
| `executed_qty` | >= 0 | Cantidad ejecutada |
| `avg_fill_price` | > 0 | Precio promedio de ejecución |
| `replenished` | 0 o 1 | Si fue reposicionada |
| `level_index` | 0-N | Índice en el grid |
| `cycle` | >= 0 | Número de ciclo |

### Check Close Response (TEST 5-6)
```json
{
  "triggered": null | "STOP_LOSS" | "TAKE_PROFIT" | "EXPIRED",
  "grid": { ... GridDetailResponse ... }
}
```

---

## Configuración

### Backend (.env)
```env
BINANCE_API_KEY=...
BINANCE_API_SECRET=...
BINANCE_TESTNET_URL=https://demo-fapi.binance.com
DEFAULT_RISK_PCT=0.02
DEFAULT_LEVERAGE=1
DEFAULT_MARGIN_TYPE=ISOLATED
MIN_STEP_FEE_MULTIPLE=5.0
MAX_CONCURRENT_GRIDS=2
```

### n8n Workflow 1 (Market Decision)
- Trigger: Manual o Webhook
- Claude Model: `claude-opus-4-8`
- Temperature: 0.5
- Output esperado: `{ launch: bool, gridCount: int, lowerLimit: float, upperLimit: float, reasoning: string }`

### n8n Workflow 2 (Monitor)
- Trigger: Cron each 15 minutes
- Continue on Fail: ✅ (en POST /refresh y /check-close)
- Loop: Split in Batches (batchSize=1)
- Wait: 1.5 segundos entre items

---

## Validaciones Clave

### Grid Creado Exitosamente ✅
```
✓ Response status: 201
✓ Grid status: RUNNING
✓ orders[].status: NEW
✓ Binance testnet UI: 10 órdenes abiertas (u otro número)
✓ Leverage: 1× (Binance UI → Position)
✓ Margin: ISOLATED (Binance UI → Symbol Settings)
```

### Workflow 1 Ejecutado ✅
```
✓ Nodo 2 (Market Analysis): 200 OK
✓ Nodo 3 (AI): launch=true, gridCount=8-20
✓ Nodo 5 (Create Grid): 201 Created, id != null
✓ Telegram: Mensaje recibido si está configurado
```

### Workflow 2 Ejecutado ✅
```
✓ Nodo 2 (List Grids): 200 OK, array con grids RUNNING
✓ Nodo 5 (Refresh): 200 OK, órdenes actualizadas
✓ Nodo 7 (Check Close): 200 OK, triggered=null (si sin SL/TP)
✓ Tiempo total: < 5 segundos
```

### Grid Cerrado ✅
```
✓ API: GET /grids/{id} → status=CANCELED
✓ Binance testnet: 0 órdenes abiertas
✓ Binance testnet: Position Amt = 0
✓ Telegram: Mensaje con trigger (STOP_LOSS, TAKE_PROFIT, EXPIRED)
✓ Backend logs: "Grid closed at STOP_LOSS" (ó similar)
```

### Ciclo Completado ✅
```
✓ Orden BUY ejecutada en nivel i (executed_qty > 0)
✓ Orden SELL nueva aparece en nivel i+1 (NEW)
✓ Campo replenished: 1 (en la orden BUY)
✓ Campo cycle: 1 (en la nueva orden SELL)
```

---

## Errores Comunes & Soluciones

| Error | Causa | Solución |
|-------|-------|----------|
| 401 Unauthorized | API key inválida | Verifica BINANCE_API_KEY en .env |
| 400 "Could not fetch klines" | Símbolo no existe | Usa BTCUSDT (o verificar testnet soporta símbolo) |
| 400 "No orders placed" | Margen insuficiente | Aumenta balance en testnet faucet |
| 400 "Grid step below minimum" | Paso < 0.2% | Reduce levels o aumenta rango |
| 400 "Max concurrent grids reached" | Ya hay 2 RUNNING | Cancela uno antes de crear otro |
| 409 "One RUNNING grid per symbol" | BTCUSDT ya tiene grid | Cancela el anterior |
| 503 "Could not fetch balance" | API rate limited | Espera 60s y reintenta |
| n8n: "Could not fetch" en HTTP node | Backend no responde | Verifica: `curl http://localhost:8000/health` |
| n8n: "Continue on Fail: true" pero se detiene | Node config error | Verifica que Continue on Fail está activado |

---

## Docker Commands

```bash
# Ver logs en tiempo real
docker logs backend-python -f

# Ver últimas 100 líneas
docker logs backend-python --tail 100

# Buscar errores
docker logs backend-python | grep ERROR

# Reiniciar backend
docker restart backend-python

# Ver estado de contenedores
docker ps

# Ver volúmenes (donde vive grid_trading.db)
docker volume ls
docker volume inspect <volume_name>
```

---

## Binance Testnet UI Checks

| Check | Ubicación | Qué Verificar |
|-------|-----------|---------------|
| Órdenes abiertas | Trading → Positions | 10 órdenes LIMIT (BUY/SELL) |
| Posición | Trading → Positions | Net position = 0 o pequeño (unfilled) |
| Leverage | Position → Symbol Settings | 1× |
| Margin Type | Position → Symbol Settings | ISOLATED |
| Fills | Order History | Órdenes con status FILLED si hubo ciclos |
| PnL | Dashboard | Unrealized PnL debe ser ~0 si sin fills |

---

## Documentos Relacionados

- `manual-qa-runbook.md` — Runbook completo con 10 tests
- `api-endpoints.md` — Referencia detallada de endpoints
- `workflow1-market-decision.md` — Especificación de Workflow 1
- `workflow2-monitor.md` — Especificación de Workflow 2
- `n8n-templates/SETUP.md` — Setup de n8n workflows

---

## Contacto & Support

Si algo falla:

1. Revisa `manual-qa-runbook.md` sección "Si falla"
2. Lee logs: `docker logs backend-python`
3. Verifica `.env` tiene todas las variables
4. Reinicia: `docker restart backend-python`
5. Si persiste, verifica que Binance testnet API está disponible
