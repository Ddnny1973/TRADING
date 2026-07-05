# Guía de implementación paso a paso — Mejoras del Grid Bot

Basada en `revision-trading-bot.md` (commit `2aa7240`). Cada paso indica: archivos a tocar, código, y cómo verificar en testnet antes de pasar al siguiente. El orden importa: no avances de fase sin cerrar la anterior.

Convención: los números entre paréntesis (#N) referencian los hallazgos del informe de revisión.

---

# FASE 1 — Correctitud (el bot no debe poder perder dinero por bugs)

## Paso 1. Cierre real de grids (#2, #3)

**Objetivo:** que cancelar un grid deje CERO órdenes vivas y CERO posición abierta en Binance.

### 1.1 Añadir métodos al cliente — `app/services/binance_client.py`

```python
async def cancel_all_open_orders(self, symbol: str) -> bool:
    """DELETE /fapi/v1/allOpenOrders — cancela todas las órdenes del símbolo en 1 llamada atómica."""
    try:
        await self.time_sync.sync_if_stale()
        params = {
            "symbol": symbol,
            "timestamp": self.time_sync.get_adjusted_time(),
            "recvWindow": settings.BINANCE_RECV_WINDOW,
        }
        params["signature"] = self.security.generate_signature(params)
        url = f"{self.base_url}/fapi/v1/allOpenOrders"
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.delete(url, params=params, headers=self.security.get_headers()) as r:
                return r.status == 200
    except Exception as e:
        print(f"Error canceling all open orders: {e}")
    return False

async def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
    """GET /fapi/v2/positionRisk — posición neta actual del símbolo."""
    try:
        await self.time_sync.sync_if_stale()
        params = {
            "symbol": symbol,
            "timestamp": self.time_sync.get_adjusted_time(),
            "recvWindow": settings.BINANCE_RECV_WINDOW,
        }
        params["signature"] = self.security.generate_signature(params)
        url = f"{self.base_url}/fapi/v2/positionRisk"
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, params=params, headers=self.security.get_headers()) as r:
                if r.status == 200:
                    data = await r.json()
                    return data[0] if data else None
    except Exception as e:
        print(f"Error fetching position: {e}")
    return None

async def place_market_close(self, symbol: str, position_amt: Decimal) -> Optional[Dict[str, Any]]:
    """Cierra la posición neta con MARKET reduceOnly (no puede abrir posición nueva)."""
    side = "SELL" if position_amt > 0 else "BUY"
    try:
        await self.time_sync.sync_if_stale()
        params = {
            "symbol": symbol,
            "side": side,
            "type": "MARKET",
            "quantity": str(abs(position_amt)),
            "reduceOnly": "true",
            "timestamp": self.time_sync.get_adjusted_time(),
            "recvWindow": settings.BINANCE_RECV_WINDOW,
        }
        params["signature"] = self.security.generate_signature(params)
        url = f"{self.base_url}/fapi/v1/order"
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, params=params, headers=self.security.get_headers()) as r:
                if r.status in (200, 201):
                    return await r.json()
                print(f"Error closing position: {r.status} - {await r.text()}")
    except Exception as e:
        print(f"Exception closing position: {e}")
    return None
```

### 1.2 Reescribir `cancel_grid()` — `app/services/grid_service.py`

Reemplaza el bucle que cancela solo órdenes `NEW`:

```python
async def cancel_grid(self, grid_id: str, trigger_condition: str = "MANUAL",
                       close_position: bool = True) -> Optional[Dict[str, Any]]:
    grid = self.get_grid(grid_id)
    if not grid:
        return None

    final_pnl = None
    try:
        final_pnl = await self.get_grid_pnl(grid_id)
    except ValueError:
        pass

    # 1) Cancelar TODAS las órdenes abiertas del símbolo (incluye PARTIALLY_FILLED)
    ok = await self.binance.cancel_all_open_orders(grid["symbol"])
    if not ok:
        raise ValueError(f"Could not cancel open orders for {grid['symbol']} — grid NOT closed")

    # 2) Cerrar la posición neta con MARKET reduceOnly
    if close_position:
        position = await self.binance.get_position(grid["symbol"])
        position_amt = Decimal(position["positionAmt"]) if position else Decimal("0")
        if position_amt != 0:
            result = await self.binance.place_market_close(grid["symbol"], position_amt)
            if not result:
                raise ValueError(
                    f"Orders canceled but position {position_amt} {grid['symbol']} "
                    "could NOT be closed — manual intervention required"
                )

    # 3) Persistir estado local
    conn = get_sqlite_connection()
    try:
        cursor = conn.cursor()
        non_terminal = [o for o in grid["orders"] if o["status"] not in _TERMINAL_ORDER_STATUSES]
        for order in non_terminal:
            cursor.execute("UPDATE grid_orders SET status = 'CANCELED' WHERE id = ?", (order["id"],))
        cursor.execute("UPDATE grids SET status = 'CANCELED' WHERE id = ?", (grid_id,))
        conn.commit()
    finally:
        conn.close()

    closed_grid = self.get_grid(grid_id)
    self._log_grid_closure(closed_grid, final_pnl, trigger_condition)
    return closed_grid
```

Nota: `cancel_all_open_orders` cancela por símbolo, no por grid. Con la regla R-07 (1 grid RUNNING por símbolo) es correcto y más seguro. Si algún día permites varios grids por símbolo, vuelve a cancelación por `orderId` pero filtrando estados no terminales.

### 1.3 Verificar

1. Crear grid en testnet, esperar ≥1 fill (o mover cantidad para forzarlo).
2. `DELETE /api/v1/grids/{id}`.
3. En testnet UI: Open Orders = 0 y Positions = 0 para el símbolo. Antes de este cambio quedaba posición abierta — esa es la prueba.

---

## Paso 2. Configurar leverage, margin type y position mode (#6)

**Objetivo:** garantizar 1×, modo one-way y tipo de margen explícito antes de colocar la primera orden.

### 2.1 Cliente — `binance_client.py`

```python
async def ensure_symbol_settings(self, symbol: str, leverage: int = 1,
                                  margin_type: str = "ISOLATED") -> bool:
    """Fija leverage y marginType. Idempotente: tolera 'no need to change' (-4046)."""
    ok = True
    for endpoint, params in [
        ("/fapi/v1/leverage", {"symbol": symbol, "leverage": leverage}),
        ("/fapi/v1/marginType", {"symbol": symbol, "marginType": margin_type}),
    ]:
        try:
            await self.time_sync.sync_if_stale()
            p = {**params,
                 "timestamp": self.time_sync.get_adjusted_time(),
                 "recvWindow": settings.BINANCE_RECV_WINDOW}
            p["signature"] = self.security.generate_signature(p)
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(f"{self.base_url}{endpoint}", params=p,
                                        headers=self.security.get_headers()) as r:
                    if r.status == 200:
                        continue
                    body = await r.json()
                    if body.get("code") == -4046:  # margin type ya es el pedido
                        continue
                    print(f"ensure_symbol_settings {endpoint}: {r.status} {body}")
                    ok = False
        except Exception as e:
            print(f"ensure_symbol_settings error: {e}")
            ok = False
    return ok

async def is_one_way_mode(self) -> Optional[bool]:
    """GET /fapi/v1/positionSide/dual → dualSidePosition=False significa one-way (lo que necesitamos)."""
    try:
        await self.time_sync.sync_if_stale()
        params = {"timestamp": self.time_sync.get_adjusted_time(),
                  "recvWindow": settings.BINANCE_RECV_WINDOW}
        params["signature"] = self.security.generate_signature(params)
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"{self.base_url}/fapi/v1/positionSide/dual",
                                   params=params, headers=self.security.get_headers()) as r:
                if r.status == 200:
                    return not (await r.json()).get("dualSidePosition", False)
    except Exception as e:
        print(f"Error checking position mode: {e}")
    return None
```

### 2.2 Config — `app/core/config.py`

```python
DEFAULT_LEVERAGE: int = 1
DEFAULT_MARGIN_TYPE: str = "ISOLATED"   # ISOLATED aísla el riesgo del grid del resto de la cuenta
```

### 2.3 Llamarlo en `create_grid()` — `grid_service.py`

Justo después de validar bounds y ANTES de colocar órdenes:

```python
one_way = await self.binance.is_one_way_mode()
if one_way is False:
    raise ValueError("Account is in hedge mode — switch to one-way mode before running grids")

if not await self.binance.ensure_symbol_settings(
        symbol, settings.DEFAULT_LEVERAGE, settings.DEFAULT_MARGIN_TYPE):
    raise ValueError(f"Could not set leverage/margin type for {symbol}")
```

### 2.4 Verificar

En testnet, cambia manualmente el símbolo a 20× cross desde la UI, crea un grid por API y confirma en la UI que quedó 1× isolated. Prueba también activando hedge mode: la creación debe fallar con mensaje claro.

---

## Paso 3. Aplicar la expiración `max_duration_hours` (#5) — rompe el deadlock (#4)

**Objetivo:** que `check-close` cierre grids vencidos con trigger `EXPIRED`.

### 3.1 `grid_service.py` → `close_grid_if_triggered()`

Añade el chequeo de edad antes del chequeo SL/TP:

```python
from datetime import datetime, timezone

def _grid_age_hours(self, grid: Dict[str, Any]) -> Optional[float]:
    raw = grid.get("created_at")
    if not raw:
        return None
    try:
        # SQLite CURRENT_TIMESTAMP es UTC
        opened = datetime.strptime(str(raw), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - opened).total_seconds() / 3600
```

Dentro de `close_grid_if_triggered`, tras confirmar `status == "RUNNING"`:

```python
max_duration = grid.get("max_duration_hours")
if max_duration is not None:
    age = self._grid_age_hours(grid)
    if age is not None and age >= float(max_duration):
        closed_grid = await self.cancel_grid(grid_id, trigger_condition="EXPIRED")
        return {"grid": closed_grid, "triggered": "EXPIRED"}
```

### 3.2 Workflow 2

El nodo `IF: Grid closed?` ya evalúa `triggered notEmpty` → `EXPIRED` fluye sin cambios. Solo ajusta el texto del Telegram si quieres distinguir el motivo.

### 3.3 Verificar

Crear grid con `max_duration_hours: 0.05` (3 min), esperar, ejecutar WF2 manualmente → debe cerrar con `triggered: "EXPIRED"`, órdenes 0, posición 0, fila en `historical_grid_logs` con `trigger_condition = EXPIRED`.

---

## Paso 4. SL/TP reales en Workflow 1 (#4)

**Objetivo:** ningún grid se lanza sin stop-loss.

### 4.1 Regla de negocio propuesta

Con capital asignado por grid = `balance × risk_pct`:

- `stop_loss` (USDT) = **50% del capital asignado**. Si el grid pierde la mitad de lo que decidiste arriesgar, el rango ya no es válido: fuera.
- `take_profit` = null al inicio (deja que la expiración mande) o 1× el capital asignado si prefieres asegurar ganancias.

### 4.2 Backend: exponer el capital asignado

En `main.py` → `analyze_market`, cuando calcula `suggested_quantity_per_order`, añade al response:

```python
capital_asignado = usdt_balance * Decimal(str(effective_risk_pct))
response["allocated_capital"] = float(capital_asignado)
response["suggested_stop_loss"] = float(capital_asignado * Decimal("0.5"))
```

(añade ambos campos opcionales a `MarketAnalysisResponse` en `grid_schema.py`).

### 4.3 Workflow 1: nodo `Create Grid (POST)`

Cambia el `jsonBody`:

```
stop_loss: $('Market Analysis').item.json.suggested_stop_loss,
take_profit: null,
max_duration_hours: null        // se calcula solo (regla 4×ATR-window)
```

### 4.4 Verificar

Lanzar WF1 manual → el grid creado debe tener `stop_loss` poblado en `GET /api/v1/grids/{id}`. Simular pérdida (crear grid con `stop_loss: 0.01`) y correr WF2 → debe cerrar con `STOP_LOSS` y posición en 0.

**Checkpoint Fase 1:** el ciclo de vida completo funciona solo: lanzar → operar → cerrar por SL o EXPIRED → WF1 puede volver a lanzar. El deadlock desaparece.

---

# FASE 2 — Rentabilidad (que los números sean reales)

## Paso 5. Comisiones (#7)

### 5.1 Obtener fees reales — `binance_client.py`

```python
async def get_commission_rate(self, symbol: str) -> Optional[Dict[str, Decimal]]:
    """GET /fapi/v1/commissionRate — fees reales de la cuenta (respeta VIP/BNB)."""
    try:
        await self.time_sync.sync_if_stale()
        params = {"symbol": symbol,
                  "timestamp": self.time_sync.get_adjusted_time(),
                  "recvWindow": settings.BINANCE_RECV_WINDOW}
        params["signature"] = self.security.generate_signature(params)
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"{self.base_url}/fapi/v1/commissionRate",
                                   params=params, headers=self.security.get_headers()) as r:
                if r.status == 200:
                    data = await r.json()
                    return {"maker": Decimal(data["makerCommissionRate"]),
                            "taker": Decimal(data["takerCommissionRate"])}
    except Exception as e:
        print(f"Error fetching commission rate: {e}")
    return None
```

### 5.2 Nueva regla de negocio: paso mínimo del grid — `indicators.py`

```python
def validate_grid_step(lower_price: Decimal, upper_price: Decimal, levels: int,
                        maker_fee: Decimal, min_fee_multiple: Decimal = Decimal("5")) -> None:
    """
    El beneficio bruto de un ciclo (comprar en nivel i, vender en i+1) es ~ el paso%.
    El costo es 2 fees (entrada + salida). Exigimos paso% >= min_fee_multiple * 2 * maker_fee.
    Con maker 0.02% y múltiplo 5 → paso mínimo 0.2%.
    """
    avg_price = (lower_price + upper_price) / 2
    step_pct = (upper_price - lower_price) / Decimal(max(levels - 1, 1)) / avg_price
    min_step_pct = min_fee_multiple * 2 * maker_fee
    if step_pct < min_step_pct:
        raise ValueError(
            f"Grid step {step_pct:.4%} is below minimum {min_step_pct:.4%} "
            f"(= {min_fee_multiple}x round-trip fees). Reduce levels or widen the range."
        )
```

En config: `MIN_STEP_FEE_MULTIPLE: float = 5.0`.

En `create_grid()`, después de calcular bounds y antes de colocar órdenes:

```python
fees = await self.binance.get_commission_rate(symbol)
maker_fee = fees["maker"] if fees else Decimal("0.0002")  # fallback conservador
validate_grid_step(Decimal(str(lower_price)), Decimal(str(upper_price)),
                   levels, maker_fee, Decimal(str(settings.MIN_STEP_FEE_MULTIPLE)))
```

### 5.3 PnL neto de fees — `indicators.py` → `calculate_grid_pnl()`

Añade parámetro `fee_rate: Decimal = Decimal("0")` y al final:

```python
total_fees = (buy_cost + sell_proceeds) * fee_rate
return {
    ...,
    "total_fees": total_fees,
    "total_pnl": realized_pnl + unrealized_pnl - total_fees,
}
```

En `get_grid_pnl()` pásale el maker fee obtenido (cachéalo en el servicio; cambia una vez al mes como mucho — basta refrescarlo al crear cada grid). Añade `total_fees: float` a `GridPnlResponse`.

Importante: como el SL/TP evalúa `total_pnl`, a partir de aquí decide sobre PnL **neto** — más conservador y correcto.

### 5.4 Informar a la IA

En el prompt de `Build Gemini Request` añade la regla para que no sugiera grids inviables:

```
- El paso del grid ((upper-lower)/(gridCount-1))/precio debe ser >= 0.2%.
  Si con el rango sugerido no caben ni 5 niveles cumpliendo eso, launch=false.
```

### 5.5 Verificar

Test unitario: `validate_grid_step` con paso 0.1% y fee 0.02% debe lanzar ValueError; con paso 0.5% pasa. En testnet: crear grid con 20 niveles en rango angosto → debe rechazarse con el mensaje claro.

---

## Paso 6. Min-notional sin inflar el riesgo (#9)

**Objetivo:** eliminar el `Math.max(qty, 65/precio)` de WF1.

### 6.1 Backend decide, no el workflow

En `analyze_market` (main.py), tras calcular `quantity`:

```python
filters = await grid_service.binance.get_symbol_filters(symbol)
min_notional = filters["min_notional"] if filters else Decimal("100")
notional_per_order = quantity * Decimal(str(bounds["lower_price"]))

response["min_notional"] = float(min_notional)
response["meets_min_notional"] = bool(notional_per_order >= min_notional)
# Máximo de niveles que el capital asignado permite cumpliendo min_notional:
response["max_affordable_levels"] = int(capital_asignado / min_notional)
```

### 6.2 Workflow 1

1. En `Build Gemini Request`, pasa `min_notional`, `meets_min_notional` y `max_affordable_levels` a la IA y añade al prompt:
   `- gridCount no puede superar max_affordable_levels. Si max_affordable_levels < 5, launch=false.`
2. En `Create Grid (POST)` elimina el `Math.max(...)`:
   ```
   quantity_per_order: $json.suggested_quantity_per_order
   ```
3. En `Parse AI Decision`, ya existe un tope de gridCount vs config — añade también `gridCount = Math.min(gridCount, max_affordable_levels)`.

Regla resultante: **si el 2% del balance no alcanza para 5 niveles con min-notional, no se lanza** y se notifica por Telegram. Nunca se sube la cantidad silenciosamente.

### 6.3 Verificar

Con balance de testnet bajo (o `risk_pct: 0.001`), correr WF1 → debe llegar Telegram "Grid NO lanzado" con el razonamiento, no un grid con notional inflado.

---

## Paso 7. Usar `executedQty` y `avgPrice` reales (#8)

### 7.1 Esquema — `connection.py` → `init_sqlite_tables()`

```python
for column_def in ("stop_loss NUMERIC", "take_profit NUMERIC", "max_duration_hours NUMERIC",
                   "..."):  # ya existente en grids
    ...
# Nuevo bloque para grid_orders:
for column_def in ("executed_qty NUMERIC DEFAULT 0", "avg_fill_price NUMERIC"):
    try:
        cursor.execute(f"ALTER TABLE grid_orders ADD COLUMN {column_def}")
    except sqlite3.OperationalError:
        pass
```

### 7.2 `refresh_order_status()` — guardar lo que Binance ya devuelve

```python
new_status = remote["status"]
executed_qty = remote.get("executedQty", "0")
avg_price = remote.get("avgPrice", "0")
cursor.execute(
    "UPDATE grid_orders SET status = ?, executed_qty = ?, avg_fill_price = ? WHERE id = ?",
    (new_status, executed_qty, avg_price, order["id"])
)
```

(actualiza siempre, no solo cuando cambia el status: un PARTIALLY_FILLED puede aumentar executedQty sin cambiar de estado).

### 7.3 `calculate_grid_pnl()` — contar lo ejecutado

Cambia la acumulación:

```python
for order in orders:
    executed = _as_decimal(order.get("executed_qty") or 0)
    if executed <= 0:
        continue  # ya no filtramos por status: PARTIALLY_FILLED con executed>0 SÍ cuenta
    price = _as_decimal(order.get("avg_fill_price") or 0) or _as_decimal(order["price"])
    if order["side"] == "BUY":
        buy_qty += executed
        buy_cost += executed * price
    elif order["side"] == "SELL":
        sell_qty += executed
        sell_proceeds += executed * price
```

### 7.4 Verificar

Test unitario nuevo: orden PARTIALLY_FILLED con `executed_qty=0.5` debe aportar 0.5 al PnL (antes aportaba 0). En testnet, comparar `GET .../pnl` contra el PnL que muestra la UI de Binance — ahora deben cuadrar (± funding).

**Checkpoint Fase 2:** el PnL que decide SL/TP es neto de fees y basado en ejecución real; el sizing respeta el % de inversión siempre.

---

# FASE 3 — Estrategia (convertirlo en un grid de verdad)

## Paso 8. Reposición de órdenes (#1)

**Objetivo:** cada fill genera la orden opuesta en el nivel adyacente → el grid opera ciclos indefinidamente hasta SL/TP/EXPIRED.

### 8.1 Esquema: identificar el nivel de cada orden

En `grids` ya está todo para recalcular niveles (`lower_price, upper_price, levels`, tipo). Añade a `grid_orders`:

```python
for column_def in ("level_index INTEGER", "cycle INTEGER DEFAULT 0"):
    try:
        cursor.execute(f"ALTER TABLE grid_orders ADD COLUMN {column_def}")
    except sqlite3.OperationalError:
        pass
```

Y añade columna `grid_type TEXT` a `grids` (hoy no se persiste y hace falta para recalcular niveles):

```python
# en create_grid(): guardar grid_type en el INSERT de grids
# en init_sqlite_tables(): ALTER TABLE grids ADD COLUMN grid_type TEXT
```

En `create_grid()`, al insertar cada orden guarda su `level_index` (posición en `price_levels`) y `cycle = 0`.

### 8.2 Lógica de reposición — `grid_service.py`

```python
async def replenish_filled_orders(self, grid_id: str) -> int:
    """
    Por cada orden FILLED sin reponer: coloca la opuesta en el nivel adyacente.
      BUY llenada en nivel i  -> SELL en nivel i+1
      SELL llenada en nivel i -> BUY en nivel i-1
    Devuelve cuántas órdenes nuevas se colocaron. Idempotente: marca la orden
    origen (cycle -> -1 no; usamos flag replenished) para no reponer dos veces.
    """
    grid = self.get_grid(grid_id)
    if not grid or grid["status"] != "RUNNING":
        return 0

    engine = GridEngine(grid["symbol"], float(grid["lower_price"]),
                        float(grid["upper_price"]), int(grid["levels"]),
                        GridType(grid.get("grid_type") or "GEOMETRIC"))
    price_levels = engine.calculate_grid_levels()
    filters = await self.binance.get_symbol_filters(grid["symbol"])
    if not filters:
        return 0

    to_place = []
    for o in grid["orders"]:
        if o["status"] != "FILLED" or o.get("replenished"):
            continue
        idx = o.get("level_index")
        if idx is None:
            continue
        if o["side"] == "BUY" and idx + 1 < len(price_levels):
            new_idx, new_side = idx + 1, "SELL"
        elif o["side"] == "SELL" and idx - 1 >= 0:
            new_idx, new_side = idx - 1, "BUY"
        else:
            continue  # fill en el borde del grid: no hay nivel adyacente
        price = self._snap_down(price_levels[new_idx], filters["tick_size"])
        to_place.append((o, new_idx, {
            "symbol": grid["symbol"], "side": new_side,
            "quantity": Decimal(str(o["quantity"])), "price": price,
        }))

    placed = 0
    conn = get_sqlite_connection()
    try:
        cursor = conn.cursor()
        for batch_start in range(0, len(to_place), _BATCH_SIZE):
            batch = to_place[batch_start:batch_start + _BATCH_SIZE]
            results = await self.binance.place_batch_orders([spec for _, _, spec in batch])
            for (source, new_idx, spec), order in zip(batch, results):
                if not order or "orderId" not in order:
                    continue  # se reintenta en el próximo ciclo (source sigue sin replenished)
                cursor.execute(
                    """INSERT INTO grid_orders
                       (id, grid_id, price, quantity, side, type, status, level_index, cycle)
                       VALUES (?, ?, ?, ?, ?, ?, 'NEW', ?, ?)""",
                    (str(order["orderId"]), grid_id, str(spec["price"]), str(spec["quantity"]),
                     spec["side"], "LIMIT", new_idx, int(source.get("cycle") or 0) + 1)
                )
                cursor.execute("UPDATE grid_orders SET replenished = 1 WHERE id = ?", (source["id"],))
                placed += 1
            conn.commit()
    finally:
        conn.close()
    return placed
```

Añade la columna flag: `ALTER TABLE grid_orders ADD COLUMN replenished INTEGER DEFAULT 0`.

### 8.3 Encadenarlo al refresh — `main.py`

En el endpoint `/refresh`, después de `refresh_order_status()`:

```python
replenished = await grid_service.replenish_filled_orders(grid_id)
```

(devuélvelo en el response para que WF2 lo pueda notificar: `"orders_replenished": replenished`).

### 8.4 Detalle importante — PnL con ciclos

Con reposición, el mismo nivel compra y vende varias veces; `calculate_grid_pnl` ya suma por lado sobre TODAS las órdenes del grid, así que los ciclos quedan contados correctamente sin cambios adicionales.

### 8.5 Verificar (la prueba más importante de todo el plan)

En testnet, grid angosto alrededor del precio actual (fills rápidos). Tras cada ciclo de WF2 confirmar: cada BUY llenada tiene una SELL nueva un nivel arriba (`level_index` correcto, `cycle` incrementado), no hay duplicados tras forzar un reintento, y el PnL realizado crece con cada ciclo completado. Dejarlo 48h corriendo.

---

## Paso 9. Refresh eficiente (#12)

Reemplaza las N llamadas por orden con 1 llamada por símbolo:

```python
async def get_open_orders(self, symbol: str) -> Optional[List[Dict[str, Any]]]:
    """GET /fapi/v1/openOrders?symbol= — todas las órdenes abiertas en 1 request."""
    # ... mismo patrón firmado que get_position()
```

En `refresh_order_status()`: obtén el set de `orderId` abiertos en Binance. Las órdenes locales no terminales que **no** estén en ese set cambiaron de estado → solo a ésas les haces `get_order_status()` individual (para saber si fue FILLED o CANCELED). Con 10 niveles y 1 fill pasas de 10 llamadas a 2.

**Opcional (siguiente iteración):** User Data Stream por websocket (`ORDER_TRADE_UPDATE`) elimina el polling y entrega `executedQty`, `avgPrice` y `commission` en tiempo real. Recomendado cuando la reposición esté estable, porque reduce la latencia de reposición de ≤15 min a segundos.

---

# FASE 4 — Robustez operativa

## Paso 10. Tope de exposición global (#10)

Config: `MAX_CONCURRENT_GRIDS: int = 2`. En `create_grid()` junto al check R-07:

```python
cursor_check.execute("SELECT COUNT(*) AS c FROM grids WHERE status = 'RUNNING'")
if cursor_check.fetchone()["c"] >= settings.MAX_CONCURRENT_GRIDS:
    raise ValueError(f"Max concurrent grids ({settings.MAX_CONCURRENT_GRIDS}) reached")
```

## Paso 11. Stop de respaldo nativo en el exchange (#13)

El SL por polling depende de que n8n esté vivo. Red de seguridad independiente: al crear el grid, coloca un `STOP_MARKET` con `closePosition=true` a un precio catastrófico (p. ej. `lower_price − 2×ATR` para el lado long). Se cancela junto con el grid en `cancel_all_open_orders` (misma llamada, mismo símbolo). Si n8n muere y el precio se desploma, el exchange cierra solo.

Adicional recomendado: bajar el cron de WF2 de 15 min a **5 min** (el costo en requests con el Paso 9 es trivial).

## Paso 12. Higiene del cliente HTTP (#14, #15, #16, #17)

1. **Sesión única:** crea `self._session: Optional[aiohttp.ClientSession]` en `BinanceClient`, con un helper `_request()` que la inicializa lazy y la reutiliza. Ciérrala en el `lifespan` shutdown de FastAPI.
2. **`sync_if_stale()` en todos los firmados:** si haces el helper `_signed_request()`, llama ahí a `sync_if_stale()` una sola vez — desaparece el riesgo -1021 de `place_limit_order`, `cancel_order`, `get_order_status`, `get_account_balance`.
3. **429/418 global:** en el mismo helper, si `status in (429, 418)` → `await asyncio.sleep(int(headers.get("Retry-After", 60)))` y un reintento.
4. **Mark price real:** renombra `get_mark_price` → `get_last_price` y añade `get_mark_price` real con `/fapi/v1/premiumIndex`. Usa mark price en `get_grid_pnl` (es el precio con el que Binance valora tu posición) y last price para los bounds.

## Paso 13. Menores (P2)

- Índice único anti-race: `CREATE UNIQUE INDEX IF NOT EXISTS idx_one_running_per_symbol ON grids(symbol) WHERE status = 'RUNNING';`
- `print()` → `logging` (`logging.getLogger("grid")`, formato con timestamp; configúralo en `main.py`).
- En `analyze_market`, cuando falla balance/klines lanza `HTTPException(status_code=503)` en vez de `ValueError` (400) para que n8n distinga error del exchange de request inválido.
- Tests nuevos mínimos: `validate_grid_step`, PnL con fees, PnL con `executed_qty` parcial, reposición idempotente, expiración.

---

# Checklist final de QA en testnet (antes de capital real)

Ejecutar el ciclo completo sin intervención manual durante **2–4 semanas**:

1. [ ] WF1 lanza grid con SL poblado, leverage 1× isolated verificado en UI.
2. [ ] Fills generan reposición correcta (nivel adyacente, sin duplicados) en ≤1 ciclo de WF2.
3. [ ] PnL del endpoint cuadra con la UI de Binance (± funding) y descuenta fees.
4. [ ] Grid con paso < 0.2% es rechazado; balance insuficiente para 5 niveles → "no launch" notificado.
5. [ ] STOP_LOSS cierra: órdenes 0, posición 0, log en Postgres, Telegram recibido.
6. [ ] EXPIRED cierra a las `max_duration_hours` y WF1 relanza en el siguiente ciclo de 4h.
7. [ ] Apagar n8n 24h con posición abierta → el STOP_MARKET de respaldo sigue en el libro.
8. [ ] Reiniciar el contenedor del backend a mitad de un grid → estado se recupera de SQLite sin órdenes huérfanas.
9. [ ] Revisar `historical_grid_logs`: PnL neto acumulado positivo tras fees en el período de prueba.

Solo si el punto 9 es positivo tiene sentido pasar a real — y empezar con el capital mínimo que cumpla min-notional × 5 niveles.