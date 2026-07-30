---
title: "Análisis 01 — Estado actual vs. futuro esperado del bot (Grid Trading)"
type: analisis
status: en progreso
started: 2026-07-30
related_brain: ["../brain/decisiones-tecnicas.md", "../brain/_index.md"]
---

# Análisis 01 — Estado actual vs. futuro esperado del bot

Este documento consolida el análisis iniciado el 2026-07-30 a partir del
documento raíz [`Estrategias de Trading Automatizado con n8n y Binance.md`](../../Estrategias%20de%20Trading%20Automatizado%20con%20n8n%20y%20Binance.md).
Objetivo: entender qué tan lejos está el bot de "mostrar resultados"
confiables, y qué falta para decidir con datos (no con intuición) el paso a
dinero real.

Carpeta `docs/analisis-bot/`: espacio para este tipo de análisis evolutivo
(comparaciones documento-vs-código, diseño de monitoreo, criterios de
go/no-go a producción). Distinto de `docs/brain/` (conocimiento tácito ya
verificado y estable) y de `Analisis Propios/` (notas personales del dueño
del repo, no necesariamente atadas a una sesión de trabajo con IA).

## 1. Estrategias del documento vs. implementación real

| # | Estrategia (documento) | Estado real |
|---|---|---|
| 1 | Grid Trading | ✅ Implementada y en producción (testnet). Única estrategia con código real. |
| 2 | Breakout primera vela (NY) | ❌ No implementada. |
| 3 | Ruptura Rango Asiático | ❌ No implementada. |
| 4 | Optimización con HMM (regímenes) | ❌ No implementada (Gemini en Workflow 1 decide lanzar o no, pero es un prompt, no un HMM). |
| 5 | EMA Cross | ❌ No implementada. |

Decisión pendiente con la compañera: si se explora alguna de las 4 restantes
o se sigue profundizando solo en Grid Trading.

## 2. Grid Trading: directrices del documento vs. código real

| Directriz | Estado |
|---|---|
| Motor de grid propio (Binance no tiene endpoint nativo) | ✅ `grid_engine.py` + `grid_service.py`. |
| Persistir órdenes en SQLite | ✅ `database/connection.py` (WAL mode). |
| Kill-switch por caída de balance global | ⚠️ Parcial — solo SL/TP por grid individual y `MAX_CONCURRENT_GRIDS`, no hay corte por % de balance total de cuenta. |
| Decimal obligatorio, prohibido `round()` | ✅ Confirmado, incluye fix de truncamiento en `place_batch_orders`. |
| Sync de reloj con `/fapi/v1/time` | ✅ Al arranque (`binance_time.py`). Pendiente confirmar si se re-sincroniza durante la vida del proceso. |
| Credenciales solo por `.env` | ✅ `pydantic_settings`, n8n solo usa `$env.BACKEND_URL`. |
| Reintentos con backoff / manejo 429 | ✅ Reforzado tras el bug real de `-1007`/`-1021`. |
| Persistencia híbrida SQLite (real time) + PostgreSQL (histórico) | ⚠️ SQLite ✅. PostgreSQL existía muy delgado (`historical_grid_logs`: solo PnL final). Ver sección 3. |

Funcionalidad del código que el documento no contemplaba: auto-selección de
par (`pair_selector.py`), derivación automática de leverage/levels/risk_pct
por fees (`auto_params.py`), endpoint `/auto-params`.

## 3. Gap crítico: no había forma de medir eficiencia real

Antes de este análisis:
- `BINANCE_TESTNET_URL` sigue siendo el default en `config.py` — todo lo
  validado hasta ahora es con dinero ficticio.
- `historical_grid_logs` (Postgres) solo registra `total_pnl` final por
  grid, sin fees desglosados, sin # de ciclos, sin serie de tiempo.
- `metricas_personalizadas` (otra base — el Postgres de **n8n**, no el del
  backend) solo mide tokens de Gemini gastados, no performance del bot.
- No existía persistencia de ejecuciones de workflows (éxito/fallo/uptime)
  ni de incidentes de reconciliación (`refresh_status`, auto-cancelaciones).

