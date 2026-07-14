# TRADING GRID — Resumen Arquitectura Macro

**Estado de la documentación:** Este documento resume el sistema a nivel macro para entender flujos y relaciones entre APIs. Fecha: 2026-07-13

---

## 1. Visión General del Sistema

El proyecto es un **bot de grid trading híbrido** que:

- Permite trading automatizado en **Binance Futures (USDT-M)** vía grillas de órdenes (grid trading)
- Usa **n8n** como orquestador de workflows (no un scheduler interno en el backend)
- Tiene inteligencia artificial (**Gemini**) para tomar decisiones de lanzamiento
- Envía notificaciones a **Telegram**
- Backend en **Python (FastAPI)** + **SQLite** local

**Componentes principales:**

1. **Backend Python (FastAPI)** — API microservicio de trading
2. **n8n** — Orquestador de workflows (2-3 flujos automáticos)
3. **Binance API** — Lectura de datos de mercado y ejecución de órdenes
4. **Telegram** — Canal de notificaciones en tiempo real
5. **Gemini API** — IA para decisiones autónomas

---

## 2. Arquitectura a Nivel Macro

```
┌─────────────────────────────────────────────────────────────────┐
│                          USUARIOS / TRIGGERS                     │
│                                                                   │
│  • Cron (cada 4h): /lanzar grid                                  │
│  • Cron (cada 15 min): monitorear grids abiertos                 │
│  • Manual: /lanzar /monitorear desde Telegram                    │
└──────────────────┬──────────────────────────────────────────────┘
                   │
                   ▼
        ┌──────────────────────┐
        │   n8n Workflows      │  (orquestador central)
        │   (2 flujos + 1 CLI) │
        └──────┬───────────────┘
               │ HTTP
        ┌──────▼──────────────────────────────────────────────┐
        │   Backend FastAPI                                    │
        │   (puerto 8000 / 8043 en prod)                       │
        │                                                      │
        │   ├─ GET /health                                     │
        │   ├─ GET /                                           │
        │   ├─ GET /api/v1/market-analysis/{symbol}            │
        │   ├─ POST /api/v1/grids  ◄─ crea grid + órdenes     │
        │   ├─ GET  /api/v1/grids  ◄─ lista grids             │
        │   ├─ GET  /api/v1/grids/{id}  ◄─ detalles grid      │
        │   ├─ DELETE /api/v1/grids/{id}  ◄─ cancela grid     │
        │   ├─ POST /api/v1/grids/{id}/refresh  ◄─ sincroniza │
        │   ├─ GET  /api/v1/grids/{id}/pnl  ◄─ ganancias      │
        │   ├─ POST /api/v1/grids/{id}/check-close            │
        │   ├─ GET  /auto-params  ◄─ auto-calcula parámetros  │
        │                                                      │
        │   [SQLite local con histórico de grids]              │
        └──────┬───────────────────────────────────────────────┘
               │ HTTP/HTTPS
      ┌────────┴────────┬─────────────────┬──────────────────┐
      ▼                 ▼                 ▼                  ▼
   BINANCE API      GEMINI API       TELEGRAM API      LOGGING
   (websocket/       (IA Decision)   (notificaciones)  (métricas)
   REST)              │
                      │ JSON → IA decide launch=true/false
                      │ Prompt system: evalúa viabilidad
                      │ Recibe: ATR, leverage, risk, top3 pares
                      │
```

---

## 3. Flujos de Negocio

### **WORKFLOW 1: Decisión & Lanzamiento de Grid** (cron cada 4h + manual `/lanzar`)

```
Trigger (cron/manual) 
       ↓
Config node: obtiene balance y símbolo (auto o manual)
       ↓
GET /api/v1/market-analysis/{symbol}  (análisis de mercado)
       ↓
GET /auto-params?balance=X&symbol=Y  (auto-calcula params: leverage, levels, etc.)
       ↓
GEMINI API: "¿lanzar grid con estos parámetros?"
       │
       ├→ launch=true → POST /api/v1/grids  (backend crea + ejecuta órdenes)
       │                    ↓
       │              Telegram: ✅ "Grid BTCUSDT creado"
       │
       └→ launch=false → Telegram: ❌ "Decisión: No lanzar por <razón>"
```

