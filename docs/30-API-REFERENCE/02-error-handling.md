# Error Handling

## HTTP Status Codes

### 2xx Success
- `200` — OK (request exitoso)
- `201` — Created (recurso creado)

### 4xx Client Error
- `400` — Bad Request (parámetros inválidos)
- `409` — Conflict (ej. max grids alcanzado)
- `422` — Validation Error (Pydantic validation)

### 5xx Server Error
- `500` — Internal Server Error
- `503` — Service Unavailable (backend down, DB error, etc.)

---

## Error Response Format

Todos los errores siguen este formato:

```json
{
  "error": "Grid validation failed",
  "message": "Step size 0.1% is less than minimum 0.2%",
  "code": "INVALID_GRID_PARAMS",
  "timestamp": "2026-07-05T20:35:00Z"
}
```

---

## Errores Comunes

### Invalid Parameters

**Escenario:** Intentas crear un grid con parámetro inválido.

```
Status: 400
{
  "error": "Grid validation failed",
  "message": "Step size 0.1% is less than minimum 0.2% (5x fees)",
  "code": "STEP_TOO_SMALL"
}
```

**Solución:** Aumenta niveles o aumenta rango (lower/upper price).

---

### Risk Too High

**Escenario:** Risk pct > 10%

```
Status: 400
{
  "error": "Risk validation failed",
  "message": "Risk 15% exceeds maximum 10%",
  "code": "RISK_TOO_HIGH"
}
```

**Solución:** Baja risk_pct (default 2%).

---

### Max Grids Reached

**Escenario:** Ya tienes 2 grids activas (máximo).

```
Status: 409
{
  "error": "Concurrency limit reached",
  "message": "Already have 2 active grids. Max is 2.",
  "code": "MAX_GRIDS_EXCEEDED"
}
```

**Solución:** Cierra una grid existente o espera a que se cierre.

---

### Min Notional Not Met

**Escenario:** Total de órdenes < 10 USDT.

```
Status: 400
{
  "error": "Notional validation failed",
  "message": "Total notional $5.50 is less than minimum $10",
  "code": "NOTIONAL_TOO_SMALL"
}
```

**Solución:** Aumenta quantity_per_order o niveles.

---

### Binance API Error (429 Rate Limit)

**Escenario:** Backend alcanzó rate limit de Binance.

```
Status: 429
{
  "error": "Binance rate limit exceeded",
  "message": "Too many requests sent; 1200 in 60 seconds",
  "code": "BINANCE_RATE_LIMIT",
  "retry_after": 60
}
```

**Solución:** Espera 60 segundos, reintentar automáticamente.

---

### Grid Not Found

**Escenario:** Intentas cerrar un grid que no existe.

```
Status: 404
{
  "error": "Grid not found",
  "message": "No grid with ID GRID_INVALID_123",
  "code": "GRID_NOT_FOUND"
}
```

**Solución:** Verifica grid ID con `GET /grids`.

---

### Database Connection Error

**Escenario:** BD desconectada.

```
Status: 503
{
  "error": "Database connection failed",
  "message": "SQLite cannot connect to grid_trading.db",
  "code": "DATABASE_ERROR"
}
```

**Solución:** Reinicia backend: `docker-compose restart backend-python`

---

### Binance Connection Error

**Escenario:** No puedo conectar a Binance.

```
Status: 503
{
  "error": "Binance API unreachable",
  "message": "Connection timeout after 30 seconds",
  "code": "BINANCE_UNREACHABLE"
}
```

**Solución:** Verifica internet, API key, IP whitelist en Binance.

---

## Troubleshooting by Error Code

| Código | Causa | Solución |
|--------|-------|----------|
| `STEP_TOO_SMALL` | Paso entre órdenes < 0.2% | Aumenta niveles o rango |
| `RISK_TOO_HIGH` | Risk > 10% | Baja risk_pct |
| `MAX_GRIDS_EXCEEDED` | Ya tienes 2 grids | Cierra una |
| `NOTIONAL_TOO_SMALL` | Total < 10 USDT | Aumenta cantidad |
| `BINANCE_RATE_LIMIT` | 1200 req/min | Espera 60 seg |
| `GRID_NOT_FOUND` | Grid ID inválido | Verifica con `/grids` |
| `DATABASE_ERROR` | BD desconectada | Reinicia backend |
| `BINANCE_UNREACHABLE` | Red/API key | Verifica conexión |

---

## Retry Logic en n8n

Los workflows n8n implementan reintentos automáticos:

```
Intento 1: Request
├─ Status 503 → Espera 5 seg
├─ Intento 2
├─ Status 429 → Espera 60 seg
├─ Intento 3
└─ Status 200 ✓ Continúa
```

---

## Logging

### Habilitar DEBUG Logs

En `.env`:
```env
LOG_LEVEL=DEBUG
```

### Ver Logs en Docker

```bash
docker-compose logs -f backend-python
```

Buscar errores:

```bash
docker-compose logs backend-python | grep ERROR
```

---

## Si Todo Falla

1. Verifica `/health`
2. Mira logs: `docker logs backend-python`
3. Reinicia: `docker-compose restart`
4. Lee [Troubleshooting](../40-OPERACIONAL/01-troubleshooting.md)

---

Ver también: [Troubleshooting](../40-OPERACIONAL/01-troubleshooting.md)
