# Ánalisis AUTO-PARAMS

**Escenario 1: Selección AUTOMÁTICA (sin moneda especificada)**

* Usuario: GET /auto-params?balance=5000  (SIN símbolo)

**Backend EVALÚA TODAS las monedas de Binance:**


```
# 1. Obtiene el universo completo de pares USDT-M
universe = [BTCUSDT, ETHUSDT, SOLUSDT, ADAUSDT, ...]  # ~180 pares

# 2. FILTRA por criterios básicos
├─ Volume 24h >= 50M USDT
├─ Spread < 0.05%
├─ ATR% <= 10%

# 3. Para los VIABLES, calcula SCORE de cada uno
for pair in viable_pairs:
    ├─ ER = Efficiency Ratio (ya vimos esto)
    ├─ Volume = volumen 24h en USDT
    ├─ ATR% = ATR / precio
    ├─ Funding = tasa de financiamiento
  
    # Puntúa cada uno
    score = 0.40*ER + 0.30*Volume_norm + 0.20*ATR%_norm + 0.10*Funding_norm

# 4. TOP 3 con score más alto
top_3 = [
    {"symbol": "BTCUSDT", "score": 0.78, "er": 0.18, "volume": 5000M},
    {"symbol": "ETHUSDT", "score": 0.72, "er": 0.15, "volume": 3000M},
    {"symbol": "SOLUSDT", "score": 0.68, "er": 0.22, "volume": 800M}
]

# 5. Elige el PRIMERO (máximo score)
chosen_symbol = "BTCUSDT"

# 6. Calcula parámetros solo para BTCUSDT
result = auto_derive_params("BTCUSDT", balance=5000)
```

**Lo que retorna a Gemini:**

* ```
  {
    "symbol": "BTCUSDT",  ← ELEGIDO automáticamente
    "symbol_selection": {
      "method": "auto",
      "candidates_evaluated": 180,
      "candidates_passed_filters": 28,
      "top_3": [
        {"symbol": "BTCUSDT", "score": 0.78, ...},
        {"symbol": "ETHUSDT", "score": 0.72, ...},
        {"symbol": "SOLUSDT", "score": 0.68", ...}
      ],
      "selected_reason": "Score 0.78: ER=0.18, vol=5000M USDT"
    },
    "params": {
      "leverage": 3,
      "levels": 10,
      "risk_pct": 0.02,
      "atr": 250,
      "klines_interval": "4h",
      ...
    }
  }
  ```

**Entonces Gemini recibe:**

* Datos de **UN símbolo** (BTCUSDT)
* PERO también ve el **top_3** (los 3 mejores evaluados)
* Usa eso para decidir si es seguro lanzar o no

---

## **Escenario 2: Selección MANUAL (moneda especificada)**

* Usuario: GET /auto-params?balance=5000&symbol=ETHUSDT  (CON símbolo)

**Backend SOLO calcula para ETHUSDT:**


```
# Salta la evaluación de todas las monedas
# Directamente:
result = auto_derive_params("ETHUSDT", balance=5000)

# Retorna
{
  "symbol": "ETHUSDT",  ← USER especificó
  "symbol_selection": {
    "method": "manual",
    "selection_skipped": True  ← No evaluó el resto
  },
  "params": {
    "leverage": 3,
    "levels": 10,
    "atr": 18,
    "klines_interval": "1h",
    ...
  }
}
```

---

## **En n8n Workflow 1: Cómo Fluye**


```
// Nodo: Get Auto Params (FIX 4)
url = "{{ $env.BACKEND_URL }}/auto-params?balance=" + balance 
      + ($symbol ? "&symbol=" + $symbol : "")
      // ↑ Si symbol viene vacío, omite el parámetro → auto-selection

// Si balance=5000, symbol="" (vacío)
// GET /auto-params?balance=5000
// Backend: evalúa 180 pares → elige BTCUSDT → retorna top_3

// Si balance=5000, symbol="ETHUSDT"
// GET /auto-params?balance=5000&symbol=ETHUSDT
// Backend: salta evaluación → solo ETHUSDT
```

---

## **Entonces ¿Qué recibe Gemini?**


