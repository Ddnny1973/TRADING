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
Workflow 2 (Monitor, cada 5 min)
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
- **Cron:** Cada 4 horas automáticamente (recomendado) — O manualmente al detectar señal de mercado

### Flujo
1. **Fetch Market Data**
   - Llama Backend `/market-analysis`
   - Obtiene: ATR, SMA, current price, trend

2. **Viabilidad Check (IF: Grid viable?)**
   - Si `grid_viable === false` → Telegram notifica y el workflow termina (no llama a Gemini)
   - Si `grid_viable === true` → continúa

3. **AI Decision (Gemini)**
   - Llama Gemini API (gemini-2.5-flash)
   - Decide si lanzar: `launch: true/false`
   - Si `launch === false` → Telegram "Grid NO lanzado" y termina

4. **Create Grid (if launch=true)**
   - Parámetros calculados dinámicamente:
     - `lower_price` / `upper_price` = de market-analysis (basados en ATR 2×)
     - `levels` = gridCount de Gemini (cappado al Config.levels = 4)
     - `risk_pct` = 0.05 (5%, configurado en nodo Config)
     - `quantity_per_order` = $json.suggested_quantity_per_order (sin Math.max)
     - `stop_loss` = $json.suggested_stop_loss (valor real, no null)
   - Llama Backend `POST /api/v1/grids`

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
- **Cron:** Cada 5 minutos automáticamente (Fase 3: Estrategia mejorada)

### Flujo
1. **Fetch Running Grids**
   - Llama Backend `GET /api/v1/grids?status=RUNNING`
   - Si no hay grids → Telegram "Sin grids en ejecución" y termina

2. **Refresh Grid (+ Replenish automático)**
   - Llama Backend `POST /api/v1/grids/{id}/refresh`
   - Sincroniza órdenes con Binance
   - El backend hace replenish internamente (BUY → SELL → BUY)

3. **Check Close**
   - Llama Backend `POST /api/v1/grids/{id}/check-close`
   - Evalúa SL, TP, EXPIRED
   - Si hay trigger → Grid se cierra automáticamente en el backend

4. **Notify to Telegram**
   - Si grid se cerró: motivo con emoji (❌ Stop Loss, ✅ Take Profit, ⏰ Expiración, 🤷 Manual)
   - Si refresh/check-close falla: error notificado, siguiente grid

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

### Hour 0 - 48: Workflow 2 cada 5 min (576 ejecuciones)
- Monitoreo continuo
- A medida que BUY se ejecuta → Crea SELL
- A medida que SELL se ejecuta → Crea BUY
- **Ciclos automáticos**: BUY @ 62500 → SELL @ 62708 → BUY @ 62500 → ...
- **Ventaja:** Detecta fills 3x más rápido (5 min vs 15 min)

### Ejemplo de Ciclo
```
1. Grid creada con 15 órdenes BUY
2. Workflow 2 (15:00): BUY @ 62500 se ejecutó
   → Replenish: Crea SELL @ 62708
3. Workflow 2 (15:05): SELL @ 62708 se ejecutó
   → Replenish: Crea BUY @ 62500
4. Workflow 2 (15:10): BUY @ 62500 se ejecutó
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
- **Intervalo:** Cada 5 minutos (nodo: "Cron: Every 5 min")
- **Razón:** Detecta fills rápido, ciclos más densos
- **Ejecuciones/día:** 288

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
2. Espera 5 min para que Workflow 2 corra
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
GET /api/v1/market-analysis/{symbol}?risk_pct=0.05&levels=4&...
POST /api/v1/grids
```

**Workflow 2:**
```
GET /api/v1/grids?status=RUNNING
POST /api/v1/grids/{id}/refresh   (incluye replenish)
POST /api/v1/grids/{id}/check-close
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
