---
title: "Decisiones técnicas y alcance de la fase actual"
type: decision
app: trading-grid-bot
repo: TRADING
tags: [decisiones, ia, alcance]
related:
  - "[[_index]]"
  - "[[n8n-sync-y-gotchas]]"
updated: 2026-09-03
owner: dueño del repo
---

# Decisiones técnicas

## Proveedor de IA: NVIDIA NIM / DeepSeek (migrado desde Gemini el 2026-07-08)

**Historial**: originalmente Workflow 1 usaba HTTP Request directo a
`generativelanguage.googleapis.com` (Gemini, `models/gemini-2.5-flash`, con
`responseSchema` para forzar JSON estructurado). El 2026-07-08 (commit
`84bb169`) se migró al nodo nativo `openAi` de n8n apuntando a **NVIDIA NIM**
(credential `DeepSeek`, id `THcslCwcwDaKT3tD`), modelo `deepseek-ai/deepseek-v4-pro`.

**2026-08-14 (commit `95e7a2e`)**: NVIDIA NIM retiró `deepseek-v4-pro` →
migrado a `deepseek-ai/deepseek-v4-flash-0731` (modelo vigente hoy). Si
vuelve a fallar con "model not found"/deprecation, revisar el catálogo de
modelos disponibles en NVIDIA NIM antes de asumir que es un bug del workflow.

Se loguea a Postgres (`public.metricas_personalizadas`) el consumo de
tokens de cada ejecución. Nota heredada de la época Gemini: si se vuelve a
usar un modelo con "thinking"/razonamiento visible, capturar también esos
tokens en el detalle (con Gemini 2.5, `thoughtsTokenCount` era más de la
mitad del costo total — no medirlo subestima el gasto real).

## Fix: `isExecuted` en referencias a `WF-Trigger-Externo` (2026-08-14, commit `9ba1c9d`)

Workflow 1 puede correr por **schedule** (cron) o por **trigger externo**
(llamado desde otro workflow/WF3). Las expresiones que leían
`$('WF-Trigger-Externo').item.json...` fallaban en runs por schedule porque
ese nodo nunca se ejecuta en ese camino. Fix: envolver esas referencias con
`$if($('WF-Trigger-Externo').isExecuted, <valor real>, <default>)` en todos
los nodos que arman `chatId`/`balance`/`symbol` y en las notificaciones de
Telegram (default de `chatId` cuando no hay trigger externo: `1060878323`).
Aplica el mismo patrón si se agregan nuevos triggers de entrada a WF1 en el
futuro — cualquier expresión que dependa de un nodo trigger opcional debe
chequear `isExecuted` primero.

## Tope de seguridad: `gridCount` vs `levels`

En "Parse AI Decision" (Workflow 1) se aplica
`gridCount = Math.min(IA_gridCount, Config.levels)` para que la IA nunca
pueda pedir más grids de los configurados como máximo. Documentado también
en [docs/50-WORKFLOWS/02-workflow1.md](../50-WORKFLOWS/02-workflow1.md).
**Pendiente**: el system prompt de la IA no sabe de este tope — razona sobre
un `gridCount` que puede ser recortado después sin que ella lo sepa.

## Alcance de la fase actual (ACTUALIZADO 2026-08-31)

⚠️ **Esta sección decía lo contrario hasta el 2026-08-31.** El alcance anterior
era "llegar a un deployment funcional de los workflows n8n, sin optimizar
todavía la estrategia/rentabilidad". **Ese objetivo ya se cumplió.**

El alcance actual, declarado explícitamente por el dueño del repo, es que el
bot: (1) opere **7/24 sin quedarse sin operar**, (2) tome decisiones solo, y
(3) **principalmente, sea rentable**.

El diagnóstico del 2026-08-31 mostró que el bot **pierde ~8 USD** acumulados.
Optimizar la rentabilidad **sí es trabajo pendiente y urgente** — lo contrario
de lo que decía esta nota antes. El plan está en
`docs/analisis-bot/03-plan-mejoras-rentabilidad.md` (22 tareas con tablero de
estado) y el análisis de estrategia/portafolio en
`docs/analisis-bot/04-estrategia-y-portafolio.md`.

