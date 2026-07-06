# Setup de n8n - Configuración Completa

## Parte 1: Variables de Entorno

Configura estas variables en n8n ANTES de importar workflows:

### Opción 1: Docker Compose (Recomendado)

En `docker-compose.yml`, agrega al servicio `n8n`:

```yaml
services:
  n8n:
    image: n8n
    environment:
      - BACKEND_URL=http://backend-python:8000
      - N8N_BLOCK_ENV_ACCESS_IN_NODE=false
      - TELEGRAM_CHAT_ID=<tu-chat-id>
      - OPENAI_API_KEY=<tu-api-key>
      - TELEGRAM_BOT_TOKEN=<tu-bot-token>
    # ... resto de config
```

Luego reinicia:
```bash
docker-compose down
docker-compose up -d
```

### Opción 2: n8n UI (Settings)

1. Abre http://localhost:5678
2. Click ⚙️ **Settings** (arriba a la derecha)
3. **Environment Variables** (left sidebar)
4. Agrega estas 3 variables:
   ```
   BACKEND_URL=http://backend-python:8000  (o http://localhost:8000 si no es Docker)
   N8N_BLOCK_ENV_ACCESS_IN_NODE=false
   TELEGRAM_CHAT_ID=<tu-chat-id>
   ```
5. **Save**
6. **Reinicia n8n completamente** (importante)

### Opción 3: Variables del Sistema

#### Linux/macOS
```bash
export BACKEND_URL=http://localhost:8000
export N8N_BLOCK_ENV_ACCESS_IN_NODE=false
export TELEGRAM_CHAT_ID=<tu-chat-id>
n8n start
```

#### Windows PowerShell
```powershell
$env:BACKEND_URL = "http://localhost:8000"
$env:N8N_BLOCK_ENV_ACCESS_IN_NODE = "false"
$env:TELEGRAM_CHAT_ID = "<tu-chat-id>"
# Luego iniciar n8n
```

---

## Parte 2: Credenciales

### Telegram Bot Token

Necesario para notificaciones.

**Crear bot:**
1. Abre Telegram, busca `@BotFather`
2. Envía `/newbot`
3. Nombre: "Grid Trading Bot"
4. Username: "grid_trading_bot_XXXX"
5. Copia el **Bot Token**

**Agregar a n8n:**
1. n8n → **Credentials** (arriba izquierda)
2. **Create New** → busca **Telegram**
3. Nombre: `TRADING_TELEGRAM`
4. Bot Token: `<tu-bot-token>`
5. **Save**

**Obtener Chat ID:**
1. Agrega el bot a tu grupo/chat privado
2. Envía un mensaje: `/start`
3. El bot responde con tu chat_id
4. O accede a: `https://api.telegram.org/bot<token>/getUpdates`

### OpenAI API Key (Opcional)

Para IA en Market Decision (puede usar Gemini en su lugar).

**Crear key:**
1. Abre https://platform.openai.com/api-keys
2. Click **Create new secret key**
3. Copia el key

**Agregar a n8n:**
1. n8n → **Credentials**
2. **Create New** → **OpenAI**
3. Nombre: `OpenAI_Key`
4. API Key: `<tu-api-key>`
5. **Save**

### Gemini API Key (Alternativa a OpenAI)

**Crear key:**
1. Abre https://ai.google.dev/
2. **Get API Key** → **Create API Key**
3. Copia el key

**Agregar a n8n:**
1. n8n → **Credentials**
2. **Create New** → **HTTP Header Auth**
3. Nombre: `Gemini_API_Key`
4. Header Name: `x-goog-api-key`
5. Value: `<tu-api-key>`
6. **Save**

---

## Parte 3: Importar Workflows

### Paso 1: Descargar JSONs

Los workflows están en `n8n-workflows/`:
- `workflow1-market-decision.json`
- `workflow2-monitor.json`

### Paso 2: Importar en n8n

1. Abre n8n UI → http://localhost:5678
2. **Create New** (arriba derecha)
3. **Import from File**
4. Selecciona `workflow1-market-decision.json`
5. **Import**
6. Repite para `workflow2-monitor.json`

### Paso 3: Configurar Nodos HTTP

Workflow 1 y 2 tienen nodos HTTP que llaman al backend:

**Verificar URLs:**
- Busca nodos que tengan **method: POST**
- URL debe ser: `{{ $env.BACKEND_URL }}/endpoint`
- El `{{ $env.BACKEND_URL }}` se expande con tu variable

**Ejemplo:**
```
POST {{ $env.BACKEND_URL }}/create-grid
POST {{ $env.BACKEND_URL }}/refresh-grid
POST {{ $env.BACKEND_URL }}/market-analysis
```

Si ves URL hardcodeada (ej. `http://localhost:8000`), cámbiala a `{{ $env.BACKEND_URL }}`.

### Paso 4: Configurar Nodos Telegram

Los workflows envían notificaciones a Telegram.

