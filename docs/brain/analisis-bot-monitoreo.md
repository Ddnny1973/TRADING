---
title: "Análisis y monitoreo del bot — línea de trabajo en curso"
type: nota
app: trading-grid-bot
repo: TRADING
tags: [monitoreo, analitica, postgres, grid-trading]
related:
  - "[[_index]]"
  - "[[decisiones-tecnicas]]"
updated: 2026-08-31
owner: dueño del repo
---

# Análisis y monitoreo del bot

## Contexto

El usuario pidió (2026-07-30) revisar el documento raíz `Estrategias de
Trading Automatizado con n8n y Binance.md` y comparar sus 5 estrategias
propuestas contra lo realmente implementado. Conclusión: **solo Grid
Trading está implementado**; las otras 4 (Breakout NY, Rango Asiático, HMM,
EMA Cross) quedaron pendientes de decisión con la compañera del usuario —
no asumir que hay que implementarlas, es una decisión de producto abierta.

De ahí se derivó una segunda necesidad, más urgente para el usuario: **poder
medir si el bot es rentable** (sigue en testnet, dinero ficticio) para
decidir con datos cuándo pasar a dinero real, no por intuición.

## Dónde vive el análisis detallado

`docs/analisis-bot/01-estado-actual-vs-futuro.md` — documento vivo con:
- Tabla estrategias documento vs. código real.
- Tabla directrices Grid Trading (Decimal, kill-switch, sync horaria, etc.)
  vs. lo implementado.
- Diseño de las tablas de monitoreo en Postgres.
- Métricas objetivo y criterio borrador para pasar a dinero real.
- Checklist de próximos pasos.

`docs/analisis-bot/` es una carpeta nueva para este tipo de análisis
evolutivo (iterativo, con estado "en progreso"). Distinta de `docs/brain/`
(conocimiento tácito ya estable/verificado) y de `Analisis Propios/` (notas
personales del usuario, no atadas a sesiones con IA).

## Hallazgo clave de infraestructura de datos

Hay **tres bases Postgres/SQLite distintas**, fácil de confundir:
1. SQLite local del contenedor backend (`grid_trading.db`) — estado
   operativo en tiempo real de grids/órdenes (`grids`, `grid_orders`,
   `grid_closures`).
2. Postgres del backend (`postgres-trading`, puerto 9043) — pensado para
   histórico/analítica. Antes de este análisis solo tenía
   `historical_grid_logs` (PnL final por grid, sin fees ni ciclos).
3. Postgres **de n8n** (puerto 9032, otra instancia física) — tiene
   `public.metricas_personalizadas`, que solo mide tokens de Gemini
   gastados por ejecución. NO tiene nada de performance del bot. Fácil de
   confundir con la #2 porque ambas son "Postgres del proyecto".

## Estado de implementación del monitoreo (actualizar aquí a medida que avance)

- ✅ 2026-07-30: Modelos SQLAlchemy `GridCycle` y `PnlSnapshot` añadidos a
  `backend-python/app/database/models.py`.
- ✅ 2026-07-30: Script manual
  `backend-python/app/database/migration_002_monitoring_tables.sql` creado
  y YA EJECUTADO por el usuario contra `postgres-trading` (confirmado:
  tablas `grid_cycles` y `pnl_snapshots` existen con todas sus columnas).
  Copilot no tiene acceso a la base de datos ni a ninguna herramienta de
  conexión SQL en este entorno — el usuario corre los scripts.
- ✅ 2026-07-30: `grid_service.py` ya escribe en ambas tablas — nuevos
  métodos `_record_completed_cycles()` y `_write_pnl_snapshot()`, enganchados
  al final de `refresh_order_status()` (ruta de reconciliación limpia).
  Nuevas columnas en SQLite `grid_orders`: `source_order_id` (enlaza una
  orden de reposición con la que la originó) y `cycle_logged` (evita
  duplicar el registro del ciclo en Postgres).