## Guardas de negocio implementadas en el backend

- Solo **1 grid RUNNING por símbolo** (guardia en `POST /api/v1/grids`,
  responde 400 "already exists" — no es un error real, n8n debe interpretarlo
  como "ya hay un grid activo").
- **`MAX_CONCURRENT_GRIDS = 4`** (era 2 hasta el 2026-08-31). Su 400 "Max
  concurrent grids" también es informativo, no un error.
- **Cap de inventario proporcional a `levels`** (2026-08-31): ver sección
  dedicada más abajo. Reemplaza al tope fijo de `3 × quantity_per_order`.
- **`stop_loss` / `take_profit` derivados del balance** (1 % / 3 %) en
  `auto_params` y propagados por WF1 — antes se enviaban siempre en `null`.
- `place_batch_orders()` (en
  [backend-python/app/services/binance_client.py](../../backend-python/app/services/binance_client.py))
  reintenta por **ítem** (no por batch completo) ante respuestas ambiguas de
  Binance (código -1007/-1021 dentro de un HTTP 200), confirmando vía
  `_get_order_by_client_id` antes de reencolar — evita duplicar órdenes ya
  colocadas exitosamente.

## WF1: 400 "Max concurrent grids" tratado como informativo (2026-08-16)

Con el tope `MAX_CONCURRENT_GRIDS=2` alcanzado, casi toda corrida de WF1
choca con el 400 "Max concurrent grids (2) reached" del `POST /api/v1/grids`
— flujo esperado, igual que el 400 "already exists" (guardas reales de BD).
El workflow lo trataba como error real y disparaba `Diagnose Grid Error`
(otra llamada LLM); ahí era donde explotaban los **504 Gateway Timeout de
NVIDIA NIM** (mensaje "Gateway timed out - perhaps try again later?",
~302s de respuesta). Fix en `Interpret Grid Result`: ese 400 ahora devuelve
`maxConcurrent:true` (rama informativa) y `Notify: Grid Launched` muestra un
mensaje distinto, saltando el Diagnose. No es "mejorar la estrategia": es
sanear el ruido de errores para poder medir la rentabilidad real (ver
[[analisis-bot-monitoreo]]).

## Dashboard web del bot (2026-08-02 → 2026-08-10)

Se agregó un dashboard de performance leyendo `postgres-trading` en vivo:
- `scripts/dashboard/export_data.py` + `scripts/dashboard/template.html`
  (2026-08-02): generador de HTML offline (corre localmente, exporta un
  snapshot estático).
- `GET /dashboard` + `GET /api/v1/dashboard/data` (2026-08-10, commit
  `d7f6c1a`): mismo template servido como parte del backend FastAPI, con
  datos en vivo vía el engine SQLAlchemy del backend
  (`backend-python/app/services/dashboard_data.py`). El template se movió a
  `backend-python/app/templates/dashboard.html` (fuente única, se hornea en
  la imagen Docker); `export_data.py` sigue existiendo para generar el HTML
  offline leyendo ese mismo template.
- Fix 2026-08-10 (`e4bc048`): casts idempotentes en `dashboard_data.py` para
  evitar doble-cast de columnas datetime (podía romper si se llamaba dos
  veces sobre el mismo objeto/fila).
- Endpoints documentados en [docs/api-endpoints.md](../api-endpoints.md).
- Fix 2026-08-16: `current` del dashboard (y `/estado` de WF3) contaba grids
  cerrados como RUNNING — `latest_snapshot` (`pnl_snapshots`, último snapshot
  por `grid_id`) incluía grids ya cerrados (p. ej. `9c3f822b` dejó un
  snapshot residual de 9 órdenes / +0.2077 USDT), inflando "Grids RUNNING",
  "Órdenes abiertas" y el PnL "vivo" con datos fantasma. Fix: `latest_snapshot`
  excluye grid_ids presentes en `historical_grid_logs` (`NOT EXISTS`) en
  `dashboard_data.py` y `scripts/dashboard/export_data.py`.

## Comando Telegram `/estado` en WF3 (2026-08-14, commit `56398f3`)

