# 🔧 Implementación de Triggers Telegram en n8n

**Archivo nuevo a crear:** `workflow3-telegram-monitor.json`

---

## 🏗️ Estructura del Workflow 3 (Telegram Monitor)

```
Telegram Webhook Trigger
  ↓
Parse Command
  ↓
Router (IF statement)
  ├─ /grids → GET /api/v1/grids
  ├─ /grid-detail → GET /api/v1/grids/{symbol}
  ├─ /history → Query grid_closures
  ├─ /stats → Calcular estadísticas
  ├─ /trigger-wf1 → executeWorkflow
  ├─ /trigger-wf2 → executeWorkflow
  └─ /config → Mostrar config
  
  ↓
Format Response
  ↓
Send Telegram Message
```

---

## 📝 Nodos Principales (Pseudo-código n8n)

### 1. Telegram Webhook Trigger
```json
{
  "name": "Telegram: Monitor Command",
  "type": "n8n-nodes-base.telegramTrigger",
  "parameters": {
    "updates": ["message"]
  },
  "position": [0, 0]
}
```

---

### 2. Parse Command
```javascript
// Nodo tipo: Code

const message = $json.message?.text || '';
const chatId = $json.message?.chat?.id;
const authorizedChatId = $env.TELEGRAM_CHAT_ID;

// Validar autorización
if (String(chatId) !== authorizedChatId) {
  return {
    json: {
      error: 'Unauthorized',
      shouldSendMessage: false
    }
  };
}

// Parse command
const parts = message.trim().split(/\s+/);
const command = parts[0].toLowerCase();
const args = parts.slice(1);

return {
  json: {
    command,
    args,
    chatId,
    message,
    authorized: true
  }
};
```

---

### 3. Router (IF Nodes)
```
┌─ IF: command === '/grids'?
│  └─ GET /api/v1/grids?status=RUNNING → Format Grids
│
├─ IF: command === '/grid-detail'?
│  └─ GET /api/v1/grids?symbol={args[0]} → Format Detail
│
├─ IF: command === '/history'?
│  └─ Query grid_closures → Format History
│
├─ IF: command === '/stats'?
│  └─ Calculate stats → Format Stats
│
├─ IF: command === '/trigger-wf1'?
│  └─ Confirm → executeWorkflow(WF1) → Format Result
│
└─ IF: command === '/trigger-wf2'?
   └─ Confirm → executeWorkflow(WF2) → Format Result
```

---

## 💻 Código Detallado para cada Comando

### COMANDO: `/grids`

**Nodo HTTP:**
```javascript
// GET /api/v1/grids?status=RUNNING
url: $env.BACKEND_URL + '/api/v1/grids?status=RUNNING'
```

**Nodo Code (Formateo):**
```javascript
const grids = $json.body || [];

if (grids.length === 0) {
  return {
    json: {
      text: '🟢 GRIDS ACTIVOS: 0\n\nNo hay grids en ejecución actualmente.'
    }
  };
}

let response = `🟢 GRIDS ACTIVOS (${grids.length}):\n`;
response += '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n';

grids.forEach((grid, idx) => {
  const ageHours = Math.floor((Date.now() - new Date(grid.created_at)) / 3600000);
  response += `${idx + 1}️⃣  ${grid.symbol} | Niveles: ${grid.levels}\n`;
  response += `   📊 Rango: ${grid.lower_price} - ${grid.upper_price}\n`;
  response += `   ⏲️  Edad: ${ageHours}h\n\n`;
});

response += 'Comando: /grid-detail SYMBOL';

return {
  json: { text: response }
};
```

---

### COMANDO: `/grid-detail SYMBOL`

**Nodo HTTP 1: Get Grid**
```javascript
url: $env.BACKEND_URL + '/api/v1/grids?symbol=' + $json.args[0]
```

**Nodo HTTP 2: Get PnL**
```javascript
const gridId = $('HTTP: Get Grid').item.json.body[0].id;
url: $env.BACKEND_URL + '/api/v1/grids/' + gridId + '/pnl'
```

