# Setup del Backend - FastAPI + Docker

## Parte 1: Clonar y Configurar

### Paso 1: Clonar Repositorio

```bash
cd /path/to/TRADING
git clone <repo-url> .
```

O si ya está clonado:
```bash
cd TRADING
```

### Paso 2: Copiar .env.example

```bash
cp backend-python/.env.example backend-python/.env
```

### Paso 3: Editar .env

Abre `backend-python/.env` y configura:

```env
# === BINANCE ===
BINANCE_API_KEY=<tu-api-key-testnet>
BINANCE_API_SECRET=<tu-api-secret-testnet>
BINANCE_TESTNET_URL=https://demo-fapi.binance.com

# Para producción (cambiar después de QA):
# BINANCE_TESTNET_URL=https://fapi.binance.com

# === GRID TRADING ===
DEFAULT_RISK_PCT=0.02              # 2% por grid (recomendado)
DEFAULT_LEVERAGE=1                  # Sin leverage (importante)
DEFAULT_MARGIN_TYPE=ISOLATED        # Aísla riesgo por símbolo
MAX_CONCURRENT_GRIDS=2              # Máximo 2 simultáneas
MIN_STEP_FEE_MULTIPLE=5.0           # Min step = 5 × 2 × fees = 0.1%

# === DATABASE ===
DATABASE_URL=sqlite:///grid_trading.db
# Para producción con PostgreSQL:
# DATABASE_URL=postgresql://user:pass@localhost/trading_db

# === LOGGING ===
LOG_LEVEL=INFO                      # DEBUG para troubleshooting
```

**Obtener API Key/Secret de Binance:**

1. Abre https://testnet.binancefuture.com (para testnet)
2. Click perfil → API Management
3. Create API Key (nombre: "Grid Trading")
4. Enable Futures Trading
5. Copia **API Key** y **Secret Key**
6. Opcional: IP Whitelist (tu IP)

---

## Parte 2: Docker Setup

### Verifica Docker está instalado

```bash
docker --version
docker-compose --version
```

Si no está, descarga desde https://www.docker.com/

### Inicia Contenedores

```bash
cd TRADING
docker-compose up -d
```

Esto inicia:
- **backend-python** (FastAPI en puerto 8000)
- **n8n** (en puerto 5678)
- **SQLite** (en backend-python/grid_trading.db)

### Verifica que iniciaron

```bash
docker-compose ps
```

Deberías ver:
```
NAME                 STATUS
backend-python      Up 2 seconds
n8n                 Up 2 seconds
```

---

## Parte 3: Verificar Conexión Backend

### Health Check

```bash
curl http://localhost:8000/health
```

**Respuesta esperada:**
```json
{
  "status": "healthy",
  "uptime_seconds": 2,
  "database": "connected",
  "binance_api": "reachable"
}
```

**Si falla:**

```bash
# Ver logs del backend
docker-compose logs backend-python

# Reiniciar
docker-compose restart backend-python

# Si sigue fallando, restart completo
docker-compose down
docker-compose up -d
```

---

## Parte 4: Base de Datos

### Verificar BD fue creada

```bash
ls -lh backend-python/grid_trading.db
```

Deberías ver el archivo (creado automáticamente).

### Acceder a BD (SQLite)

```bash
docker-compose exec backend-python sqlite3 grid_trading.db
```

Dentro de sqlite3:

```sql
.tables
SELECT * FROM grids;
.quit
```

### Para PostgreSQL (Producción)

Si quieres usar PostgreSQL en lugar de SQLite:

```env
DATABASE_URL=postgresql://username:password@localhost:5432/trading
```

Luego:
```bash
docker run -d \
  --name trading-postgres \
  -e POSTGRES_PASSWORD=yourpassword \
  -p 5432:5432 \
  postgres:15
```

---

## Parte 5: Dependencias Python

### Verificar que fueron instaladas

```bash
docker-compose exec backend-python pip list
```

Deberías ver: `fastapi`, `sqlalchemy`, `aiohttp`, `pydantic`, etc.

### Si faltan dependencias

```bash
docker-compose exec backend-python pip install -r requirements.txt
```

O reinicia completamente:
```bash
docker-compose down
docker-compose up -d --build
```

---

## Parte 6: Logs y Debugging

### Ver logs en tiempo real

```bash
docker-compose logs -f backend-python
```

**Ctrl+C** para salir.

### Ver solo errores

```bash
docker-compose logs backend-python | grep ERROR
```

### Ver logs de n8n

```bash
docker-compose logs -f n8n
```

---

## Parte 7: Primeros Tests

### Test 1: Health

```bash
curl http://localhost:8000/health
```

Esperado: `{"status": "healthy", ...}`

### Test 2: Market Analysis

```bash
curl -X POST http://localhost:8000/market-analysis \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTCUSDT",
    "interval": "4h",
    "atr_period": 14,
    "sma_period": 50
  }'
```

Esperado: `{"symbol": "BTCUSDT", "current_price": ..., "atr": ..., "trend": ...}`

### Test 3: Account

```bash
curl http://localhost:8000/account
```

Esperado: `{"balance_usdt": ..., "available_usdt": ..., "positions": [...]}`

Si ves balance_usdt > 0 → ✅ API key funciona

---

## Parte 8: Configuración Avanzada

### Aumentar Logging

En `.env`:
```env
LOG_LEVEL=DEBUG
```

Reinicia:
```bash
docker-compose restart backend-python
```

### Custom Docker Build

Si editas código Python:

```bash
docker-compose down
docker-compose up -d --build
```

### Usar Backend Local (Sin Docker)

Para desarrollo local:

```bash
cd backend-python
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

Luego en n8n usa: `http://localhost:8000` (no `http://backend-python:8000`)

---

## Parte 9: Limpieza y Mantenimiento

### Resetear BD (Borra datos)

```bash
rm backend-python/grid_trading.db
docker-compose restart backend-python
```

### Ver uso de disco

```bash
docker exec backend-python du -sh /app
```

### Backup de BD

```bash
docker-compose exec backend-python sqlite3 grid_trading.db ".dump" > backup-$(date +%Y%m%d).sql
```

### Restore de BD

```bash
docker-compose exec -T backend-python sqlite3 grid_trading.db < backup-20260705.sql
```

---

## Checklist Setup

- [ ] `.env` configurado (API key, secret)
- [ ] `docker-compose up -d` ejecutado
- [ ] `docker-compose ps` muestra 2 servicios UP
- [ ] `/health` devuelve OK
- [ ] `/account` devuelve balance > 0
- [ ] BD creada (`grid_trading.db`)
- [ ] Logs no muestran errores CRITICAL
- [ ] n8n accesible en http://localhost:5678

---

## Próximos Pasos

1. [Setup de n8n](01-setup-n8n.md) — Configurar workflows
2. [Verificación](03-verificacion.md) — Tests de integración
3. [QA Quick Reference](../40-OPERACIONAL/03-qa-quick-reference.md) — Primeros tests

---

## Referencia Rápida

```bash
# Iniciar todo
docker-compose up -d

# Ver estado
docker-compose ps

# Logs
docker-compose logs -f backend-python
docker-compose logs -f n8n

# Health check
curl http://localhost:8000/health

# Reiniciar backend
docker-compose restart backend-python

# Detener todo
docker-compose down

# Reiniciar completamente
docker-compose down
docker-compose up -d --build
```