Nuevo comando en Workflow 3 que devuelve un resumen (grids activos, PnL,
actividad reciente del bot) directo por Telegram, sin tener que abrir el
dashboard web. Complementa `/lanzar` y `/monitorear` ya existentes.

## Línea de trabajo abierta (2026-07-30): monitoreo/analítica antes de pasar a dinero real

El usuario sigue en testnet (`BINANCE_TESTNET_URL` en `config.py`) a
propósito — la prioridad inmediata NO es explorar las otras 4 estrategias
del documento raíz `Estrategias de Trading Automatizado con n8n y
Binance.md` (eso queda pendiente de decidir con su compañera), sino poder
**medir objetivamente si Grid Trading es rentable** para decidir con datos
cuándo pasar a dinero real. Ver [[analisis-bot-monitoreo]] para el detalle
completo y el estado de avance (evita repetir esta exploración en sesiones
futuras).

## Período de gracia en check-close (2026-08-26)

**Problema**: los grids se cancelaban por `OUT_OF_RANGE` en el primer ciclo
de monitoreo (5 min después de creación). Con bounds ATR-based (multiplier
1.5-3.5x), un movimiento de precio mínimo en crypto provocaba cierre inmediato
sin que el grid tuviera oportunidad de llenar órdenes o completar ciclos.

**Solución**: `CHECK_CLOSE_GRACE_MINUTES = 30` en `config_auto_params.py`.
El check-close no evalúa `OUT_OF_RANGE` hasta que el grid tenga al menos 30
minutos de vida. Los demás triggers (`EXPIRED`, `MAX_POSITION`, `STOP_LOSS`,
`TAKE_PROFIT`) NO se ven afectados por la gracia — solo `OUT_OF_RANGE`.

**Archivo**: `app/services/grid_service.py`, método `close_grid_if_triggered`.
**Constante**: `CHECK_CLOSE_GRACE_MINUTES` en `app/config_auto_params.py`.

## Auto-close de posiciones residuales (2026-08-26)

**Problema**: después de cancelar un grid, a veces queda una posición residual
tiny (ej. 0.0009 BTC) por redondeo en el market close. El siguiente intento
de crear un NEUTRAL grid falla con "existing position != 0".

**Solución**: `create_grid` ahora intenta cerrar automáticamente cualquier
posición residual antes de crear el grid. Solo falla si el cierre no logra
limpiar la posición completamente.

**Archivo**: `app/services/grid_service.py`, create_grid method (~línea 155).

## El inventario deja de ser motivo de cierre (2026-08-31, commits `b315faf` + `5f9b5b0`)

Las tres decisiones más importantes tomadas tras el diagnóstico de
rentabilidad. Cambian el comportamiento operativo del bot, no solo su código.

**1. Un grid NEUTRAL puede (y debe) cargar inventario.** El guard de
`replenish_filled_orders()` usaba `tolerance = quantity_per_order * 0.05`, así
que tras el *primer* fill la posición ya valía 20× la tolerancia y la
reposición quedaba bloqueada de forma casi permanente — el motor quedaba
inerte. Ahora la tolerancia es
`_max_net_position_qty(grid) * REPLENISH_POSITION_TOLERANCE_RATIO` (0.80).

**2. Superar el cap pausa, no cierra — y la pausa es direccional.** El cap de
posición neta pasó de `MAX_NET_POSITION_LEVELS (3) × qty × 1.05` fijo a
`max(MAX_NET_POSITION_LEVELS, ceil(levels × MAX_NET_POSITION_RATIO)) × qty`,
es decir escala con el tamaño del grid. Al superarlo **solo se pausa la
reposición del lado que acumula**; la pata que descarga inventario se sigue
colocando, que es lo que permite que la posición vuelva sola a cero. El cierre
por `MAX_POSITION` queda como red de seguridad a `MAX_POSITION_HARD_MULTIPLE`
(2.0×) del cap.

> Detalle de implementación fácil de romper: en el bucle de
> `replenish_filled_orders()` el **lado de la orden se resuelve ANTES del claim
> atómico** (`UPDATE ... replenished = 1`). Si se invierte ese orden, una pata
> pausada quema su claim y no vuelve a reponerse nunca.

