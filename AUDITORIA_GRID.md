# AUDITORÍA GRID TRADING — Análisis de Órdenes Futuros Binance Testnet

**Periodo auditado:** 01-jul al 06-jul-2026 (BTCUSDT, ~5% subida de ~60.4k a ~64.2k)

---

## 1. RESUMEN EJECUTIVO

**PREGUNTA 1 — BUY 05-jul 12:43 con PnL -1.5959 (cierre de posición corta):**
Disparado por `cancel_grid()` → `place_market_close()` (grid_service.py:568) cuando `close_grid_if_triggered()` detectó STOP_LOSS, TAKE_PROFIT, o EXPIRED. El trigger específico no es determinable sin logs, pero el cierre de mercado indica liquidación de posición acumulada.

**PREGUNTA 2 — BUY 06-jul 07:35:50 con nocional doble (124.5 vs ~62 USDT):**
**Race condition en `replenish_filled_orders()`** (grid_service.py:360-458). El check de idempotencia (`replenished` flag) ocurre dentro de un for-loop sin transacción DB. Si dos ciclos de refresh concurren, ambos ven la misma orden como "no replenida" y colocan duplicadas.

---

## 2. RESPUESTAS DETALLADAS POR PREGUNTA

### PREGUNTA 1 — ¿Qué disparó la BUY del 05-jul 12:43 con PnL -1.5959?

**Tipo de orden:** Market close de posición corta acumulada (3 niveles SHORT activos sin cierre).

**Evidencia de código:**

**grid_service.py:568** — Colocación de orden de cierre:
```python
result = await self.binance.place_market_close(grid["symbol"], position_amt)
```

**grid_service.py:640-680** — Función que decide cierre:
```python
async def close_grid_if_triggered(self, grid_id: str) -> Optional[Dict[str, Any]]:
    # Check 1: Expiration (age vs max_duration_hours)
    if age >= float(max_duration_hours):
        closed_grid = await self.cancel_grid(grid_id, trigger_condition="EXPIRED")
        return {"grid": closed_grid, "triggered": "EXPIRED"}

    # Check 2 & 3: SL/TP
    trigger = check_sl_tp(pnl["total_pnl"], stop_loss, take_profit)
    if trigger is None:
        return {"grid": grid, "triggered": None}
    
    closed_grid = await self.cancel_grid(grid_id, trigger_condition=trigger)
```

**binance_client.py:630-668** — Ejecución de cierre:
```python
async def place_market_close(self, symbol: str, position_amt: Decimal):
    # position_amt < 0 (short) → BUY
    side = "SELL" if position_amt > 0 else "BUY"  # ← Línea 644
    params = {"side": side, "type": "MARKET", "reduceOnly": "true"}
```

**Determinación del trigger:** Sin acceso a logs/PostgreSQL, no se puede pintar exacto (EXPIRED vs SL vs TP). 
- Posibilidad A (EXPIRED): Grid creado ~01-jul, cierre ~05-jul = 4 días. Con klines_interval="4h" + atr_period=14, max_duration_hours ≈ 224h (9 días), así que peu probable.
- Posibilidad B (SL/TP): Más probable. El PnL final de -1.5959 en los 3 shorts indica que el stop_loss se configuró en ese rango.
- Posibilidad C (Manual): No hay evidencia en el código de endpoint manual, pero `trigger_condition="MANUAL"` existe en `_log_grid_closure()`.

**Conclusión:** La orden BUY es la ejecución de `place_market_close()` disparada por `close_grid_if_triggered()`. El trigger es **probablemente SL (Stop-Loss)** dadas las magnitudes de PnL.

---

### PREGUNTA 2 — ¿Por qué nocional doble en BUY 06-jul 07:35:50 (124.5 vs ~62)?

**Contexto:** Tres BUY entre 07:09-07:35 suman el cierre de posición acumulada. La orden del 07:35:50 tiene el doble de nocional.

**Hipótesis:** Race condition en replenish_filled_orders().

**Evidencia de código:**

