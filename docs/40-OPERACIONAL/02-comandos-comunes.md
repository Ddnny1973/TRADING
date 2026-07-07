# Comandos Comunes

## Docker

```bash
# Ver estado de contenedores
docker-compose ps

# Ver logs en tiempo real
docker-compose logs -f backend-python
docker-compose logs -f n8n

# Reiniciar
docker-compose restart
docker-compose restart backend-python

# Detener todo
docker-compose down

# Iniciar todo
docker-compose up -d

# Ver uso de recursos
docker stats
```

---

## Backend API (curl)

### Health Check
```bash
curl http://localhost:8000/health
```

### Market Analysis
```bash
# Sin levels: solo devuelve ATR y precios sugeridos
curl "http://localhost:8000/api/v1/market-analysis/BTCUSDT?atr_period=14&atr_multiplier=2.0&klines_interval=4h"

# Con levels+risk_pct: también calcula cantidad, capital, SL y viabilidad
curl "http://localhost:8000/api/v1/market-analysis/BTCUSDT?atr_period=14&atr_multiplier=2.0&klines_interval=4h&risk_pct=0.05&levels=4"
```

### List Grids
```bash
curl http://localhost:8000/api/v1/grids
curl "http://localhost:8000/api/v1/grids?status=RUNNING"
```

### Create Grid
```bash
curl -X POST http://localhost:8000/api/v1/grids \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTCUSDT",
    "lower_price": 62500,
    "upper_price": 65000,
    "levels": 4,
    "quantity_per_order": 0.002,
    "grid_type": "GEOMETRIC",
    "stop_loss": 100.0
  }'
```

### Refresh Grid (sync + replenish automático)
```bash
curl -X POST "http://localhost:8000/api/v1/grids/GRID_ID/refresh"
```

### Cancel Grid (cierre manual)
```bash
curl -X DELETE "http://localhost:8000/api/v1/grids/GRID_ID"
```

### Get Grid Detail (con órdenes)
```bash
curl "http://localhost:8000/api/v1/grids/GRID_ID"
```

### Get PnL
```bash
curl "http://localhost:8000/api/v1/grids/GRID_ID/pnl"
```

### Check Close
```bash
curl -X POST "http://localhost:8000/api/v1/grids/GRID_ID/check-close"
```

---

## Database (SQLite)

### Acceder a BD
```bash
docker-compose exec backend-python sqlite3 grid_trading.db
```

### Queries Útiles (dentro de sqlite3)
```sql
-- Ver grids en ejecución
SELECT * FROM grids WHERE status = 'RUNNING';

-- Ver todas las órdenes de una grid
SELECT * FROM orders WHERE grid_id = 'GRID_20260705_001' ORDER BY created_at DESC;

-- Ver órdenes ejecutadas
SELECT * FROM orders WHERE status = 'FILLED' ORDER BY executed_at DESC LIMIT 10;

-- Ver PnL realizado
SELECT * FROM pnl_history ORDER BY timestamp DESC LIMIT 20;

-- Contar órdenes por grid
SELECT grid_id, COUNT(*) as total FROM orders GROUP BY grid_id;

-- Ver balance total PnL
SELECT SUM(pnl_realized) as total_pnl FROM pnl_history;

-- Salir
.quit
```

---

## Python / Testing

### Ejecutar Tests
```bash
cd backend-python
pytest -v

# Test específico
pytest tests/test_grid_service.py -v

# Con coverage
pytest --cov=app tests/
```

### Verifica Dependencias
```bash
cd backend-python
pip list
```

### Virtual Environment (Desarrollo Local)
```bash
cd backend-python
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
pip install -r requirements.txt
```

---

## n8n

### Acceder a UI
```
http://localhost:5678
```

### Ver ejecuciones de workflow
1. n8n → Workflow 1/2 → Executions
2. Click en ejecución para ver logs completos

### Test manual de HTTP node
```javascript
// Dentro de un Code node en n8n
const response = await fetch(process.env.BACKEND_URL + '/health');
const data = await response.json();
return data;
```

---

## Tareas de Mantenimiento

### Backup de BD
```bash
docker-compose exec backend-python sqlite3 grid_trading.db ".dump" > backup-$(date +%Y%m%d).sql
```

### Restore de BD
```bash
docker-compose exec -T backend-python sqlite3 grid_trading.db < backup-20260705.sql
```

### Ver tamaño de BD
```bash
ls -lh backend-python/grid_trading.db
```

### Limpiar logs de Docker
```bash
docker system prune -a --volumes
```

---

## Diagnóstico Rápido

```bash
# 1. ¿Backend está up?
curl http://localhost:8000/health

# 2. ¿DB está connected?
curl http://localhost:8000/health | grep database

# 3. ¿Binance API está reachable?
curl http://localhost:8000/health | grep binance

# 4. ¿Hay grids activas?
curl "http://localhost:8000/api/v1/grids?status=RUNNING"
```

---

## Alias Útiles (Linux/macOS)

Agrega a `.bash_profile` o `.zshrc`:

```bash
alias trading-health='curl http://localhost:8000/health'
alias trading-grids='curl "http://localhost:8000/api/v1/grids?status=RUNNING"'
alias trading-logs='docker-compose logs -f backend-python'
alias trading-db='docker-compose exec backend-python sqlite3 grid_trading.db'
```

---

## Windows PowerShell Equivalentes

```powershell
function trading-health { Invoke-WebRequest http://localhost:8000/health | Select-Object -ExpandProperty Content }
function trading-grids { Invoke-WebRequest "http://localhost:8000/api/v1/grids?status=RUNNING" | Select-Object -ExpandProperty Content }
function trading-logs { docker-compose logs -f backend-python }
```

---

Ver también: [API Reference](../30-API-REFERENCE/01-request-response.md)
