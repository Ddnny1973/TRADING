# Configuración de n8n para Workflows Grid Trading

## 🔧 Variables de Entorno Requeridas

Configura estas 3 variables en n8n antes de ejecutar los workflows:

### Opción 1: Backend en Localhost (Desarrollo Local)

```env
BACKEND_URL=http://localhost:8000
N8N_BLOCK_ENV_ACCESS_IN_NODE=false
TELEGRAM_CHAT_ID=<tu-chat-id>
```

**Casos de uso:**
- ✅ Desarrollo local (n8n y backend en la misma máquina)
- ✅ Testing rápido
- ✅ Puerto por defecto: 8000 (o 8043 si cambió)

---

### Opción 2: Backend por Red Interna (Docker/Multi-Servidor)

```env
BACKEND_URL=http://backend-python:8000
N8N_BLOCK_ENV_ACCESS_IN_NODE=false
TELEGRAM_CHAT_ID=<tu-chat-id>
```

**Casos de uso:**
- ✅ Docker Compose con contenedores en la misma red
- ✅ n8n y backend en servidores diferentes en la misma red
- ✅ Producción

**Nota:** Si n8n y backend están en IPs privadas diferentes (ej. 10.0.0.5 y 10.0.0.4), usa:
```env
BACKEND_URL=http://10.0.0.4:8000
```

---

## 📝 Cómo Configurar en n8n

### Método 1: Docker Compose (Recomendado para tu caso)

En `docker-compose.yml`, agrega al servicio `n8n`:

```yaml
services:
  n8n:
    image: n8n
    environment:
      - BACKEND_URL=http://backend-python:8000  # Si está en Docker
      # - BACKEND_URL=http://localhost:8000     # Si backend está en localhost
      - N8N_BLOCK_ENV_ACCESS_IN_NODE=false
      - TELEGRAM_CHAT_ID=<tu-chat-id>
    # ... resto de config
```

Luego:
```bash
docker compose up -d --force-recreate n8n
```

### Método 2: n8n UI (Settings)

1. Abre n8n → **Settings** ⚙️
2. Busca **Environment Variables**
3. Agrega:
   - `BACKEND_URL` = `http://localhost:8000` (o la URL correcta)
   - `N8N_BLOCK_ENV_ACCESS_IN_NODE` = `false`
   - `TELEGRAM_CHAT_ID` = `<tu-chat-id>`
4. Guarda
5. **Reinicia n8n** (importante)

### Método 3: Variables del Sistema (Windows/Linux)

```bash
# Linux/macOS
export BACKEND_URL=http://localhost:8000
export N8N_BLOCK_ENV_ACCESS_IN_NODE=false
export TELEGRAM_CHAT_ID=<tu-chat-id>

# Luego inicia n8n
n8n start

# Windows (PowerShell)
$env:BACKEND_URL = "http://localhost:8000"
$env:N8N_BLOCK_ENV_ACCESS_IN_NODE = "false"
$env:TELEGRAM_CHAT_ID = "<tu-chat-id>"
```

---

## ✅ Verificar Configuración

Después de configurar, valida:

```bash
# 1. Verifica que el backend responde
curl http://localhost:8000/health
# Debe devolver: {"status": "healthy", ...}

# 2. En n8n, crea un nodo Code con:
console.log("BACKEND_URL =", process.env.BACKEND_URL)
console.log("N8N_BLOCK_ENV_ACCESS_IN_NODE =", process.env.N8N_BLOCK_ENV_ACCESS_IN_NODE)

# 3. Ejecuta el nodo y revisa los logs
# Deberías ver ambas variables con valores correctos
```

---

## 🔐 Credenciales (Aparte de Variables de Entorno)

### Telegram Bot Token
1. n8n → **Credentials** (arriba a la izquierda)
2. **Create New** → **Telegram**
3. Nombre: `TRADING`
4. Bot Token: `<tu-token-del-bot>`
5. Guarda

### Gemini API Key (Header Auth)
1. n8n → **Credentials**
2. **Create New** → **HTTP Header Auth**
3. Nombre: `Gemini API Key` (o `Header Auth GeminiAI`)
4. Header Name: `x-goog-api-key`
5. Value: `<tu-api-key-de-gemini>`
6. Guarda

---

## 🚀 Orden de Ejecución

1. **Configurar variables de entorno** (ver arriba)
2. **Crear credenciales** (Telegram + Gemini)
3. **Importar workflows** desde `n8n-workflows/`
4. **Ejecutar WF1 manualmente** (Market Decision)
5. **Esperar a que cree un grid**
6. **Ejecutar WF2 manualmente** (Monitor)

---

## 📌 Resumen Rápido

Para tu caso (backend en localhost o red interna):

```env
# Si backend está en la misma máquina
BACKEND_URL=http://localhost:8000

# Si backend está en Docker con n8n
BACKEND_URL=http://backend-python:8000

# Siempre necesario para acceso a $env
N8N_BLOCK_ENV_ACCESS_IN_NODE=false

# Para notificaciones de Telegram
TELEGRAM_CHAT_ID=<tu-id>
```

¿Cuál es tu caso exacto?
- [ ] Backend en localhost:8000
- [ ] Backend en localhost:8043
- [ ] Backend en Docker (mismo compose que n8n)
- [ ] Backend en otro servidor IP privada
