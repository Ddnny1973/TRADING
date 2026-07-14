
## **RESUMEN: Tareas para Afinar auto_params + market_analysis**

### **NUEVA VISIÓN: Leverage + Risk DINÁMICOS + SL/TP OBLIGATORIOS**

**Estrategia:**
- ✅ **Leverage DINÁMICO** (2-5x según ATR%)
- ✅ **Risk DINÁMICO** (3-10% según ATR%)
- ✅ **SL/TP AUTO-DERIVADOS** (obligatorios, sin opción de omitir)
- ✅ **Sin riesgo liquidación** (SL termina posición antes)

---

### **MÓDULO 1: [config_auto_params.py](vscode-file://vscode-app/c:/Users/EQUIPO/AppData/Local/Programs/Microsoft%20VS%20Code/fc3def6774/resources/app/out/vs/code/electron-browser/workbench/workbench.html) - NUEVAS CONFIGURACIONES**

| Tarea | Estado | Prioridad | Detalles |
|-------|--------|-----------|----------|
| **MANTENER: LEVERAGE_BY_VOLATILITY** | ✅ KEEP | 🔴 ALTA | (2-5x según ATR%) - NO eliminar |
| **ADD: RISK_BY_VOLATILITY** | ⏳ TODO | 🔴 ALTA | Riesgo dinámico: ATR%<1%→10%, 1-3%→7%, >3%→3% |
| **ADD: STOP_LOSS_BY_VOLATILITY** | ⏳ TODO | 🔴 ALTA | SL dinámico: ATR%<1%→5%, 1-3%→8%, >3%→15% |
| **ADD: TAKE_PROFIT_BY_VOLATILITY** | ⏳ TODO | 🔴 ALTA | TP dinámico: ATR%<1%→10%, 1-3%→8%, >3%→5% |
| **ADD: Max absolutos (guardias)** | ⏳ TODO | 🔴 ALTA | MAX_RISK=15%, MAX_SL=25%, MIN_TP=2% |
| Documentar intención de cada parámetro | ⏳ TODO | 🟢 BAJA | Comentarios claros en config |

---

### **MÓDULO 2: [auto_params.py](vscode-file://vscode-app/c:/Users/EQUIPO/AppData/Local/Programs/Microsoft%20VS%20Code/fc3def6774/resources/app/out/vs/code/electron-browser/workbench/workbench.html) - FUNCIONES DE DERIVACIÓN**

| Tarea | Estado | Prioridad | Detalles |
|-------|--------|-----------|----------|
| **ADD: derive_risk_pct_dynamic(atr_pct)** | ⏳ TODO | 🔴 ALTA | Retorna risk% dinámico según RISK_BY_VOLATILITY |
| **ADD: derive_stop_loss_dynamic(atr_pct, balance)** | ⏳ TODO | 🔴 ALTA | Retorna SL en USDT según STOP_LOSS_BY_VOLATILITY |
| **ADD: derive_take_profit_dynamic(atr_pct, balance)** | ⏳ TODO | 🔴 ALTA | Retorna TP en USDT según TAKE_PROFIT_BY_VOLATILITY |
| **MODIFY: auto_derive_params() retorna SL/TP** | ⏳ TODO | 🔴 ALTA | Añadir stop_loss, take_profit, stop_loss_pct, take_profit_pct a respuesta |
| **KEEP: derive_leverage()** | ✅ DONE | 🟢 BAJA | Mantener, devuelve 2-5x dinámico |
| **KEEP: derive_risk_pct_and_levels()** | ✅ DONE | 🟢 BAJA | Validación de levels según risk_pct |
| Validar balance [10, 1M] USDT | ⏳ TODO | 🔴 ALTA | Implementar check con error claro |
| Documentar cada función con ejemplos | ⏳ TODO | 🟢 BAJA | Docstrings claros con valores esperados |

---

### **MÓDULO 3: market_analysis/{symbol} (Indicadores)**

| Tarea | Estado | Prioridad | Detalles |
|-------|--------|-----------|----------|
| **KEEP: ATR(14) cálculo** | ✅ DONE | 🟢 BAJA | Se usa bien, period=14 fijo |
| **KEEP: ER (Efficiency Ratio)** | ✅ DONE | 🟢 BAJA | Per-symbol, per-interval, correcto |
| **KEEP: Selección intervalo 1h/4h/1d** | ✅ DONE | 🟡 MED | Elige intervalo con MENOR ER (mejor dirección) |
| Validar ER_MAX_TRADEABLE threshold | ⏳ TODO | 🟡 MED | Actual: 0.35, considerar 0.40-0.50 si es necesario |
| Documentar relación ATR% → Leverage/Risk/SL/TP | ⏳ TODO | 🟡 MED | Explicar cómo ATR% controla derivaciones |

---

### **MÓDULO 4: pair_selector.py (Scoring)**

