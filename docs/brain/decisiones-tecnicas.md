---
title: "Decisiones técnicas y alcance de la fase actual"
type: decision
app: trading-grid-bot
repo: TRADING
tags: [decisiones, ia, alcance]
related:
  - "[[_index]]"
  - "[[n8n-sync-y-gotchas]]"
updated: 2026-08-16
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

## Alcance de la fase actual

Objetivo declarado por el usuario: llegar a un **deployment funcional de los
workflows n8n**, sin optimizar todavía la estrategia de trading/rentabilidad
(esa optimización es una fase posterior). No inferir que falta trabajo de
"mejora de estrategia" como pendiente urgente — es intencional en esta fase.

## Guardas de negocio ya implementadas en el backend

- Solo **1 grid RUNNING por símbolo** (guardia en `POST /api/v1/grids`,
  responde 400 "already exists" — no es un error real, n8n debe interpretarlo
  como "ya hay un grid activo").
- `place_batch_orders()` (en
  [backend-python/app/services/binance_client.py](../../backend-python/app/services/binance_client.py))
  reintenta por **ítem** (no por batch completo) ante respuestas ambiguas de
  Binance (código -1007/-1021 dentro de un HTTP 200), confirmando vía
  `_get_order_by_client_id` antes de reencolar — evita duplicar órdenes ya
  colocadas exitosamente.

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
