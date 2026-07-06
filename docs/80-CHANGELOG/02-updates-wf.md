# 🔄 Actualizaciones de Workflows n8n para Integrar Mejoras del Backend

**Fecha:** 2026-07-05  
**Estado:** Cambios listos para aplicar en n8n UI

---

## 📝 Resumen de Cambios

Los workflows operativos en `n8n-workflows/` necesitan ser actualizados para usar todas las mejoras del backend que fueron implementadas (Fases 1-4 del runbook).

---

## ✅ WORKFLOW 1 — Market Decision

### Cambio 1: Propagar `suggested_stop_loss` y `allocated_capital`

**Nodo:** "Build Gemini Request" (Code node)  
**Línea:** Agregar al return statement JSON

**Cambio:**
```javascript
// ANTES:
return {
  json: {
    geminiRequestBody,
    symbol,
    suggested_quantity_per_order: marketData.suggested_quantity_per_order,
    atr_period: ctx.atr_period,
    atr_multiplier: ctx.atr_multiplier,
    klines_interval: ctx.klines_interval
  }
};

// DESPUÉS:
return {
  json: {
    geminiRequestBody,
    symbol,
    suggested_quantity_per_order: marketData.suggested_quantity_per_order,
    allocated_capital: marketData.allocated_capital,
    suggested_stop_loss: marketData.suggested_stop_loss,
    atr_period: ctx.atr_period,
    atr_multiplier: ctx.atr_multiplier,
    klines_interval: ctx.klines_interval
  }
};
```

---

### Cambio 2: Propagar en "Parse AI Decision"

**Nodo:** "Parse AI Decision" (Code node)  
**Línea:** Agregar al return statement

**Cambio:**
```javascript
// ANTES:
return {
  json: {
    symbol: ctx.symbol,
    reasoning: decision.reasoning,
    launch: decision.launch === true,
    lowerLimit: decision.lowerLimit,
    upperLimit: decision.upperLimit,
    gridCount: cappedGridCount,
    suggested_quantity_per_order: ctx.suggested_quantity_per_order,
    atr_period: ctx.atr_period,
    atr_multiplier: ctx.atr_multiplier,
    klines_interval: ctx.klines_interval
  }
};

// DESPUÉS:
return {
  json: {
    symbol: ctx.symbol,
    reasoning: decision.reasoning,
    launch: decision.launch === true,
    lowerLimit: decision.lowerLimit,
    upperLimit: decision.upperLimit,
    gridCount: cappedGridCount,
    suggested_quantity_per_order: ctx.suggested_quantity_per_order,
    allocated_capital: ctx.allocated_capital,
    suggested_stop_loss: ctx.suggested_stop_loss,
    atr_period: ctx.atr_period,
    atr_multiplier: ctx.atr_multiplier,
    klines_interval: ctx.klines_interval
  }
};
```

---

### Cambio 3: Usar SL en "Create Grid (POST)"

**Nodo:** "Create Grid (POST)" (HTTP Request)  
**Campo:** jsonBody

**Cambio:**
```javascript
// ANTES:
{
  symbol: $json.symbol,
  lower_price: $json.lowerLimit,
  upper_price: $json.upperLimit,
  levels: $json.gridCount,
  grid_type: 'GEOMETRIC',
  quantity_per_order: Math.max($json.suggested_quantity_per_order || 0, (65 / (($json.lowerLimit + $json.upperLimit) / 2))),
  atr_period: $json.atr_period,
  atr_multiplier: $json.atr_multiplier,
  klines_interval: $json.klines_interval,
  stop_loss: null,  // ← CAMBIO AQUI
  take_profit: null,
  max_duration_hours: null
}

// DESPUÉS:
{
  symbol: $json.symbol,
  lower_price: $json.lowerLimit,
  upper_price: $json.upperLimit,
  levels: $json.gridCount,
  grid_type: 'GEOMETRIC',
  quantity_per_order: Math.max($json.suggested_quantity_per_order || 0, (65 / (($json.lowerLimit + $json.upperLimit) / 2))),
  atr_period: $json.atr_period,
  atr_multiplier: $json.atr_multiplier,
  klines_interval: $json.klines_interval,
  stop_loss: $json.suggested_stop_loss,  // ← USA VALOR DEL ENDPOINT
  take_profit: null,
  max_duration_hours: null
}
```

---

### Cambio 4: Mostrar SL en notificación

**Nodo:** "Notify: Grid Launched" (Telegram)  
**Campo:** text

