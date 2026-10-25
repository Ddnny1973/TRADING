---
title: "Sincronización repo → n8n y gotchas de su API"
type: process
app: trading-grid-bot
repo: TRADING
tags: [n8n, ci-cd, api, powershell]
related:
  - "[[_index]]"
  - "[[infra-multi-servidor]]"
updated: 2026-10-25
owner: dueño del repo
---

# Sincronización repo → n8n

Fuente única de verdad de los workflows: carpeta [n8n-workflows/](../../n8n-workflows/)
en la raíz (no `docs/n8n-templates/`, que son plantillas legacy).

## Vía automática (pipeline)

[.github/workflows/n8n-sync.yml](../../.github/workflows/n8n-sync.yml) hace
`PUT /api/v1/workflows/{id}` a `https://n8n.gestorconsultoria.com.co` cuando
cambia algún `n8n-workflows/*.json` en `main`. IDs de workflow reales,
hardcodeados en el pipeline:

| Workflow | ID |
|---|---|
| workflow1-market-decision.json | `yggk1wajL1tsmABi` |
| workflow2-monitor.json | `96qAStQwfrHAVXRd` |
| workflow3-telegram-monitor.json | `zH79H6HyVleecAm7` |

El pipeline extrae con `jq` solo los campos que la API pública de n8n acepta:
`name`, `nodes`, `connections`, `settings.executionOrder` (el resto del
export completo, como `id`/`versionId`/`meta`/`tags`/`active`, es rechazado
con 400 "must NOT have additional properties").

## Vía manual (PowerShell) — gotchas ya resueltos

Si se necesita hacer el PUT a mano desde Windows (documentado también en
[n8n-workflows/README.md](../../n8n-workflows/README.md)):

1. **Leer el archivo con encoding explícito**: `Get-Content -Raw -Encoding UTF8`.
   PowerShell 5.1 no codifica confiablemente en UTF-8 por defecto cuando el
   JSON tiene emojis/tildes (mensajes de Telegram) — genera un
   `Content-Length` inconsistente con los bytes reales.
2. **Enviar como bytes, no como string**: `[System.Text.Encoding]::UTF8.GetBytes($body)`
   como `-Body`, con header `Content-Type: application/json; charset=utf-8`.
3. Sin esto, nginx (el proxy del bastión) devuelve **500 HTML genérico** en
   bodies grandes (>8-16KB, cuando tiene que bufferear a disco) — parece un
   problema del proxy pero **no lo es**: es el cliente PowerShell enviando
   bytes mal codificados. Confirmado con `curl` desde Linux (mismo archivo,
   directo a n8n y a través de nginx) → ambos dieron 400 normal de
   validación, nunca 500. Ver [[infra-multi-servidor]] para el detalle del
   vhost.
4. Si no se usa `-Encoding UTF8` en la lectura, el texto con tildes puede
   subir con mojibake (doble-codificación, ej. "ejecuciÃ³n").

## Restricciones de la instancia (Community Edition)

- No hay `$vars` (Settings → Variables es feature de pago). Todo debe usar
  `$env.*`, ver [[infra-multi-servidor]].
- Un solo webhook de Telegram por bot: por eso comandos como `/monitorear`
  no usan un 2do Telegram Trigger, sino **Execute Sub-workflow** desde el
  mismo Trigger del Workflow 1.

## Acceso de agentes por MCP (2026-10-03)

n8n expone un servidor MCP que permite a un agente **diagnosticar** WF1/WF2/WF3
sin entrar a la UI:

- **URL**: `https://n8n.gestorconsultoria.com.co/mcp-server/http` (HTTP
  streamable), cabecera `Authorization: Bearer <token>`.
- **Token**: la variable de entorno de usuario de Windows `N8N_API_KEY` (la
  misma que usan opencode y Gemini; no copiarla a ningún archivo). ⚠️ Es el
  token del **servidor MCP**: contra la API REST pública
  (`/api/v1/executions`) da **401**.
- **Habilitar por workflow**: cada workflow debe tener "Disponible en MCP"
  (tarjeta de la lista o ajustes del workflow). "Published" (activo) **no**
  basta: sin eso las herramientas devuelven *"Workflow is not available in MCP"*.
  WF1/WF2/WF3 ya lo tienen.
- **Registro en Claude Code** (una vez, a nivel de usuario; requiere el CLI
  `claude`, instalable con `npm install -g @anthropic-ai/claude-code`):

  ```
  claude mcp add --transport http --scope user n8n https://n8n.gestorconsultoria.com.co/mcp-server/http --header 'Authorization: Bearer ${N8N_API_KEY}'
  ```

  Comillas **simples**: así Claude Code expande `${N8N_API_KEY}` al arrancar.
  Con comillas dobles en bash la clave real queda escrita en `~/.claude.json`,
  y en PowerShell `${...}` se lee como variable de PowerShell (queda vacía).
  Verificar con `claude mcp list` y `/mcp` en una sesión nueva.