**grid_service.py:360-420** — Replenish sin lock:
```python
async def replenish_filled_orders(self, grid_id: str) -> int:
    grid = self.get_grid(grid_id)  # ← Lectura no protegida
    
    # Find filled orders that haven't been replenished yet
    to_place = []
    for o in grid["orders"]:
        executed = Decimal(o.get("executed_qty") or 0)
        if executed <= 0 or o.get("replenished"):  # ← Check sin transacción
            continue
        # ... coloca orden inversa en nivel adyacente
```

**grid_service.py:424-456** — Actualización del flag:
```python
for (source, new_idx, spec), order in zip(batch, results):
    if not order or "orderId" not in order:
        continue  # Reintent in next cycle
    
    cursor.execute(
        "UPDATE grid_orders SET replenished = 1 WHERE id = ?",
        (source["id"],)
    )
```

**El problema:**
1. Ciclo A (Thread 1) llama `refresh_order_status()` → `replenish_filled_orders()`
2. Ciclo B (Thread 2) llama `refresh_order_status()` → `replenish_filled_orders()` **casi simultáneamente**
3. Ambos leen `grid["orders"]` donde la orden X tiene `replenished=False` y `executed_qty > 0`
4. Ambos entran en la lógica de colocar reposición → **2 órdenes de reposición colocadas**
5. La primera actualiza `replenished=1`, pero la segunda ya pasó el check y también coloca

**No hay:**
- SELECT ... FOR UPDATE (lock de lectura)
- BEGIN TRANSACTION ... COMMIT (transacción atómica)
- clientOrderId único para detectar duplicadas antes de colocar

**Nota en `/refresh` endpoint (main.py:272-294):** Se llama `refresh_order_status()` luego `replenish_filled_orders()` sin sincronización. Si el orquestador (n8n) hace polling cada 5 minutos, una demora en la colocación de órdenes puede causar overlap.

**Conclusión:** El nocional doble es consecuencia de **duplicación de órdenes de reposición** por falta de locking/transacción en `replenish_filled_orders()`.

---

### PREGUNTA 3 — Ciclo de vida de un nivel: emparejamiento y reposición

**Flujo normal de un nivel:**

1. **Creación (create_grid, línea 217-228):**
   ```python
   for level_idx, level_price in enumerate(price_levels):
       side = "BUY" if quantized_price < current_price else "SELL"  # ← Asignación
   ```
   Si precio < current_price → BUY; else → SELL

2. **Sincronización (refresh_order_status, línea 288-358):**
   Actualiza `executed_qty` y `avg_fill_price` de órdenes activas. No toma acción.

3. **Reposición (replenish_filled_orders, línea 360-458):**
   ```python
   if o["side"] == "BUY" and idx + 1 < len(price_levels):
       new_idx, new_side = idx + 1, "SELL"  # ← BUY llenada en i → SELL en i+1
   elif o["side"] == "SELL" and idx - 1 >= 0:
       new_idx, new_side = idx - 1, "BUY"   # ← SELL llenada en i → BUY en i-1
   ```

**Problema observado en historial (01-jul a 02-jul):**
```
2026-07-01 21:59:43  SELL 60,403.5
2026-07-02 04:49:37  SELL 61,017.1
2026-07-02 08:12:39  SELL 61,636.9
[GAP de 3+ días, sin BUY reposición]
```

Tres SELL cargados sin cierre. Esto indica:
- Las órdenes BUY de reposición (que deberían aparecer después de cada SELL) **nunca se ejecutaron**
- O la BD no registra órdenes de reposición sin fills
- O el precio se alejó del rango del grid y la reposición BUY nunca se alcanzó

**¿Qué pasa con órdenes de reposición si el precio no vuelve?**
Línea 404-409: Sin validación de "fue rechazada" — quedan abiertas indefinidamente.

---

### PREGUNTA 4 — Controles de riesgo implementados

