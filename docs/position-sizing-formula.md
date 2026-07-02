# Position Sizing Formula — Cálculo de Quantity per Order

**Responsable del cálculo:** Función pura `calculate_position_size()` en `indicators.py`, consumida por endpoint `GET /api/v1/market-analysis/{symbol}`.

---

## Dónde vive el valor de risk_pct

**Cadena de decisión (del genérico al específico):**

```
.env.example (o .env local)
└── DEFAULT_RISK_PCT=0.02
    └── config.py::settings.DEFAULT_RISK_PCT = 0.02
        └── main.py::analyze_market(risk_pct: float = None)
            ├─ Si risk_pct se proporciona en query param → úsalo
            └─ Si no → effective_risk_pct = settings.DEFAULT_RISK_PCT (0.02)
                └── indicators.py::calculate_position_size(..., effective_risk_pct, ...)
                    └── Función genérica, recibe el número, no lo define

```

**Implicaciones:**
- **Genérico:** `calculate_position_size()` no sabe ni le importa si recibe 0.01 o 0.02 — es un parámetro
- **Centralizado:** El valor por defecto vive en **config.py** (y es configurable via .env)
- **Flexible:** Query param permite sobrescribir: `?risk_pct=0.015` → úsa 1.5%, ignorando el default

---

## Fórmula Matemática (Sin Leverage, 1-2% Riesgo)

```
capital_a_arriesgar = balance_disponible × risk_pct

precio_promedio = (lower_price + upper_price) / 2

quantity_per_order = capital_a_arriesgar / (levels × precio_promedio)
```

---

## Componentes

### 1. **balance_disponible**
- Saldo USDT disponible en la cuenta Binance Futures
- **Fuente:** `/fapi/v2/balance` (llamada firmada, HMAC-SHA256)
- **Campo clave:** `availableBalance` para USDT
- **Ejemplo:** $10,000 USDT

### 2. **risk_pct**
- Fracción del balance a arriesgar por grid
- **Rango recomendado:** 0.01 a 0.02 (1-2%)
- **No es leverage:** es el % del balance que "se arriesga" en total del grid
- **Ejemplo:** 0.02 = 2% (típico y conservador)

### 3. **lower_price, upper_price**
- Límites del grid (calculados vía ATR o manuales)
- **Fuente:** Resultado de `calculate_grid_bounds()` en el endpoint market-analysis
- **Ejemplo:** lower=42,100 USDT, upper=42,900 USDT

### 4. **precio_promedio**
- Precio medio del rango del grid
- Útil porque la mayoría de órdenes se ejecutarán cerca del promedio
- **Ejemplo:** (42,100 + 42,900) / 2 = 42,500 USDT

### 5. **levels**
- Número de órdenes en el grid
- **Ejemplo:** 10 niveles = 10 órdenes de compra distribuidas en el rango

---

## Ejemplo Numérico Completo

**Entrada:**
```
balance_disponible = 10,000 USDT
risk_pct = 0.02 (2%)
levels = 10
lower_price = 42,100 USDT
upper_price = 42,900 USDT
```

**Paso 1: Capital a arriesgar**
```
capital_a_arriesgar = 10,000 × 0.02 = 200 USDT
```

**Paso 2: Precio promedio**
```
precio_promedio = (42,100 + 42,900) / 2 = 42,500 USDT
```

**Paso 3: Quantity per order**
```
quantity_per_order = 200 / (10 × 42,500)
                   = 200 / 425,000
                   ≈ 0.00047 BTC
```

**Salida:**
```json
{
  "quantity_per_order": 0.00047,
  "notional_per_order": 0.00047 × 42,500 = $19.98 USD,
  "total_grid_notional": 0.00047 × 10 × 42,500 = $199.75 USD,
  "total_capital_at_risk": 200 USD (2% del balance)
}
```

---

## Interpretación: Qué significa "2% de riesgo"

En este contexto, `risk_pct = 0.02` significa:
- **Se asignan $200 de tu balance a este grid** (2% de $10,000)
- **Esas $200 se distribuyen equitativamente entre 10 niveles** → $20 por nivel
- **A precio promedio $42,500, eso equivale a 0.00047 BTC por orden**
- **Si el grid ejecuta todas las órdenes y el precio cae al lower_price, la pérdida máxima no realizada es ~$200**

**Es un límite de riesgo de capital, no de leverage:**
- No estás usando apalancamiento (1× notional)
- Solo estás comprometiendo el 2% de tu balance en este grid
- El 98% sigue siendo capital libre para otros grids o estrategias

---

## Recomendaciones de Risk Management

| Scenario | risk_pct | Razón |
|---|---|---|
| **Principiante / Testnet** | 0.01 (1%) | Bajo riesgo, aprender el flujo |
| **Account <$1,000** | 0.01 (1%) | Aún más conservador, errores costosos |
| **Experiencia media** | 0.02 (2%) | Balance entre oportunidad y seguridad |
| **Multiple grids activos** | 0.01-0.015 (1-1.5%) | Cada grid es independiente, evitar sobreapalancamiento acumulado |
| **Mercado muy volátil (atr_pct >2%)** | 0.01 (1%) | Reducir porque los swings son mayores |

---

## Integración con n8n Workflow

### Flujo de cálculo automático:

```
Workflow 1 (Decision Node)
  ↓
  GET /api/v1/market-analysis/BTCUSDT?risk_pct=0.02&levels=10
  ↓
  Backend:
    1. Fetch balance via /fapi/v2/balance → $10,000 USDT
    2. Fetch ATR, bounds → lower=42100, upper=42900
    3. calculate_position_size($10000, 0.02, 10, 42100, 42900) → 0.00047
  ↓
  Response:
    {
      "suggested_quantity_per_order": 0.00047,
      "suggested_lower_price": 42100.0,
      "suggested_upper_price": 42900.0
    }
  ↓
  AI Node (Claude):
    - Recibe quantity_per_order ya calculada
    - Decide: ¿launch=true y uso esta cantidad, o ajusto?
    - Devuelve: launch, gridCount, lowerLimit, upperLimit
  ↓
  POST /api/v1/grids (usa quantity_per_order del análisis o la que la IA decide)
```

---

## Cálculo Manual (sin endpoint)

Si necesitas calcular localmente o en un Function node:

```javascript
// Node.js pseudocódigo
const balance = 10000;
const risk_pct = 0.02;
const levels = 10;
const lower = 42100;
const upper = 42900;

const capital = balance * risk_pct;
const avg_price = (lower + upper) / 2;
const quantity = capital / (levels * avg_price);

console.log(`Capital: ${capital}, Qty: ${quantity}`);
// Capital: 200, Qty: 0.00047
```

---

## Limitaciones y Supuestos

- **Sin leverage:** Cantidad = notional 1× en Binance
- **Sin slippage:** Asume ejecución a los precios exactos del grid
- **Sin fees:** No resta comisiones de trading (típicamente 0.02% per side)
- **Static balance:** Calcula basado en el balance actual en el momento del endpoint call
  - Si el balance cambia antes de POST /grids, la quantity será ligeramente inexacta
  - Solución: recalcular si hay retrasos > 5 min entre análisis y creación

---

## Ajustes Dinámicos (Phase 2)

**Futuro:** La IA podría devolver `adjusted_quantity_per_order` si detecta:
- Volatilidad extrema → reduce 50%
- Múltiples grids activos → reduce 25% (para no sobre-apalancarse)
- Balance muy bajo → aumenta (porque el 2% de $500 es $10, cantidad mínima viable)

Eso es un refinamiento posterior. Por ahora, la fórmula es determinística y el AI solo la valida.
