---
title: "Hub — Cerebro digital de TRADING"
type: hub
app: trading-grid-bot
repo: TRADING
tags: [hub, grid-trading, n8n, binance]
related:
  - "[[infra-multi-servidor]]"
  - "[[n8n-sync-y-gotchas]]"
  - "[[decisiones-tecnicas]]"
updated: 2026-07-29
owner: dueño del repo
---

# TRADING — Cerebro digital

## Qué es este repo

Sistema de **grid trading autónomo para Binance Futures**, compuesto por:

- **Backend FastAPI** ([backend-python/](../../backend-python/)) — único componente de
  código de aplicación en este repo. Expone la API de grids (crear, refrescar,
  cerrar por SL/TP/expiración, calcular PnL) y calcula parámetros de mercado
  (ATR, tamaño de posición) vía `app/auto_params.py` y `app/services/`.
- **Workflows n8n** ([n8n-workflows/](../../n8n-workflows/)) — orquestación externa:
  Workflow 1 (decisión de mercado con Gemini), Workflow 2 (monitor cada 15 min),
  Workflow 3 (Telegram). Son la fuente de verdad de los `.json`; el backend NO
  tiene scheduler interno ni envía webhooks salientes — todo el polling lo
  dispara n8n.
- **Docs de producto/operación** ya extensamente cubiertos en [docs/00-START/](../00-START/)
  hasta [docs/90-APPENDICES/](../90-APPENDICES/) (estructura numerada, ver
  [docs/00-START/02-tabla-contenidos.md](../00-START/02-tabla-contenidos.md)).

Este `docs/brain/` **no duplica** esa documentación de producto. Complementa
con conocimiento tácito de infraestructura/operación que hoy solo vivía en
memoria de sesiones de IA y no estaba escrito en ningún archivo del repo.

## Mapa de contenido

- [[infra-multi-servidor]] — topología real de despliegue (2 servidores físicos
  distintos + bastión nginx), por qué nombres de red iguales en compose NO
  implican red compartida, y el fix de conectividad usado.
- [[n8n-sync-y-gotchas]] — cómo se sincronizan los `.json` de `n8n-workflows/`
  hacia la instancia real de n8n (pipeline automático + método manual), y
  gotchas de la API de n8n (payload aceptado, encoding UTF-8 en PowerShell,
  Community Edition sin `$vars`).
- [[decisiones-tecnicas]] — decisiones de producto/arquitectura tomadas y su
  razón (proveedor de IA, límites de seguridad, alcance de la fase actual).
- [[analisis-bot-monitoreo]] — línea de trabajo en curso: diseño de tablas
  de monitoreo en Postgres (`grid_cycles`, `pnl_snapshots`) para poder medir
  rentabilidad real del bot antes de decidir el paso a dinero real. Ver
  también `docs/analisis-bot/` (carpeta de análisis evolutivos, distinta de
  `docs/brain/` y de `Analisis Propios/`).

## Puntos de entrada existentes (no duplicar, solo enlazar)

- [README.md](../../README.md) — índice maestro del repo.
- [docs/00-START/01-inicio-rapido.md](../00-START/01-inicio-rapido.md) — setup en 30 min.
- [docs/10-ARQUITECTURA/01-componentes.md](../10-ARQUITECTURA/01-componentes.md) — arquitectura lógica del sistema.
- [docs/70-DEVELOPMENT/01-code-structure.md](../70-DEVELOPMENT/01-code-structure.md) — anatomía del código backend.
- [n8n-workflows/README.md](../../n8n-workflows/README.md) — procedimiento de sync repo→n8n.

## Aplicación de una sola pieza

Este repo es autocontenido (no hay repos hermanos en el workspace). La
infraestructura de n8n corre en servidores separados fuera de este repo — ver
[[infra-multi-servidor]] para los detalles de esa topología.
