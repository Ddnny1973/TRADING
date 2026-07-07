# Grid Trading Basics

## Qué es un Grid?

Un grid es un **conjunto de órdenes automáticas** distribuidas entre un precio inferior y superior.

```
Upper Price: 65000 ─┐
                    │
Órdenes SELL        ├─ Grid 15 niveles
Órdenes BUY         │
                    │
Lower Price: 62500 ─┘

Precio cada nivel = (upper - lower) / (levels - 1)
Precio cada nivel = (65000 - 62500) / 14 = 178.57 USDT
```

---

## Grid Simple: Cómo Funciona

### Escenario

```
Precio actual: 63500 USDT
Lower: 62500
Upper: 65000
Levels: 3 (simplicidad)
```

### Órdenes Creadas

```
Nivel 3 (Upper): 1 x SELL @ 65000
Nivel 2 (Mid):   1 x BUY  @ 63750
Nivel 1 (Lower): 1 x BUY  @ 62500
```

### Ejecución: Mercado sube

```
T=0:     Precio = 63500 (mercado actual)
         BUY @ 62500 abierta (espera)
         BUY @ 63750 abierta (espera)
         SELL @ 65000 abierta (espera)

T=1:     Precio sube a 63750
         ✅ BUY @ 63750 EJECUTADA (compré 1 BTC)
         Replenish: Crea SELL @ 64050 (precio + 0.4%)
         
         Estado: Tengo 1 BTC, esperando vender más alto

T=2:     Precio sube a 64050
         ✅ SELL @ 64050 EJECUTADA (vendí 1 BTC)
         Ganancia realizada: 64050 - 63750 = 300 USDT (tras fees: ~290 USDT)
         Replenish: Crea BUY @ 63750 (nueva orden)
         
         Estado: Sin BTC, esperando comprar más bajo

T=3:     Precio baja a 63750
         ✅ BUY @ 63750 EJECUTADA (compré 1 BTC de nuevo)
         Replenish: Crea SELL @ 64050
         
         ✅ CICLO COMPLETADO
         Ganancia total: ~290 USDT
```

---

## Grid Real: 15 Niveles

Mismo concepto, pero con 15 órdenes simultáneas:

```
Nivel 15: SELL @ 65000
Nivel 14: SELL @ 64893
Nivel 13: SELL @ 64786
...
Nivel 8:  SELL @ 64071
Nivel 7:  (sin orden, mitad del rango)
Nivel 6:  BUY @ 63929
...
Nivel 2:  BUY @ 64107
Nivel 1:  BUY @ 62500
```

### Ventajas
- **Más órdenes** = Más oportunidades de ejecución
- **Pasos pequeños** = Ciclos más rápidos
- **Riego diversificado** = No todo cae en una orden

### Desventajas
- Más órdenes = Más comisiones
- Pasos muy pequeños = No rentable tras fees

---

## Tipos de Grid

### GEOMETRIC (Geométrico)
Espacios **porcentuales** iguales.

```
Paso = 0.4% entre órdenes
Precio 1: 62500
Precio 2: 62500 × (1 + 0.004) = 62750
Precio 3: 62750 × (1 + 0.004) = 63001
```

**Ventaja:** Mejor para mercados volátiles  
**Desventaja:** Órdenes apretadas en precios altos

### ARITHMETIC (Aritmético)
Espacios **absolutos** iguales.

```
Paso = 178.57 USDT entre órdenes
Precio 1: 62500
Precio 2: 62500 + 178.57 = 62678.57
Precio 3: 62678.57 + 178.57 = 62857.14
```

**Ventaja:** Distribución uniforme  
**Desventaja:** Puede ser ineficiente en mercados calientes

---

## Dinero en Riesgo

### Cálculo

```
Capital total: 10,000 USDT
Risk %: 2%
Capital a arriesgar: 10,000 × 0.02 = 200 USDT

Cantidad por orden = 200 / (cantidad_de_niveles × precio_promedio)

Ejemplo:
Precios BUY: 62500, 62710, 62920, ... (8 niveles)
Precio promedio: 62710
Cantidad por orden = 200 / (8 × 62710) = 0.000000397 BTC

Pero Binance Futures requiere min notional de 50 USDT
Así que ajustamos a cantidad viable: ~0.0008 BTC (~50 USDT)
```

