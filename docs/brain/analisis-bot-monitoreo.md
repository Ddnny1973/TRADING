---
title: "Análisis y monitoreo del bot — línea de trabajo en curso"
type: nota
app: trading-grid-bot
repo: TRADING
tags: [monitoreo, analitica, postgres, grid-trading]
related:
  - "[[_index]]"
  - "[[decisiones-tecnicas]]"
updated: 2026-08-16
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
  - 2 grids RUNNING (BTC `b13d5f9a`, ETH `7da515ef`) con **0 ciclos en ~7
    días** — `grid_cycles` solo tiene el grid histórico `9c3f822b`: 8 ciclos,
    +3.64 neto, pero cerró en +0.18 por MAX_POSITION (la posición neta
    devolvió ~3.46).
  - Unrealized negativo casi permanente en `pnl_snapshots` (BTC 87%, ETH
    96%) pero **en centavos** (−0.04/−0.06) → estructural, no sangrado de
    cuenta; `total_pnl == unrealized_pnl` (realized=0, confirma 0 ciclos).
  - `launch:true` en el 100% de las decisiones de WF1 (la IA nunca vetó).
  - Errores post-migración del modelo = **504 Gateway Timeout de NVIDIA
    NIM** (no "model not found"): explotaban al diagnosticar el 400 esperado
    "Max concurrent grids". Fix aplicado en WF1 (el 400 se trata como
    informativo y se salta el Diagnose) — ver [[decisiones-tecnicas]].

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