**Endpoints Backend usados:**

- `GET /api/v1/market-analysis/{symbol}` — datos de mercado (ATR, precio actual)
- `GET /auto-params` — auto-derivación de leverage, levels, risk, etc.
- `POST /api/v1/grids` — crear grid y colocar órdenes en Binance

---

### **WORKFLOW 2: Monitor & Cierre de Grids** (cron cada 15 min + manual `/monitorear`)

```
Trigger (cron/manual)
       ↓
GET /api/v1/grids?status=RUNNING  (lista todos los grids abiertos)
       ├─ [grid_1, grid_2, ...]
       │
       ├─ Para cada grid: (loop split in batches)
       │   │
       │   ├─ POST /api/v1/grids/{id}/refresh  (sincroniza con Binance)
       │   │   ├─ Actualiza estado de órdenes (filled, canceled, etc.)
       │   │   └─ Repone órdenes ejecutadas (cycle)
       │   │
       │   ├─ POST /api/v1/grids/{id}/check-close  (evalúa SL/TP)
       │   │   │
       │   │   ├→ triggered != null  (grid debe cerrarse)
       │   │   │   └─ DELETE /api/v1/grids/{id}  (cancela todo)
       │   │   │       └─ Telegram: 🔒 "Grid BTCUSDT cerrado por <motivo>"
       │   │   │
       │   │   └→ triggered = null  (grid sigue abierto)
       │   │       └─ Telegram: 📊 "Grid <symbol> OK: PnL = +$X"
       │   │
       │   └─ Wait 1.5s (rate limiting)
       │
       └─ [loop vuelve al siguiente grid]
```

**Endpoints Backend usados:**

- `GET /api/v1/grids?status=RUNNING` — listar grids activos
- `GET /api/v1/grids/{id}/pnl` — calcular PnL actual
- `POST /api/v1/grids/{id}/refresh` — sincronizar con Binance
- `POST /api/v1/grids/{id}/check-close` — evaluar condiciones de cierre
- `DELETE /api/v1/grids/{id}` — cancelar grid

---

### **WORKFLOW 3: Monitor por Telegram (Commands & Notificaciones)**

```
User en Telegram: /lanzar, /monitorear, /status
       ↓
Telegram Trigger (webhook)
       ↓
Parse Command node
       ├─ IF chat authorized? (valida TELEGRAM_CHAT_ID)
       │  │
       │  └─ Switch: /lanzar → ejecuta Workflow 1
       │               /monitorear → ejecuta Workflow 2
       │               /status → ???
       │
       └─ Telegram: envía respuesta + resultado
```

---

## 4. Relación de APIs Backend


| Endpoint                           | Método | Propósito                                                | Usado por                     |
| ------------------------------------ | --------- | ----------------------------------------------------------- | ------------------------------- |
| `/health`                          | GET     | Healthcheck Docker                                        | n8n (verificación)           |
| `/`                                | GET     | Info del servicio                                         | n8n (debug)                   |
| `/api/v1/market-analysis/{symbol}` | GET     | Análisis de mercado (ATR, bounds)                        | Workflow 1 (pre-validación)  |
| `/auto-params`                     | GET     | Auto-calcula parámetros de grid (leverage, levels, risk) | Workflow 1 (decisión IA)     |
| `/api/v1/grids`                    | POST    | **Crea grid + coloca órdenes en Binance**                | Workflow 1 (lanzamiento)      |
| `/api/v1/grids`                    | GET     | Lista grids (filtro: status=RUNNING)                      | Workflow 2 (monitoreo)        |
| `/api/v1/grids/{id}`               | GET     | Detalles de grid específico                              | Workflow 2 (logging)          |
| `/api/v1/grids/{id}`               | DELETE  | **Cancela grid + cierra órdenes**                        | Workflow 2 (cierre)           |
| `/api/v1/grids/{id}/refresh`       | POST    | **Sincroniza con Binance + repone órdenes**              | Workflow 2 (cada 15 min)      |
| `/api/v1/grids/{id}/pnl`           | GET     | Calcula PnL realizado/no realizado                        | Workflow 2 (notificación)    |
| `/api/v1/grids/{id}/check-close`   | POST    | **Evalúa SL/TP + cierra si aplica**                      | Workflow 2 (decisión cierre) |

