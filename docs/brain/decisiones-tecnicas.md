---
title: "Decisiones técnicas y alcance de la fase actual"
type: decision
app: trading-grid-bot
repo: TRADING
tags: [decisiones, ia, alcance]
related:
  - "[[_index]]"
  - "[[n8n-sync-y-gotchas]]"
updated: 2026-07-29
owner: dueño del repo
---

# Decisiones técnicas

## Proveedor de IA: Gemini (no OpenAI/Claude)

Workflow 1 usa HTTP Request directo a `generativelanguage.googleapis.com`
(no el nodo nativo `openAi` de n8n) con `responseSchema` para forzar salida
JSON estructurada. Modelo estable en uso: `models/gemini-2.5-flash`.

**Cuidado**: `GET /v1beta/models` puede listar un modelo (ej.
`gemini-2.0-flash`) aunque ya no esté disponible para `generateContent` — no
confiar solo en la presencia en el listado; si un modelo falla con "model
not found", volver a listar y elegir uno con `generateContent` en
`supportedGenerationMethods`.

Se loguea a Postgres (`public.metricas_personalizadas`) el consumo de
tokens de cada ejecución, incluyendo `thoughtsTokenCount` (tokens de
"thinking" de Gemini 2.5 — puede ser más de la mitad del costo total; no
capturarlo subestima el gasto real).

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

## Línea de trabajo abierta (2026-07-30): monitoreo/analítica antes de pasar a dinero real

El usuario sigue en testnet (`BINANCE_TESTNET_URL` en `config.py`) a
propósito — la prioridad inmediata NO es explorar las otras 4 estrategias
del documento raíz `Estrategias de Trading Automatizado con n8n y
Binance.md` (eso queda pendiente de decidir con su compañera), sino poder
**medir objetivamente si Grid Trading es rentable** para decidir con datos
cuándo pasar a dinero real. Ver [[analisis-bot-monitoreo]] para el detalle
completo y el estado de avance (evita repetir esta exploración en sesiones
futuras).
