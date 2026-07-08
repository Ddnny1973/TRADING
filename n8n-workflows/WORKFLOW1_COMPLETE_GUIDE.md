# Workflow 1: Market Decision — Versión Completa con Fixes

**Archivo:** `workflow1-market-decision-complete.json`

**Estado:** ✅ Integra todos los fixes (FIX 1, 2, 3, 4)

---

## 📊 Flujo Visual

```
┌─────────────────┐
│  Start (Manual) │  ← Usuario o Schedule Trigger (cada 4h)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Config         │  ← Define symbol=BTCUSDT, balance=5000 USDT
└────────┬────────┘
         │
         ▼
┌──────────────────────────────────────────────────────┐
│ Get Auto Params (FIX 4)                             │ ← GET /auto-params
│ Consulta: symbol, balance                           │
│ Retorna: grid_viable, params.*, current_price, ...  │
└──────────┬───────────────────────────┬──────────────┘
           │                           │
           │ ✅ grid_viable=true       │ ❌ grid_viable=false
           ▼                           ▼
    ┌──────────────────┐      ┌───────────────────────────┐
    │ IF: Viable? (FIX4)       │ Notify: Not Viable (FIX 4)│
    └────────┬─────────┘      └───────────────────────────┘
             │
             ▼
    ┌────────────────────────────────────────┐
    │ Build Gemini Request                   │ ← Usa params derivados
    │ (levels, risk_pct, atr_mult, interval) │   (NO Config estático)
    └────────┬─────────────────────────────┘
             │
             ▼
    ┌────────────────────────────────────┐
    │ Gemini: AI Decision                │ ← Modelo gemini-2.5-flash
    │ Recibe: auto-params validados      │
    │ Decide: launch = true/false        │
    └────────┬────────────────────────────┘
             │
             ▼
    ┌────────────────────────────────┐
    │ Parse AI Decision              │ ← JSON: reasoning, launch
    └────────┬──────────────────┬────┘
             │                  │
     launch=true        launch=false
             │                  │
             ▼                  ▼
    ┌─────────────────────┐  ┌──────────────────────┐
    │ IF: Launch=true?    │  │ Notify: No Launch    │
    └────────┬────────────┘  │ (IA decision reason) │
             │               └──────────────────────┘
             ▼
    ┌──────────────────────────────────────┐
    │ Create Grid (POST /api/v1/grids)     │ ← USA PARÁMETROS DERIVADOS:
    │                                      │   • levels
    │ Parámetros usados:                   │   • risk_pct → quantity_per_order
    │ • symbol (Config)                    │   • atr_multiplier
    │ • levels (auto-params.params)        │   • atr_period
    │ • quantity_per_order (calculado)     │   • klines_interval
    │ • atr_multiplier (auto-params)       │
    │ • atr_period (auto-params)           │
    │ • klines_interval (auto-params)      │
    │ • grid_type = GEOMETRIC              │
    └────────┬─────────────────────────────┘
             │
             ▼
    ┌───────────────────────────────────┐
    │ Interpret Grid Result             │ ← Valida HTTP 200/201
    └────────┬──────────────────┬───────┘
             │                  │
         error=false      error=true
             │                  │
             ▼                  ▼
    ┌──────────────────┐  ┌──────────────────────┐
    │ IF: Real Error?  │  │ Notify: Grid Error   │
    └────────┬─────────┘  │ (HTTP status + msg)  │
             │            └──────────────────────┘
             ▼
    ┌──────────────────────────────────────────┐
    │ Notify: Grid Launched                    │
    │                                          │
    │ Mensaje incluye:                         │
    │ • Grid ID                                │
    │ • Symbol, Levels, Rango                  │
    │ • Parámetros auto-derivados mostrados   │
    │ • Reasoning de IA                        │
    └──────────────────────────────────────────┘
```

---

## 🔑 Cambios principales vs workflow original

### 1. **Gate de Viabilidad (FIX 4)**
   - **Antes:** Iba directo a `Market Analysis` → `Build Gemini Request`
   - **Ahora:** `Config` → `Get Auto Params` → `IF: Grid Viable?` → continúa solo si viable

