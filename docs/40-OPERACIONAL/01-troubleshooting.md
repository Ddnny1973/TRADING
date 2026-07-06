# Troubleshooting - Problemas y Soluciones

## Backend No Responde

**Síntoma:** `curl http://localhost:8000/health` → Connection refused

**Solución:**
```bash
# 1. Verifica si el contenedor está corriendo
docker-compose ps

# 2. Inicia si no está
docker-compose up -d

# 3. Verifica logs
docker-compose logs -f backend-python

# 4. Si sigue sin funcionar, reinicia completamente
docker-compose down
docker-compose up -d
```

---

## Grid Creation Falla con "Step Too Small"

**Síntoma:** Intento crear grid pero recibo error `STEP_TOO_SMALL`

```json
{
  "error": "Grid validation failed",
  "message": "Step size 0.1% is less than minimum 0.2%"
}
```

**Causa:** El espacio entre órdenes es muy pequeño (no rentable tras fees).

**Solución:**
- Aumenta `levels` (más órdenes en el mismo rango)
- O aumenta el rango (upper_price - lower_price)
- Ejemplo: En lugar de 10 niveles en rango 1000, usa 20 niveles

---

## Max Grids Exceeded

**Síntoma:** "Already have 2 active grids. Max is 2."

**Causa:** Sistema está limitado a 2 grids simultáneos (seguridad).

**Solución:**
```bash
# 1. Lista grids activas
curl http://localhost:8000/grids?status=ACTIVE

# 2. Cierra una (reemplaza GRID_ID)
curl -X POST http://localhost:8000/close-grid/GRID_ID

# 3. Ahora puedes crear una nueva
```

---

## Orders No Se Ejecutan en Binance

**Síntoma:** Grid created correctamente pero órdenes no aparecen en Binance

**Soluciones:**
1. **Verifica Testnet API Key:**
   - En `backend-python/.env`, confirma:
     ```env
     BINANCE_API_KEY=your_testnet_key
     BINANCE_API_SECRET=your_testnet_secret
     BINANCE_TESTNET_URL=https://demo-fapi.binance.com
     ```

2. **Verifica Balance en Testnet:**
   ```bash
   curl http://localhost:8000/account
   ```
   - balance_usdt debe ser > 0

3. **Verifica IP Whitelist en Binance:**
   - Si tienes IP whitelist, agrega tu IP a Binance account

4. **Logs del Backend:**
   ```bash
   docker-compose logs backend-python | tail -50
   ```
   - Busca "Binance API error"

---

## Workflow 2 No Replenish

**Síntoma:** Grid no se está "ciclando" (BUY → SELL → BUY...)

**Soluciones:**

1. **Verifica que Workflow 2 está ejecutándose:**
   - En n8n, ve a Workflow 2 → Executions
   - Debe tener ejecuciones recientes

2. **Verifica que hay fills:**
   ```bash
   # Ver órdenes ejecutadas
   curl http://localhost:8000/grids/{GRID_ID}/orders?status=FILLED
   ```

3. **Ejecuta replenish manualmente:**
   ```bash
   curl -X POST http://localhost:8000/replenish-grid/{GRID_ID}
   ```

4. **Si sigue sin funcionar:**
   - Mira logs de Workflow 2 en n8n
   - Mira logs del backend: `docker logs backend-python`

---

## n8n No Puede Conectar al Backend

**Síntoma:** En Workflow 1, HTTP node devuelve error de conexión

**Causa:** URL del backend incorrecta en n8n

**Soluciones:**

1. **Verifica BACKEND_URL en n8n:**
   - n8n Settings → Environment Variables
   - `BACKEND_URL` debe ser correcto:
     - Localhost: `http://localhost:8000`
     - Docker: `http://backend-python:8000`

2. **Reinicia n8n:**
   ```bash
   docker-compose restart n8n
   ```

3. **Test manual en n8n Code node:**
   ```javascript
   const url = process.env.BACKEND_URL;
   const health = await fetch(url + '/health');
   return await health.json();
   ```

---

## PnL Negativo (Pérdida)

**Síntoma:** Grid tiene PnL negativo

**Causas Posibles:**
1. Fees (comisiones) fueron altas
2. Stop Loss fue ejecutado
3. Grid se cerró antes de ciclar suficiente

**Verificar:**
```bash
curl http://localhost:8000/pnl/{GRID_ID}
```

**Soluciones:**
1. Aumenta rango (lower/upper) para más ciclos
2. Aumenta niveles para pasos pequeños (menos fees %)
3. Usa leverage? (No recomendado, riesgo alto)

---

## Database Error: "grid_trading.db is locked"

**Síntoma:** SQLite está locked por otro proceso

**Soluciones:**
1. **Reinicia backend:**
   ```bash
   docker-compose restart backend-python
   ```

2. **Si persiste, limpia DB (⚠ borra datos):**
   ```bash
   rm backend-python/grid_trading.db
   docker-compose restart backend-python
   ```

---

## Binance API: 418 Status (IP Ban)

**Síntoma:** 418 status from Binance (IP temporarily banned)

**Causa:** Demasiadas requests fallidas o desde IP sospechosa

**Soluciones:**
1. **Espera 15-30 minutos** (ban temporal)
2. **Verifica IP whitelist:**
   - Binance Account → API Management
   - Agrega tu IP actual
3. **Usa VPN/Proxy** si es necesario

---

## High Latency / Slow Responses

**Síntoma:** `/grids` toma 2+ segundos

**Causas:**
1. DB sin índices (optimización pendiente)
2. Muchas órdenes en una grid
3. Network lenta

**Soluciones:**
```bash
# Verifica estado general
curl http://localhost:8000/health

# Si BD es el problema:
docker-compose restart backend-python
```

---

## Workflow 1 Devuelve "IA decision: NOT BULLISH"

**Síntoma:** Workflow 1 no crea grids porque mercado no es bullish

**Esto es normal.** Grid trading solo funciona bien en mercados alcistas.

**Soluciones:**
1. Espera a que mercado sea bullish (ATR arriba de SMA)
2. Ajusta el prompt de IA si quieres ser más agresivo
3. O usa estrategia diferente (pairs trading, arbitrage)

---

## Checklist de Troubleshooting

- [ ] Backend responde: `curl http://localhost:8000/health`
- [ ] n8n es accesible: `http://localhost:5678`
- [ ] Binance API key es válida
- [ ] Testnet tiene balance (> 10 USDT)
- [ ] Workflows están habilitados en n8n
- [ ] BACKEND_URL es correcta en n8n
- [ ] Docker está corriendo: `docker-compose ps`
- [ ] Logs no muestran errores: `docker logs backend-python`

---

## Si Nada Funciona

**Nuclear Option (⚠ borra todo):**
```bash
docker-compose down
rm backend-python/grid_trading.db
docker-compose up -d
```

Luego sigue [Inicio Rápido](../00-START/01-inicio-rapido.md) de nuevo.

---

Ver también: [Error Handling](../30-API-REFERENCE/02-error-handling.md)
