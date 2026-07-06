# Fees & PnL Calculation

## Comisiones de Binance Futures

### Tarifas por Tipo de Orden

| Tipo | Tarifa | Descripción |
|------|--------|-------------|
| MAKER | 0.01% | Órdenes LIMIT que se aceptan (grid) |
| TAKER | 0.05% | Órdenes MARKET (cierre rápido) |

**Ejemplo:**
```
Orden LIMIT BUY @ 62500 (espera a ejecutarse) = MAKER
Orden MARKET BUY (ejecuta inmediato) = TAKER
```

### Comisión por Orden

```
Comisión = Notional × Tarifa

Ejemplo (MAKER):
Cantidad: 0.01 BTC
Precio: 62500
Notional: 0.01 × 62500 = 625 USDT
Comisión: 625 × 0.01% = 0.0625 USDT
```

---

## PnL de un Ciclo

### Escenario Simple

```
BUY:
  Cantidad: 0.01 BTC
  Precio: 62500 USDT
  Comisión: 625 × 0.01% = 0.0625 USDT
  Costo total: 62500 × 0.01 + 0.0625 = 625.0625 USDT

SELL:
  Cantidad: 0.01 BTC
  Precio: 62710 USDT
  Comisión: 627.10 × 0.01% = 0.06271 USDT
  Ingreso total: 62710 × 0.01 - 0.06271 = 627.09729 USDT

PnL Bruto:
  627.10 - 62500 = 210 USDT

PnL Neto (tras comisiones):
  627.09729 - 625.0625 = 2.03479 USDT
  PnL %: 2.03479 / 625.0625 = 0.325%
```

---

## Cálculo Exacto: Order Execution

### Binance usa "executedQty" y "avgPrice"

```
Orden BUY:
  orderId: 123456
  symbol: "BTCUSDT"
  side: "BUY"
  status: "FILLED"
  executedQty: 0.01
  avgPrice: 62500.00
  commission: 0.0625  (USDT)

Costo real:
  = executedQty × avgPrice + commission
  = 0.01 × 62500 + 0.0625
  = 625.0625 USDT

Orden SELL:
  executedQty: 0.01
  avgPrice: 62710.00
  commission: 0.06271

Ingreso real:
  = executedQty × avgPrice - commission
  = 0.01 × 62710 - 0.06271
  = 627.09729 USDT

PnL Neto:
  = 627.09729 - 625.0625
  = 2.03479 USDT
```

---

## Impacto de Comisiones

### Grid de 15 órdenes (8 BUY, 7 SELL)

```
Total notional: ~8 BUY × 625 + 7 SELL × 627 = 10225 USDT

Comisiones totales:
  BUY comisiones: 8 × (625 × 0.01%) = 0.5 USDT
  SELL comisiones: 7 × (627 × 0.01%) = 0.44 USDT
  Total: ~0.94 USDT

Paso entre órdenes: 0.4%
Ganancia bruta por ciclo: ~210 USDT
Ganancia neta (10 ciclos): ~210 × 10 - 0.94 × 10 ≈ 2091 USDT
PnL neto %: ~2.04%
```

---

## Validación: Step Mínimo Rentable

### Fórmula

```
Min Step % = 5 × 2 × Maker Fee
Min Step % = 5 × 2 × 0.01% = 0.1%

Razón:
1. BUY con comisión (maker 0.01%)
2. SELL con comisión (maker 0.01%)
3. Ciclo = BUY + SELL = 2 × 0.01% = 0.02%
4. Para que sea rentable: Step % > 5 × 0.02% = 0.1%
```

### Aplicación en Sistema

```
Sistema rechaza grids con step < 0.2% (double safety margin)

Tu Grid:
  Lower: 62500
  Upper: 65000
  Levels: 15
  Step: (65000 - 62500) / 14 / 62750 = 0.283%
  
  Validación: 0.283% > 0.2%? SÍ ✅ Aceptado
```

---

## Unrealized vs Realized PnL

### Unrealized PnL (Posición Abierta)

