# QA Manual Runbook — Grid Trading System (Testnet)

**Objetivo:** Validar el ciclo completo de grid trading de forma manual desde n8n, sin pruebas automatizadas.

**Duración estimada:** 2-4 semanas de ejecución continua (no dedicación full-time)

**Ambiente:** Binance Futures **TESTNET** únicamente

---

## PRE-REQUISITOS

### 1. Setup de Cuentas

- ✅ Binance Futures Testnet account con saldo (https://testnet.binancefuture.com)
- ✅ Cuenta con ~1000 USDT de testnet (suficiente para grids pequeños)
- ✅ Backend FastAPI corriendo en Docker (puerto 8000 o configurado)
- ✅ n8n corriendo (puerto 5678 o configurado)
- ✅ Workflows 1 y 2 importados en n8n y **ACTIVOS**

### 2. Validar Conexión Backend

**Paso 1:** En terminal, verifica que el backend responde

```bash
curl http://localhost:8000/health
```

**Resultado esperado:**
```json
{
  "status": "healthy",
  "service": "grid-trading-backend",
  "version": "0.1.0",
  "binance_synced": true,
  "time_offset_ms": <número en rango -1000 a 1000>
}
```

**Si falla:**
- Verifica Docker: `docker ps | grep backend`
- Lee logs: `docker logs <container-id>`
- Reinicia: `docker restart <container-id>`

---

## SUITE DE PRUEBAS

### TEST 1: Endpoint de Market Analysis Funciona

**Objetivo:** Validar que el backend puede analizar mercado sin crear órdenes.

**Pasos:**

1. Abre Postman o curl
2. Haz GET a:
   ```
   http://localhost:8000/api/v1/market-analysis/BTCUSDT?atr_period=14&atr_multiplier=2.0&klines_interval=4h&risk_pct=0.02&levels=10
   ```

**Resultado esperado:**
```json
{
  "symbol": "BTCUSDT",
  "current_price": 42500.0,
  "atr": 200.0,
  "atr_period": 14,
  "atr_multiplier": 2.0,
  "klines_interval": "4h",
  "suggested_lower_price": 42100.0,
  "suggested_upper_price": 42900.0,
  "suggested_range": 800.0,
  "suggested_quantity_per_order": 0.00047,
  "allocated_capital": 200.0,
  "suggested_stop_loss": 100.0
}
```

**Validación:**
- ✓ `suggested_quantity_per_order` > 0
- ✓ `allocated_capital` = account_balance × risk_pct (2%)
- ✓ `suggested_stop_loss` = allocated_capital × 0.5
- ✓ `suggested_lower_price` < current_price < `suggested_upper_price`

**Si falla:**
- Verifica que `BINANCE_API_KEY` y `BINANCE_API_SECRET` están en `.env`
- Verifica saldo: `GET /fapi/v2/balance` en Postman con auth
- Si "Could not fetch klines": revisa que BTCUSDT existe en testnet

---

### TEST 2: Workflow 1 Crea Grid Correctamente

**Objetivo:** Validar que Workflow 1 (Market Decision) lanza un grid con los parámetros correctos.

**Pasos:**

1. En n8n, abre Workflow 1 (Market Decision)
2. Haz clic en "Manual Trigger" o ejecuta el workflow manualmente
3. Observa la ejecución en tiempo real

**Resultado esperado en cada nodo:**

**Nodo 1 (Trigger):** Activa
- Status: ✅ Ejecutado

**Nodo 2 (Market Analysis):**
- Response: Market analysis JSON (como en TEST 1)
- Status: ✅ Ejecutado

**Nodo 3 (AI Decision - Claude):**
- Input: Market data
- Output: JSON con `launch: true` o `false`, `gridCount`: 8-15, `reasoning`: texto
- Status: ✅ Ejecutado
- Ejemplo:
  ```json
  {
    "launch": true,
    "gridCount": 10,
    "lowerLimit": 42100,
    "upperLimit": 42900,
    "reasoning": "ATR 0.5% es óptimo para 10 niveles, mercado lateral es ideal para grids"
  }
  ```

**Nodo 4 (IF: Launch = true?):**
- Evalúa si `launch === true`
- Status: ✅ True o False (depende de AI)

**Nodo 5 (Create Grid - POST):**
- Si Nodo 4 fue True:
  - Status: ✅ Ejecutado
  - Response: GridDetailResponse con:
    - `id`: UUID del grid
    - `symbol`: "BTCUSDT"
    - `status`: "RUNNING"
    - `levels`: 10 (u otro número que AI eligió)
    - `orders[]`: array con 10 órdenes, cada una con `status: "NEW"`
    - `stop_loss`: 100.0 (50% del capital asignado)
  - En Binance testnet UI: verifica que aparecen 10 órdenes LIMIT en Order Book

- Si Nodo 4 fue False:
  - Nodo 5 se salta (no ejecuta)
  - Nodo 6b (Notify: Skipped) ejecuta

**Nodo 6a o 6b (Notificación):**
- Telegram mensaje recibido (si configurado)
- Status: ✅ Ejecutado

**Validación:**
- ✓ Grid fue creado en backend: `GET /api/v1/grids` devuelve el grid con `status: RUNNING`
- ✓ Todas las órdenes tienen estado `NEW`
- ✓ Binance testnet UI muestra 10 órdenes LIMIT abiertas para BTCUSDT
- ✓ Leverage es 1× (verificar en Binance testnet UI: Position → Symbol Settings)
- ✓ Margin Type es ISOLATED (verificar en Binance testnet UI)

**Si falla:**

| Síntoma | Posible Causa | Solución |
|---------|---------------|----------|
| Nodo 2 error "Could not fetch balance" | API key sin permisos | Verifica que la key tiene permisos de lectura en testnet |
| Nodo 3 error "Invalid API key for Claude" | OpenAI API key inválida | Regenera y guarda la key en n8n credentials |
| Nodo 5 error "No orders placed" | Margin insuficiente | Aumenta balance en testnet faucet o reduce `risk_pct` |
| Nodo 5 error "Grid step below minimum" | Paso muy pequeño (paso < 0.2%) | Grid muy angosto, AI debe elegir rango más ancho |
| Binance testnet UI no muestra órdenes | Órdenes fueron rechazadas silenciosamente | Lee logs del backend: `docker logs backend-python` |

---

### TEST 3: Workflow 2 Refresh Sincroniza Órdenes

**Objetivo:** Validar que Workflow 2 (Monitor) actualiza el estado de órdenes desde Binance.

**Pasos:**

1. Asegúrate de que existe un grid RUNNING (si no, corre TEST 2 primero)
2. En Binance testnet UI, busca órdenes LIMIT del grid y verifica que están `NEW`
3. En n8n, abre Workflow 2 (Grid Monitor)
4. Ejecuta manualmente (sin esperar 15 minutos)
5. Observa la ejecución

**Resultado esperado en cada nodo:**

**Nodo 1 (Cron):**
- Status: ✅ Ejecutado

**Nodo 2 (GET /grids?status=RUNNING):**
- Response: Array con 1+ grids RUNNING
- Ejemplo:
  ```json
  [
    {
      "id": "uuid-123",
      "symbol": "BTCUSDT",
      "status": "RUNNING",
      "lower_price": 42100,
      "upper_price": 42900,
      "levels": 10
    }
  ]
  ```
- Status: ✅ Ejecutado

**Nodo 3 (IF: Any grids running?):**
- Condition: Array length > 0
- Status: ✅ True (continúa)

**Nodo 4 (Split in Batches):**
- Itera sobre cada grid (1 a la vez)
- Status: ✅ Ejecutado

**Nodo 5 (POST /refresh):**
- Input: Grid ID
- Response: GridDetailResponse actualizado con órdenes y `executed_qty`
- Status: ✅ Ejecutado
- Validación: órdenes tienen `executed_qty: "0"` (sin fills aún)

**Nodo 6 (IF: Refresh failed?):**
- Condition: no hay error
- Status: ✅ False (continúa a Nodo 7)

**Nodo 7 (POST /check-close):**
- Input: Grid ID
- Response:
  ```json
  {
    "triggered": null,
    "grid": { ... }
  }
  ```
- Status: ✅ Ejecutado
- Validación: `triggered` es `null` (sin SL/TP aún)

**Nodo 8 (IF: Check-close failed?):**
- Status: ✅ False (continúa a Nodo 9)

**Nodo 9 (IF: Grid closed?):**
- Condition: `triggered !== null`
- Status: ✅ False (grid sigue RUNNING)
- Nodo 9a NO ejecuta

**Nodo 10 (Wait 1.5s):**
- Status: ✅ Ejecutado

**Nodo 11 (Loop back):**
- Status: ✅ Fin del loop

**Validación:**
- ✓ Workflow 2 completó sin errores
- ✓ Backend devolvió status actualizado
- ✓ Grid sigue RUNNING
- ✓ Tiempo total: < 5 segundos

**Si falla:**

| Síntoma | Posible Causa | Solución |
|---------|---------------|----------|
| Nodo 2 devuelve array vacío | No hay grids RUNNING | Corre TEST 2 primero para crear un grid |
| Nodo 5 error 404 | Grid ID no existe | Verifica que el grid_id es correcto |
| Nodo 5 error "Could not fetch mark price" | Binance API down | Espera 1 min y reintenta |

---

### TEST 4: Fills Generan Reposición (Ciclos)

**Objetivo:** Validar que cuando una orden se llena, Workflow 2 automáticamente crea la orden opuesta en el nivel adyacente.

**Pasos (esto toma tiempo, simulamos un fill manualmente):**

1. Tienes un grid RUNNING desde TEST 2
2. En Binance testnet UI:
   - Ve a tu símbolo (BTCUSDT)
   - Busca una orden BUY en el nivel más bajo del grid
   - Haz clic en "Edit" → sube el precio para que se cruce con el market price
   - Guarda el cambio (o cancela y coloca una orden BUY market a ese precio para forzar el fill)
   - La orden debe llenar parcial o completamente

   **Alternativa si no funciona:**
   - Crea una orden MARKET manual BUY pequeña para cruzar con una orden LIMIT del grid
   - Verifica que alguna orden del grid se llena

3. En n8n, ejecuta Workflow 2 manualmente
4. Observa la ejecución completa

**Resultado esperado:**

**Nodo 5 (POST /refresh):**
- Response muestra la orden que se llenó con `status: "FILLED"` o `status: "PARTIALLY_FILLED"`
- Campo `executed_qty` > 0
- Status: ✅ Ejecutado

**Nodo 7 (POST /check-close):**
- Grid sigue RUNNING (SL/TP aún no triggered)
- Status: ✅ Ejecutado

**Después del refresh:**
- Backend automáticamente repuso la orden opuesta
- Si fue BUY llena en nivel i → aparece SELL nuevo en nivel i+1
- Si fue SELL llena en nivel i → aparece BUY nuevo en nivel i-1

**Validación:**
- ✓ `GET /api/v1/grids/{grid_id}` devuelve órdenes con:
  - La original: `status: "FILLED"`, `executed_qty > 0`, `replenished: 1`
  - La nueva: `status: "NEW"`, lado opuesto, nivel adyacente
- ✓ Binance testnet UI muestra una nueva orden LIMIT en el nivel adyacente
- ✓ Contador de órdenes en el grid pasó de 10 a 11 (o más)

**Si no hay reposición:**

| Síntoma | Posible Causa | Solución |
|---------|---------------|----------|
| Nueva orden NO aparece | Fill ocurrió pero replenish falló | Lee logs: `docker logs backend-python` |
| "Grid was already replenished" error | Mismo fill procesado dos veces | Esperado si ejecutas WF2 dos veces; next ciclo será limpio |
| Nueva orden aparece pero en nivel incorrecto | level_index no grabado | Verifica que grids tienen grid_type y orders tienen level_index |

---

### TEST 5: SL Cierra Grid Completamente

**Objetivo:** Validar que Stop Loss cierra el grid CON 0 ÓRDENES Y 0 POSICIÓN.

**Pasos:**

1. Tienes un grid RUNNING con fills (del TEST 4, o crea uno nuevo)
2. En backend, obtén el SL value:
   ```bash
   curl http://localhost:8000/api/v1/grids/{grid_id}
   ```
   Busca `stop_loss` field (debe ser ~50% del capital asignado)

3. En Binance testnet:
   - Mueve el precio para que el PnL del grid sea NEGATIVO y alcance/supere el SL
   - O usa el bot para llenar órdenes compradas a precios altos y venidas bajas para generar pérdida

4. En n8n, ejecuta Workflow 2

**Resultado esperado:**

**Nodo 7 (POST /check-close):**
- Response: 
  ```json
  {
    "triggered": "STOP_LOSS",
    "grid": { "status": "CANCELED", "id": "...", ... }
  }
  ```
- Status: ✅ Ejecutado

**Nodo 9 (IF: Grid closed?):**
- Condition: `triggered !== null` → ✅ TRUE
- Nodo 9a (Notify) ejecuta

**Telegram/Notificación:**
- Recibe mensaje: "🔒 GRID CLOSED — BTCUSDT | Trigger: STOP_LOSS | Total PnL: <número negativo>"

**En Binance testnet UI:**
- ✅ **0 órdenes abiertas** para BTCUSDT (todas canceladas)
- ✅ **0 posición** (net amount = 0)
- Verificar: Position Tab → BTCUSDT → Position Amt = 0

**En backend:**
- `GET /api/v1/grids/{grid_id}` devuelve `status: "CANCELED"`
- `GET /api/v1/grids` con `status=RUNNING` NO incluye este grid

**Validación:**
- ✓ Grid fue cerrado por SL (no manual)
- ✓ Todas las órdenes abiertas canceladas
- ✓ Posición neta es 0
- ✓ Log en historical_grid_logs con `trigger_condition: "STOP_LOSS"`

**Si falla:**

| Síntoma | Posible Causa | Solución |
|---------|---------------|----------|
| SL no se dispara aunque PnL < -SL | PnL no actualizado | Ejecuta WF2 refresh primero para sincronizar fills |
| Grid cancelado pero posición ≠ 0 | close_position falló | Cierra manualmente en Binance testnet UI |
| Órdenes aún abiertas | cancel_all_open_orders falló | Cancela manualmente y verifica logs |

---

### TEST 6: EXPIRED Cierra Grid por Edad

**Objetivo:** Validar que grids expiran automáticamente después de `max_duration_hours`.

**Pasos:**

1. Crea un grid NUEVO con `max_duration_hours: 0.05` (3 minutos) via Postman:
   ```bash
   POST http://localhost:8000/api/v1/grids
   ```
   Body:
   ```json
   {
     "symbol": "ETHUSDT",
     "levels": 5,
     "grid_type": "GEOMETRIC",
     "quantity_per_order": 0.01,
     "stop_loss": null,
     "take_profit": null,
     "max_duration_hours": 0.05
   }
   ```

   **Validación inmediata:**
   - ✓ Grid creado con `id: "..."`
   - ✓ `status: "RUNNING"`
   - ✓ `max_duration_hours: 0.05`

2. Espera 3 minutos (ó simula en backend editando `created_at` del grid)

3. En n8n, ejecuta Workflow 2

**Resultado esperado:**

**Nodo 7 (POST /check-close):**
- Response:
  ```json
  {
    "triggered": "EXPIRED",
    "grid": { "status": "CANCELED", ... }
  }
  ```
- Status: ✅ Ejecutado

**Nodo 9 (IF: Grid closed?):**
- ✅ TRUE

**Telegram/Notificación:**
- "🔒 GRID CLOSED — ETHUSDT | Trigger: EXPIRED"

**Validación:**
- ✓ Grid fue cerrado por EXPIRED (no SL/TP)
- ✓ Posición = 0, órdenes = 0
- ✓ Edad del grid >= max_duration_hours

**Si falla:**

| Síntoma | Posible Causa | Solución |
|---------|---------------|----------|
| EXPIRED no se dispara después de max_duration_hours | Cálculo de edad incorrecto | Verifica `created_at` en BD (debe ser UTC) |
| Grid cerrado pero no por EXPIRED | Otro trigger (SL/TP) se disparó primero | Normal si hay fills |

---

### TEST 7: Grid con Bajo Balance Rechaza (Min-Notional)

**Objetivo:** Validar que grids con quantity muy pequeña se rechazan.

**Pasos:**

1. En Postman, intenta crear grid con quantity muy pequeña:
   ```bash
   POST http://localhost:8000/api/v1/grids
   Body: {
     "symbol": "BTCUSDT",
     "levels": 50,
     "quantity_per_order": 0.00001,
     "lower_price": 42000,
     "upper_price": 43000,
     "grid_type": "GEOMETRIC"
   }
   ```

**Resultado esperado:**

- Status: ❌ 400 Bad Request
- Response:
  ```json
  {
    "detail": "quantity_per_order too small: order notional must be at least 100 USDT (got 0.42)"
  }
  ```

**Validación:**
- ✓ Backend rechazó por min-notional
- ✓ No se crearon órdenes en Binance

---

### TEST 8: Grid con Paso Pequeño Rechaza (Min Step)

**Objetivo:** Validar que grids con paso < 0.2% se rechazan (muy pequeños para ser rentables).

**Pasos:**

1. En Postman:
   ```bash
   POST http://localhost:8000/api/v1/grids
   Body: {
     "symbol": "BTCUSDT",
     "levels": 500,
     "quantity_per_order": 0.001,
     "lower_price": 42490,
     "upper_price": 42510,
     "grid_type": "GEOMETRIC"
   }
   ```
   (Rango muy estrecho: 20 USDT en 500 niveles = paso 0.00004%)

**Resultado esperado:**

- Status: ❌ 400 Bad Request
- Response:
  ```json
  {
    "detail": "Grid step 0.0001% is below minimum 0.2000% (= 5x round-trip fees of 2 × 0.0200%). Reduce levels or widen the range to make cycles profitable."
  }
  ```

**Validación:**
- ✓ Backend rechazó por paso mínimo
- ✓ No se crearon órdenes

---

### TEST 9: Máximo 2 Grids Simultáneos

**Objetivo:** Validar que no se pueden crear > MAX_CONCURRENT_GRIDS (default 2).

**Pasos:**

1. Asegúrate de tener 2 grids RUNNING (crea manualmente si falta)
2. Intenta crear un 3er grid via Postman:
   ```bash
   POST http://localhost:8000/api/v1/grids
   Body: { ... grid params ... }
   ```

**Resultado esperado:**

- Status: ❌ 400 Bad Request
- Response:
  ```json
  {
    "detail": "Max concurrent grids (2) reached. Cancel an existing grid before creating a new one."
  }
  ```

**Validación:**
- ✓ Backend rechazó por límite de exposición global

---

### TEST 10: Health Check Devuelve Estado Correcto

**Objetivo:** Validar que health check refleja estado del sistema.

**Pasos:**

1. Ejecuta:
   ```bash
   curl http://localhost:8000/health
   curl http://localhost:8000/
   ```

**Resultado esperado:**

`/health`:
```json
{
  "status": "healthy",
  "service": "grid-trading-backend",
  "version": "0.1.0",
  "binance_synced": true,
  "time_offset_ms": 123
}
```

`/`:
```json
{
  "service": "Grid Trading Hybrid - Backend",
  "status": "ready",
  "api_version": "v1",
  "docs": "/api/docs",
  "running_grids": 1,
  "max_concurrent_grids": 2,
  "default_risk_pct": 0.02,
  "default_leverage": 1
}
```

**Validación:**
- ✓ `binance_synced: true`
- ✓ `time_offset_ms` en rango [-1000, 1000]
- ✓ `running_grids` coincide con grids RUNNING en BD

---

## ESCENARIO DE ESTRÉS: 48 HORAS CONTINUAS

**Objetivo:** Validar que el sistema es estable en ejecución prolongada.

**Duración:** 48 horas

**Configuración:**
- Workflow 2 ejecutándose cada 15 minutos
- Workflow 1 ejecutándose cada 4 horas (ó manualmente cuando se cierren grids)
- 1-2 grids activos simultáneamente

**Checklist cada 6 horas:**

- [ ] Workflow 2 ejecuta sin errores
- [ ] No hay órdenes huérfanas en Binance testnet
- [ ] PnL en endpoint coincide con Binance testnet UI (±0.5%)
- [ ] Logs no tienen exceptions
- [ ] Backend sigue respondiendo en < 2s

**Validación final:**

```bash
GET http://localhost:8000/api/v1/grids
```

- ✓ Todos los grids RUNNING tienen orders con `executed_qty` > 0 (ciclos ocurrieron)
- ✓ Total PnL realizado en grids cerrados > 0 (grids fueron rentables)

---

## CHECKLIST FINAL DE QA (Antes de Capital Real)

Después de completar todos los tests anteriores, verifica:

- [ ] **Corrección:**
  - [ ] TEST 1: Market analysis devuelve datos correctos
  - [ ] TEST 2: Workflow 1 crea grids con parámetros correctos
  - [ ] TEST 3: Workflow 2 sincroniza órdenes
  - [ ] TEST 5: SL cierra con posición = 0

- [ ] **Rentabilidad:**
  - [ ] TEST 4: Ciclos ocurren (fill → reposición)
  - [ ] Escenario 48h: PnL total acumulado > 0

- [ ] **Robustez:**
  - [ ] TEST 6: EXPIRED funciona
  - [ ] TEST 7: Min-notional rechaza órdenes pequeñas
  - [ ] TEST 8: Min-step rechaza grids no rentables
  - [ ] TEST 9: Max concurrent grids se respeta
  - [ ] TEST 10: Health check refleja estado

- [ ] **Operativa:**
  - [ ] Workflow 2 se ejecuta reliablemente cada 15 min
  - [ ] No hay API key leaks en logs
  - [ ] Telegram notifications son consistentes

---

## RESULTADOS: Documento Final

Después de completar QA, genera un documento `qa-results-{DATE}.md` con:

```markdown
# QA Results — {DATE}

## Summary
- Duration: X days
- Total grids tested: N
- Total cycles completed: M
- Final PnL: ±X%

## Test Results
- [ ] TEST 1: ✅ PASS / ❌ FAIL
- [ ] TEST 2: ✅ PASS / ❌ FAIL
- ...

## Issues Found
1. [Issue description] — Status: FIXED / OPEN / N/A

## Conclusion
Ready for production: YES / NO
```

---

## Soporte & Debugging

### Logs del Backend

```bash
docker logs backend-python --tail 100 -f
```

Busca:
- `ERROR` → fallos críticos
- `ValueError` → validación fallida
- `Traceback` → exception detallado

### Logs de n8n

En UI de n8n, haz clic en cada nodo ejecutado y ve "Execution Result" para ver exactamente qué devolvió.

### Reset Completo (si todo se rompe)

```bash
# Limpia BD local
rm grid_trading.db

# Reinicia backend
docker restart backend-python

# Re-importa workflows en n8n
# Re-crea un grid de TEST 2 para empezar desde cero
```

---

**¡Buena suerte con el QA! 🚀**
