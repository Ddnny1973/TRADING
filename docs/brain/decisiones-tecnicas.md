---
title: "Decisiones técnicas y alcance de la fase actual"
type: decision
app: trading-grid-bot
repo: TRADING
tags: [decisiones, ia, alcance]
related:
  - "[[_index]]"
  - "[[n8n-sync-y-gotchas]]"
updated: 2026-08-31
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

## Estado de la suite de tests (2026-08-31)

`pytest` en `backend-python/` tiene **21 fallos preexistentes** en `main`
(verificado con un worktree limpio en `5a4209a`, antes de cualquier cambio de
esa sesión). **No hay CI que corra tests**, así que nadie se entera.

Al validar cambios en este repo: comparar contra ese baseline de 21 fallos,
**no** esperar 0. La forma segura de medir el baseline es
`git worktree add <tmp> HEAD` — ⚠️ **no usar `git stash push -u`**: intenta
borrar `docs/n8n-templates/`, `tests/` y `thunder-tests/`, falla con
"Permission denied" y deja el estado a medias.

Entorno local: `pip install -r requirements.txt` falla en Windows por
`psycopg2-binary` (no hay `pg_config`). Instalar el resto de paquetes a mano;
los tests saltan Postgres igualmente.
