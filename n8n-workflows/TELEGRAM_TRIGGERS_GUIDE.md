# 📱 Guía de Triggers Telegram — Monitoreo en Vivo

**Objetivo:** Agregar comandos Telegram para consultar estado de órdenes, histórico de flujos y estadísticas en tiempo real.

---

## 🎯 Triggers Sugeridos (Por Funcionalidad)

### GRUPO 1: Estado de Órdenes Activas

#### 1. `/grids` — Ver grids activos
```
Usuario envía: /grids
Bot responde:

🟢 GRIDS ACTIVOS (2):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1️⃣  BTCUSDT | Niveles: 8 | Ciclos: 3
   📊 Rango: 62,229 - 63,381 USDT
   ⏲️  Edad: 5h 23m

2️⃣  ETHUSDT | Niveles: 6 | Ciclos: 1
   📊 Rango: 3,100 - 3,280 USDT
   ⏲️  Edad: 2h 10m

Comando: /grid-detail BTCUSDT (para detalles)
```

**Implementación n8n:**
- Trigger: Telegram message with text `/grids`
- Action: GET `/api/v1/grids?status=RUNNING`
- Response: Parse y formatear respuesta

---

#### 2. `/grid-detail SYMBOL` — Detalles de una grid específica
```
Usuario envía: /grid-detail BTCUSDT
Bot responde:

📊 GRID: BTCUSDT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ID: grid_20260707_abc123
Status: RUNNING
Edad: 5h 23m

📈 Órdenes:
  BUY  62,229.6 × 0.001 BTC → ✅ FILLED (avg: 62,229)
  SELL 62,707.3 × 0.001 BTC → ❌ OPEN
  BUY  62,385.4 × 0.001 BTC → ❌ OPEN
  ...

💰 PnL Realizado: +45.32 USDT
📊 PnL No realizado: +12.50 USDT
🎯 Total: +57.82 USDT

⚙️ Config:
  Niveles: 8
  Risk: 5%
  Rango: 62,229 - 63,381
  Stop Loss: N/A
  Take Profit: N/A
```

**Implementación n8n:**
- Trigger: Telegram message parsing `/grid-detail SYMBOL`
- Action 1: GET `/api/v1/grids?symbol=SYMBOL`
- Action 2: GET `/api/v1/grids/{id}/pnl`
- Response: Formatear con órdenes, PnL, config

---

### GRUPO 2: Historial de Ejecuciones

#### 3. `/history` — Últimos 10 cierres de grids
```
Usuario envía: /history
Bot responde:

📜 HISTÓRICO DE CIERRES (últimas 10):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ 2026-07-07 16:50:36 | BTCUSDT | TAKE_PROFIT | +45.32 USDT
❌ 2026-07-07 12:43:58 | ETHUSDT | STOP_LOSS | -15.00 USDT
🚫 2026-07-06 09:12:15 | BTCUSDT | MAX_POSITION | +22.11 USDT
⏰ 2026-07-06 03:05:42 | BNBUSDT | EXPIRED | +8.50 USDT
...

Comando: /history-detail ID (para detalles de un cierre)
Estadísticas: /stats
```

**Implementación n8n:**
- Trigger: Telegram message with text `/history`
- Action: GET `/api/v1/grids?status=CANCELED` (o consultar `grid_closures` via backend endpoint)
- Response: Formatear últimos 10 con trigger emoji

---

#### 4. `/history-detail GRID_ID` — Detalles de un cierre específico
```
Usuario envía: /history-detail grid_20260707_abc123
Bot responde:

📋 CIERRE DETALLADO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Grid ID: grid_20260707_abc123
Symbol: BTCUSDT
Estado: CANCELED
Razón: TAKE_PROFIT ✅

⏱️ Cronología:
  Creado: 2026-07-07 11:27:22 UTC
  Cerrado: 2026-07-07 16:50:36 UTC
  Duración: 5h 23m

📊 Resultados:
  Órdenes colocadas: 8
  Órdenes llenadas: 5
  Ciclos completados: 3

💰 PnL Final: +45.32 USDT
  Ganancia realizada: +45.32 USDT
  Fees pagadas: -2.10 USDT (0.02%)
  Balance adicional: +43.22 USDT

⚙️ Parámetros:
  Niveles: 8, Risk: 5%
  Rango: 62,229 - 63,381 USDT
  SL/TP: Ninguno
  Max Duration: 224h
```