```
Sistema prompt de Gemini recibe:

{
  "symbol": "BTCUSDT",
  "symbol_selection": {
    "top_3": [
      {"symbol": "BTCUSDT", "score": 0.78},
      {"symbol": "ETHUSDT", "score": 0.72},
      {"symbol": "SOLUSDT", "score": 0.68}
    ]
  },
  "params": {
    "leverage": 3,
    "levels": 10,
    "atr": 250,
    "atr_multiplier": 2.1,
    ...
  }
}

Gemini decide:
├─ ¿Es BTCUSDT seguro con leverage 3?
├─ ¿ER de 0.18 es suficientemente plano?
├─ ¿Top 3 tiene candidatos viables si queremos diversificar?
└─ launch: true/false
```

---

## **Flujo Visual Completo**


```
┌─────────────────────────────────────────────────────────────────┐
│                 Workflow 1: Decision & Launch                   │
└─────────────────────────────────────────────────────────────────┘

[Telegram: /lanzar]  (sin moneda especificada)
       ↓
[n8n Config]: balance = 5000, symbol = "" (vacío)
       ↓
[HTTP] GET /auto-params?balance=5000  (SIN symbol)
       ↓
Backend:
  1. Evalúa 180 pares USDT-M
  2. Filtra por volume, spread, ATR%
  3. Puntúa los 28 viables
  4. Top 3: BTCUSDT(0.78), ETHUSDT(0.72), SOLUSDT(0.68)
  5. Elige BTCUSDT (máximo score)
  6. Calcula parámetros para BTCUSDT
       ↓
[HTTP Response]:
{
  "symbol": "BTCUSDT",
  "top_3": [...],
  "params": { "leverage": 3, "levels": 10, ... }
}
       ↓
[n8n Code]: Build Gemini Request
       ↓
[HTTP] POST Gemini /generateContent
       ↓
Gemini recibe:
  - Símbolo elegido: BTCUSDT
  - Top 3 alternativas: ETHUSDT, SOLUSDT
  - Parámetros calculados: leverage, levels, ATR, etc.
  
Decide:
  "launch": true/false
  "reasoning": "BTCUSDT con ER 0.18 es plano, leverage 3x es conservador, pero top_3 tiene ETHUSDT mejor? Verificar funding..."
       ↓
[HTTP] POST /api/v1/grids (si launch=true)
       ↓
[Telegram] Notificación: ✅ "Grid BTCUSDT creado"
```

---

**Resumen:**

* ✅ **Sí, el backend evalúa MUCHAS monedas** (180 pares de Binance)
* ✅ **Las puntúa automáticamente** (score = ER + Volume + ATR% + Funding)
* ✅ **Elige LA MEJOR** (máximo score)
* ✅ **Calcula parámetros solo para esa 1 moneda**
* ✅ **Envía TODO a Gemini** (símbolo elegido + top_3 alternativas + parámetros)
* ✅ **Gemini decide** si lanzar o no

La clave esta en el auto-params

## **Arquitectura Actual (Capa Doble)**


```
┌─────────────────────────────────────────────────────────────┐
│                 Capa 1: /auto-params (BACKEND)               │
│  Lógica ALGORÍTMICA: selecciona par + calcula parámetros   │
│  - Score ponderado (ER, Volume, ATR%, Funding)             │
│  - Fórmulas matemáticas determinísticas                    │
│  - SIN IA, SIN aprendizaje                                 │
└─────────────────────────────────────────────────────────────┘
                           ↓ (JSON con top_3)
┌─────────────────────────────────────────────────────────────┐
│           Capa 2: Gemini IA (EN n8n Workflow 1)            │
│  Lógica de DECISIÓN: ¿lanzar o NO este grid?              │
│  - Recibe parámetros + top_3                              │
│  - Evalúa "¿es seguro lanzar BTCUSDT?"                     │
│  - Aplica heurísticas + razonamiento                       │
└─────────────────────────────────────────────────────────────┘
```

---

## **¿Qué hace cada capa hoy?**

### **Capa 1: [/auto-params](vscode-file://vscode-app/c:/Users/EQUIPO/AppData/Local/Programs/Microsoft%20VS%20Code/fc3def6774/resources/app/out/vs/code/electron-browser/workbench/workbench.html) (Algoritmo)**


```
Score = 0.40*ER + 0.30*Volume_norm + 0.20*ATR%_norm + 0.10*Funding_norm

Parámetros calculados (determinísticos):
├─ leverage = f(ATR%) → if ATR% < 1% then 5x else if < 3% then 3x else 2x
├─ levels = f(min_notional, price_range, fee_coverage)
├─ atr_multiplier = price_range / (2 * ATR)
└─ risk_pct = capital / (levels * price)
```

