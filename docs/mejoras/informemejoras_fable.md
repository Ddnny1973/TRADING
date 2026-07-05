# Revisión técnica y de negocio — TRADING (Grid Bot Binance Futures)

Fecha: 2026-07-05 · Commit revisado: `2aa7240` · Alcance: backend Python completo, workflows n8n 1 y 2, docs.

Todos los hallazgos fueron verificados directamente en el código (archivo y comportamiento citados en cada punto).

---

## Resumen ejecutivo

El proyecto está bien estructurado (separación determinista/IA, Decimal en cálculos, manejo de errores ambiguos -1007/-1021, idempotencia con clientOrderId, WAL en SQLite). Sin embargo, **hay 7 hallazgos P0 que impiden ponerlo a operar con dinero real**. Los tres más graves: el grid no repone órdenes (opera una sola pasada), cancelar un grid deja la posición neta abierta en Binance, y el flujo n8n actual entra en un bloqueo operativo permanente tras lanzar el primer grid.

---

## P0 — Bloqueantes antes de operar en real

### 1. El grid no repone órdenes (estrategia incompleta)
`grid_service.py` coloca las órdenes LIMIT una sola vez en `create_grid()`. Cuando una BUY se llena, **nunca se coloca la SELL del nivel superior** (ni viceversa). Un grid real gana repitiendo ciclos compra-venta; este solo puede completar una pasada y queda inerte. Con el rango ±2·ATR, en horas el grid puede quedar sin órdenes activas.

**Acción:** en `refresh_order_status()`, al detectar una orden que pasó a `FILLED`, colocar la orden opuesta en el nivel adyacente (BUY llenada en nivel i → SELL en nivel i+1). Usar `clientOrderId` derivado de `grid_id + nivel + ciclo` para idempotencia ante reintentos. Registrar cada ciclo en `grid_orders` para que el PnL realizado refleje los ciclos completados.

### 2. Cancelar un grid no cierra la posición neta
`cancel_grid()` cancela órdenes abiertas y marca el grid CANCELED, pero el inventario acumulado (posición long/short neta en Binance) **queda abierto y sin gestión**. Tras un STOP_LOSS la pérdida sigue corriendo indefinidamente.

**Acción:** al cerrar, si `net_position_qty != 0`, enviar orden MARKET `reduceOnly=true` por esa cantidad. Confirmar posición en 0 vía `GET /fapi/v2/positionRisk` antes de marcar CANCELED.

### 3. `cancel_grid` solo cancela órdenes con status local `NEW`
Filtro en `grid_service.py`: `o["status"] == "NEW"`. Una orden `PARTIALLY_FILLED` (estado no terminal, sigue viva en el libro) **no se cancela y queda operando** después de "cerrar" el grid.

**Acción:** cancelar todo estado no terminal, o mejor: una sola llamada `DELETE /fapi/v1/allOpenOrders?symbol=` (atómica, 1 request en vez de N).

### 4. Deadlock operativo: WF1 lanza grids que nunca se cierran
Workflow 1 crea el grid con `stop_loss: null, take_profit: null, max_duration_hours: null`. `check-close` solo evalúa SL/TP → **nunca dispara**. Combinado con la regla R-07 (un grid RUNNING por símbolo), tras el primer lanzamiento el sistema recibe "already exists" cada 4h para siempre. El bot lanza exactamente 1 grid en toda su vida y nadie lo cierra.

**Acción:** que WF1 envíe SL/TP calculados (p.ej. SL = capital_riesgo del grid, TP = múltiplo del paso) y que la expiración se aplique (punto 5).

### 5. `max_duration_hours` se calcula, se persiste y nadie lo evalúa
La regla 4×(interval×atr_period) está implementada y guardada en DB, pero ni `close_grid_if_triggered()` ni ningún nodo n8n la comparan contra `created_at`. La estrategia de expiración documentada en `grid-expiration-strategy.md` está sin cablear.

**Acción:** en `check-close`: `if now - created_at > max_duration_hours → cancel_grid(trigger="EXPIRED")`. Con esto además se rompe el deadlock del punto 4 (~cada 9 días se reevalúa).

