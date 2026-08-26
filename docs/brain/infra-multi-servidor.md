---
title: "Infraestructura multi-servidor (n8n vs backend)"
type: infra
app: trading-grid-bot
repo: TRADING
tags: [infra, deploy, nginx, docker, red]
related:
  - "[[_index]]"
  - "[[n8n-sync-y-gotchas]]"
updated: 2026-08-26
owner: dueño del repo
---

# Infraestructura multi-servidor

## Topología real (3 servidores Hetzner, tras migración 2026-08-20)

| Servidor | Rol | IP pública | IP privada | Contenedor clave | Puerto publicado |
|---|---|---|---|---|---|
| **Docker-alma-16gb-hel1-1** (Hetzner hel1) | Backend trading | `2.29.11.73` | `10.0.0.6` | `trading-backend` (imagen `43-backend-python`, carpeta compose `/data/odoo/43`) | `8043 -> 8000`, Postgres `9043 -> 5432` |
| **ubuntu-8gb-hel1-1** (Hetzner hel1) | n8n (+ wppapi, ocr, etc.) | `37.27.190.155` | `10.0.0.2` | `32-n8n-1` (carpeta compose `/data/odoo/32`, sin `container_name`) | `8032 -> 5678` |
| **Bastión** (`10.0.0.3`) | Proxy inverso | — | `10.0.0.3` | nginx directo en el host (no contenedor) | 443 público |

Servidores anteriores (decomisionados o repurposeados): `Docker-New-alma-4gb-fsn1-1`
(`10.0.0.4`, ex-backend trading, stack parado el 2026-08-20) y el ex-servidor de
n8n (`10.0.0.5`).

`docker-compose.yml` de este repo despliega también `postgres-trading`
(9043) y `redis-trading`, en la red `infra_shared` (externa, creada a mano).
El compose de n8n (fuera de este repo) declara una red con el **mismo nombre**
`infra_shared` pero es una red bridge local distinta (NetworkID distinto).

## Migración 2026-08-20 (fsn1 -> hel1) — qué pasó y aprendizajes

- Esa mañana un restore del repo de infra dejó la carpeta `/data/odoo/43` del
  servidor viejo reducida a solo `postgres-trading-data` (el `.git` de infra no
  trackea esa carpeta): se perdieron del disco el código, el compose, el `.env`
  y `backend-data`. Los contenedores sobrevivieron porque corren de imagen ya
  construida, pero el SQLite quedó perdido → grids cerradas por
  `RECONCILIATION_FAILED` por los workflows antes del corte.
- El estado se recuperó desde backup al nuevo servidor; el corte fue:
  arrancar stack nuevo → cambiar `BACKEND_URL` en el compose de n8n
  (`/data/odoo/32/docker-compose.yml`, `http://10.0.0.6:8043`) +
  `--force-recreate` → parar stack viejo → apuntar vhost del bastión.
- **OpenSSH 9.9 penaliza IPs por fallos de auth (`PerSourcePenalties`)**: tras
  intentos fallidos con claves, el servidor rechaza conexiones nuevas de esa IP
  con banner `"Not allowed at this time"` (afectó a la PC personal y a los
  runners de GitHub Actions). Fix permanente:
  `/etc/ssh/sshd_config.d/00-penalties.conf` con `PerSourcePenalties no`.
- Los puertos publicados por Docker **se saltan firewalld** (cadena DOCKER de
  iptables): el wget de n8n al 8043 funcionó aunque las rich rules no estuvieran.
  Las rich rules del nuevo servidor para 8043 son cosméticas; existe una vieja
  para `10.0.0.5` que quedó obsoleta (n8n ahora es `10.0.0.2`).
- CI/CD intacto: `deploy.yml` sigue haciendo `git pull` + build vía secrets
  (`SERVER_HOST=2.29.11.73`, `SERVER_USER=root`, `SERVER_PORT=22`,
  `SSH_PRIVATE_KEY`=clave ED25519 `docker-alma-16gb`, autorizada en
  `authorized_keys` del root). El repo Docker usa su propio secret
  `DEPLOY_SSH_KEY` (clave `ci-deploy`) contra el mismo servidor.

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
BACKEND_URL=http://10.0.0.6:8043
```

Confirmado funcionando: `docker exec 32-n8n-1 wget -qO- http://10.0.0.6:8043/health` → 200 healthy.
(El backend y n8n están en la misma red privada Hetzner 10.0.0.x.)

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

**2026-08-26**: `TELEGRAM_CHAT_ID=1561962049` agregado al docker-compose de n8n
(archivo `32/docker-compose.yml` del repo Docker). Sin esta variable, WF3
rechazaba silenciosamente todos los comandos (authorized=false).

## Proxy inverso (bastión)

Dos vhosts en el bastión (`10.0.0.3`):

- `trading.gestorconsultoria.com.co` → `proxy_pass http://10.0.0.6:8043;`
  (actualizado en la migración 2026-08-20).
- `n8n.gestorconsultoria.com.co` → apuntaba a `10.0.0.5:8032`; **verificar que
  quedó actualizado a `10.0.0.2:8032`** tras mover n8n de servidor.

Ambos con `proxy_http_version 1.1`, `Connection: upgrade` hardcodeado (no
condicional vía `map $http_upgrade`), `proxy_read_timeout`/`proxy_send_timeout`
en 300s. Sin `client_max_body_size` explícito (default 1MB). SELinux en modo
`Permissive`. Ver [[n8n-sync-y-gotchas]] para el debugging de un 500 que
parecía ser del proxy pero en realidad era un bug de encoding del lado cliente
(PowerShell).