### 2. **Parámetros Derivados**
   - **Antes:** `Config` tenía `levels=4, risk_pct=0.05` hardcodeados
   - **Ahora:** Se obtienen de `/auto-params` en tiempo real:
     - `levels` (calculado por rango + fees)
     - `risk_pct` (derivado del balance)
     - `atr_multiplier` (derivado del rango real)
     - `klines_interval` (elegido por Efficiency Ratio)
     - `atr_period` = 14

### 3. **Gemini recibe contexto validado**
   - **Antes:** Gemini decidía con solo datos de mercado brutos
   - **Ahora:** Gemini recibe `autoParams` donde `grid_viable=true` ya está garantizado
     - Prompt simplificado: solo decide `launch = true/false`
     - No necesita hacer validaciones que ya pasaron el backend

### 4. **Create Grid usa parámetros derivados**
   - **Antes:** `quantity_per_order` era fijo o derivado localmente
   - **Ahora:**
     ```javascript
     quantity_per_order = risk_pct * balance / (levels * current_price)
     ```
     Usa valores exactos de `/auto-params`, no recalculos

### 5. **Notificación mejorada**
   - Muestra parámetros auto-derivados en el mensaje Telegram
   - Usuario ve: `risk_pct: 0.0111 | atr_mult: 2.3 | interval: 4h`

---

## 🚀 Instalación

**Nota:** El archivo está nombrado `workflow1-market-decision.json` para compatibilidad con CI/CD.

1. **Auto-actualización por CI/CD:**
   ```bash
   # Si tu CI/CD está configurado para importar automáticamente:
   # El archivo ya está en el directorio correcto con el nombre esperado
   # No requiere acción manual
   ```

2. **Importación manual en n8n (si no hay CI/CD):**
   ```
   En n8n UI → Import from File → seleccionar workflow1-market-decision.json
   ```

2. **Verificar credenciales n8n:**
   - ✅ Telegram Bot credential (nombre: TRADING)
   - ✅ Gemini API HTTP Header Auth credential
   - ✅ Environment variables:
     - `BACKEND_URL` = `http://backend:8000` (o tu URL)
     - `TELEGRAM_CHAT_ID` = tu chat ID

3. **Ejecutar:**
   - Manual: Click "Start" button en n8n UI
   - Automático: Se ejecuta cada 4h a las 00:00, 04:00, 08:00, etc. UTC

---

## 📋 Variables de Entrada

**De Config (puedes editar):**
- `symbol` = "BTCUSDT" (cambiar para otros pares)
- `balance` = 5000 (balance disponible en USDT)

**De /auto-params (leídas, no editadas):**
- `grid_viable` (bool)
- `current_price` (float)
- `params.levels` (int)
- `params.risk_pct` (float)
- `params.atr_multiplier` (float)
- `params.klines_interval` (str)
- `params.atr_period` (int = 14)
- `reasoning` (dict con detalles)

---

## 🔍 Debugging

### Grid no se crea (pero no hay error HTTP)
1. Revisa el log de "Parse AI Decision" → ¿`launch = false`?
   - Si sí: Ver `reasoning` en el Telegram "Grid NO LANZADO"
   - Si es error parse: Ver "Gemini: AI Decision" response

### Grid se crea pero con parámetros "raros"
1. Revisa "Get Auto Params" response
2. ¿`grid_viable = true`? ¿`params` tiene valores razonables?
3. Si no: revisar balance/symbol en Config

### Telegram no notifica
1. Revisa credencial "TRADING" en n8n
2. Verifica `TELEGRAM_CHAT_ID` env var
3. Prueba manualmente: `curl http://backend:8000/health`

---

## 🎯 Ventajas de esta versión

✅ **Seguridad:** Grid siempre viable antes de llamar Gemini
✅ **Eficiencia:** Parámetros pre-validados, Gemini solo decide
✅ **Trazabilidad:** Reasoning de IA + reasoning de auto-derivation visibles
✅ **Adaptabilidad:** Responde a cambios de balance/mercado automáticamente
✅ **Fixes Integrados:** Usa /auto-params (FIX 4) en n8n workflow

---

## 📝 Notas

- El workflow puede modificarse en n8n UI después de importar
- No editar IDs de nodos (n8n los regenera)
- Si necesitas diferentes `balance` por ejecución, agregar un nodo de input
- La rama FALSE de "IF: Grid Viable?" está lista para agregar lógica adicional
- Gemini prompt puede ajustarse en "Build Gemini Request" según necesidad

