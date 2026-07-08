# n8n Workflows for Grid Trading

## AutoParams Gate

**File:** `auto_params_gate.json`

**Purpose:** Gate que consulta `/auto-params` antes de crear un grid para validar viabilidad.

**Nodes:**
1. **Get Auto Params** — HTTP GET a `/auto-params` con `symbol` y `balance`
2. **Grid Viable?** — IF que verifica `grid_viable === true`
3. **Create Grid** — HTTP POST a `/api/v1/grids` con parámetros derivados (rama TRUE)

**Branches:**
- **TRUE** (grid_viable=true): Coloca el grid con los parámetros derivados
- **FALSE** (grid_viable=false): Conexión vacía — **aquí conectar notificación Telegram** con `$json.reasoning.no_viable`

**Environment Variables Requeridas:**
- `BACKEND_URL` — URL del backend (ej: `http://localhost:8000`)
- `TELEGRAM_CHAT_ID` — Chat ID para notificaciones (en rama FALSE)

**Integration:** Este gate se usa como pre-step antes de cualquier creación de grid. Reemplaza la llamada directa a `/api/v1/grids` con una que primero valida viabilidad.
