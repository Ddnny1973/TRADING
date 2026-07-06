# Inicio Rápido - Grid Trading Binance Futures

## Para Usuarios Nuevos

**Objetivo:** Tener el sistema funcionando en menos de 30 minutos.

### Paso 1: Clonar & Configurar Backend

```bash
cd TRADING/backend-python
cp .env.example .env
# Edita .env con tus credenciales de Binance Testnet
```

### Paso 2: Iniciar Docker

```bash
cd TRADING
docker-compose up -d
```

Verifica que esté listo:
```bash
curl http://localhost:8000/health
# Debe devolver: {"status": "healthy"}
```

### Paso 3: Configurar n8n

1. Abre http://localhost:5678
2. Crea cuenta / inicia sesión
3. **Settings** ⚙️ → Environment Variables
4. Agrega:
   ```
   BACKEND_URL=http://localhost:8000
   N8N_BLOCK_ENV_ACCESS_IN_NODE=false
   TELEGRAM_CHAT_ID=<tu-chat-id>
   ```
5. Reinicia n8n

### Paso 4: Importar Workflows

1. n8n → **Create New** → **Import from File**
2. Importa `n8n-workflows/workflow1-market-decision.json`
3. Importa `n8n-workflows/workflow2-monitor.json`
4. Configura credenciales (Telegram, OpenAI/Gemini)

### Paso 5: Ejecutar Primer Test

```bash
# En otra terminal, con backend corriendo:
curl -X POST http://localhost:8000/market-analysis \
  -H "Content-Type: application/json" \
  -d '{"symbol": "BTCUSDT", "interval": "4h"}'
```

Si devuelve datos → **¡Ready!**

## Próximos Pasos

- Lee [Tabla de Contenidos](02-tabla-contenidos.md) para navegar la documentación
- Lee [Flujos por Rol](03-flujos-por-rol.md) para tu tipo de usuario
- Ve a [API Reference](../30-API-REFERENCE/01-request-response.md) para detalles técnicos

## Si Algo Falla

Ver [Troubleshooting](../40-OPERACIONAL/01-troubleshooting.md)