**Cambio:**
```javascript
// ANTES:
"✅ Grid lanzado: " + $json.symbol + "\n📊 ID: " + $json.grid.id + " | Niveles: " + $json.grid.levels + " | Rango: " + $json.grid.lower_price + "-" + $json.grid.upper_price + "\n💭 " + $json.reasoning

// DESPUÉS:
"✅ Grid lanzado: " + $json.symbol + "\n📊 ID: " + $json.grid.id + " | Niveles: " + $json.grid.levels + " | SL: " + $json.suggested_stop_loss + " USDT | Rango: " + $json.grid.lower_price + "-" + $json.grid.upper_price + "\n📌 Capital en riesgo: " + $json.allocated_capital + " USDT\n💭 " + $json.reasoning
```

---

## ✅ WORKFLOW 2 — Grid Monitor

### Cambio 1: Mejorar notificación de éxito en "Notify: Grid Launched"

**Nodo:** "Notify: Grid Launched" (Telegram)  
**Campo:** text

**Cambio:**
```javascript
// ANTES:
"✅ Grid " + $json.symbol + " (id: " + $json.grid.id + ") operando"

// DESPUÉS:
"✅ Grid " + $json.symbol + " (id: " + $json.grid.id + ") operando\n📌 Estado: " + $json.grid.status + "\n🔄 Ciclos activos: reposición automática en cada fill\n⏰ Duración máxima: " + ($json.grid.max_duration_hours || "Sin límite") + " horas"
```

---

### Cambio 2: Actualizar notificación de cierre para mostrar TRIGGERED

**Nodo:** "Notify: Grid Closed" (Telegram)  
**Campo:** text

**Cambio:**
```javascript
// ANTES:
"🔒 GRID CERRADO - " + $json.symbol + "\n📌 Motivo: " + ($json.triggered || "Manual") + "\n📊 PnL Total: " + ($json.grid.total_pnl || "N/A") + " USDT\n🆔 ID: " + $json.grid.id

// DESPUÉS:
"🔒 GRID CERRADO - " + $json.symbol + "\n📌 Motivo: " + ($json.triggered === 'STOP_LOSS' ? '❌ Stop Loss' : $json.triggered === 'TAKE_PROFIT' ? '✅ Take Profit' : $json.triggered === 'EXPIRED' ? '⏰ Expiración' : '🤷 Manual') + "\n📊 PnL Total: " + ($json.grid.total_pnl || "N/A") + " USDT\n🆔 ID: " + $json.grid.id\n✨ Ciclos completados: " + ($json.grid.cycles_completed || "N/A")
```

---

### Cambio 3: Agregar información en notificación de Refresh

**Nodo:** "Notify: Refresh Completed" (Telegram) — agregada si no existe

**Contenido:**
```
Cada vez que el refresh se completa exitosamente, notificar (opcional, solo si hay ciclos):

"🔄 Grid " + $json.symbol + " actualizado\n✅ Órdenes sincronizadas\n🚀 Reposición automática en proceso\n📊 Status: " + $json.grid.status
```

---

## 🔧 Cómo Aplicar los Cambios

### En n8n UI:

1. **Abre Workflow 1**
2. **Edita cada nodo mencionado arriba:**
   - Haz clic en el nodo
   - Actualiza el contenido según el cambio
   - Guarda
3. **Guarda el workflow completo**
4. **Descarga el JSON actualizado:**
   - Workflow → **Settings** → **Download** → Guarda como `workflow1-market-decision.json`
5. **Repite para Workflow 2**
6. **Reemplaza los archivos en `n8n-workflows/` del repo**
7. **Commitea al repo:**
   ```bash
   git add n8n-workflows/workflow*.json
   git commit -m "feat: integrate backend improvements into n8n workflows (Phases 1-4)

   - Workflow 1: use suggested_stop_loss from /market-analysis endpoint
   - Workflow 1: show allocated_capital in notifications
   - Workflow 2: add replication and EXPIRED trigger info to notifications
   - Both: improved feedback and observability"
   ```

---

## ✨ Resultado Final

**Workflow 1:**
- ✅ Usa SL automático del backend
- ✅ Muestra capital en riesgo en Telegram
- ✅ Transmite ALL información del análisis de mercado

**Workflow 2:**
- ✅ Notifica sobre reposición automática
- ✅ Distingue entre SL, TP, EXPIRED, Manual en cierres
- ✅ Mejor observabilidad del sistema

---

## 🚀 Próximo Paso

Una vez aplicados los cambios:
1. Re-importa los workflows en n8n desde los JSONs actualizados
2. Ejecuta `docs/manual-qa-runbook.md` para validar que todo funciona
3. Los tests deberían mostrar SL y capital asignado en notificaciones

---

**Nota:** Estos cambios son **opcionales pero recomendados** para tener visibility completa de todas las mejoras implementadas en el backend.
