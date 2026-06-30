# Plan de pruebas — Swagger UI (`/api/docs`)

> **Nota de revisión:** este plan fue corregido contra el código actual de `backend-python`. Cambios respecto a la versión original:
> 1. `grid_service.py` solo permite **un grid `RUNNING` por símbolo a la vez** (guardia anti-duplicados) — se reasignaron símbolos distintos a `GRID_A`/`GRID_B`/`GRID_C`/`GRID_D` para evitar choques de `400 "already exists"`.
> 2. `levels: 0` **no** produce `400`. `GridEngine` trata `levels < 2` como caso especial y devuelve igualmente un grid válido de 2 niveles (`lower_price` y `upper_price` solamente). El caso 2.5 se dividió para reflejar esto como comportamiento documentado, no como error.
> 3. Se añadió el caso 2.6 (guardia anti-duplicados) y una nota en la sección 9 sobre un efecto secundario real de la idempotencia de `DELETE`.

Pre-requisito: contenedor reconstruido y corriendo.

```
docker compose build backend-python
docker compose up -d backend-python
```

Abrir `http://<tu-host>:8043/api/docs`. Símbolos sugeridos (ajustar si alguno no existe en tu cuenta testnet): `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `ADAUSDT`, `DOGEUSDT`.

Ejecutar en este orden — varios pasos reutilizan el `id` devuelto por la creación de grid (anotarlo como `GRID_A`, `GRID_B`, etc.).

## 1. Sanity check

| # | Endpoint | Esperado |
|---|----------|----------|
| 1.1 | `GET /health` | 200 — `{"status":"healthy","service":"grid-trading-backend","version":"0.1.0"}` |
| 1.2 | `GET /` | 200 — `{"service":...,"status":"ready","api_version":"v1","docs":"/api/docs"}` |

## 2. Creación de grids — `POST /api/v1/grids`

**2.1 Bounds manuales (caso base) — símbolo `BTCUSDT`**
```json
{
  "symbol": "BTCUSDT",
  "lower_price": 40000.0,
  "upper_price": 45000.0,
  "levels": 10,
  "grid_type": "GEOMETRIC",
  "quantity_per_order": 0.001
}
```
Esperado: 200, `status: "RUNNING"`, `lower_price`/`upper_price` tal cual los enviados, `stop_loss`/`take_profit` en `null`, `orders[]` con 10 órdenes. → Guardar `id` como `GRID_A`. Queda `RUNNING` (no cancelar todavía).

**2.2 Bounds automáticos por ATR (omitir lower_price/upper_price) — símbolo `ETHUSDT`**
```json
{
  "symbol": "ETHUSDT",
  "levels": 6,
  "quantity_per_order": 0.01,
  "atr_period": 14,
  "atr_multiplier": 2.0,
  "klines_interval": "4h"
}
```
Esperado: 200, `lower_price < precio_actual < upper_price` (valores calculados, no enviados). → Guardar `id` como `GRID_B`. Queda `RUNNING`.

**2.3 Con stop_loss/take_profit — símbolo `SOLUSDT`**
Igual a 2.1 (bounds manuales razonables para SOL) agregando `"stop_loss": 5, "take_profit": 10`.
Esperado: 200, respuesta refleja `stop_loss: 5, take_profit: 10`. → Guardar `id` como `GRID_C`. Queda `RUNNING`.

**2.4 Validación — bounds incompletos (debe fallar) — símbolo `BTCUSDT`**
Igual a 2.1 pero quitando `upper_price` (solo `lower_price`). Esto falla *antes* de tocar la DB, así que es seguro reusar `BTCUSDT` aunque `GRID_A` siga `RUNNING`.
Esperado: **400**, `detail` explicando que `lower_price`/`upper_price` deben enviarse ambos o ninguno.

**2.5a Validación — cantidad inválida (debe fallar) — símbolo `BTCUSDT`**
Igual a 2.1 pero con `"quantity_per_order": -1`.
Esperado: **400** — `quantity_per_order is smaller than the minimum step size...`. Esta validación también ocurre antes de la guardia anti-duplicados, así que es segura de reusar con `BTCUSDT`.

**2.5b Comportamiento documentado — `levels: 0` (NO es un error) — símbolo `ADAUSDT`**
```json
{
  "symbol": "ADAUSDT",
  "lower_price": 0.30,
  "upper_price": 0.50,
  "levels": 0,
  "grid_type": "GEOMETRIC",
  "quantity_per_order": 10
}
```
Esperado: **200** (no 400) — `GridEngine` trata `levels < 2` como caso especial y crea un grid de exactamente **2** órdenes (`lower_price` y `upper_price`), ignorando el `0`/`1` enviado. `orders[]` tendrá longitud 2, no 0. → Guardar `id` como `GRID_E` si se quiere usar luego; si no, cancelarlo para no dejar ruido (`DELETE`).

**2.6 Guardia anti-duplicados (debe fallar) — símbolo `BTCUSDT`**
Repetir el payload de 2.1 (`BTCUSDT`) mientras `GRID_A` sigue `RUNNING`.
Esperado: **400** — `detail` tipo `"A RUNNING grid for BTCUSDT already exists (id: ...)"`.

## 3. Lectura

| # | Endpoint | Esperado |
|---|----------|----------|
| 3.1 | `GET /api/v1/grids` | 200 — array incluye `GRID_A`, `GRID_B`, `GRID_C` (y cualquier otro creado) |
| 3.2 | `GET /api/v1/grids/{GRID_A}` | 200 — incluye `orders[]` con `price`, `quantity`, `side`, `status` |
| 3.3 | `GET /api/v1/grids/no-existe` | **404** — `"Grid not found"` |

## 4. Refresh de estado — `POST /api/v1/grids/{id}/refresh`

| # | Caso | Esperado |
|---|------|----------|
| 4.1 | `POST /api/v1/grids/{GRID_A}/refresh` | 200, mismo shape que el detalle. Si alguna orden tuvo fill en testnet, su `status` cambia de `NEW` a `FILLED`/`PARTIALLY_FILLED` |
| 4.2 | `POST /api/v1/grids/no-existe/refresh` | **404** |

## 5. PnL — `GET /api/v1/grids/{id}/pnl`

| # | Caso | Esperado |
|---|------|----------|
| 5.1 | `GET /api/v1/grids/{GRID_A}/pnl` (sin fills aún) | 200 — `realized_pnl=0, unrealized_pnl=0, total_pnl=0, net_position_qty=0`; `current_price` con el mark price real |
| 5.2 | Repetir 5.1 después de 4.1 si hubo fills | Los campos de PnL cambian acorde a las órdenes llenadas (solo cuentan órdenes `FILLED`, no `PARTIALLY_FILLED`) |
| 5.3 | `GET /api/v1/grids/no-existe/pnl` | **404** |

## 6. Check-close — `POST /api/v1/grids/{id}/check-close`

**6.1 Sin disparo** (usar `GRID_C`, SL=5/TP=10, sin fills → PnL=0, dentro de rango)
Esperado: 200, `"triggered": null`, `grid.status` sigue `"RUNNING"`.

**6.2 Con disparo forzado — símbolo `DOGEUSDT` (grid nuevo, dedicado)**
Crear un grid en `DOGEUSDT` con `take_profit` muy bajo (ej. `0.01`) para que cualquier fill mínimo lo dispare. Tras al menos un fill (puede requerir esperar o ajustar precios cerca del mercado) + `POST .../refresh`, llamar a `check-close`.
Esperado: 200, `"triggered": "TAKE_PROFIT"` (o `"STOP_LOSS"` si se fuerza al revés), `grid.status == "CANCELED"`. → Anotar este id como `GRID_D`.

**6.3** `POST /api/v1/grids/no-existe/check-close` → **404**

## 7. Cancelación manual — `DELETE /api/v1/grids/{id}`

| # | Caso | Esperado |
|---|------|----------|
| 7.1 | `DELETE /api/v1/grids/{GRID_B}` | 200, `status: "CANCELED"`. Verificar en Binance testnet que las órdenes abiertas de ese grid quedaron canceladas |
| 7.2 | `DELETE /api/v1/grids/no-existe` | **404** |

## 8. Verificación fuera de Swagger — historical_grid_logs (Postgres)

Tras 6.2 y 7.1, confirmar (vía `psql` o cliente contra `postgres-trading`) que existe una fila por cada grid cerrado:

```sql
SELECT grid_id, symbol, total_pnl, trigger_condition, opened_at, closed_at
FROM historical_grid_logs
ORDER BY closed_at DESC;
```
Esperado: una fila para `GRID_B` con `trigger_condition = 'MANUAL'` (de 7.1) y otra para `GRID_D` con `'TAKE_PROFIT'` o `'STOP_LOSS'` (de 6.2), ambas con `closed_at` poblado.

## 9. Idempotencia (regresión rápida)

- Repetir 6.1 (`check-close`) sobre `GRID_D`, que ya está `CANCELED` tras 6.2 → debe responder 200 con `"triggered": null` sin recalcular PnL (`close_grid_if_triggered` corta apenas ve que `status != RUNNING`, sin volver a llamar a Binance).
- Repetir 7.1 (`DELETE`) sobre `GRID_B`, que ya está `CANCELED` → debe responder 200 sin error (no debe intentar cancelar de nuevo en Binance ni fallar — `_log_grid_closure` usa `merge()` sobre `grid_id` único).
  **Atención:** `cancel_grid()` siempre escribe `trigger_condition="MANUAL"` salvo que se llame internamente desde `check-close`. Si se repite `DELETE` sobre un grid que en realidad se cerró por SL/TP (p. ej. `GRID_D`), el `merge()` **sobrescribirá** la fila de `historical_grid_logs` cambiando su `trigger_condition` de `"TAKE_PROFIT"`/`"STOP_LOSS"` a `"MANUAL"`. Es un efecto secundario real del código actual, no un bug de este plan — evitar llamar `DELETE` manualmente sobre grids que ya se cerraron solos si se quiere preservar el `trigger_condition` original en el histórico.
