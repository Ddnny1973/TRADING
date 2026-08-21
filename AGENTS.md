# AGENTS.md

Grid trading bot para Binance Futures (testnet). Un único backend FastAPI de aplicación (`backend-python/`) + workflows n8n externos (`n8n-workflows/`) que orquestan todo el polling. Toda la documentación está en español: mantén los docs nuevos en español.

## Antes de responder sobre este repo

- Leer `docs/brain/_index.md` (hub de conocimiento tácito: infra, sync n8n, decisiones técnicas) y seguir sus enlaces si el tema aplica. Es el mismo punto de entrada que usa `.github/copilot-instructions.md`.

## Arquitectura (lo que no es obvio)

- `backend-python/` es el ÚNICO código de aplicación. Entrypoint `app/main.py`. La constante `CODE_VERSION` se expone en `/health` y `/auto-params` para verificar remotamente qué build corre en el servidor.
- El backend NO tiene scheduler ni webhooks salientes: n8n (servidor externo) hace todo el polling — WF1 decisión de mercado, WF2 monitor/refresh/check-close, WF3 comandos Telegram.
- `n8n-workflows/*.json` son la fuente de verdad de los workflows. NO editar `docs/n8n-templates/` (legacy). Los nombres `workflow{1,2,3}-*.json` son estándar para CI/CD — no renombrarlos.
- Bases de datos (tres, fáciles de confundir): SQLite `grid_trading.db` = estado en tiempo real (`grids`/`grid_orders`/`grid_closures`); Postgres `postgres-trading` (9043) = histórico/analítica (`historical_grid_logs`, `grid_cycles`, `pnl_snapshots`); Postgres de n8n (9032) es OTRA instancia y solo guarda métricas de tokens de Gemini. Ver `docs/brain/analisis-bot-monitoreo.md`.
- Sigue en Binance TESTNET a propósito (`BINANCE_TESTNET_URL` en `app/core/config.py`) — el objetivo actual es medir rentabilidad antes de pasar a dinero real. No asumir que falta "mejorar la estrategia": es una decisión de producto abierta (ver `docs/analisis-bot/`).
- "1 grid RUNNING por símbolo" es una guardia real de BD (índice parcial UNIQUE en SQLite): el 400 "already exists" de `POST /api/v1/grids` es flujo esperado, no un error.

## Comandos

- Tests (desde `backend-python/`): `pytest -v`. `pytest.ini` fija `pythonpath=.` y `testpaths=tests`.
  - ⚠️ El `.venv` local está vacío (sin pytest ni deps): para correr tests localmente primero `pip install -r backend-python/requirements.txt`, o correrlos en Docker. No hay workflow de CI que corra tests.
  - La suite nunca toca red real: Binance mockeado, SQLite descartable por test, Postgres salteado (`SessionLocal=None`). `conftest.py` setea las env vars `BINANCE_*`/`POSTGRES_*` ANTES de importar `app.core.config` (pydantic valida al importar) — respeta ese orden si agregas fixtures.
- Docker: `docker compose up -d` desde la raíz. Puertos: backend `8043→8000`, postgres `9043→5432`. `docker-compose.yml` sustituye `${REDIS_PASSWORD}`/`${POSTGRES_*}` desde el `.env` raíz y requiere la red externa `infra_shared`.

## Deploy y sync n8n (GitHub Actions, rama `main`)

- Push a `main` → `deploy.yml` rebuild/restarta el backend en el servidor (`/data/odoo/43`). `paths-ignore: n8n-workflows/**, docs/**, *.md` → cambios solo de docs NO despliegan.
- Push a `main` tocando `n8n-workflows/*.json` → `n8n-sync.yml` hace PUT a producción (`https://n8n.gestorconsultoria.com.co`). IDs hardcodeados: WF1 `yggk1wajL1tsmABi`, WF2 `96qAStQwfrHAVXRd`, WF3 `zH79H6HyVleecAm7`. Editar esos JSON y pushear = cambiar producción en vivo.
- Sync manual desde Windows: `scripts/update-workflows-n8n.ps1`. Gotcha crítico de PowerShell 5.1: leer el JSON con `Get-Content -Raw -Encoding UTF8` y enviar el body como bytes UTF-8 (`[Text.Encoding]::UTF8.GetBytes`). Sin eso, nginx devuelve 500 genérico en bodies grandes o sube mojibake (tildes/emojis). La API pública de n8n rechaza campos extra de `settings` — enviar solo `executionOrder`.

## Infra multi-servidor (detalle en `docs/brain/infra-multi-servidor.md`)

- **Actualización 2026-08-20:** Backend y n8n ahora consolidados en `Docker-alma-16gb-hel1-1` (`10.0.0.6`). Backend en puerto `8043`, n8n en `8032`, nginx en bastión (`10.0.0.3`).
- Antes de la consolidación: Backend estaba en `10.0.0.6`, n8n en `10.0.0.2` (Docker-New-03) — **workflows n8n pueden tener references hardcodeadas a la IP vieja, revisar y actualizar**.
- ⚠️ **Tarea pendiente:** Verificar que los workflows en n8n (`n8n.gestorconsultoria.com.co`) tengan `BACKEND_URL=http://10.0.0.6:8043` en Environment Variables (Settings ⚙️).
- Nombres de red Docker iguales entre hosts ≠ red compartida: `BACKEND_URL` entre servidores SIEMPRE por IP privada + puerto publicado (`http://10.0.0.6:8043`), nunca por nombre de contenedor.
- n8n es Community Edition: no hay `$vars` → los workflows usan `$env.*`; requiere `N8N_BLOCK_ENV_ACCESS_IN_NODE=false`. Los JSON del repo contienen emojis/tildes en mensajes de Telegram — preservarlos.

## Convenciones

- Docs de producto: estructura numerada `docs/00-START/` … `docs/90-APPENDICES/`. Conocimiento tácito estable: `docs/brain/` (cada archivo lleva frontmatter `updated`). Análisis evolutivo/en curso: `docs/analisis-bot/`. Notas personales del usuario: `Analisis Propios/` (no tocar).
- Si un cambio de código invalida algo de `docs/brain/`, actualizarlo en el mismo PR, incluido el campo `updated` (regla de `.github/copilot-instructions.md`).
- `n8n-workflows/backup-*.json` y `.env` están en `.gitignore` por contener credenciales — no commitearlos.
