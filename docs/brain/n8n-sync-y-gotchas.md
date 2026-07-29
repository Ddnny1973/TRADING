---
title: "Sincronización repo → n8n y gotchas de su API"
type: process
app: trading-grid-bot
repo: TRADING
tags: [n8n, ci-cd, api, powershell]
related:
  - "[[_index]]"
  - "[[infra-multi-servidor]]"
updated: 2026-07-29
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

## CI/CD y `docs/`

[.github/workflows/deploy.yml](../../.github/workflows/deploy.yml) ya
excluye `docs/**` y `*.md` vía `paths-ignore` — cambios en `docs/brain/` (o
cualquier `.md`) **no** disparan un deploy del backend. No fue necesario
modificar el pipeline para esto.