### 6. Leverage, margin mode y position mode nunca se configuran
No existe ninguna llamada a `POST /fapi/v1/leverage`, `/fapi/v1/marginType` ni verificación de `positionSide/dualSidePosition` en todo el backend (grep verificado). La regla de negocio es 1× sin apalancamiento, pero una cuenta de futures nueva viene por defecto en **20× cross**: el bot operaría 20× sin saberlo. Además, si la cuenta está en hedge mode, todas las órdenes fallarían con -4061.

**Acción:** al crear cada grid (o al startup por símbolo): fijar `leverage=1`, verificar/forzar one-way mode, y decidir explícitamente ISOLATED vs CROSSED.

### 7. Las comisiones no existen en ninguna parte del sistema
`calculate_grid_pnl()` usa precio×cantidad puros; no hay referencia a fees en todo el repo (grep verificado). Impacto real con la config actual de WF1 (levels=5, multiplier=2):

- Paso del grid ≈ 4·ATR/(levels−1). Con atr_pct 0.5% → paso ≈ 0.5%.
- Fee USDⓈ-M estándar: maker 0.02%, taker 0.05%. Ciclo compra+venta: 0.04%–0.10%.
- Con 5 niveles: fees ≈ 8–20% del beneficio bruto por ciclo. Si la IA sube a 10–15 niveles (como sugiere su prompt), el paso cae a ~0.13–0.28% y **las fees se comen 30–70% del ciclo, o lo dejan en pérdida con fills taker**.

**Acciones:**
1. Obtener fees reales: `GET /fapi/v1/commissionRate` (por símbolo, respeta VIP/BNB).
2. Validar en `create_grid()`: rechazar si `paso% < k·(makerFee·2)` con k ≥ 4–5. Esto acota `levels` en función del ATR — regla de negocio nueva y necesaria.
3. Restar fees estimadas en `calculate_grid_pnl()` (hoy el SL/TP decide sobre un PnL inflado).
4. Ideal: reconciliar con `GET /fapi/v1/userTrades` que devuelve `commission` y `realizedPnl` reales por fill.

---

## P1 — Reglas de negocio y precisión

### 8. PnL usa precio límite y cantidad solicitada, no lo ejecutado
`refresh_order_status()` solo guarda `status`, descartando `executedQty` y `avgPrice` que Binance ya devuelve en la misma respuesta. Consecuencias: `PARTIALLY_FILLED` aporta 0 al PnL (documentado, pero el SL/TP decide con datos incompletos) y el precio real de fill puede diferir del límite.

**Acción:** añadir columnas `executed_qty` y `avg_fill_price` a `grid_orders`, poblarlas en refresh, y usarlas en `calculate_grid_pnl()`. Costo: cero llamadas extra.

### 9. El piso de $65/orden en WF1 viola silenciosamente el % de inversión
`quantity_per_order: Math.max(suggested_qty, 65/avgPrice)`. Si el sizing por riesgo (2%) sugiere menos que el min-notional, el workflow **infla la cantidad** sin avisar: con 5 niveles son ≥$325 de notional aunque el balance solo justifique $100. Además el 65 está hardcodeado (el minNotional real de BTCUSDT en producción es 100 USDT; 65 parece valor de testnet).

**Acción:** leer `min_notional` del exchange (el backend ya lo obtiene en `get_symbol_filters`). Si `suggested_qty·precio < minNotional` → reducir `levels` o **no lanzar y notificar**; nunca subir la cantidad silenciosamente.

### 10. Sin tope de exposición global
Cada grid toma 2% del `availableBalance` en el momento de crearse, pero no hay límite de grids concurrentes entre símbolos ni tope de margen agregado.

**Acción:** `MAX_CONCURRENT_GRIDS` y/o tope de notional total en config; verificar en `create_grid()`.

### 11. Cantidad calculada con bounds ATR, grid creado con bounds de la IA
`suggested_quantity_per_order` se calcula sobre los bounds sugeridos, pero el grid se crea con `lowerLimit/upperLimit` de Gemini (que puede ajustarlos). Inconsistencia menor pero gratuita de arreglar: recalcular qty con los límites finales (o pasar `risk_pct` a `create_grid` y que el backend calcule todo).

---

## P1 — Tiempos y eficiencia

### 12. Refresh: N llamadas firmadas secuenciales por grid
`refresh_order_status()` hace un `GET /fapi/v1/order` por cada orden abierta, cada 15 min. Con 10 niveles: 10 requests secuenciales (~5–10 s por grid).