**Nodo Code (Formateo):**
```javascript
const grid = $json.grid;
const pnl = $json.pnl;

if (!grid) {
  return { json: { text: '❌ Grid no encontrada' } };
}

const ageHours = Math.floor((Date.now() - new Date(grid.created_at)) / 3600000);
const ordersSummary = grid.orders.reduce((acc, o) => {
  acc[o.status] = (acc[o.status] || 0) + 1;
  return acc;
}, {});

let response = `📊 GRID: ${grid.symbol}\n`;
response += '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n';
response += `ID: ${grid.id.substring(0, 20)}...\n`;
response += `Status: ${grid.status}\n`;
response += `Edad: ${ageHours}h\n\n`;

response += `📈 Órdenes:\n`;
response += `  FILLED: ${ordersSummary['FILLED'] || 0}\n`;
response += `  OPEN: ${ordersSummary['NEW'] || 0}\n`;
response += `  CANCELLED: ${ordersSummary['CANCELED'] || 0}\n\n`;

response += `💰 PnL:\n`;
response += `  Realizado: +${pnl.realized_pnl} USDT\n`;
response += `  No realizado: +${pnl.unrealized_pnl} USDT\n`;
response += `  Total: +${pnl.total_pnl} USDT\n`;

return { json: { text: response } };
```

---

### COMANDO: `/stats`

**Nodo HTTP: Query grid_closures**
```javascript
// Crear endpoint en backend: GET /api/v1/grid-stats?days=7
url: $env.BACKEND_URL + '/api/v1/grid-stats?days=7'
```

**Nodo Code (Formateo):**
```javascript
const stats = $json.body;

let response = `📊 ESTADÍSTICAS (últimos 7 días)\n`;
response += '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n';

response += `📈 Grids: ${stats.total_grids}\n`;
response += `  ✅ Ganancias: ${stats.profit_grids}\n`;
response += `  ❌ Pérdidas: ${stats.loss_grids}\n`;
response += `  Win Rate: ${((stats.profit_grids/stats.total_grids)*100).toFixed(1)}%\n\n`;

response += `💰 PnL Total: ${stats.total_pnl} USDT\n`;
response += `  ROI: ${stats.roi_pct.toFixed(2)}%\n`;
response += `  Promedio: ${(stats.total_pnl/stats.total_grids).toFixed(2)} USDT/grid\n\n`;

response += `⏱️ Duración promedio: ${stats.avg_duration_hours}h ${stats.avg_duration_minutes}m\n`;

return { json: { text: response } };
```

---

### COMANDO: `/trigger-wf1`

**Nodo Code (Confirmación):**
```javascript
const message = 'Ejecutar Workflow 1 (Market Decision)? (Toma ~15 seg)\n\n✅ Sí\n❌ No';

return {
  json: {
    text: message,
    reply_markup: {
      inline_keyboard: [
        [
          { text: '✅ Ejecutar', callback_data: 'confirm_wf1_yes' },
          { text: '❌ Cancelar', callback_data: 'confirm_wf1_no' }
        ]
      ]
    }
  }
};
```

**Nodo: executeWorkflow (si confirma)**
```javascript
{
  "workflowId": "WF1_ID",
  "waitForCompletion": true
}
```

---

### COMANDO: `/history`

**Nodo HTTP: Query grid_closures**
```javascript
// GET /api/v1/grid-closures?limit=10
url: $env.BACKEND_URL + '/api/v1/grid-closures?limit=10'
```

**Nodo Code (Formateo):**
```javascript
const closures = $json.body || [];

const triggerEmojis = {
  'STOP_LOSS': '❌',
  'TAKE_PROFIT': '✅',
  'EXPIRED': '⏰',
  'MAX_POSITION': '🚫',
  'MANUAL': '🤷'
};

let response = `📜 HISTÓRICO DE CIERRES (últimas ${closures.length}):\n`;
response += '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n';

closures.forEach(c => {
  const emoji = triggerEmojis[c.trigger_condition] || '❓';
  const pnl = parseFloat(c.total_pnl);
  const sign = pnl >= 0 ? '+' : '';
  
  response += `${emoji} ${c.closed_at.substring(0, 10)} | ${c.symbol} | ${sign}${pnl} USDT\n`;
});

response += '\nComando: /history-detail ID';

return { json: { text: response } };
```