```
Tengo:
  0.05 BTC comprado @ promedio 62500

Mark Price Actual: 63500

Unrealized PnL:
  = (Mark Price - Avg Price) × Quantity
  = (63500 - 62500) × 0.05
  = 1000 × 0.05
  = 50 USDT (sin comisiones)

PnL %: 50 / (62500 × 0.05) = 0.16%
```

### Realized PnL (Ciclo Completado)

```
BUY @ 62500 (compré 0.05 BTC)
SELL @ 63500 (vendí 0.05 BTC)

Comisiones:
  BUY: 0.03125 USDT
  SELL: 0.03175 USDT

Realized PnL:
  = (63500 - 62500) × 0.05 - 0.03125 - 0.03175
  = 50 - 0.0635
  = 49.9365 USDT
```

---

## PnL Total del Grid

### Fórmula

```
Total PnL = Sum(Realized PnL per cycle) - Open Position Unrealized PnL

Ejemplo:
Ciclo 1 Realized: +49.94 USDT
Ciclo 2 Realized: +49.94 USDT
Ciclo 3 Realized: +49.94 USDT
Sum Realized: +149.82 USDT

Posición abierta (0.05 BTC):
  Unrealized: +50 USDT (mark price vs avg)

Total PnL: 149.82 + 50 = 199.82 USDT (hasta que cierre todo)
```

---

## Impacto del Leverage (⚠ No Recomendado)

### 1x Leverage (Sin Apalancamiento)

```
Capital: 200 USDT
Exposición: 200 USDT
PnL posible: ±200 USDT
Comisiones: ~1 USDT (0.5%)
```

### 5x Leverage (Peligroso)

```
Capital: 200 USDT
Exposición: 1000 USDT (5×)
PnL posible: ±1000 USDT
Comisiones: ~5 USDT (0.5% de exposición)
SL 2% = -20 USDT (10% del capital) ⚠️ Muy alto
```

---

## Métricas de Rentabilidad

### Por Ciclo

```
Step: 0.4%
Comisiones: ~0.02% (2 × maker 0.01%)
PnL neto: 0.4% - 0.02% = 0.38% por ciclo

Ejemplo:
Ciclo 1: +0.38% = +2.38 USDT (en 625 USDT)
Ciclo 2: +0.38% = +2.38 USDT
...
Ciclo 10: +0.38% = +2.38 USDT

Total: 0.38% × 10 = 3.8%
```

### Por Día

```
Ciclos esperados por día: 3-5 (depende volatilidad)

PnL diario: 0.38% × 4 ciclos = 1.52%

Capital: 625 USDT
PnL diario: 625 × 1.52% ≈ 9.5 USDT
```

### Por Semana

```
PnL semanal: 1.52% × 7 ≈ 10.6%

Capital: 625 USDT
PnL semanal: 625 × 10.6% ≈ 66 USDT
```

---

## Casos Especiales

### Closure por Stop Loss

```
Grid cerrada con SL: -2% (pérdida máxima)

Capital arriesgado: 200 USDT
Pérdida: 200 × 2% = 4 USDT

Comisiones pagadas hasta cierre: ~1 USDT
Total realizado: -5 USDT
```

### Closure por Take Profit

```
Grid cerrada con TP: +5%

Capital: 625 USDT (notional total)
Ganancia: 625 × 0.38% (step) × ciclos completados

Si TP se ejecuta después 8 ciclos:
  Ganancia: 625 × 0.38% × 8 ≈ 19 USDT
  (Aproximado, comisiones incluidas)
```

---

## Calculadora Rápida

### Ingresar
```
Capital: 625 USDT
Step %: 0.4%
Comisiones: 0.02%
Ciclos esperados: 10
```

### Resultado
```
PnL neto por ciclo: 0.4% - 0.02% = 0.38%
PnL neto total: 0.38% × 10 = 3.8%
PnL en USDT: 625 × 3.8% ≈ 23.75 USDT

Breakeven: 0.02% / 0.4% ≈ 5% de ciclos
(5% de 10 ciclos = 0.5 ciclos)
```

---

## Próximas Secciones

- [Risk Management](02-risk-management.md)
- [Grid Basics](01-grid-basics.md)