---

## 5. Flujo de Datos: Ejemplo End-to-End

### Escenario: Usuario ejecuta `/lanzar` en Telegram

```
User: /lanzar 5000 BTCUSDT
  ↓ [Telegram Trigger]
n8n: Parse Command → authorized? → Config (balance=5000, symbol=BTCUSDT)
  ↓ [HTTP request]
Backend GET /api/v1/market-analysis/BTCUSDT
  ├─ Fetches: precio actual, ATR(14) en interval 4h
  └─ Retorna: suggested_lower_price, suggested_upper_price, ATR
  ↓ [HTTP request]
Backend GET /auto-params?balance=5000&symbol=BTCUSDT
  ├─ Valida: balance en rango [10, 1M]
  ├─ Calcula: leverage = f(ATR%), levels = f(margen Binance), risk = 2% default
  └─ Retorna: JSON con todos los parámetros + reasoning
  ↓ [HTTP request + JS code]
n8n: Construye prompt Gemini → envía /generateContent
  ├─ Gemini recibe: ATR, leverage, risk, top_3 pares, reasoning
  ├─ IA decide: launch=true/false con reasoning
  └─ Retorna: {"launch": true, "reasoning": "..."}
  ↓ [IF: launch == true]
n8n: POST /api/v1/grids (con todos los parámetros)
  ├─ Backend: valida, calcula grid levels, coloca batch de órdenes en Binance
  ├─ Binance: ejecución atómica de ~10-20 órdenes
  └─ Backend: persiste grid en SQLite + retorna status
  ↓
n8n: Telegram notify → ✅ "Grid BTCUSDT creado, 10 niveles, PnL: 0"
```

---

## 6. Integraciones Externas

### **Binance API**

- **GET** klines (histórico de velas para ATR)
- **GET** mark price (precio actual)
- **GET** account info (balance, leverage)
- **POST** batchOrders (crear múltiples órdenes atómicamente)
- **GET** openOrders (sincronizar estado)
- **DELETE** orders (cancelar por clientOrderId)
- **GET** fills (PnL realizado)

### **Gemini API (Google)**

- **POST** `/v1beta/models/{model}/generateContent` (IA decisión launch)
- Modelo: `gemini-2.5-flash` (stable, soporta responseSchema)
- Autenticación: Header Auth `x-goog-api-key: {API_KEY}`
- Respuesta: forzada a JSON estructura (2 campos: `reasoning`, `launch`)

### **Telegram Bot API**

- **POST** `/sendMessage` (notificaciones a chat_id)
- Credentials: token de bot (configurado en n8n)
- Emojis soportados: ✅ ❌ 🔒 ⏰ 📊 etc.

---

## 7. Guardrails & Límites

### Backend

- **Max concurrent grids:** 1 por símbolo (guardarrail: 400 "already exists" si se intenta 2da vez)
- **Max total grids:** 5 (configurable `MAX_CONCURRENT_GRIDS`)
- **Balance mínimo:** 10 USDT
- **Balance máximo:** 1,000,000 USDT
- **Risk % default:** 2% (0.02)
- **Leverage default:** derivado de ATR% (rango 2-10x)
- **Max duration (grid expiration):** 4x(klines_interval × atr_period)
  - Ejemplo: 4h interval + 14 atr_period = 224h max (9 días)

### n8n (Workflow 2)

- **Polling frequency:** 15 minutos (hardcoded cron)
- **Rate limit:** 1.5s entre items (wait node)
- **Batch size:** 5 grids procesados en paralelo (split in batches)
- **Retry on error:** continue on fail (notifica error pero no detiene el loop)