**3. El freno real pasa a ser el dinero, no el inventario.**
`auto_derive_params()` deriva `stop_loss` = 1 % y `take_profit` = 3 % del
balance (`GRID_STOP_LOSS_PCT_OF_BALANCE` / `GRID_TAKE_PROFIT_PCT_OF_BALANCE`).
Antes WF1 enviaba siempre `null` y por eso **nunca** hubo un cierre por SL/TP
en toda la historia del bot.

> Gotcha: `AutoParamsParamsV2` en `app/main.py` **debe declarar** los campos
> nuevos o FastAPI los filtra silenciosamente de la respuesta de
> `/auto-params`, y WF1 recibe `undefined`.

**Constantes**: todas en `app/config_auto_params.py`, salvo
`MAX_CONCURRENT_GRIDS` / `MAX_NET_POSITION_LEVELS` que viven en
`app/core/config.py`.

## T1: reportar la pausa de resposición (2026-09-02, rama `feat/rentabilidad-t1-t5-pnl-20260902`)

Al pausar la reposición por inventario, `replenish_filled_orders()` no distinguía
el caso de haber colocado órdenes del de haber quedado bloqueado: WF2 y el
dashboard veían el refresh "ok" y no había forma de saber que el grid estaba
parado por posición. Ahora devuelve (y `/refresh` propaga en cada llamada, no
solo cuando coloca) `replenish_status` (`ok` / `paused_position` / `skipped`) más
`replenish_placed`, `replenish_paused`, `replenish_blocked_side`,
`replenish_position_amt`, `replenish_tolerance`, `replenish_reason`. Con esto
WF2 puede notificar "reposición pausada" y el dashboard dejar rastro.

- `app/services/grid_service.py::replenish_filled_orders` → devuelve `Dict` con
  `replenish_*` (antes `bool`/sin rastro).
- `app/schemas/grid_schema.py::GridDetailResponse` → campos transient
  `replenish_*` junto a `refresh_status`.
- `app/main.py::/refresh` → propaga los `replenish_*` siempre.
- Tests: `tests/test_replenish_status.py` (4 tests, todos pasan).

## T5: restar el fee de salida al PnL no realizado (arreglar D8, 2026-09-02)

`calculate_grid_pnl` descuenta fees de las patas **realizadas** (compra+venta)
pero **no** del inventario sin cerrar, así que `total_pnl` era mayor que lo que
realmente quedará al cerrar la posición → el SL/TP (que dispara sobre
`total_pnl`) era demasiado optimista y el SL llegaba tarde. Ahora
`unrealized_pnl` resta `abs(net_position_qty) × current_price × fee_rate`
(`app/services/indicators.py` ~L193-196), y `get_grid_pnl` propaga el **maker
real** de `get_commission_rate` vía helper `_effective_fee_rate` (fallback
`0.0002`), en vez de hardcodear el default.

De paso se arreglaron 2 `TypeError` preexistentes en `tests/test_indicators.py`
(el helper `_order` comparaba `executed_qty` str), que hacían que los tests de
PnL nunca hubieran pasado; se añadió `test_calculate_grid_pnl_deducts_exit_fee_from_unrealized`.

## T2: RECENTER en vez de cerrar en OUT_OF_RANGE (2026-09-02, rama `feat/t2-recenter-t6-metrics-20260902`)

El cierre por `OUT_OF_RANGE` al mercado cristalizaba la pérdida en el peor
punto. Ahora, configurable vía `OUT_OF_RANGE_POLICY` ("CLOSE" | "RECENTER",
default RECENTER):

- **Gatillo con buffer anti-ruido:** no se dispara en el primer tick fuera del
  rango. Exige **salida decisiva** (`precio < lower − ATR×OUT_OF_RANGE_ATR_BUFFER
  = 0.5×ATR`, o el simétrico superior) **persistida** `OUT_OF_RANGE_STRIKES_TO_
  TRIGGER = 2` ciclos consecutivos de WF2 (persistido en la columna nueva
  `out_of_range_strikes` de `grids`; se resetea al volver a rango/con ruido). El
  comportamiento histórico (`OUT_OF_RANGE_POLICY = "CLOSE"`) sigue intacto como
  fallback.