| Tarea | Estado | Prioridad | Detalles |
|-------|--------|-----------|----------|
| **KEEP: Scoring weights** | ✅ DONE | 🟢 BAJA | ER(40%) Vol(30%) ATR%(20%) Funding(10%) = OK |
| Implementar **Opción C** (historical boost) | ⏳ TODO | 🟡 MED | Query grid_closures por symbol, win_rate → boost 0.7-1.2x |
| Validar MIN_VOLUME_24H_USDT | ✅ DONE | 🟢 BAJA | 50M USDT razonable |
| Revisar MAX_SPREAD_PCT | ✅ DONE | 🟢 BAJA | 0.05% (5bps) es estricto, OK para grids |
| Revisar MAX_CANDIDATES_TO_SCORE | ⏳ TODO | 🟡 MED | Actual: 20, considerar 30-50 (vs 180 total) |

---

### **MÓDULO 5: GridRequest + schemas**

| Tarea | Estado | Prioridad | Detalles |
|-------|--------|-----------|----------|
| **MODIFY: stop_loss → auto-rellenado** | ⏳ TODO | 🔴 ALTA | Si omitido, usar derive_stop_loss_dynamic() |
| **MODIFY: take_profit → auto-rellenado** | ⏳ TODO | 🔴 ALTA | Si omitido, usar derive_take_profit_dynamic() |
| Validar balance [10, 1M] USDT | ⏳ TODO | 🔴 ALTA | Error claro si está fuera de rango |
| Documentar que SL/TP son RECOMENDADOS pero sobrescribibles | ⏳ TODO | 🟢 BAJA | Usuario puede cambiarlos si quiere |

---

## **FLUJO DE IMPLEMENTACIÓN: Leverage + Risk DINÁMICOS + SL/TP AUTO**

```
FASE 1: CONFIGURACIÓN DINÁMICA (30 min)
├─ 1. config_auto_params.py: Mantener LEVERAGE_BY_VOLATILITY (✅ ya existe)
├─ 2. config_auto_params.py: ADD RISK_BY_VOLATILITY (3-10% según ATR%)
├─ 3. config_auto_params.py: ADD STOP_LOSS_BY_VOLATILITY (5-15% pérdida)
├─ 4. config_auto_params.py: ADD TAKE_PROFIT_BY_VOLATILITY (5-10% ganancia)
├─ 5. config_auto_params.py: ADD máximos absolutos (guardias)
└─ ✅ Result: Toda config dinámmica por volatilidad en 1 lugar

FASE 2: FUNCIONES DE DERIVACIÓN (40 min)
├─ 1. auto_params.py: ADD derive_risk_pct_dynamic(atr_pct)
├─ 2. auto_params.py: ADD derive_stop_loss_dynamic(atr_pct, balance)
├─ 3. auto_params.py: ADD derive_take_profit_dynamic(atr_pct, balance)
├─ 4. auto_params.py: MODIFY auto_derive_params() retorna SL/TP
├─ 5. Test: POST /auto-params → retorna leverage, risk, SL, TP automáticos
└─ ✅ Result: Parámetros 100% auto-derivados

FASE 3: VALIDACIONES Y GUARDIAS (20 min)
├─ 1. auto_params.py: Validar balance [10, 1M] USDT
├─ 2. auto_params.py: Validar SL <= MAX_STOP_LOSS_PCT
├─ 3. auto_params.py: Validar TP >= MIN_TAKE_PROFIT_PCT
├─ 4. auto_params.py: Validar risk_pct <= MAX_RISK_PCT (máximo 15%)
├─ 5. Test: POST /auto-params con valores fuera rango → error claro
└─ ✅ Result: Sin valores inválidos, sistema robusto

FASE 4: SCHEMAS Y AUTO-RELLENO (20 min)
├─ 1. schemas/grid_schema.py: MODIFY stop_loss → auto-rellenado si omitido
├─ 2. schemas/grid_schema.py: MODIFY take_profit → auto-rellenado si omitido
├─ 3. main.py: POST /grids pre-rellena SL/TP si vienen vacíos
├─ 4. Test: POST /grids sin SL/TP → usa valores derivados
└─ ✅ Result: SL/TP OBLIGATORIOS pero user-override si quiere

FASE 5: TESTING COMPLETO (30 min)
├─ 1. Test mercado plano: ATR%=0.5% → leverage 5x, risk 10%, SL 5%, TP 10%
├─ 2. Test mercado normal: ATR%=1.5% → leverage 3x, risk 7%, SL 8%, TP 8%
├─ 3. Test mercado volátil: ATR%=5% → leverage 2x, risk 3%, SL 15%, TP 5%
├─ 4. Test límites: balance muy bajo/alto → error o adaptación
├─ 5. Test override: user puede cambiar SL/TP derivados
└─ ✅ Result: Todos los casos funcionales

FASE 6: OPCIÓN C - HISTORICAL BOOST (30 min - NEXT WEEK)
├─ 1. pair_selector.py: ADD get_symbol_historical_boost(symbol)
├─ 2. Query grid_closures para win_rate histórico
├─ 3. Apply boost: score_final = score_base × (0.7 + 0.5 × win_rate)
├─ 4. Test: Símbolos ganadores suben en ranking
└─ ✅ Result: Pair selection mejora con experiencia
```

---