- ⚠️ PENDIENTE: validar en vivo (Binance testnet) que un ciclo completo
  BUY→replenish SELL→FILLED genera la fila esperada en `grid_cycles`.
  `pytest` local no se pudo correr (falta `sqlalchemy` en el venv local) —
  validar en Docker/CI antes de desplegar a los servidores reales.
- ❌ PENDIENTE (fase 2, no diseñado en detalle aún): tablas `bot_executions`
  (uptime/errores de Workflow 1 y 2) y `bot_health_events` (incidentes de
  reconciliación, auto-cancelaciones). Ver sección 4 de
  `docs/analisis-bot/01-estado-actual-vs-futuro.md`.
- ✅ 2026-08-02 → 2026-08-10: dashboard de performance construido sobre estas
  tablas (`grid_cycles`/`pnl_snapshots`). Primero como script offline
  (`scripts/dashboard/export_data.py`), luego servido en vivo por el propio
  backend (`GET /dashboard`, `GET /api/v1/dashboard/data`,
  `backend-python/app/services/dashboard_data.py`). Esta es la primera
  herramienta real para visualizar si el bot es rentable sin consultar SQL
  a mano. Ver [[decisiones-tecnicas]] para el detalle de commits.
- ✅ 2026-08-14: WF3 ganó el comando Telegram `/estado` (resumen de grids,
  PnL y actividad) como atajo al dashboard desde el celular.
- ✅ 2026-08-16: Diagnóstico con datos reales (Postgres + log de ejecuciones
  de n8n + órdenes de Binance testnet). Hallazgos:
  - 2 grids RUNNING (BTC `b13d5f9a-…`, ETH `7da515ef-…`), **creados el
    14-08 (14:41/17:01 UTC) → ~1.7 días de vida, NO 7 días**, y casi todo
    ese tiempo corrió con el bug del 504/400 activo (el fix entró el 16-08).
    Datos reales de SQLite: levels BTC 8 / ETH 5; step real 0.65%/0.66%
    (≈3.3× el mínimo 0.2% del validador); precios de hoy DENTRO del rango
    (BTC 63,036 en 61,347.25..64,146.15; ETH 1,881 en 1,860.19..1,909.59)
    → **refutadas** las hipótesis de rango angosto y de precio fuera del
    rango. Aun así **0 ciclos** — `grid_cycles` solo tiene el grid histórico
    `9c3f822b`: 8 ciclos, +3.64 neto, pero cerró en +0.18 por MAX_POSITION
    (la posición neta devolvió ~3.46).
  - Unrealized negativo casi permanente en `pnl_snapshots` (BTC 87%, ETH
    96%) pero **en centavos** (−0.04/−0.06) → estructural, no sangrado de
    cuenta; `total_pnl == unrealized_pnl` (realized=0, confirma 0 ciclos).
  - `launch:true` en el 100% de las decisiones de WF1 (la IA nunca vetó).
  - Errores post-migración del modelo = **504 Gateway Timeout de NVIDIA
    NIM** (no "model not found"): explotaban al diagnosticar el 400 esperado
    "Max concurrent grids". Fix aplicado en WF1 (el 400 se trata como
    informativo y se salta el Diagnose) — ver [[decisiones-tecnicas]].

## Diagnóstico de rentabilidad con ~2 meses de datos (2026-08-31)

Primer análisis con volumen de datos suficiente (30 ciclos, 43 grids
cerrados). **Resultado real del bot: ≈ −8 USD acumulados**, no los +12,86
que muestra la tarjeta "PnL neto (ciclos)" ni los +4,88 de "PnL combinado".

Tres causas raíz encadenadas, todas en el backend (no en n8n):

1. **La reposición está bloqueada casi siempre.** El guard de modo NEUTRAL
   en `replenish_filled_orders()` usa `tolerance = qty_per_order * 0.05`:
   tras el primer fill la posición vale `1.0 × qty`, 20× la tolerancia →
   deja de reponer. Explica los 8/20 grids que cerraron con **0 ciclos**.