**Ventajas:** Rápido, reproducible, sin costo, offline
**Desventajas:** Rígido, pesos fijos, no aprende

### **Capa 2: Gemini (IA)**


Prompt: "¿Lanzar grid BTCUSDT con leverage=3, levels=10?"

IA razona:
├─ "ER=0.18 es plano ✓"
├─ "ATR% = 0.6% es bajo volatility ✓"
├─ "Funding = -0.01% es negativo, tengo que pagar, cuidado"
├─ "Top 3: ETHUSDT mejor score (0.72), pero más volátil"
└─ Decisión: launch=true/false + reasoning

**Ventajas:** Inteligente, ve contexto, puede aprender del prompt
**Desventajas:** Costo ($), latencia, no determinístico

---

## **3 Opciones Arquitectónicas**

### **OPCIÓN A: Mantener Algoritmo (ACTUAL)**


```
/auto-params: SCORE ponderado (40% ER, 30% Volume, ...)
     ↓
Gemini: "¿es seguro lanzar?"
```

✅ **Pros:**

* Barato (Gemini solo para decisión final, no selección)
* Rápido (algoritmo es instantáneo)
* Reproducible (mismos inputs = mismos outputs)
* Fácil de auditar/debuggear

❌ **Contras:**

* Pesos fijos (no adaptable a cambios de mercado)
* Si el score está mal diseñado, siempre elige mal
* No aprende de historiales

---

### **OPCIÓN B: IA en `/auto-params` (Reemplazar Algoritmo)**


```
/auto-params: GEMINI selecciona par + calcula parámetros
     ↓
Workflow 1: [HTTP] POST /api/v1/grids directamente
```

❌ **Contras graves:**

* **MUCHO MÁS CARO:** Gemini por CADA request de `/auto-params`
* **NO DETERMINÍSTICO:** cada llamada es diferente (temperature > 0)
* **LATENCIA:** + 2-3 segundos por request
* **2 LLMs:** redundante, por qué preguntar dos veces?
* **Complejidad:** parsing JSON de Gemini es frágil

---

### **OPCIÓN C: Híbrida Avanzada (RECOMENDADA si quieres mejorar)**


```
/auto-params: ALGORITMO + HISTÓRICO

├─ Calcula score como ahora
├─ PERO: consulta BD con histórico de grids cerrados
│   └─ "¿Qué pares han sido rentables antes?"
│   └─ "¿Cuál es el win rate de cada moneda?"
│
├─ Ajusta pesos dinámicamente
│   └─ Si BTCUSDT tiene 70% win rate → aumenta su score
│   └─ Si ETHUSDT tiene 40% win rate → reduce su score
│
└─ Retorna: score "inteligente" (no IA, sino data-driven)

     ↓
Gemini: "¿es seguro lanzar?" (sigue igual)
```

✅ **Pros:**

* **Mejora continua sin costo extra**
* Aprende del histórico
* Rápido (sigue siendo algoritmo)
* Determinístico (mismas condiciones = mismos ajustes)

⚠️ **Riesgo:**

* Overfitting a historiales cortos
* Sesgo si no hay suficientes datos

---

## **Mi Recomendación**

**Mantén Algoritmo en `/auto-params`, pero implementa OPCIÓN C:**


```
# backend-python/app/auto_params.py

async def calculate_pair_score(symbol, ...)：
    # Score base (como ahora)
    base_score = 0.40*ER + 0.30*Volume_norm + 0.20*ATR%_norm + 0.10*Funding
  
    # NUEVO: ajuste por histórico
    historical_winrate = await get_symbol_winrate(symbol)  # DB query
  
    # Si ganaste 70% del tiempo con BTCUSDT, bonus
    if historical_winrate > 0.60:
        boost = (historical_winrate - 0.50) * 0.1  # max +10%
        adjusted_score = base_score * (1 + boost)
    else:
        adjusted_score = base_score
  
    return adjusted_score
```

**Ventajas:**

* ✅ Mejora sin IA costosa
* ✅ Aprende de experiencia real
* ✅ Mantiene reproducibilidad
* ✅ Fácil de auditar
* ✅ Gemini sigue siendo "juez final"

---

## **¿Cuándo cambiarías a IA pura?**

Solo si:

1. **Los resultados del algoritmo son CONSISTENTEMENTE malos**
   * Ejemplo: score no correlaciona con rentabilidad
   * Solución: tuning de pesos, no reemplazar con IA
2. **Necesitas adaptación en TIEMPO REAL a cambios de mercado**
   * Ejemplo: Mercado pasa de "trending" a "lateral" y algoritmo no se adapta
   * Solución: añadir histórico + ajustes dinámicos, no IA
3. **Estrategia de trading es COMPLEJA con muchas interacciones**
   * Ejemplo: ER × Volume × Funding × Sentiment × Correlaciones
   * Solución: fine-tuned IA model en `/auto-params` (modelo local, no Gemini)

---

## **Estado Actual (Resumen)**


| Componente      | Tipo      | Costo       | Latencia | Determinismo |
| ----------------- | ----------- | ------------- | ---------- | -------------- |
| `/auto-params`  | Algoritmo | $0          | <100ms   | ✅ Sí       |
| Gemini decision | IA LLM    | ~$0.01-0.05 | 2-3s     | ❌ No        |

**Balance actual es BUENO:**

* Backend rápido y barato
* IA solo para validación final

---

## **Mi Conclusión**

**OPCIÓN RECOMENDADA: Mantén algoritmo, añade histórico**


```
Fase 1 (HOY): /auto-params = score ponderado → Gemini valida
Fase 2 (MEJORA): /auto-params = score + histórico boost → Gemini valida
Fase 3 (SI FALLA): /auto-params = fine-tuned LLM local → Gemini solo vigilancia
```



## **¿Qué información FALTA para Opción C Avanzada?**

❌ **Esto NO está disponible (pero NO es crítico):**