## 4. Diseño de monitoreo propuesto (Postgres del backend)

Prioridad acordada: empezar por `grid_cycles` + `pnl_snapshots` (sin esto no
hay forma de medir nada). Quedan pendientes para una siguiente iteración:
`bot_executions` (uptime/errores de workflows n8n) y `bot_health_events`
(incidentes de reconciliación).

### 4.1 `grid_cycles` — unidad real de "ganó o no ganó"
Un ciclo = una orden BUY llenada + su réplenish SELL llenado (o viceversa).
Columnas: `grid_id, symbol, cycle_number, buy_order_id, sell_order_id,
buy_price, sell_price, quantity, fee_paid, gross_pnl, net_pnl,
completed_at`.

### 4.2 `pnl_snapshots` — curva de equity en el tiempo
Un registro por cada `refresh` de Workflow 2 (~cada 15 min) en vez de
descartar el cálculo de `get_grid_pnl` como hoy. Columnas: `grid_id, symbol,
taken_at, realized_pnl, unrealized_pnl, total_pnl, account_balance,
open_orders_count`.

**Estado de implementación (2026-07-30):**
- ✅ Modelos SQLAlchemy añadidos en
  [`backend-python/app/database/models.py`](../../backend-python/app/database/models.py)
  (`GridCycle`, `PnlSnapshot`).
- ✅ Script SQL manual para crear las tablas ya, sin esperar redeploy:
  [`backend-python/app/database/migration_002_monitoring_tables.sql`](../../backend-python/app/database/migration_002_monitoring_tables.sql)
  (el usuario lo corre directamente contra `postgres-trading`; Copilot no
  tiene acceso a la base de datos).
- ❌ PENDIENTE: el código de `grid_service.py` todavía NO escribe en estas
  tablas — los modelos/tablas son solo el esqueleto. Falta:
  1. En `replenish_filled_orders()` (o donde se detecta el fill opuesto que
     cierra un ciclo): insertar una fila en `grid_cycles`.
  2. En `refresh_order_status()` / el endpoint `/refresh`: insertar una fila
     en `pnl_snapshots` con el resultado de `get_grid_pnl`.
  - También sigue pendiente correr el `Base.metadata.create_all()` (o el
    `.sql`) contra la base real, y decidir si `init_postgres_tables()`
    (automático al boot) es suficiente o si se prefiere solo el script manual.

## 5. Métricas objetivo para responder "¿es rentable el bot?"

- Net PnL acumulado (ciclos cerrados + no realizado del grid abierto).
- Win rate de ciclos (% con `net_pnl > 0`).
- Fees como % de ganancia bruta (valida si `MIN_STEP_FEE_MULTIPLE` está bien calibrado).
- Ciclos completados por día / por grid (velocidad de rotación).
- Max drawdown (peor caída de `pnl_snapshots.total_pnl` desde su pico).
- Uptime real del monitor (pendiente de `bot_executions`, fase 2).
- Tasa de incidentes/auto-cancelaciones (pendiente de `bot_health_events`, fase 2).

## 6. Criterio propuesto para pasar a dinero real (borrador, a validar)

- Net PnL positivo sostenido tras fees por un período mínimo (ej. 2-4 semanas).
- Win rate y fees% estables en ese período (no un pico afortunado aislado).
- Cero (o muy pocas, explicadas) auto-cancelaciones por fallas de reconciliación.
- Drawdown máximo observado dentro de lo asumible con capital real.

## 7. Próximos pasos

1. Usuario corre `migration_002_monitoring_tables.sql` contra `postgres-trading`.
2. Copilot implementa la escritura real a `grid_cycles` y `pnl_snapshots` en `grid_service.py`.
3. Definir con la compañera si se retoma alguna estrategia adicional del documento original (sección 1).
4. Diseñar `bot_executions` y `bot_health_events` (fase 2 de monitoreo).
5. Una vez haya datos reales de varias semanas, evaluar el criterio de la sección 6.
