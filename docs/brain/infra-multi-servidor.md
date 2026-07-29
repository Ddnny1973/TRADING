---
title: "Infraestructura multi-servidor (n8n vs backend)"
type: infra
app: trading-grid-bot
repo: TRADING
tags: [infra, deploy, nginx, docker, red]
related:
  - "[[_index]]"
  - "[[n8n-sync-y-gotchas]]"
updated: 2026-07-29
owner: dueño del repo
---

# Infraestructura multi-servidor

## Topología real (3 servidores físicos Hetzner)

| Servidor | Rol | IP privada | Contenedor clave | Puerto publicado |
|---|---|---|---|---|
| **New-01** (Hetzner fsn1) | Backend trading | `10.0.0.4` | `trading-backend` (imagen `43-backend-python`, carpeta compose `43`) | `8043 -> 8000` |
| **New-02** (Hetzner hel1) | n8n | `10.0.0.5` | `32-n8n-1` (carpeta compose `32`, sin `container_name`) | `8032 -> 5678` |
| **Bastión** | Proxy inverso | — | nginx directo en el host (no contenedor), hostname `Bastion-151431447-centos-4gb-hel1-1` | 443 (público, `n8n.gestorconsultoria.com.co`) |

`docker-compose.yml` de este repo (New-01) despliega también `postgres-trading`
(9043) y `redis-trading`, en la red `infra_shared`. El compose de n8n
(New-02, fuera de este repo) declara una red con el **mismo nombre**
`infra_shared` pero es una red bridge local distinta (NetworkID distinto).

## Lección clave: nombres de red iguales ≠ red compartida

Una red bridge de Docker nunca cruza hosts físicos. Que dos `docker-compose.yml`
en servidores distintos declaren una red llamada igual (`infra_shared`) es
coincidencia de nombres, no conectividad real. `docker exec n8n wget
http://trading-backend:8000` falla con `bad address` (fallo de DNS) porque
los contenedores viven en universos de red Docker separados.

**Fix**: comunicación entre stacks de compose en servidores distintos siempre
vía **IP privada del host + puerto publicado**, nunca por nombre de
contenedor/DNS interno de Docker:

```
BACKEND_URL=http://10.0.0.4:8043
```

Confirmado funcionando: `docker compose exec n8n wget -qO- http://10.0.0.4:8043/health` → 200 healthy.
(New-01 y New-02 están en la misma red privada Hetzner 10.0.0.x.)

## n8n bloquea `$env` por defecto

n8n rechaza el acceso a variables de entorno en expresiones ("access to env
vars denied") salvo que se habilite explícitamente:

```yaml
environment:
  - N8N_BLOCK_ENV_ACCESS_IN_NODE=false
```

Requiere `docker compose up -d --force-recreate n8n` para aplicar. Con esto,
`{{ $env.BACKEND_URL }}` funciona en los nodos HTTP Request.

**Nota de seguridad pendiente**: exponer todas las env vars del proceso
(incluye secrets como `POSTGRES_PASSWORD`, `ENCRYPTION_KEY`) a los workflows
es más permisivo de lo ideal. La alternativa nativa de n8n (`$vars`, Settings
→ Variables) requiere licencia paga — la instancia actual es **Community
Edition** y no la tiene disponible. Mientras siga en Community, todos los
workflows deben seguir usando `$env.*` (`BACKEND_URL`, `TELEGRAM_CHAT_ID`).

## Proxy inverso (bastión)

Vhost: `/etc/nginx/sites-available/n8n.gestorconsultoria.com.co.conf` →
`proxy_pass http://10.0.0.5:8032;` con `proxy_http_version 1.1`, `Connection:
upgrade` hardcodeado (no condicional vía `map $http_upgrade`),
`proxy_read_timeout`/`proxy_send_timeout` en 300s. Sin `client_max_body_size`
explícito (default 1MB). SELinux en modo `Permissive`. Ver
[[n8n-sync-y-gotchas]] para el debugging de un 500 que parecía ser del
proxy pero en realidad era un bug de encoding del lado cliente (PowerShell).