---

## 🔌 Integración con n8n

### Opción A: Crear Workflow 3 Nuevo

```json
{
  "name": "workflow3-telegram-monitor",
  "nodes": [
    {
      "name": "Telegram Webhook",
      "type": "n8n-nodes-base.telegramTrigger",
      "parameters": {
        "updates": ["message"]
      }
    },
    {
      "name": "Parse Command",
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "parameters": {
        "jsCode": "// ... código arriba"
      }
    },
    {
      "name": "Router: /grids",
      "type": "n8n-nodes-base.if",
      "parameters": {
        "conditions": {
          "conditions": [
            {
              "leftValue": "={{ $json.command }}",
              "rightValue": "/grids",
              "operator": { "type": "string", "operation": "equals" }
            }
          ]
        }
      }
    },
    // ... más IF nodes para otros comandos
    {
      "name": "Send Response",
      "type": "n8n-nodes-base.telegram",
      "parameters": {
        "chatId": "={{ $json.chatId }}",
        "text": "={{ $json.text }}"
      }
    }
  ]
}
```

### Opción B: Integrar en WF2 (Monitor)

Agregar nodos al final de WF2 para responder comandos Telegram recibidos durante monitoreo.

---

## 📊 Backend Endpoints Requeridos

Para implementar los triggers, se necesitan estos endpoints en backend:

```python
# EXISTENTES (usar como están):
GET /api/v1/grids?status=RUNNING
GET /api/v1/grids?symbol={symbol}
GET /api/v1/grids/{id}/pnl

# NUEVOS (crear):
GET /api/v1/grid-closures?limit=10
GET /api/v1/grid-stats?days=7
GET /api/v1/workflow-executions?limit=5  (para /last-execution)
GET /api/v1/config  (para /config)
```

---

## 🚀 Flujo de Implementación (Recomendado)

### Fase 1: Comandos Básicos (1-2 días)
1. `/grids` — Estado actual
2. `/grid-detail` — Detalles de grid
3. `/trigger-wf1` — Ejecutar manualmente

### Fase 2: Histórico y Stats (1 día)
4. `/history` — Últimos cierres
5. `/stats` — Estadísticas

### Fase 3: Comandos Avanzados (1 día)
6. `/config` — Mostrar configuración
7. `/perf` — Performance por símbolo
8. `/trigger-wf2` — Monitor manual

---

## 🎨 Prueba Local (n8n Sandbox)

```bash
# 1. Crear webhook Telegram en n8n
# 2. Obtener URL del webhook
# 3. Enviar test message via curl:

curl -X POST https://n8n-instance/webhook/abc123 \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "text": "/grids",
      "chat": { "id": 1234567890 }
    }
  }'

# 4. Verificar respuesta en n8n logs
```

---

## 📱 Ejemplo de Conversación Completa

```
User:  /grids
Bot:   🟢 GRIDS ACTIVOS (2):
       ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
       1️⃣  BTCUSDT | Niveles: 8 | Ciclos: 3
          📊 Rango: 62,229 - 63,381 USDT
          ⏲️  Edad: 5h

       2️⃣  ETHUSDT | Niveles: 6 | Ciclos: 1
          📊 Rango: 3,100 - 3,280 USDT
          ⏲️  Edad: 2h
       
       Comando: /grid-detail BTCUSDT

User:  /grid-detail BTCUSDT
Bot:   📊 GRID: BTCUSDT
       ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
       ID: grid_20260707_abc123
       Status: RUNNING
       Edad: 5h

       📈 Órdenes:
         FILLED: 2
         OPEN: 5
         CANCELLED: 1

       💰 PnL:
         Realizado: +45.32 USDT
         No realizado: +12.50 USDT
         Total: +57.82 USDT

User:  /stats
Bot:   📊 ESTADÍSTICAS (últimos 7 días)
       ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
       📈 Grids: 12
         ✅ Ganancias: 8
         ❌ Pérdidas: 2
         🚫 Max Position: 1
         ⏰ Expiración: 1
         Win Rate: 66.7%

       💰 PnL Total: +270.77 USDT
         ROI: +5.4%
         Promedio: +22.56 USDT/grid
```