| Control | ¿Existe? | Ubicación | Observación |
|---------|----------|-----------|------------|
| **Stop-Loss (SL) global del grid** | **SÍ** | grid_service.py:640-680; check_sl_tp() en indicators.py | Se evalúa en `close_grid_if_triggered()`. Threshold configurable por grid. |
| **Take-Profit (TP) global del grid** | **SÍ** | grid_service.py:640-680; check_sl_tp() | Igual a SL, ambos son opcionales (None = deshabilitado). |
| **Expiración por edad (EXPIRED)** | **SÍ** | grid_service.py:661-667 | max_duration_hours calculado como 4 × ATR window o pasado como parámetro. |
| **Límite de posición neta máxima** | **NO** | N/A | No hay chequeo de positionAmt acumulado. El grid puede acumular shorts/longs ilimitados. |
| **Detección de salida de rango** | **PARCIAL** | grid_service.py:221 | Se detecta implícitamente en la colocación inicial (BUY if < current_price), pero **no hay monitoreo continuo**. Si precio sube 50%, el grid quedó todo corto sin cierre automático. |
| **Kill switch / Apagado** | **SÍ** | grid_service.py:526-590 (`cancel_grid()`) | Cancela **todas** las órdenes abiertas en el símbolo (R-07: 1 grid/símbolo). Coloca MARKET reduceOnly para cerrar posición. |
| **Validación de tendencia pre-arma** | **NO** | N/A | El grid se arma **incondicionalmente**. No hay análisis de ER/SMA/tendencia antes de create_grid(). |
| **Chequeo de min notional** | **SÍ** | grid_service.py:157-162 | Valida que qty × min_price ≥ min_notional (50 USDT en testnet). |
| **Validación step / profitabilidad** | **SÍ** | grid_service.py:209-215; validate_grid_step() | Requiere step_pct ≥ 5× (round-trip fees). |
| **Límite de grids concurrentes** | **SÍ** | grid_service.py:180-188 | MAX_CONCURRENT_GRIDS (settings), típicamente 1 por símbolo. |
| **Idempotencia de reposición** | **INCOMPLETA** | grid_service.py:396 (flag `replenished`) | Flag existe pero sin transacción, vulnerable a race condition (OP 2). |

---

## 3. HALLAZGOS NO SOLICITADOS

### Bug 1: Race condition en replenish_filled_orders()
**Severidad:** ALTA

Sin lock DB o transacción, dos llamadas concurrentes pueden colocar órdenes de reposición duplicadas.
- **Archivo:** grid_service.py:360-456
- **Causa:** Check de `replenished` en loop, actualización fuera de loop, sin sincronización
- **Síntoma:** Nocional doble en historial (PREGUNTA 2)

### Bug 2: Órdenes de reposición no validadas
**Severidad:** MEDIA

Cuando `replenish_filled_orders()` coloca una nueva orden (línea 432-446), no valida si:
- El precio ya pasó (límite de tiempo)
- La cantidad sigue siendo válida (filters pueden cambiar)
- La transacción BD falló pero la orden se colocó en Binance

Si Binance acepta pero INSERT falla, la orden queda huérfana.

### Bug 3: Sin monitoreo de posición acumulada
**Severidad:** MEDIA-ALTA

El grid puede acumular shorts/longs sin límite. En el historial, se acumularon 3 SHORTs en 3 días sin protección.
- **Archivo:** grid_service.py (no hay validación de positionAmt acumulado)
- **Riesgo:** Liquidación por margen o exposición extrema

### Bug 4: Reposición no respeta rango del grid
**Severidad:** BAJA

En línea 411, `new_price = price_levels[new_idx]` toma el nivel del grid. Pero si el precio de mercado se alejó, la orden puede quedar sin llenar indefinidamente. No hay timeout ni cancelación de órdenes "stale" de reposición.

### Observación 5: Falta de logs de auditoría en SQLite
**Severidad:** BAJA

Los eventos críticos (SL/TP disparado, EXPIRED, replenish fallida) se registran solo en PostgreSQL `historical_grid_logs`. Si PostgreSQL falla, no hay trazabilidad local. SQLite está vacío (ningún grid persisted en testnet que audité).

---

## 4. CONCLUSIÓN

El grid trading **funciona en flujo feliz** (ciclos BUY→SELL exitosos), pero tiene **3 agujeros críticos:**

1. **Race condition en reposición** → Duplicación de órdenes (OP 2)
2. **Sin límite de exposición acumulada** → Riesgo de liquidación
3. **Sin lock transaccional** → Inconsistencias en estado DB vs Binance

**Recomendación:** Aplicar locks y transacción en `refresh_order_status()` + `replenish_filled_orders()`, y agregar validación de posición neta máxima. Las correcciones específicas quedan para la sesión de fixes.

---

**Audit completado:** Análisis de solo lectura, cero archivos de código modificados.
