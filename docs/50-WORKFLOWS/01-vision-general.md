# Visión General de Workflows

## Qué son los Workflows

Los workflows son **automatizaciones en n8n** que orquestan la creación y monitoreo de grids. Actúan como el "cerebro" del sistema.

```
Usuario / Cron
    ↓
Workflow 1 (Market Decision)
    ↓ [Decide crear grid]
    ↓
Backend [Coloca órdenes]
    ↓ [Órdenes en Binance]
    ↓
Workflow 2 (Monitor, cada 15 min)
    ↓ [Verifica fills, replenish, SL/TP]
    ↓
Backend [Sincroniza BD]
    ↓ [Loop continuo...]
```

---

## Workflow 1: Market Decision

### Propósito
Analizar mercado y **decidir si crear un nuevo grid**.

### Trigger
- **Manual:** Usuario hace click en n8n UI
- **Cron:** Cada 4 horas automáticamente (recomendado)

### Flujo
1. **Fetch Market Data**
   - Llama Backend `/market-analysis`
   - Obtiene: ATR, SMA, current price, trend

2. **AI Decision**
   - Llama OpenAI/Gemini API
   - Pregunta: "¿Es bullish? (Debe ser YES para crear grid)"
   - Prompt: "Current price {price}, ATR {atr}, SMA {sma}, trend {trend}"

3. **Create Grid (if YES)**
   - Parámetros calculados dinámicamente:
     - `lower_price` = current_price - 2.5% ATR
     - `upper_price` = current_price + 2.5% ATR
     - `levels` = 15
     - `risk_pct` = 0.02 (2%)
   - Llama Backend `/create-grid`

4. **Set Stop Loss**
   - Llama Backend `/set-stop-loss`
   - Stop loss = capital_a_arriesgar × 0.5

5. **Notify to Telegram**
   - Envía mensaje a chat Telegram
   - "✅ Grid GRID_20260705_001 created with SL at {price}"

### Duración
~15-30 segundos

### Output Esperado
```
✅ Grid created: GRID_20260705_001
   Symbol: BTCUSDT
   Levels: 15
   Stop Loss: 62250
   Orders: 15
```

---

## Workflow 2: Grid Monitor

### Propósito
**Sincronizar y monitorear grids existentes**. Ejecutar ciclos automáticos.

### Trigger
- **Cron:** Cada 15 minutos automáticamente

### Flujo
1. **Fetch Active Grids**
   - Llama Backend `/grids?status=ACTIVE`
   - Para cada grid activa:

2. **Refresh Grid**
   - Llama Backend `/refresh-grid/{grid_id}`
   - Sincroniza órdenes con Binance
   - Detecta órdenes ejecutadas (fills)

3. **Replenish Grid**
   - Llama Backend `/replenish-grid/{grid_id}`
   - Por cada BUY ejecutado → Crea SELL a precio + 0.33%
   - Por cada SELL ejecutado → Crea BUY a precio - 0.33%
   - **Esto crea ciclos automáticos**

4. **Evaluate Closures**
   - Chequea Stop Loss: Si precio baja threshold → Close
   - Chequea Take Profit: Si profit alcanzado → Close
   - Chequea EXPIRED: Si grid > max_duration → Close
   - Llama Backend `/close-grid/{grid_id}` si aplica

5. **Notify to Telegram**
   - "📊 Grids monitored: 2"
   - "✅ Orders replenished: 3"
   - "❌ Grids closed: 0" (si aplica)

### Duración
~3-5 segundos (muy rápido)

### Output Esperado
```
📊 Monitoring Results:
   Grids checked: 2
   Orders synced: 45
   Orders filled: 3
   Orders replenished: 3
   Grids closed: 0
   Timestamp: 2026-07-05T20:35:00Z
```

---

## Flujo Completo: 48 Horas

### Hour 0
- Usuario ejecuta Workflow 1 manualmente
- Grid creado: `GRID_001`
- 15 órdenes BUY en Binance

### Hour 0 - 48: Workflow 2 cada 15 min (192 ejecuciones)
- Monitoreo continuo
- A medida que BUY se ejecuta → Crea SELL
- A medida que SELL se ejecuta → Crea BUY
- **Ciclos automáticos**: BUY @ 62500 → SELL @ 62708 → BUY @ 62500 → ...

### Ejemplo de Ciclo
```
1. Grid creada con 15 órdenes BUY
2. Workflow 2 (15:00): BUY @ 62500 se ejecutó
   → Replenish: Crea SELL @ 62708
3. Workflow 2 (15:15): SELL @ 62708 se ejecutó
   → Replenish: Crea BUY @ 62500
4. Workflow 2 (15:30): BUY @ 62500 se ejecutó
   → Replenish: Crea SELL @ 62708
   → ✅ Ciclo completado, ganancia realizada
5. Repetir indefinidamente hasta SL/TP/EXPIRED
```

### PnL Esperado (después de 10 ciclos)
- Ganancia por ciclo: ~0.2% (tras fees)
- 10 ciclos en 48h: ~2% ganancia total

---

## Configuración Recomendada

### Workflow 1: Cron Schedule
- **Intervalo:** Cada 4 horas
- **Horarios:** 00:00, 04:00, 08:00, 12:00, 16:00, 20:00 UTC
- **Razón:** Análisis de mercado diario, espacio para múltiples grids

### Workflow 2: Cron Schedule
- **Intervalo:** Cada 15 minutos
- **Razón:** Rápido para capturar fills, actualizar ciclos

### n8n Settings
- **MAX_EXECUTION_TIMEOUT:** 60 segundos
- **RETRY_ON_FAIL:** Enabled (3 reintentos)
- **ERROR_NOTIFICATION:** Telegram chat

---

## Flujo por Rol

### Operador
1. Cada mañana: Revisa Telegram para notificaciones
2. Cada 4h: Opcionalmente ejecuta Workflow 1 manualmente
3. Semanalmente: Revisa PnL total

### QA/Tester
1. Ejecuta Workflow 1 manualmente
2. Espera 15 min para que Workflow 2 corra
3. Verifica órdenes en Binance
4. Repite 10+ veces en 48h

### Developer
1. Entiende el flujo completo
2. Modifica lógica de decisión (IA prompt)
3. Agrega nuevas validaciones
4. Prueba cambios localmente

---

## Integración con Backend

### Endpoints Llamados

**Workflow 1:**
```
POST /market-analysis
POST /create-grid
POST /set-stop-loss
```

**Workflow 2:**
```
GET /grids?status=ACTIVE
POST /refresh-grid/{grid_id}
POST /replenish-grid/{grid_id}
POST /close-grid/{grid_id}
POST /evaluate-closures
```

### Manejo de Errores

Si algún endpoint falla:
1. n8n reintentar 3 veces (espera 5 seg entre intentos)
2. Si sigue fallando: Notificar a Telegram
3. Workflow continúa con próxima grid

---

## Nextxt Pasos

- [Workflow 1: Market Decision](02-workflow1.md) — Detalle completo
- [Workflow 2: Monitor](03-workflow2.md) — Detalle completo
- [Setup de n8n](../20-SETUP/01-setup-n8n.md) — Cómo configurar
