
## **RESUMEN: Tareas para Afinar auto_params + market_analysis**

### **MÓDULO 1: [config_auto_params.py](vscode-file://vscode-app/c:/Users/EQUIPO/AppData/Local/Programs/Microsoft%20VS%20Code/fc3def6774/resources/app/out/vs/code/electron-browser/workbench/workbench.html)**


| Tarea                                       | Estado  | Prioridad | Línea                                                   |
| --------------------------------------------- | --------- | ----------- | ---------------------------------------------------------- |
| **Cambiar leverage dinámico → 1x fijo**   | ⏳ TODO | 🔴 ALTA   | Remove LEVERAGE_BY_VOLATILITY, Add GRID_LEVERAGE_FIXED=1 |
| Reducir MAX_RISK_PCT: 0.15 → 0.05          | ⏳ TODO | 🔴 ALTA   | ~16                                                      |
| Reducir LEVELS_BOUNDS: (4,20) → (4,10)     | ⏳ TODO | 🔴 ALTA   | ~27                                                      |
| Ajustar MAX_ATR_PCT_TRADEABLE (validación) | ✅ DONE | 🟡 MED    | ~25 (0.10 actual)                                        |
| Documentar parámetros en comentarios       | ⏳ TODO | 🟢 BAJA   | Global                                                   |

---

### **MÓDULO 2: [auto_params.py](vscode-file://vscode-app/c:/Users/EQUIPO/AppData/Local/Programs/Microsoft%20VS%20Code/fc3def6774/resources/app/out/vs/code/electron-browser/workbench/workbench.html)**