- **`recenter_grid(grid_id)`:** cancela las órdenes abiertas **sin**
  `place_market_close`, conserva el inventario, marca el grid CANCELED, calcula
  la posición (`get_position`) y reconstruye vía
  `create_grid(parent_grid_id=..., recenter_count+1)` en modo LONG/SHORT/NEUTRAL
  según el inventario heredado (para que `create_grid` no cierre la posición).
  Registra en `grid_closures` un evento `trigger_condition="RECENTERED"` con la
  columna `parent_grid_id` apuntando al grid nuevo, lo que permite al dashboard
  encadenar la vida real de una operación. Tope `MAX_RECENTERS_PER_GRID = 2`; si
  `recenter_grid` falla o se supera, fallback a cierre `OUT_OF_RANGE`.
  `close_grid_if_triggered` devuelve `{"grid": <nuevo>, "triggered": "RECENTERED"}`.
- **API:** `POST /api/v1/grids/{grid_id}/recenter` (400 si no RUNNING, 404 si no
  existe). Frenos: `MAX_RECENTERS_PER_GRID` + stop-loss (T4).
- **Tests:** `tests/test_recenter.py` (6, pasan): salida decisiva con 1 strike no
  dispara; el 2º strike dispara RECENTER; volver a rango resetea el contador; por
  debajo del buffer ATR se trata como ruido; endpoint `/recenter` devuelve el grid
  nuevo.

## T6: métricas de dashboard que sí significan algo (2026-09-02, rama `feat/t2-recenter-t6-metrics-20260902`)

`dashboard_data.py` (+ espejo `scripts/dashboard/export_data.py`) y
`dashboard.html` añaden `closing_metrics`: **closure drag** agregado y por grid
(pérdida por cierre a mercado), **PnL por trigger_condition**, **tasa de grids
rentables** (`closed_pnl > 0` / total cerrados, reemplaza el win-rate de ciclos),
**grids con 0 ciclos** y **drawdown máximo** con fechas. Permite verificar si T2
(no liquidar) y T3 (no gatillar cierre) funcionaron de verdad.

## T10: relanzar WF1 al cerrar un grid (2026-09-03, rama `feat/continuidad-t10-t12-20260903`)

WF2 (`workflow2-monitor.json`), rama `IF: Grid closed? = true`:
`Notify: Grid Closed → Execute WF1: Relanzar grid → Wait`. El nodo
`executeWorkflow` v1.2 apunta a WF1 (`yggk1wajL1tsmABi`) con
`waitForSubWorkflow: false` (async, no bloquea el ciclo de monitoreo). Como WF1
es idempotente (400 "already exists"/"Max concurrent grids" = informativo), el
relanzado es seguro aunque WF1 ya tuviera cupo. Cierra el hueco
cierre→nuevo grid de "hasta 4 h" a **≤ 5 min**.

## T12: watchdog de "bot inactivo" (2026-09-03, rama `feat/continuidad-t10-t12-20260903`)

WF2, rama "No Running Grids": contador `noGridsCount` en
`$getWorkflowStaticData('global')`. 3 ciclos consecutivos (15 min, a 5 min/ciclo)
con 0 grids → `fire=true` y se resetea → alerta Telegram
"⚠️ Bot sin grids 15 min" + `Execute WF1: Relanzar watchdog`. La rama true de
`IF: Hay grids running?` lleva `Watchdog: reset contador` (`noGridsCount = 0` y
`return $input.all()` para no alterar el batch de grids → **importante: el reset
no debe reemplazar los items del grid**). Mantiene el aviso informativo "Sin
grids en ejecución".

## T8: tablas de salud `bot_executions` / `bot_health_events` (2026-09-03, rama `feat/t8-health-tables-20260903`)

`backend-python/app/database/migration_003_health_tables.sql` define dos tablas
en `postgres-trading` (el Postgres de analítica del backend, NO el de n8n):

- **`bot_executions`** — una fila por ejecución de WF1/WF2: `workflow_id`,
  `status` ('success'|'error'), `trigger_source`, `started_at`, `finished_at`,
  `duration_ms`, `error_message`. Da uptime real del orquestador y tasa de error
  por workflow.