- **Herramientas de lectura útiles**: `search_workflows`, `get_workflow_details`
  (nodos y conexiones, para comparar con el JSON del repo),
  `search_workflow_executions` (últimas corridas y su estado) y
  `get_workflow_execution` con `includeData: true` (+ `nodeNames` y
  `truncateData` para no traerse todo) para ver el error de un nodo.
- **Escrituras** (`update_workflow`, `publish_workflow`, …) cambian producción en
  vivo: el repo es la fuente de verdad, así que tras cualquier cambio hecho en
  n8n hay que reflejarlo en `n8n-workflows/*.json` (si no, el siguiente sync
  lo revierte). Receta de comparación repo↔desplegado: comparar por nombre de
  nodo `type`, `typeVersion`, `parameters`, ids de credenciales y `connections`.

**Receta "el bot no crea grids"** (caso real 2026-10-03, ver
[[decisiones-tecnicas]]): `search_workflow_executions` de WF1 → si todas están
en `error` y duran 5–10 s, `get_workflow_execution` de la última con
`includeData: true` y leer `resultData.error` (nodo + mensaje). Un 410 en el
nodo del LLM = modelo retirado.

## MCP de consultas Postgres de solo lectura (2026-10-25)

Para que un agente lea bases Postgres sin túneles ni accesos directos, se
crearon dos workflows en n8n (proyecto personal del dueño, **no** viven en
`n8n-workflows/` ni los sincroniza CI):

- **`DB Query MCP (solo lectura)`** (`NQ5ZhRQN1ApFBUTs`): nodo MCP Server Trigger
  con path `db-query`, auth **Bearer** (credencial propia `DB Query MCP - Bearer`)
  y dos herramientas: `describe_db(db)` y `query_db(db, sql, limit)`.
- **`DB Query Guard (solo lectura)`** (`VLrYCl8fkTEy6VWu`): sub-workflow que
  valida (alias permitido; una sola sentencia `SELECT`/`WITH`/`EXPLAIN`; lista
  negra de palabras como `insert`, `copy`, `into`, `pg_read_file`, `dblink`;
  `LIMIT` ≤ 500; respuesta ≤ ~150 KB), enruta por alias con un Switch a un nodo
  Postgres por base y formatea la salida.

Alias: `trading` (`postgres-trading`), `n8n_metrics` (Postgres de n8n),
`aserprem` (solo las tablas autorizadas). **La barrera real es el rol
`claude_ro` de cada base** (`default_transaction_read_only = on`,
`statement_timeout = 30s`, solo `SELECT`). El filtro del guard es una defensa
extra. Agregar una base = alias en "Validar consulta" + rama en "Enrutar por
base" + nodo Postgres con su credencial `claude_ro`. La auditoría es el
historial de ejecuciones del guard (SQL + alias + resultado).

⚠️ **Gotcha de `create_workflow_from_code`:** n8n **auto-asigna credenciales
existentes del mismo tipo** cuando el código usa `newCredential(...)`. Al crear
estos workflows asignó `Postgres aserprem` a los 3 nodos PG y `Google Workspace
Gateway MCP` al trigger. Siempre revisar `autoAssignedCredentials` en la
respuesta y reemplazarlas a mano antes de publicar.

**Estado (2026-10-25): operativo y verificado.** Credenciales asignadas en el
guard: `Postgres trading` (host `10.0.0.6`, puerto `9043`, base
`trading_history`, user `trading_user` — **no** `db`, que es el Postgres de
n8n), `Postgres n8n` y `Postgres aserprem`. Pruebas: `describe_db("trading")` →
5 tablas; `DELETE` y `SELECT 1; DROP ...` rechazados por el guard; sin token →
403. ⚠️ Hoy las 3 credenciales son de usuarios con permiso de escritura: el
guard es la única barrera hasta migrar a `claude_ro`. El transporte es MCP
streamable HTTP con sesión (`initialize` → header `mcp-session-id` →
`notifications/initialized` → `tools/call`); sin sesión responde "Server not
initialized".

Registro en Claude Code (token en la variable de usuario de Windows
`N8N_DB_MCP_TOKEN`, nunca en archivos):
`claude mcp add --scope user --transport http n8n-db https://n8n.gestorconsultoria.com.co/mcp/db-query --header 'Authorization: Bearer ${N8N_DB_MCP_TOKEN}'` (ya registrado a nivel usuario). Si sale `403 Authorization data is wrong`, la app se abrió antes de crear la variable con `setx`: cerrarla del todo (también desde la bandeja) y abrirla de nuevo.

## CI/CD y `docs/`

[.github/workflows/deploy.yml](../../.github/workflows/deploy.yml) ya
excluye `docs/**` y `*.md` vía `paths-ignore` — cambios en `docs/brain/` (o
cualquier `.md`) **no** disparan un deploy del backend. No fue necesario
modificar el pipeline para esto.