### Gemini (Workflow 1)

- **Temperature:** 0.3 (bajo, decisiones determinísticas)
- **Response schema:** JSON forzado ({reasoning, launch})
- **Tokens aprox por llamada:** 400-600 input + 200 output (incluyendo "thinking")

---

## 8. Persistencia & Estado

### SQLite (Backend)

```
Tabla: grids
├─ id (UUID)
├─ symbol (BTCUSDT, etc.)
├─ status (RUNNING, CLOSED, CANCELED)
├─ orders (JSON array de órdenes)
├─ created_at, updated_at
└─ pnl_total, cycles_completed

Tabla: historical_grid_log (audit)
├─ grid_id
├─ event (created, refresh, closed)
├─ details (JSON)
└─ timestamp
```

### N8N (Workflow State)

- **Workflow 1 state:** disparado por cron cada 4h + manual `/lanzar`
  - Persiste: último grid creado (para validar no duplicar)
  - Cache: auto-params durante 5 min por balance_bucket
- **Workflow 2 state:** disparado cada 15 min + manual `/monitorear`
  - Loop recorre todos los grids RUNNING
  - Reintenta failed refreshes (max 3 intentos antes de auto-cancel)

---

## 9. Mapa de Comunicación

```
                          ┌─────────────────┐
                          │    Telegram     │
                          │   (user input)  │
                          └────────┬────────┘
                                   │ (webhook)
                    ┌──────────────▼──────────────┐
                    │         n8n Server         │
                    │   (orquestador principal)  │
                    ├──────────────┬──────────────┤
                    │ Workflow 1   │ Workflow 2   │
                    │ (cron 4h)    │ (cron 15min) │
                    │ (manual)     │              │
                    └──────────────┼──────────────┘
                                   │ HTTP
          ┌────────────────────────▼────────────────────────┐
          │      Backend Python (FastAPI)                   │
          │      (puerto 8043 en prod)                      │
          │   ┌──────────────────────────────────────┐      │
          │   │  API REST (11 endpoints)             │      │
          │   │  SQLite persistence                 │      │
          │   │  Grid calculation engine            │      │
          │   └──────────────────────────────────────┘      │
          └────────────────┬────────────────────────────────┘
                           │
          ┌────────────────┼────────────────┬──────────────┐
          │                │                │              │
          ▼                ▼                ▼              ▼
       BINANCE API      GEMINI API   TELEGRAM BOT    POSTGRES
       (datos,          (IA           (notificaciones) (logging)
       órdenes)         decisión)
```

---

## 10. Seguridad & Autenticación


| Componente       | Autenticación                        | Ubicación                |
| ------------------ | --------------------------------------- | --------------------------- |
| Binance API      | API Key + Secret (testnet/mainnet)    | Backend env vars          |
| Gemini API       | API Key (header auth)                 | n8n credentials           |
| Telegram Bot     | Bot Token                             | n8n credentials           |
| Backend Health   | No requerida (puerto local/privado)   | Abierto                   |
| Backend Grid API | No requerida (puerto 8000, red local) | Abierto                   |
| n8n Workflows    | Webhook token (implícito en n8n)     | Protegido por n8n         |
| n8n API pública | X-N8N-API-KEY header                  | Optional, usado por CI/CD |

---

## 11. Próximos Pasos & Roadmap

**Fase actual (implementada):**

- ✅ Backend con 11 endpoints
- ✅ Workflow 1: decisión + lanzamiento vía IA
- ✅ Workflow 2: monitoreo + cierre automático
- ✅ Notificaciones Telegram

**Pendiente (no implementado):**

- ❌ Redis para caché distribuida
- ❌ Webhooks salientes del backend a n8n (hoy es polling)
- ❌ Comando `/status` en Telegram
- ❌ Dashboard web de monitoreo
- ❌ Pruebas end-to-end (Workflow 2 probado en vivo, Workflow 1 parcialmente)

---

**Documento generado:** 2026-07-13
**Responsable:** Análisis de arquitectura macro para diseño de diagrama en Lucidchart