**Busca "Telegram" nodes:**
1. Selecciona el nodo Telegram
2. En **Credentials**, selecciona `TRADING_TELEGRAM` (que creaste arriba)
3. En **Chat**, ingresa tu **TELEGRAM_CHAT_ID** (o usa variable: `{{ $env.TELEGRAM_CHAT_ID }}`)
4. **Save**

Repite para todos los nodos Telegram.

### Paso 5: Configurar Nodos OpenAI/Gemini

Para IA decision en Workflow 1:

**Si usas OpenAI:**
1. Busca el nodo OpenAI
2. Selecciona credencial `OpenAI_Key`
3. Configura el prompt (busca "bullish" en el nodo)

**Si usas Gemini (HTTP):**
1. Busca el nodo HTTP con Gemini
2. Headers debe incluir: `x-goog-api-key` = `{{ $env.OPENAI_API_KEY }}` o similar
3. URL: `https://generativelanguage.googleapis.com/v1/models/gemini-pro:generateContent`

---

## Parte 4: Configurar Cronogramas

### Workflow 1: Market Decision

**Trigger: Cron cada 4 horas**

1. Abre Workflow 1
2. **Edit**
3. Busca el nodo **Cron** (triggering)
4. Configura:
   ```
   Interval: Hours
   Hours: 4
   Timezone: UTC (o tu zona)
   ```
5. **Save & Activate**

**O manual:** Omite Cron, ejecuta manual con botón **Execute** en n8n UI.

### Workflow 2: Monitor

**Trigger: Cron cada 15 minutos**

1. Abre Workflow 2
2. **Edit**
3. Busca el nodo **Cron**
4. Configura:
   ```
   Interval: Minutes
   Minutes: 15
   ```
5. **Save & Activate**

---

## Parte 5: Verificar Configuración

### Test 1: Variables de Entorno

Crea un nodo **Code** en cualquier workflow:

```javascript
console.log("BACKEND_URL =", process.env.BACKEND_URL);
console.log("TELEGRAM_CHAT_ID =", process.env.TELEGRAM_CHAT_ID);
```

Ejecuta (⏯️ button), revisa output. Debe mostrar tus valores.

### Test 2: Conexión al Backend

En un nodo **HTTP**:

```
Method: GET
URL: {{ $env.BACKEND_URL }}/health
```

Ejecuta. Debe devolver:
```json
{
  "status": "healthy",
  "database": "connected",
  "binance_api": "reachable"
}
```

### Test 3: Telegram

En un nodo **Telegram**:

```
Chat: {{ $env.TELEGRAM_CHAT_ID }}
Text: "Test de n8n: OK ✅"
```

Ejecuta. Deberías recibir mensaje en Telegram.

---

## Parte 6: Activar Workflows

Cuando todo esté configurado:

1. Abre Workflow 1
2. **Activate** (switch arriba derecha)
3. Abre Workflow 2
4. **Activate**

Ambos deberían tener un **✅ Active** badge.

---

## Orden de Ejecución (Primera Vez)

1. ✅ Variables de entorno configuradas
2. ✅ Credenciales Telegram/OpenAI creadas
3. ✅ Workflows importados
4. ✅ HTTP URLs corregidas
5. ✅ Tests pasados (health, telegram)
6. ✅ Crons configurados
7. ✅ Workflows activados

---

## Troubleshooting

### "Variable not found: BACKEND_URL"

**Problema:** Variable no está en n8n.

**Solución:**
1. Settings → Environment Variables
2. Agrega: `BACKEND_URL` = tu URL
3. **Save**
4. **Reinicia n8n completamente**

### "HTTP 502 Bad Gateway"

**Problema:** Backend no responde.

**Solución:**
1. Verifica backend: `curl http://localhost:8000/health`
2. Verifica URL en workflow (usar `{{ $env.BACKEND_URL }}`)
3. Reinicia backend: `docker-compose restart backend-python`

### "No Telegram message received"

**Problema:** Credencial o chat ID incorrecto.

**Solución:**
1. Verifica `TELEGRAM_CHAT_ID` es número (no nombre)
2. Verifica bot está en tu chat
3. Verifica credencial está seleccionada en nodo
4. Test con `/start` en chat

### Workflow no ejecuta

**Problema:** No está activado o cron no dispara.

**Solución:**
1. Verifica **Activate** switch está ON
2. Verifica cron (hours/minutes)
3. Ejecuta manualmente (⏯️ button) para test
4. Revisa logs de n8n

---

## Referencia Rápida

```env
# Variables requeridas
BACKEND_URL=http://backend-python:8000
N8N_BLOCK_ENV_ACCESS_IN_NODE=false
TELEGRAM_CHAT_ID=<tu-numero>

# Credenciales a crear
- Telegram Bot (token)
- OpenAI API Key (opcional, usar Gemini si no tienes)

# Workflows a importar
- workflow1-market-decision.json
- workflow2-monitor.json

# Crons
Workflow 1: Cada 4 horas
Workflow 2: Cada 15 minutos
```

---

Próximos pasos: [Setup Backend](02-setup-backend.md) → [Verificación](03-verificacion.md)