---

## Stop Loss & Take Profit

### Stop Loss (SL)
Si el mercado cae más del threshold → **CIERRA TODO**.

```
Grid lower_price: 62500
SL %: 2%
SL price: 62500 × (1 - 0.02) = 61250

Si precio cae a 61250 (o menos):
→ Cancela todas las órdenes abiertas
→ Vende cualquier posición abierta al mercado
→ Grid cierra con pérdida controlada
```

### Take Profit (TP)
Si ganancia alcanza threshold → **CIERRA TODO**.

```
Grid upper_price: 65000
TP %: 5%
TP price: 65000 × (1 + 0.05) = 68250

Si precio sube a 68250 (o más):
→ Cancela todas las órdenes abiertas
→ Vende posición abierta
→ Grid cierra con ganancia
```

---

## Expiración por Edad (Max Duration)

Grids no pueden correr indefinidamente. Hay un máximo de tiempo:

```
Max duration = 4 × (kline_interval_hours × atr_period)

Ejemplo:
Kline interval: 4h
ATR period: 14
Max duration: 4 × (4 × 14) = 224 horas (~9 días)

Si grid fue creada hace 9 días:
→ Cierra automáticamente en Workflow 2
```

---

## Ciclos y PnL

### Ciclo = BUY → SELL → BUY...

```
Ciclo 1:
  BUY @ 62500 → SELL @ 62710
  Ganancia bruta: 210 USDT
  Comisiones: ~0.25 USDT (0.02% maker × 2 lados)
  Ganancia neta: ~209.75 USDT
  PnL %: 209.75 / 62500 = 0.335%

Ciclo 2:
  BUY @ 62500 → SELL @ 62710
  Ganancia neta: ~205 USDT
  
Ciclo 10:
  BUY @ 62500 → SELL @ 62710
  Ganancia neta: ~205 USDT

Total en 10 ciclos: ~2050 USDT (2.05%)
```

### Validación: Paso Mínimo Rentable

```
Min step % = 5 × 2 × maker_fee
Min step % = 5 × 2 × 0.02% = 0.2%

Tu grid step: 0.4%
¿Es rentable? 0.4% > 0.2%? SÍ ✅

Si tu grid step < 0.2% → RECHAZADO
Razón: Comisiones consumen toda la ganancia
```

*Nota: El fee por defecto en PnL es 0.0002 (0.02%), el fee estándar maker en Binance Futures.*

---

## Cuándo Funciona un Grid

✅ **Mercado alcista (BULLISH)**
- Órdenes BUY se ejecutan
- Órdenes SELL se ejecutan
- Ciclos ocurren naturalmente

✅ **Mercado lateral (SIDEWAYS)**
- Si el rango es predecible
- Ciclos ocurren arriba-abajo

❌ **Mercado bajista (BEARISH)**
- Órdenes BUY se ejecutan pero no se venden
- SELL está arriba, nunca se ejecutan
- Sin ciclos, acumulas posición
- Stop Loss se ejecuta, pérdida

---

## Configuración Recomendada

```
Symbol: BTCUSDT
Levels: 4 (config WF1) — el backend schema acepta hasta cualquier número
Risk: 5% (config WF1 actual: risk_pct=0.05)
Lower Price: current_price - (ATR × atr_multiplier=2.0)
Upper Price: current_price + (ATR × atr_multiplier=2.0)
Leverage: 1x (sin apalancamiento)
Margin: ISOLATED (aísla riesgo)

SL: sugerido = allocated_capital × 0.5 (configurado automáticamente por WF1)
TP: null (no configurado por defecto en WF1)
Max Duration: 224 horas (4h interval × ATR14 × 4)

Expected Cycle Time: 30-120 min (depende volatilidad)
Expected PnL/Cycle: ~0.33% (step) - 0.04% (fees) = ~0.29% neto
```

---

## Próximas Secciones

- [Risk Management](02-risk-management.md)
- [Fees & PnL](03-fees-pnl.md)