2. **Los cierres cristalizan la pérdida en la excursión adversa máxima.**
   `cancel_grid()` siempre hace market-close del inventario, y los dos
   triggers dominantes (`MAX_POSITION` 7/20, `OUT_OF_RANGE` 7/20) disparan
   justo cuando ese inventario está bajo el agua. El "closure drag"
   (PnL final − PnL de ciclos) suma **−15,43 USD** en 8 grids.
3. **No hay stop-loss real.** `auto_params` no deriva `stop_loss`/
   `take_profit` y WF1 los envía en `null` → 0 cierres por SL/TP en toda la
   historia. `MAX_POSITION` (3 × qty) actúa como stop-loss de facto, pero
   dispara por inventario, no por pérdida en USD.

Otros hallazgos: el **win rate de 100 % es un artefacto** (la reposición se
coloca siempre en el nivel adyacente favorable, así que todo ciclo
registrado es positivo por construcción); y `combined_pnl` del dashboard
**dobla el conteo** (`grid_closures.total_pnl` ya incluye lo realizado por
los ciclos).

➡️ **Plan accionable completo** (18 tareas priorizadas, con archivos, líneas,
criterios de aceptación y orden de PRs):
`docs/analisis-bot/03-plan-mejoras-rentabilidad.md`. Leerlo antes de
proponer cualquier cambio de estrategia o de cierres.

### Correcciones ya aplicadas (2026-08-31, rama `fix/rentabilidad-fase1`)

- ✅ **T1**: la tolerancia del guard NEUTRAL pasa de `0.05 × qty_per_order` a
  `MAX_NET_POSITION_LEVELS × qty_per_order × REPLENISH_POSITION_TOLERANCE_RATIO`
  (0.80). El grid ya puede acumular inventario y colocar la pata que cierra
  el ciclo; solo se pausa cerca del límite duro.
- ✅ **T4**: `derive_stop_loss_take_profit()` en `auto_params.py` traduce
  `GRID_STOP_LOSS_PCT_OF_BALANCE` (1 %) y `GRID_TAKE_PROFIT_PCT_OF_BALANCE`
  (3 %) a umbrales en USDT. Se exponen en `/auto-params`
  (`AutoParamsParamsV2` tuvo que declararlos o FastAPI los filtraba) y WF1
  los propaga al `POST /api/v1/grids` en vez de mandar `null`.
- ✅ **T7**: `dashboard_data.py` y `scripts/dashboard/export_data.py` ya no
  suman `grid_cycles` con `historical_grid_logs`. Nuevo `strategy_pnl =
  cierres + PnL vivo de grids abiertos`; `combined_pnl` queda como alias
  retrocompatible para el template y WF3.
- ⚠️ La suite `pytest` de `backend-python/` tenía **21 fallos preexistentes**
  en `main` antes de estos cambios (comprobado con un worktree limpio en
  `5a4209a`). No hay CI que los detecte — ver T18 del plan.
- ✅ **T3**: `MAX_POSITION` deja de ser un gatillo de cierre. El cap de
  inventario ahora escala con `levels` (`MAX_NET_POSITION_RATIO = 0.6`, con
  `MAX_NET_POSITION_LEVELS` como piso); superarlo **pausa la reposición solo
  del lado que acumula** (la pata que descarga inventario se sigue colocando),
  y solo se cierra al superar `MAX_POSITION_HARD_MULTIPLE = 2.0×` el cap. El
  freno en dinero pasa a ser `stop_loss` (T4).
- ✅ **T19**: `MAX_CONCURRENT_GRIDS` 2 → 4.

## Análisis estratégico de portafolio (2026-08-31)

Pregunta del usuario: qué estrategias implementar para que el bot sea rentable
y si se pueden correr varias a la vez. Respuesta completa en
`docs/analisis-bot/04-estrategia-y-portafolio.md`. Conclusiones clave:

- **El grid es una estrategia short-vol / short-gamma** (perfil de pagos de
  vender opciones). Los datos lo confirman: win rate 100 % estructural en
  ciclos y pérdidas concentradas en los cierres. Su complemento correcto NO es
  otra estrategia direccional, sino una **negativamente correlacionada**
  (breakout), o simplemente apagar el grid en tendencia.
- **Añadir estrategias no arregla la rentabilidad.** El cuello de botella es
  $N_{ciclos}$ (0,5/día) y el destrozo en la salida, no la falta de estrategias.
- **Descartadas hasta tener arnés de backtesting**: EMA Cross (sangra en
  lateral, suma varianza sin descorrelacionar) y HMM (imán de sobreajuste).
- **Idea de mayor valor (T21)**: convertir el evento `OUT_OF_RANGE` en la señal
  de breakout — el stop del grid pasa a ser la entrada de la tendencia. Solo
  después de T2 y de 4+ semanas con datos.
- **Una estrategia por símbolo, regla dura**: Binance netea posiciones por
  símbolo en one-way mode, y `cancel_grid()` hace `cancel_all_open_orders(symbol)`
  — dos estrategias en el mismo par se cancelarían las órdenes entre sí.
- **Hallazgo sin verificar**: el **funding no se contabiliza en ningún cálculo
  de PnL** (`calculate_grid_pnl` solo descuenta fees de trading). En una
  estrategia que gana ~0,43 USD por ciclo puede ser una fuga material invisible.
  Verificar con `GET /fapi/v1/income?incomeType=FUNDING_FEE` (T22).

## Visión a futuro: orquestador multi-estrategia con IA (2026-07-30)

El usuario planteó el "sueño" de un agente que revise indicadores y decida
QUÉ estrategia usar (no solo lanzar/no lanzar Grid) — ver
`docs/analisis-bot/02-vision-orquestador-multiestrategia.md` para el
detalle completo (patrón propuesto extendiendo Workflow 1 + Gemini, qué NO
debe hacer el LLM — calcular indicadores o colocar órdenes directamente —,
y las 3 opciones para tener indicadores NRT: acortar cron, triggers por
horario de sesión, o websocket+Redis). Es un borrador/brainstorm, **no una
decisión tomada** — depende de si se implementan más estrategias (pendiente
con la compañera del usuario).

## Siguiente sesión: retomar aquí, no repetir la exploración

Si se retoma este tema en otra sesión, leer primero
`docs/analisis-bot/01-estado-actual-vs-futuro.md` y
`docs/analisis-bot/02-vision-orquestador-multiestrategia.md` completos
(tienen todas las tablas y el razonamiento) y esta nota, antes de volver a
analizar el documento raíz o el código del backend desde cero.

## Fix OUT_OF_RANGE y gracia de 30 min (2026-08-26)

**Problema descubierto**: los grids se cancelaban por `OUT_OF_RANGE` en el
primer ciclo de monitoreo (5 min después de creación). Con bounds ATR-based
(multiplier 1.5-3.5x), un movimiento mínimo de precio provocaba cierre
inmediato sin que el grid tuviera oportunidad de llenar órdenes.

**Causa raíz**: `check_close` no tenía período de gracia — evaluaba
`OUT_OF_RANGE` inmediatamente al primer ciclo. Ver `decisiones-tecnicas.md`
para el fix (`CHECK_CLOSE_GRACE_MINUTES = 30`).

## Dashboard: sección Operaciones Activas (2026-08-26)

Se agregó una sección al dashboard que consulta SQLite en tiempo real para
mostrar grids RUNNING con: símbolo, leverage, modo, rango, niveles, órdenes
(abiertas/fills/canceladas), PnL realizado/no realizado, timestamps.

**Bug corregido**: `current_map` se definía después del bloque que la usaba
(variable unbound), causando fallo silencioso. Fix en commit `8d47a3b`.

## Auto-close de posiciones residuales (2026-08-26)

`create_grid` ahora cierra automáticamente cualquier posición residual antes
de crear un NEUTRAL grid (común después de cancelar un grid con redondeo).
Ver `decisiones-tecnicas.md`.