**Acción inmediata:** una sola llamada `GET /fapi/v1/openOrders?symbol=` y diff contra lo local (las que ya no aparecen → consultar individualmente o asumir terminal y confirmar).
**Acción recomendada:** User Data Stream (websocket `ORDER_TRADE_UPDATE`): elimina el polling, entrega fills en tiempo real con `executedQty`, `avgPrice` y `commission` — habilita además la reposición de órdenes (punto 1) sin latencia.

### 13. 15 minutos de latencia para SL/TP es demasiado en futures
Un movimiento fuerte puede atravesar el stop completo entre ciclos, y si n8n cae no hay protección alguna.

**Acción:** (a) backstop nativo en el exchange: `STOP_MARKET` con `closePosition=true` como red de seguridad independiente de n8n; (b) bajar el ciclo de check-close a 1–5 min (el costo en requests es trivial a esta escala).

### 14. `ClientSession` nueva por request
Cada método de `binance_client.py` crea su propia `aiohttp.ClientSession` (handshake TLS por llamada). Reusar una sesión por cliente reduce latencia y sockets.

### 15. `sync_if_stale()` solo se llama en `place_batch_orders`
`place_limit_order`, `cancel_order`, `get_order_status` y `get_account_balance` usan el offset sin refrescarlo → riesgo de -1021 en contenedor de larga vida (el mismo bug que ya resolvieron para batch).

**Acción:** mover `await self.time_sync.sync_if_stale()` a un helper común de requests firmados.

### 16. Manejo 429/418 solo existe en batchOrders
`get_order_status` (la llamada más frecuente del sistema) devuelve None ante un 429 sin respetar `Retry-After`. Añadir el mismo manejo, y opcionalmente leer `X-MBX-USED-WEIGHT-1M` para throttling proactivo.

### 17. `get_mark_price` no devuelve mark price
Usa `/fapi/v1/ticker/price` (last price). Para bounds del grid es aceptable, pero la liquidación y el PnL de Binance van por mark price (`/fapi/v1/premiumIndex`). Renombrar o cambiar el endpoint para evitar decisiones de SL con el precio equivocado en momentos de divergencia (funding, mechas).

---

## P2 — Menores

- **Race en anti-duplicado R-07**: check-then-insert no atómico en `create_grid()`. Bajo riesgo con n8n secuencial; un índice único parcial `(symbol) WHERE status='RUNNING'` lo cierra gratis.
- **`print()` → `logging`** estructurado con niveles; hoy el diagnóstico depende de logs de contenedor sin timestamps ni contexto.
- **`market-analysis` devuelve 400** cuando falla el fetch de balance/klines (error del lado servidor/exchange, no del cliente) → debería ser 502/503 para que n8n lo distinga de un request mal formado.
- **Errores silenciosos**: varios métodos devuelven `None` tanto para "no existe" como para "Binance caído"; distinguirlos evita interpretar una caída como estado vacío.
- **Tests** (52) cubren bien engine/indicators/API; añadir casos para fees, reposición y cierre de posición cuando se implementen.

---

## Lo que está bien y conviene conservar

Manejo de códigos ambiguos -1007/-1021 con confirmación por `clientOrderId` antes de reintentar (evita órdenes duplicadas — mejor que muchos bots en producción). Firma sobre body pre-encoded en batch (fix -1022 correcto). Decimal end-to-end con snap a tickSize/stepSize y validación de minNotional en backend. WAL en SQLite. Rollback implícito si ninguna orden se coloca. Separación estricta determinista/IA con schema JSON estructurado en Gemini. "Continue on fail" + notificaciones Telegram en ambos workflows.

## Orden de implementación sugerido

1. **Semana 1 (correctitud):** #2, #3 (cierre real de grids), #6 (leverage/margin/position mode), #5 (expiración → rompe el deadlock #4), SL/TP no nulos en WF1.
2. **Semana 2 (rentabilidad):** #7 (fees: validación de paso mínimo + PnL neto), #9 (min-notional sin inflar riesgo), #8 (executedQty/avgPrice).
3. **Semana 3 (estrategia):** #1 (reposición de órdenes — idealmente junto con websocket #12).
4. **Después:** #10, #13 backstop STOP_MARKET, #14–17, P2.

Con #1–#7 resueltos y 2–4 semanas más de testnet validando ciclos completos (crear → fills → reposición → expiración/SL → cierre con posición en 0), el sistema queda en condiciones de operar con capital pequeño real.