| Tarea                                                                                                                                                                                                         | Estado  | Prioridad | Detalles                                       |
| --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- | ----------- | ------------------------------------------------ |
| **Remove [derive_leverage()](vscode-file://vscode-app/c:/Users/EQUIPO/AppData/Local/Programs/Microsoft%20VS%20Code/fc3def6774/resources/app/out/vs/code/electron-browser/workbench/workbench.html) function** | ⏳ TODO | 🔴 ALTA   | Line ~205-216, reemplazar con leverage=1       |
| Simplificar[auto_derive_params()](vscode-file://vscode-app/c:/Users/EQUIPO/AppData/Local/Programs/Microsoft%20VS%20Code/fc3def6774/resources/app/out/vs/code/electron-browser/workbench/workbench.html)       | ⏳ TODO | 🔴 ALTA   | Remove Step 2b (leverage), hardcode leverage=1 |
| Validar[derive_risk_pct_and_levels()](vscode-file://vscode-app/c:/Users/EQUIPO/AppData/Local/Programs/Microsoft%20VS%20Code/fc3def6774/resources/app/out/vs/code/electron-browser/workbench/workbench.html)   | ✅ DONE | 🟡 MED    | Funciona bien con max 5%                       |
| Documentar derivación de risk_pct                                                                                                                                                                            | ⏳ TODO | 🟡 MED    | Añadir comentarios en función                |
| Validar[derive_levels()](vscode-file://vscode-app/c:/Users/EQUIPO/AppData/Local/Programs/Microsoft%20VS%20Code/fc3def6774/resources/app/out/vs/code/electron-browser/workbench/workbench.html) con MAX=10     | ⏳ TODO | 🟡 MED    | Verificar que acepta niveles hasta 10          |
| Documentar reasoning output                                                                                                                                                                                   | ⏳ TODO | 🟢 BAJA   | Mejorar mensajes en reasoning                  |

---

### **MÓDULO 3: market_analysis/ {symbol} (Indicadores)**


| Tarea                                      | Estado  | Prioridad | Detalles                                        |
| -------------------------------------------- | --------- | ----------- | ------------------------------------------------- |
| **Revisar ATR(14) cálculo**               | ✅ DONE | 🟢 BAJA   | Se usa bien, period=14 fijo                     |
| **Revisar ER (Efficiency Ratio)**          | ✅ DONE | 🟢 BAJA   | Per-symbol, per-interval, correcto              |
| Validar selección de intervalo (1h/4h/1d) | ✅ DONE | 🟡 MED    | Elige intervalo con MENOR ER (mejor dirección) |
| Ajustar ER_MAX_TRADEABLE threshold         | ⏳ TODO | 🟡 MED    | Actual: 0.35, considerar 0.40-0.50              |
| Revisar klines_interval bounds             | ✅ DONE | 🟢 BAJA   | ["1h", "4h", "1d"] correcto                     |
| Documentar qué cada indicador mide        | ⏳ TODO | 🟢 BAJA   | ATR=volatilidad, ER=dirección                  |

---

### **MÓDULO 4: pair_selector.py (Scoring)**


| Tarea                                       | Estado  | Prioridad | Detalles                                                   |
| --------------------------------------------- | --------- | ----------- | ------------------------------------------------------------ |
| **Revisar scoring weights**                 | ✅ DONE | 🟢 BAJA   | ER(40%) Vol(30%) ATR%(20%) Funding(10%) = OK               |
| Implementar**Opción C** (historical boost) | ⏳ TODO | 🟡 MED    | Query grid_closures por symbol, win_rate → boost 0.7-1.2x |
| Validar MIN_VOLUME_24H_USDT                 | ✅ DONE | 🟢 BAJA   | 50M USDT razonable                                         |
| Revisar MAX_SPREAD_PCT                      | ✅ DONE | 🟢 BAJA   | 0.05% (5bps) es estricto, OK para grids                    |
| Revisar MAX_CANDIDATES_TO_SCORE             | ⏳ TODO | 🟡 MED    | Actual: 20, considerar 30-50 (vs 180 total)                |
| Documentar selección de "top 3"            | ✅ DONE | 🟢 BAJA   | Retorna best + alternatives                                |

---

### **MÓDULO 5: GridRequest + Validaciones**


| Tarea                                       | Estado  | Prioridad | Detalles                             |
| --------------------------------------------- | --------- | ----------- | -------------------------------------- |
| **Validar balance: [10, 1M] USDT**          | ⏳ TODO | 🔴 ALTA   | Implementar check en /auto-params    |
| Validar stop_loss + take_profit             | ✅ DONE | 🟢 BAJA   | Schema define ambos como optional    |
| Documentar max_duration_hours               | ✅ DONE | 🟢 BAJA   | Schema define, usado en /check-close |
| Revisar grid_type (GEOMETRIC vs ARITHMETIC) | ✅ DONE | 🟢 BAJA   | Ambos soportados                     |

---

## **FLUJO RECOMENDADO DE IMPLEMENTACIÓN**


```
FASE 1: LEVERAGE (URGENTE - 20 min)
├─ 1. Editar config_auto_params.py: Remove LEVERAGE_BY_VOLATILITY, Add GRID_LEVERAGE_FIXED=1
├─ 2. Editar auto_params.py: Remove derive_leverage(), hardcode leverage=1
├─ 3. Test: POST /auto-params con múltiples símbolos → leverage siempre 1x
└─ ✅ Result: leverage=1 en todos los parámetros derivados

FASE 2: RISK PARAMETERS (20 min)
├─ 1. config_auto_params.py: MAX_RISK_PCT 0.15 → 0.05
├─ 2. config_auto_params.py: LEVELS_BOUNDS (4,20) → (4,10)
├─ 3. Test: POST /auto-params → risk_pct siempre <= 5%, levels <= 10
└─ ✅ Result: Riesgo máximo limitado a 5% del balance

FASE 3: VALIDACIONES (10 min)
├─ 1. auto_params.py: Añadir check de balance [10, 1M] USDT
├─ 2. Test: POST /auto-params con balance fuera rango → error claro
└─ ✅ Result: Grids no viables con balance inválido

FASE 4: OPCIÓN C - HISTORICAL BOOST (30 min)
├─ 1. pair_selector.py: Crear get_symbol_historical_boost(symbol)
├─ 2. Query: SELECT win_rate FROM grid_closures WHERE symbol=? GROUP BY symbol
├─ 3. Apply: score_final = score_base × (0.7 + 0.5 × win_rate)
├─ 4. Test: Símbolos ganadores suben en ranking
└─ ✅ Result: Pair selection mejora con experiencia

FASE 5: DOCUMENTACIÓN (20 min)
├─ 1. auto_params.py: Documentar risk_pct derivation
├─ 2. market_analysis: Documentar ATR + ER + interval selection
├─ 3. pair_selector.py: Documentar scoring + Opción C
└─ ✅ Result: Código autodocumentado
```

---

## **TAREAS CRÍTICAS vs NICE-TO-HAVE**

### **🔴 CRÍTICAS (Implement YA)**

1. ✅ Leverage: 1x fijo (conversación terminada)
2. ✅ MAX_RISK_PCT: 0.05
3. ✅ LEVELS_BOUNDS: (4, 10)
4. ✅ Balance validation: [10, 1M]
5. ✅ Remove derive_leverage()

### **🟡 IMPORTANTE (This Week)**

6. ⏳ Opción C - historical boost
7. ⏳ Documentar derivaciones
8. ⏳ Ajustar ER_MAX_TRADEABLE si es necesario

### **🟢 NICE-TO-HAVE (Future)**

9. ⏳ MAX_CANDIDATES_TO_SCORE: optimizar 20→30-50
10. ⏳ Mejorar reasoning messages
11. ⏳ Añadir métricas de performance

---

## **¿IMPLEMENTAMOS YA?**

**Mi recomendación:** Comenzar con **FASE 1 + FASE 2 + FASE 3** (50 min total)


```
Esto te da:
✅ Leverage seguro (1x)
✅ Riesgo controlado (5%)
✅ Validaciones robustas
✅ Listo para testing real
```

**¿Iniciamos?**