| Data                          | Para qué                                                                                                                                                                                                        | Cómo obtenerlo                                                                                                                                                                                                                      |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Duración promedio            | Ajustar[max_duration_hours](vscode-file://vscode-app/c:/Users/EQUIPO/AppData/Local/Programs/Microsoft%20VS%20Code/fc3def6774/resources/app/out/vs/code/electron-browser/workbench/workbench.html) dinámicamente | [closed_at - opened_at](vscode-file://vscode-app/c:/Users/EQUIPO/AppData/Local/Programs/Microsoft%20VS%20Code/fc3def6774/resources/app/out/vs/code/electron-browser/workbench/workbench.html) (está en grids + grid_closures)       |
| ROI% por símbolo             | Rentabilidad vs capital invertido                                                                                                                                                                                | [total_pnl / (levels × quantity_per_order × price_promedio)](vscode-file://vscode-app/c:/Users/EQUIPO/AppData/Local/Programs/Microsoft%20VS%20Code/fc3def6774/resources/app/out/vs/code/electron-browser/workbench/workbench.html) |
| Volatilidad (ATR%) histórico | Correlacionar con rentabilidad                                                                                                                                                                                   | Refetch klines de archivo histórico                                                                                                                                                                                                 |
| Sharpe Ratio                  | Riesgo/rendimiento                                                                                                                                                                                               | Requiere más data histórica                                                                                                                                                                                                        |
| Correlación ER vs Win%       | Mejorar score                                                                                                                                                                                                    | Cross-join grids + grid_closures                                                                                                                                                                                                     |



## **Conclusión: ¿Es suficiente?**


| Aspecto                       | Disponible?                                                                                                                                                                                        | Suficiente para Opción C? |
| ------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------- |
| **Win rate**                  | ✅ Sí ([total_pnl > 0](vscode-file://vscode-app/c:/Users/EQUIPO/AppData/Local/Programs/Microsoft%20VS%20Code/fc3def6774/resources/app/out/vs/code/electron-browser/workbench/workbench.html))     | ✅ Sí                     |
| **PnL promedio**              | ✅ Sí (guardado en`grid_closures`)                                                                                                                                                                | ✅ Sí                     |
| **Rentabilidad por símbolo** | ✅ Sí (agregar query)                                                                                                                                                                             | ✅ Sí                     |
| **Duración promedio**        | ✅ Sí (opened_at vs closed_at)                                                                                                                                                                    | ✅ Sí                     |
| **Motivo de cierre**          | ✅ Sí ([trigger_condition](vscode-file://vscode-app/c:/Users/EQUIPO/AppData/Local/Programs/Microsoft%20VS%20Code/fc3def6774/resources/app/out/vs/code/electron-browser/workbench/workbench.html)) | ✅ Sí                     |
| **Correlaciones ATR/ER**      | ❌ No (se perdió después de cálculo)                                                                                                                                                            | ❌ No es crítico          |
| **ROI%**                      | 🟡 Calculable pero no guardado                                                                                                                                                                     | 🟡 Fácil agregar          |


RIESGO.



## **¿Puede ser DINÁMICO? SÍ, 3 Opciones**

### **OPCIÓN 1: Dinámico por Volatilidad (RECOMENDADO)**


```
# Si mercado está volátil → reduce riesgo
# Si mercado está plano → aumenta riesgo

async def get_dynamic_risk_limit(symbol: str, atr_pct: float):
    """Riesgo dinámico basado en volatilidad actual"""
  
    if atr_pct > 0.05:  # Muy volátil
        return 0.08  # Máximo 8% (más conservador)
    elif atr_pct > 0.02:  # Normal
        return 0.12  # Máximo 12%
    else:  # Muy plano
        return 0.15  # Máximo 15% (máximo permitido)
```

**Ventajas:**

* ✅ Adapta a condiciones de mercado
* ✅ Menos riesgo en mercados caóticos
* ✅ Más aprovechamiento en mercados ordenados

**Implementación:** Cambiar [MAX_RISK_PCT](vscode-file://vscode-app/c:/Users/EQUIPO/AppData/Local/Programs/Microsoft%20VS%20Code/fc3def6774/resources/app/out/vs/code/electron-browser/workbench/workbench.html) a función en lugar de constante.

---

### **OPCIÓN 2: Dinámico por Histórico (Opción C)**


```
# Si símbolo ha tenido buenos resultados → aumenta riesgo un poco
# Si símbolo ha tenido pérdidas → reduce riesgo

async def get_risk_limit_by_history(symbol: str):
    """Riesgo basado en win rate histórico"""
  
    # Query histórico
    winrate = await get_symbol_winrate(symbol)  # 0-1
  
    if winrate > 0.70:  # Muy rentable
        return 0.15  # Máximo permitido
    elif winrate > 0.55:  # Rentable
        return 0.12
    elif winrate > 0.45:  # Neutral
        return 0.10
    else:  # Pérdidas
        return 0.06  # Muy conservador
```

**Ventajas:**

* ✅ Aprende de experiencia
* ✅ Reduce riesgo en símbolos problemáticos
* ✅ Aumenta en ganadores

---

### **OPCIÓN 3: Dinámico por Usuario (Entrada Manual)**


```
API Parameter:

GET /auto-params?balance=5000&symbol=BTCUSDT&risk_pct=0.05
                                                    ↑
                                           Usuario especifica 5%

Backend:
├─ Respeta 0.05 (máximo 5% en lugar del default 15%)
├─ Calcula niveles bajo ese límite
└─ Retorna parámetros más conservadores
```

**Ventajas:**

* ✅ Usuario tiene control
* ✅ Flexible según apetito de riesgo

---

## **¿De Qué DEPENDE el Riesgo?**


| Factor                      | Depende de                                                                                                                                                                                               | Cálculo                                                 |
| ----------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| **Volatilidad (ATR%)**      | Mercado                                                                                                                                                                                                  | Si ATR alto → volatilidad alta → riesgo aumenta        |
| **Leverage**                | Backend ([LEVERAGE_BY_VOLATILITY](vscode-file://vscode-app/c:/Users/EQUIPO/AppData/Local/Programs/Microsoft%20VS%20Code/fc3def6774/resources/app/out/vs/code/electron-browser/workbench/workbench.html)) | Leverage alto → margin % alto → riesgo aumenta         |
| **Número de niveles**      | Backend (calculado)                                                                                                                                                                                      | Más niveles → más capital comprometido → riesgo sube |
| **Balance**                 | Usuario                                                                                                                                                                                                  | Balance bajo → mismo grid = % riesgo más alto          |
| **Histórico del símbolo** | BD histórico                                                                                                                                                                                            | Win rate bajo → riesgo debe bajar                       |

---

## **Fórmula Actual de Riesgo**


```
risk_pct = (levels × quantity_per_order × current_price) / (leverage × balance)

Simplificado:
risk_pct = capital_a_riesgo / balance_total
```

---

## **Mi Recomendación**

**Implementa OPCIÓN 1 (Dinámico por Volatilidad) + Opción C (Histórico):**


```
# backend-python/app/auto_params.py

async def get_effective_risk_limit(symbol: str, atr_pct: float) -> Decimal:
    """
    Calcula límite de riesgo dinámico combinando:
    1. Volatilidad actual
    2. Histórico de rentabilidad
    """
  
    # Base: volatilidad
    if atr_pct > 0.05:
        base_limit = Decimal("0.08")
    elif atr_pct > 0.02:
        base_limit = Decimal("0.12")
    else:
        base_limit = Decimal("0.15")
  
    # Ajuste: histórico
    winrate = await get_symbol_winrate(symbol)
    if winrate < 0.50:
        # Símbolo problemático: reduce 30%
        adjusted = base_limit * Decimal("0.70")
    elif winrate > 0.65:
        # Símbolo ganador: aumenta 20%
        adjusted = base_limit * Decimal("1.20")
    else:
        adjusted = base_limit
  
    # Máximo global nunca excede original MAX_RISK_PCT
    return min(adjusted, Decimal("0.15"))
```

---

**Resumen de tu pregunta:**


| Aspecto                                  | Respuesta                                               |
| ------------------------------------------ | --------------------------------------------------------- |
| **¿Qué incluir para entender riesgo?** | ATR%, leverage, levels, balance, histórico             |
| **¿Puede ser dinámico?**               | ✅ Sí (volatilidad, histórico, input usuario)         |
| **¿Quién decide?**                     | Backend (límite), IA (validación), Usuario (override) |
| **¿De qué depende?**                   | Volatilidad, leverage, levels, balance, histórico      |


Leverage - StopLose

**El leverage es actualmente dinámico, pero cambiar a 1x FIJO es una decisión importante con implicaciones profundas** . Te muestro el análisis:



Estado Actual (DINÁMICO)


```
# Regla: Basado en volatilidad del par (ATR%)
ATR% < 1%   → 5x leverage (mercado muy plano, puede arriesgar más)
ATR% 1-3%   → 3x leverage (normal)
ATR% > 3%   → 2x leverage (volátil, reduce apalancamiento)

Ejemplo Real:
├─ BTCUSDT (ATR% = 0.8%) → 5x leverage
├─ ETHUSDT (ATR% = 1.5%) → 3x leverage
└─ SHIB (ATR% = 5%)     → 2x leverage
```

Propuesta: Cambiar a 1x (SIN APALANCAMIENTO)


```
# Cambio: leverage siempre = 1
# Implicación: usar SOLO capital propio, CERO margin de Binance

GRID_LEVERAGE_FIXED = 1

# Fórmula de riesgo cambia:
# ANTES: risk_pct = levels * qty * price / (leverage × balance)
# DESPUÉS: risk_pct = levels * qty * price / balance  ← 5-10x MÁS RIESGO
```



Comparativa: Dinámico vs 1x
OPCIÓN 1: Mantener Dinámico (ACTUAL)
Pros:

✅ Aprovecha mercados planos (5x cuando ATR% < 1%)
✅ Auto-protege en mercados volátiles (2x cuando ATR% > 3%)
✅ Maximiza ROI en condiciones favorables
✅ Balanceo automático: volatilidad ↑ → leverage ↓
Contras:

❌ Más complejo de entender / debuggear
❌ Mayor riesgo si parámetros ATR% mal calibrados
❌ Exposición a 5x en mercados planos (puede ser excesivo)
Riesgo Máximo Teórico:


```
Peor escenario: ATR% = 0.5%, leverage = 5x
Balance = 1000 USDT
20 niveles × 50 USDT × 5x leverage = 250 USDT de margin
risk_pct = 250 / 1000 = 25% ← ALTO
```

OPCIÓN 2: Cambiar a 1x FIJO (SIN APALANCAMIENTO)
Pros:

✅ Máxima simplicidad y seguridad
✅ Sin riesgo de liquidación (no usas margin)
✅ Más predecible (no depende de volatilidad)
✅ Ideal para testing/aprendizaje
Contras:

❌ Riesgo 5-10x MAYOR (mismo grid = mayor % de balance)
❌ ROI limitado (5x menos capital apalancado)
❌ Ineficiente: con balance bajo, grids no viables
Riesgo Máximo:


```
Mismo ejemplo:
Balance = 1000 USDT, 20 niveles × 50 USDT
risk_pct = 1000 / 1000 = 100% ← TODA el balance en riesgo
            (vs 25% con 5x leverage)
```

Mi Recomendación (FUNDADA)
Para FASE ACTUAL (que parece ser testing/validación):
→ IMPLEMENTA 1x FIJO, pero CON 2 cambios compensadores:

1. Reduce MAX_RISK_PCT (compensar riesgo)


```
# ANTES (con leverage dinámico)
MAX_RISK_PCT = 0.15  # 15% safe porque leveraged

# DESPUÉS (sin leverage)
MAX_RISK_PCT = 0.05  # 5% más conservador
```

1. Razón: Sin apalancamiento, 15% es muy agresivo. 5% protege.
2. Ajusta LEVELS_BOUNDS (menos órdenes)


```
# ANTES
LEVELS_BOUNDS = (4, 20)

# DESPUÉS  
LEVELS_BOUNDS = (4, 10)  # Máximo 10 niveles en lugar de 20
```

1. Razón: Con 1x, menos niveles = menos capital desperdigado.

Tabla de Comparativa con Cambios




| Aspecto             | Dinámico (Actual) | 1x + Ajustes |
| --------------------- | -------------------- | -------------- |
| **Leverage**        | 2x-5x              | 1x           |
| **MAX_RISK_PCT**    | 15%                | 5%           |
| **LEVELS_BOUNDS**   | 4-20               | 4-10         |
| **Riesgo por Grid** | 5-25%              | 2-5%         |
| **Liquidación**    | Posible            | ❌ Imposible |
| **Complejidad**     | Media              | Baja         |
| **ROI Teórico**    | Alto               | Medio-Bajo   |
| **Seguridad**       | Buena              | Excelente    |

Plan de Implementación (1x FIJO)
Paso 1: Cambiar config


```
# backend-python/app/config_auto_params.py

# Cambio 1: Leverage fijo
# REMOVE esto:
# LEVERAGE_BY_VOLATILITY = [...]

# ADD esto:
GRID_LEVERAGE_FIXED = 1

# Cambio 2: Reducir riesgo
MAX_RISK_PCT = Decimal("0.05")  # De 0.15 a 0.05

# Cambio 3: Reducir niveles
LEVELS_BOUNDS = (4, 10)  # De (4, 20) a (4, 10)
```

Paso 2: Simplificar auto_params.py


```
# REMOVE función:
# def derive_leverage(atr_pct: float) -> int:

# REEMPLAZAR en auto_derive_params():
# leverage = derive_leverage(atr_pct)  # ← REMOVE
leverage = 1  # ← FIXED

# SIMPLIFICAR reasoner:
reasoning["leverage"] = "Fixed at 1x (no leverage)"
```

Mi Recomendación FINAL
📊 Basada en tu contexto actual:

Si estás en fase de:

Validación de la lógica → SÍ, usa 1x
Testing de profitabilidad → SÍ, usa 1x
Producción a escala → NO, mantén dinámico
¿Por qué?

1x es más seguro → mejor para entender si el algoritmo funciona sin volatilidad externa
Dinámico es más eficiente → mejor cuando confías en los parámetros



## **Tabla Comparativa: El Punto Crítico**


| Aspecto                        | Con 5x Leverage       | Con 1x (SIN Leverage) |
| -------------------------------- | ----------------------- | ----------------------- |
| **Dinero que prestó Binance** | 4000 USDT (DEUDA)     | 0 USDT (sin deuda)    |
| **Margen requerido**           | Sí (20%)             | No                    |
| **Binance monitorea?**         | SÍ, continuamente    | NO                    |
| **¿Se liquida automática?**  | SÍ, si baja margen   | ❌ NO                 |
| **Quién cierra la posición** | Binance (forzado)     | TÚ (decides)         |
| **Pérdida en crash -17%**     | 850-900 USDT (85-90%) | 170 USDT (17%)        |
| **Control sobre decisión**    | CERO (Binance decide) | TOTAL (tú decides)   |




## **Tabla Comparativa: Precio SUBE +12.9%**


| Aspecto                           | Con 5x Leverage     | Con 1x (Sin Leverage) |
| ----------------------------------- | --------------------- | ----------------------- |
| **Inversión inicial**            | 1000 USDT           | 1000 USDT             |
| **Capital de Binance**            | 4000 USDT prestados | 0 USDT                |
| **BTC comprado**                  | 0.23 BTC            | 0.0235 BTC            |
| **Precio sube a**                 | 48,000              | 48,000                |
| **Valor posición**               | 11,040 USDT         | 1,128 USDT            |
| **Ganancia bruta**                | +1,610 USDT         | +164.5 USDT           |
| **Ganancia neta (después fees)** | +5,990 USDT         | +118 USDT             |
| **Retorno %**                     | **+599%**           | **+11.8%**            |
| **Riesgo de liquidación**        | Sí (si baja)       | ❌ No                 |
| **Control sobre posición**       | Binance (si cae)    | TÚ (siempre)         |



## **Tabla: Stop Loss + Leverage**


| Escenario | Leverage | Stop Loss | Caída -17% | Liquidación | Pérdida  |
| ----------- | ---------- | ----------- | ------------- | -------------- | ----------- |
| **A**     | 5x       | ❌ No     | Automática | Sí (margin) | -950 USDT |
| **B**     | 5x       | ✅ -150   | Controlada  | No           | -150 USDT |
| **C**     | 1x       | ❌ No     | Manual      | No           | -141 USDT |
| **D**     | 1x       | ✅ -150   | Controlada  | No           | -150 USDT |



## **MI RECOMENDACIÓN FINAL**

### **Si cambias a 1x FIJO:**


```
# OPCIÓN 1: Sin stop loss (porque no hay riesgo de liquidación)
POST /grids
{
    "symbol": "BTCUSDT",
    "balance": 1000,
    "levels": 10,
    "stop_loss": null,      # ← Desactivado
    "take_profit": 100      # ← Cierra con +100 ganancia
}
```

**Ventaja:** Simplicidad. Si cae, esperas; si no, tomas ganancia.

---

### **Si mantienes 5x LEVERAGE:**


```
# OPCIÓN 2: OBLIGATORIO stop loss (protección contra liquidación)
POST /grids
{
    "symbol": "BTCUSDT",
    "balance": 1000,
    "leverage": 5,
    "levels": 10,
    "stop_loss": 150,       # ← OBLIGATORIO: límite -150 USDT
    "take_profit": 300      # ← Objetivo +300 USDT
}
```

**Obligatorio:** Sin SL + 5x = riesgo de perder 950 en una caída sorpresa.

---

## **Configuración Recomendada para Cada Caso**

### **CASO 1: Testing (1x Seguro)**


```
{
    "symbol": "BTCUSDT",
    "balance": 1000,
    "levels": 6,
    "stop_loss": null,
    "take_profit": 50,
    "max_duration_hours": 24
}
```

**Lógica:**

* 1x → sin margen
* TP=50 (5% ganancia) → objetivo realista
* SL=null → esperas naturalmente
* 24h max → evita grids atrapadas

---

### **CASO 2: Producción (1x Moderado)**


```
{
    "symbol": "BTCUSDT",
    "balance": 1000,
    "levels": 10,
    "stop_loss": 100,
    "take_profit": 200,
    "max_duration_hours": 72
}
```

**Lógica:**

* 1x → sin riesgo de liquidación
* SL=100 (10% loss) → protección psicológica
* TP=200 (20% ganancia) → meta realista
* 72h → tiempo para convergencia

---

### **CASO 3: Aggressive (5x - SOLO si confías)**


```
{
    "symbol": "BTCUSDT",
    "balance": 1000,
    "leverage": 5,
    "levels": 8,
    "stop_loss": 100,       # ← OBLIGATORIO
    "take_profit": 500,     # ← Meta agresiva
    "max_duration_hours": 48
}
```

**Lógica:**

* 5x → ROI mayor
* **SL=100 es CRÍTICO** (protege contra liquidación)
* TP=500 (50% ganancia) → meta agresiva pero realista
* 48h → evita overnight gaps

---

## **Conclusión: ¿Qué Hacer?**

**Mi recomendación:**


```
├─ Cambiar a 1x FIJO (como dijiste)
├─ Añadir take_profit = 50-100 USDT
├─ Dejar stop_loss = null (no necesario con 1x)
└─ Activar max_duration_hours = 48h (stop time-based)
```

Esto te da:

* ✅ Seguridad (sin liquidación)
* ✅ Ganancias predecibles (TP automático)
* ✅ Tiempo limitado (no grids eternos)
* ✅ Control (puedes editar SL/TP por grid si quieres)