**Implementación n8n:**
- Trigger: Telegram message parsing `/history-detail GRID_ID`
- Action: GET `/api/v1/grids/{id}` (grid cerrado)
- Response: Mostrar órdenes, PnL breakdown, cronología

---

### GRUPO 3: Estadísticas y Resumen

#### 5. `/stats` — Estadísticas generales del trading
```
Usuario envía: /stats
Bot responde:

📊 ESTADÍSTICAS DE TRADING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Período: Últimos 7 días

📈 Grids Completadas: 12
  ✅ Ganancia: 8 grids (+285.42 USDT)
  ❌ Pérdida: 2 grids (-45.30 USDT)
  🚫 Max Position: 1 grid (+12.15 USDT)
  ⏰ Expiración: 1 grid (+18.50 USDT)

💰 PnL TOTAL: +270.77 USDT
  ROI: +5.4% (sobre 5,000 USDT base)
  Promedio por grid: +22.56 USDT
  Mejor: +52.30 USDT
  Peor: -18.75 USDT

⚡ Velocidad:
  Duración promedio: 4h 12m
  Más rápida: 45m
  Más lenta: 18h 30m

🎯 Win Rate: 66.7% (8/12)
📊 Profit Factor: 6.3 (ganancia/pérdida)

🔄 Grids Activos Ahora: 2
```

**Implementación n8n:**
- Trigger: Telegram message with text `/stats`
- Action: Query `grid_closures` (últimos 7 días)
- Action 2: GET `/api/v1/grids?status=RUNNING` (contar activos)
- Response: Calcular y formatear estadísticas

---

#### 6. `/perf SYMBOL` — Performance de una moneda
```
Usuario envía: /perf BTCUSDT
Bot responde:

📊 PERFORMANCE: BTCUSDT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Últimos 7 días

Grids: 5
  ✅ Ganancias: 4
  ❌ Pérdidas: 1
  Win Rate: 80%

💰 PnL Total: +145.20 USDT
  Promedio: +29.04 USDT/grid

⏱️ Duración promedio: 5h 15m

Comparar con: /perf-compare BTCUSDT ETHUSDT
```

---

### GRUPO 4: Ejecución de Flujos

#### 7. `/trigger-wf1` — Ejecutar manualmente WF1 (Market Decision)
```
Usuario envía: /trigger-wf1
Bot responde:

🚀 Ejecutando Workflow 1 (Market Decision)...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⏳ Paso 1: GET /auto-params (BTCUSDT, 5000 USDT)
✅ Grid viable: true
✅ Levels: 8, Risk: 5%

⏳ Paso 2: Llamando Gemini...
✅ Decision: launch = true

⏳ Paso 3: Creando grid en Binance...
✅ Grid creado: grid_20260707_xyz789

📊 RESULTADO:
  Symbol: BTCUSDT
  Niveles: 8
  Rango: 62,229 - 63,381 USDT
  Órdenes: 8 colocadas
  
✅ Workflow completó exitosamente (15.3 segundos)

Monitorear: /grids
```

**Implementación n8n:**
- Trigger: Telegram message with text `/trigger-wf1`
- Action: `executeWorkflow` para WF1
- Response: Capture steps y mostrar progreso

---

#### 8. `/trigger-wf2` — Ejecutar manualmente WF2 (Monitor)
```
Usuario envía: /trigger-wf2
Bot responde:

🔄 Ejecutando Workflow 2 (Grid Monitor)...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Grids activos: 2

Grid 1: BTCUSDT (grid_20260707_abc123)
  ✅ Refresh: 10 órdenes sincronizadas, 2 fills nuevos
  ✅ Replenish: 2 órdenes de reposición colocadas
  ✅ Check-close: No trigger (RUNNING)

Grid 2: ETHUSDT (grid_20260707_def456)
  ✅ Refresh: 6 órdenes sincronizadas, 0 fills
  ✅ Check-close: No trigger (RUNNING)

✅ Workflow completó (2.1 segundos)

Ver detalles: /grid-detail BTCUSDT
```

**Implementación n8n:**
- Trigger: Telegram message with text `/trigger-wf2`
- Action: `executeWorkflow` para WF2
- Response: Show grid processing summary

---

### GRUPO 5: Información Operacional