## **RESPUESTA ESPERADA DE /auto-params (NUEVA VISIÓN)**

### **Input**
```bash
POST /auto-params?balance=1000&symbol=BTCUSDT
```

### **Output (EJEMPLO: Mercado plano, ATR% < 1%)**
```json
{
  "symbol": "BTCUSDT",
  "grid_viable": true,
  "params": {
    "leverage": 5,
    "risk_pct": 0.10,
    "stop_loss": 50.0,
    "take_profit": 100.0,
    "stop_loss_pct": 0.05,
    "take_profit_pct": 0.10,
    "levels": 10,
    "quantity_per_order": 25.5,
    "lower_price": 40250.0,
    "upper_price": 44750.0,
    "atr_multiplier": 2.0,
    "klines_interval": "4h",
    "atr_period": 14
  },
  "reasoning": {
    "leverage": "5x - ATR% 0.82% (plano, puede aprovechar más)",
    "risk_pct": "10% dinámico - mercado plano permite riesgo mayor",
    "stop_loss": "SL=50 USDT (5%) - tight debido a baja volatilidad",
    "take_profit": "TP=100 USDT (10%) - ganancia rápida esperada",
    "atr": "ATR=350 USDT (0.82% del precio)",
    "er": "ER=0.25 (muy eficiente, precio mueve dirección clara)"
  }
}
```

---

## **TAREAS CRÍTICAS vs NICE-TO-HAVE**

### **🔴 CRÍTICAS (PHASE 1-4, Implement esta semana)**
1. ⏳ ADD RISK_BY_VOLATILITY config
2. ⏳ ADD STOP_LOSS_BY_VOLATILITY config
3. ⏳ ADD TAKE_PROFIT_BY_VOLATILITY config
4. ⏳ ADD 3 funciones de derivación en auto_params.py
5. ⏳ MODIFY auto_derive_params() retorna SL/TP
6. ⏳ Validar balance [10, 1M] USDT
7. ⏳ AUTO-RELLENAR SL/TP en schemas

### **🟡 IMPORTANTE (PHASE 5-6, This week)**
8. ⏳ Testing completo de casos
9. ⏳ Opción C - historical boost
10. ⏳ Documentar cada función

### **🟢 NICE-TO-HAVE (Future)**
11. ⏳ Métricas de performance
12. ⏳ UI para ver parámetros derivados
13. ⏳ Alertas si SL/TP cambian mucho

---

## **RESUMEN COMPARATIVO: Antes vs Después**

| Aspecto | ANTES (Conversación 1) | AHORA (Visión Final) |
|--------|------------------------|----------------------|
| **Leverage** | 2-5x dinámico ❓ | ✅ 2-5x dinámico (MANTENER) |
| **Risk** | 15% máximo fijo | ✅ 3-10% dinámico (NUEVO) |
| **Stop Loss** | Opcional, manual | ✅ **AUTOMÁTICO, DINÁMICO** |
| **Take Profit** | Opcional, manual | ✅ **AUTOMÁTICO, DINÁMICO** |
| **Liquidación Risk** | ALTO (con 5x) | ✅ BAJO (SL protege) |
| **Complejidad** | Baja | Media (pero automática) |
| **Seguridad** | Depende del usuario | ✅ Sistema auto-protegido |
| **Aprovechamiento** | Limitado | ✅ MÁXIMO (dinámico) |

---

## **¿POR QUÉ ESTA VISIÓN ES MEJOR?**

### **Tu Razonamiento Original (CORRECTO):**
```
Leverage dinámico + Risk dinámico 
└─ PROBLEMA: Sin SL/TP = riesgo de liquidación
   
Solución: Activar SL/TP obligatorios
└─ RESULTADO: Liquidación imposible + máximo aprovechamiento
```

### **Lo Que Logramos:**
```
✅ Mercado plano (ATR% < 1%):
   └─ Leverage 5x, Risk 10%, SL 5%, TP 10%
   └─ ROI potencial: 50% en 1 trade
   └─ Pérdida máxima: 50 USDT (controlada)

✅ Mercado volátil (ATR% > 3%):
   └─ Leverage 2x, Risk 3%, SL 15%, TP 5%
   └─ ROI potencial: 10% en 1 trade
   └─ Pérdida máxima: 150 USDT (controlada)

✅ TODOS los casos: SL mata posición antes de liquidación
```

---

## **ROADMAP FINAL**

### **Semana 1 (Hoy)**
- [ ] FASE 1: Configs dinámicas (RISK/SL/TP)
- [ ] FASE 2: 3 funciones de derivación
- [ ] FASE 3: Validaciones y guardias
- [ ] FASE 4: Auto-relleno de SL/TP

### **Semana 2**
- [ ] FASE 5: Testing exhaustivo
- [ ] FASE 6: Opción C (historical boost)
- [ ] Deploy a n8n workflows

### **Semana 3**
- [ ] Monitoreo de grids reales
- [ ] Ajuste de thresholds según experiencia
- [ ] Documentación final

---

**¿INICIAMOS IMPLEMENTACIÓN?** 🚀
