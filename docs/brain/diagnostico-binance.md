---
title: "Diagnóstico de posiciones y órdenes en Binance (demo)"
type: receta
app: trading-grid-bot
repo: TRADING
tags: [diagnostico, binance, ordenes, posiciones, runbook]
related:
  - "[[_index]]"
  - "[[decisiones-tecnicas]]"
  - "[[n8n-sync-y-gotchas]]"
updated: 2026-11-27
owner: dueño del repo
---

# Diagnóstico de posiciones y órdenes en Binance (demo)

Cuándo usarlo: alertas `CHECK-CLOSE FALLIDO` repetidas, `RESIDUAL_POSITION`, posiciones sin
grid dueño, o cualquier diferencia entre lo que cree el bot y lo que hay en Binance. Caso
real que originó esta receta: grid HYPE, 2026-11-23 → 2026-11-27 (ver [[decisiones-tecnicas]]).

**Reparto de papeles.** Un agente (Claude) puede leer: GET al backend con las credenciales de
usuario de Windows `TRADING_DASH_USER`/`TRADING_DASH_PASS` (nunca POST/DELETE), ejecuciones de
n8n y Postgres por MCP. **No ejecuta operaciones ni cancela órdenes** en cuentas de trading,
ni siquiera en demo: prepara el guion y el dueño lo corre en el servidor.

## 1. Qué ve el backend (solo lectura)

- `GET /api/v1/grids?status=RUNNING` y `GET /api/v1/grids/{id}`: estado y órdenes **según la
  base local** (no según Binance).
- `GET /api/v1/grids/{id}/pnl`: PnL y `net_position_qty` calculados con los fills del grid.
- `GET /api/v1/account/income-summary?days=28`: cifra oficial de Binance y `account.unrealized_pnl`
  de toda la cuenta. Si ese no realizado es mucho mayor que el de los grids vivos, hay
  posiciones sin dueño.
- El refresh de WF2 trae `replenish_position_amt`: la posición que lee Binance.
- No existe ningún endpoint que muestre las órdenes abiertas ni la posición en Binance.

## 2. El error real de Binance

Solo está en el log del contenedor, no en Postgres. En `/data/odoo/43` del servidor Alma:

```bash
docker compose logs --since 40m | grep "Error closing position" | tail -3
```

## 3. Guion de diagnóstico (solo lectura)

Usa el cliente del propio backend dentro del contenedor, así no se tocan claves. Cambia
`SYM` según el caso. La última llamada es el endpoint de **prueba** (no ejecuta nada).

```bash
docker exec -i trading-backend python - <<'PY'
import asyncio, json
from app.services.binance_client import BinanceClient
SYM = "HYPEUSDT"
async def main():
    c = BinanceClient()
    get = lambda ep, **p: c._signed_request("GET", ep, dict(p))
    print("== modo de posicion, True = one-way:", await c.is_one_way_mode())
    print("== multi-assets:", await get("/fapi/v1/multiAssetsMargin"))
    print("== positionRisk:"); print(json.dumps(await get("/fapi/v2/positionRisk", symbol=SYM), indent=1))
    print("== ordenes abiertas:", await get("/fapi/v1/openOrders", symbol=SYM))
    print("== ordenes condicionales (algo) abiertas:", await get("/fapi/v1/openAlgoOrders"))
    acc = await get("/fapi/v2/account") or {}
    print("== posiciones abiertas en la cuenta:")
    for p in acc.get("positions", []):
        if float(p.get("positionAmt", 0)) != 0:
            print(" ", p["symbol"], p["positionAmt"], "lado", p.get("positionSide"), "entrada", p.get("entryPrice"), "no realizado", p.get("unrealizedProfit"), "aislada", p.get("isolated"))
    print("== total no realizado de la cuenta:", acc.get("totalUnrealizedProfit"))
    await c.close_session()
asyncio.run(main())
PY
```

## 4. Órdenes huérfanas: cancelarlas por ID

`DELETE /fapi/v1/allOpenOrders` responde 200 aunque algunas órdenes sobrevivan. Si el
diagnóstico muestra órdenes que ningún grid RUNNING usa (compara sus ids con
`GET /api/v1/grids/{id}`), las cancela el dueño por ID:

```bash
docker exec -i trading-backend python - <<'PY'
import asyncio
from app.services.binance_client import BinanceClient
async def main():
    c = BinanceClient()
    for oid in (882442412, 882490369):   # <- ids del diagnóstico
        print("cancelando", oid, "->", await c._signed_request("DELETE", "/fapi/v1/order", {"symbol": "HYPEUSDT", "orderId": oid}))
    print("abiertas ahora:", await c._signed_request("GET", "/fapi/v1/openOrders", {"symbol": "HYPEUSDT"}))
    await c.close_session()
asyncio.run(main())
PY
```

## 5. Posición atascada: cierre en dos pasos

Lo ejecuta el dueño. Lee la posición primero y no hace nada si ya está en cero; el intento 1
es reduce-only (no puede abrir posición nueva) y el 2 solo corre si la posición sigue abierta,
con la cantidad exacta releída y sin `reduceOnly`. Probado con un exchange simulado en cinco
escenarios y, el 2026-11-27, contra el demo real (HYPE: el intento 1 dio `-2022`, el 2 cerró).
Cambia `SYM` y `STEP` (paso del símbolo).

```bash
docker exec -i trading-backend python - <<'PY'
import asyncio
from decimal import Decimal
from app.services.binance_client import BinanceClient
SYM = "HYPEUSDT"
STEP = Decimal("0.01")
async def pos(c):
    p = await c.get_position(SYM)
    return Decimal(p["positionAmt"]) if p else Decimal("0")
async def main():
    c = BinanceClient()
    amt = await pos(c)
    print("posicion inicial:", amt)
    if amt == 0:
        print("ya esta en cero, no se hace nada"); await c.close_session(); return
    side = "BUY" if amt < 0 else "SELL"
    r = await c._signed_request("POST", "/fapi/v1/order", {"symbol": SYM, "side": side, "type": "MARKET", "quantity": str(abs(amt) + STEP), "reduceOnly": "true"})
    print("intento 1 (reduce-only, un paso mayor):", r)
    amt = await pos(c)
    print("posicion ahora:", amt)
    if amt != 0:
        side = "BUY" if amt < 0 else "SELL"
        r = await c._signed_request("POST", "/fapi/v1/order", {"symbol": SYM, "side": side, "type": "MARKET", "quantity": str(abs(amt))})
        print("intento 2 (sin reduce-only, cantidad exacta):", r)
        print("posicion final:", await pos(c))
    await c.close_session()
asyncio.run(main())
PY
```

Después, el siguiente ciclo de WF2 (≤ 5 min) ve la posición en cero y cierra el grid.

## 6. Casos conocidos

| Fecha | Síntoma | Causa | Qué lo resolvió |
|---|---|---|---|
| 2026-11-23 | `-2022` al cerrar el corto de HYPE; alerta cada 5 min | El demo rechaza el MARKET `reduceOnly` (también con 0,12) sin órdenes abiertas; causa del rechazo desconocida | Orden MARKET sin `reduceOnly` por la cantidad exacta (paso 5) |
| 2026-11-26 | 2 órdenes `NEW` en Binance que la base daba por `CANCELED` | `allOpenOrders` responde 200 sin cancelarlas (grid `afe4a317`, octubre) | Cancelación por ID (paso 4); no era la causa del `-2022` |
| 2026-11-04 | Residual de −0,020 ETH tras un stop-loss | El cierre no dejó la posición en cero; ningún grid la reclamó | **Sigue abierto** (entrada 2.325,34; +12,77 USD sin realizar el 26-nov) |

## 7. Notas

- `/fapi/v1/order/test` acepta la orden aunque el real la rechace: valida formato y filtros,
  no el estado de la cuenta.
- Binance documenta `-2022` como una orden reduce-only que choca con órdenes abiertas. El caso
  de HYPE muestra que en el demo también puede aparecer sin ellas.
- Las columnas de hora de `postgres-trading` van 5 h adelantadas respecto a UTC (ver
  [[n8n-sync-y-gotchas]]).

Fuentes: [códigos de error de USDS-M Futures](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code),
[FAQ de órdenes reduce-only](https://www.binance.com/el/support/faq/detail/360039707291).