- **`bot_health_events`** — incidentes de negocio con `event_type` tipado:
  `RECONCILIATION_FAILED`, `AUTO_CANCEL`, `REPLENISH_PAUSED`, `RECENTERED` (T2);
  con `severity` ('info'|'warning'|'critical'), `grid_id`, `symbol`,
  `details JSONB`, `occurred_at`.

**Estado:** T8 = solo el script de migración (el dueño del repo lo ejecuta; el
agente no tiene acceso a Postgres). La escritura real desde backend/n8n a estas
tablas es un follow-up posterior, no parte de T8. Uso previsto: dashboard de
uptime (T6 ya muestra drag/drawdown; uptime real quedó pendiente de
`bot_executions`).

## T13: puerta determinista `veto_reasons` en /auto-params (2026-09-03, rama `feat/t13-puerta-determinista-20260903`)

El LLM de WF1 decidió `launch:true` en el 100 % de las ejecuciones históricas y
sus criterios son todos deterministas y computables en el backend. T13 (paso 1 =
instrumentación): `/auto-params` devuelve ahora `veto_reasons: []`, espejo de los
4 criterios del prompt del LLM:

1. `ER > 0.35` — mercado en tendencia (ya está en `ER_MAX_TRADEABLE = 0.35`).
2. `leverage > 5x` con `ATR% > 2%` — helper puro `derive_leverage_atr_veto()`;
   con la config actual el leverage topea en 5x, así que no se disparará en la
   práctica (se mantiene como espejo fiel para comparar contra el LLM).
3. `top_3` vacío — se enruta por `symbol_selection` en modo auto.
4. `candidatos < 5` — `selection["candidates_passed_filters"] < 5` en modo auto.

**Decisión clave:** durante el periodo de observación `veto_reasons` = solo
instrumentación; NO fuerza `grid_viable=False`, para no cambiar el comportamiento
mientras se junta la comparación LLM-vs-determinista. El paso 2 (degradar el LLM
a solo-notificación) se aplica tras 2-4 semanas de datos, y el paso 1 completo
requiere que WF1 registre en Postgres la decisión determinista y la del LLM.

Los `veto_reasons` per-symbol viven en `auto_derive_params()`; los de selección
auto se mergean en `/auto-params` (`main.py`). `CODE_VERSION` → `v1.10.0-t13-puerta-determinista`.
Tests: `tests/test_auto_params_veto.py` (fallo no detectado en ejecución local —
el `.venv` de Python 3.14 no puede instalar las dependencias pinneadas; solo
`py_compile` verificado).

## Estado de la suite de tests (2026-08-31)

`pytest` en `backend-python/` tiene **21 fallos preexistentes** en `main`
(verificado con un worktree limpio en `5a4209a`, antes de cualquier cambio de
esa sesión). **No hay CI que corra tests**, así que nadie se entera.

> Actualización 2026-09-02: al corregir los 2 `TypeError` de
> `tests/test_indicators.py` (T5), el baseline bajó **19**, pero en `main` sigue
> siendo 21. Seguir comparando contra **21** mientras no se mergee la rama
> `feat/rentabilidad-t1-t5-pnl-20260902`.
>
> Con T2+T6 encima de la rama T1/T5 (`feat/t2-recenter-t6-metrics-20260902`) la
> suite es **61 passed / 19 failed** (19 preexistentes, sin regresiones nuevas;
> incluye los 6 tests nuevos de `test_recenter.py`).

Al validar cambios en este repo: comparar contra ese baseline de 21 fallos,
**no** esperar 0. La forma segura de medir el baseline es
`git worktree add <tmp> HEAD` — ⚠️ **no usar `git stash push -u`**: intenta
borrar `docs/n8n-templates/`, `tests/` y `thunder-tests/`, falla con
"Permission denied" y deja el estado a medias.

Entorno local: `pip install -r requirements.txt` falla en Windows por
`psycopg2-binary` (no hay `pg_config`). Instalar el resto de paquetes a mano;
los tests saltan Postgres igualmente.