#### 9. `/last-execution` — Última ejecución de WF1
```
Usuario envía: /last-execution
Bot responde:

⏲️ ÚLTIMA EJECUCIÓN WF1
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Hace: 3 horas 12 minutos
Timestamp: 2026-07-07 13:45:22 UTC

Estado: ✅ ÉXITO
  Grid creado: BTCUSDT
  Niveles: 8
  Grid viable: true
  Gemini decision: launch=true

Duración: 14.2 segundos

Próxima: En 48 minutos (próximo cron = 16:00 UTC)
Triggers manuales: /trigger-wf1
```

---

#### 10. `/config` — Ver configuración actual
```
Usuario envía: /config
Bot responde:

⚙️ CONFIGURACIÓN ACTUAL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 Mercado:
  Symbol: BTCUSDT
  Balance: 5000 USDT
  Risk%: 5%

🔄 Workflows:
  WF1: Cada 4 horas (próximo: 16:00 UTC)
  WF2: Cada 5 minutos (288×/día)

🛡️ Protecciones:
  MAX_POSITION_LEVELS: 3
  Max Grid Duration: 224h
  Min Notional: 50 USDT

📡 Integraciones:
  Backend: http://backend:8000 ✅
  Binance: Testnet ✅
  Gemini: Configurado ✅
  Telegram: Configurado ✅

Editar: /config-set PARAM VALUE
```

---

## 🔧 Implementación en n8n

### Patrón General para cada Trigger

```javascript
// Nodo: Telegram Webhook o Message Trigger

// Detectar comando:
const message = $json.message?.text || '';
const [command, ...args] = message.split(' ');

switch(command) {
  case '/grids':
    // GET /api/v1/grids?status=RUNNING
    break;
  case '/grid-detail':
    // GET /api/v1/grids?symbol=args[0]
    break;
  case '/history':
    // Query grid_closures tabla
    break;
  case '/stats':
    // Calcular estadísticas
    break;
  case '/trigger-wf1':
    // executeWorkflow(WF1_ID)
    break;
  // ... etc
}
```

---

## 📋 Prioridad de Implementación

| Prioridad | Comando | Complejidad | Impacto |
|-----------|---------|------------|---------|
| 🔴 **ALTA** | `/grids` | Baja | Alto: estado actual |
| 🔴 **ALTA** | `/grid-detail SYMBOL` | Media | Alto: monitoreo detallado |
| 🟡 **MEDIA** | `/history` | Media | Medio: histórico |
| 🟡 **MEDIA** | `/stats` | Media | Medio: análisis |
| 🟡 **MEDIA** | `/trigger-wf1` | Baja | Medio: manual trigger |
| 🟢 **BAJA** | `/last-execution` | Baja | Bajo: info operacional |
| 🟢 **BAJA** | `/config` | Baja | Bajo: referencia |
| 🟢 **BAJA** | `/perf SYMBOL` | Media | Bajo: análisis avanzado |

---

## 🎨 Emojis Estándar (Mantener Consistencia)

```
Estado de Grid:
  🟢 RUNNING / Activo
  🔴 CANCELED / Cerrado
  ⏳ PENDING / Por iniciar

Triggers:
  ✅ TAKE_PROFIT
  ❌ STOP_LOSS
  ⏰ EXPIRED
  🚫 MAX_POSITION
  🤷 MANUAL

Órdenes:
  ✅ FILLED
  ❌ OPEN
  ⏳ PARTIALLY_FILLED
  🛑 CANCELED

Flujos:
  🟢 ÉXITO
  🔴 ERROR
  ⏳ EJECUTANDO
  ⚙️ CONFIG
```

---

## 📱 Comandos Rápidos (Emoji Menu)

```
Opción: Agregar un nodo "Build Message" con menú inline en n8n:

🔍 Ver estado: /grids
📊 Detalles: /grid-detail BTCUSDT
📜 Histórico: /history
📈 Estadísticas: /stats
🚀 Ejecutar WF1: /trigger-wf1
🔄 Ejecutar WF2: /trigger-wf2
⏲️ Última ejecución: /last-execution
⚙️ Configuración: /config

[cada uno como botón de Telegram inline]
```

---

## 🔐 Seguridad

- ✅ Todos los comandos verifican `$env.TELEGRAM_CHAT_ID` (solo usuario autorizado)
- ✅ Comandos de escritura (`/trigger-wf1`, `/trigger-wf2`) requieren confirmación
- ✅ Rate limit: máximo 10 comandos/minuto por usuario
- ✅ Logging: todos los comandos se registran en BD (auditoría)

