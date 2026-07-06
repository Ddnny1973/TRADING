# Risk Management

## Capital en Riesgo por Grid

### Fórmula Básica

```
Capital a Arriesgar = Balance Total × Risk %

Ejemplo:
Balance: 10,000 USDT
Risk %: 2% (recomendado)
Capital a Arriesgar: 10,000 × 0.02 = 200 USDT por grid

Máximo en 2 grids simultáneas: 400 USDT (4% del balance)
```

### Risk % por Tipo de Trader

| Risk % | Perfil | Observaciones |
|--------|--------|---------------|
| 0.5% | Ultra-conservador | Pocas pérdidas posibles |
| 1% | Conservador | Bajo riesgo, bajo retorno |
| 2% | Balanceado | Recomendado |
| 5% | Agresivo | Riesgo significativo |
| 10%+ | Muy agresivo | Peligroso, no recomendado |

---

## Stop Loss (SL)

### Propósito
Limitar pérdidas si el mercado cae.

### Cálculo

```
SL Price = Lower Price × (1 - SL%)

Ejemplo:
Lower Price: 62500
SL: 2%
SL Price: 62500 × (1 - 0.02) = 61250

Si precio cae a 61250 → Grid se cierra
Pérdida máxima: 2% del capital en riesgo = 4 USDT
```

### Recomendaciones

```
SL recomendado = Capital a Arriesgar × 0.5 / Precio Promedio

Ejemplo:
Capital a Arriesgar: 200 USDT
Precio Promedio: 63500
SL recomendado: 200 × 0.5 / 63500 = 0.00157 BTC = ~100 USDT

Porcentaje: 100 / 63500 ≈ 0.16%
```

---

## Take Profit (TP)

### Propósito
Cerrar grid cuando la ganancia alcanza un nivel.

### Cálculo

```
TP Price = Upper Price × (1 + TP%)

Ejemplo:
Upper Price: 65000
TP: 5%
TP Price: 65000 × (1 + 0.05) = 68250

Si precio sube a 68250 → Grid se cierra
Ganancia máxima: ~5% (tras fees)
```

### Recomendaciones

```
TP % recomendado = Step % × Number of Cycles

Ejemplo:
Step %: 0.4%
Cycles esperados: 10
TP %: 0.4% × 10 = 4%
```

---

## Max Grids Simultáneos

### Límite: 2 Grids

```
Razón:
1. Diversificación: 2 símbolos ≠ riesgo concentrado
2. Monitoreo: 2 es manejable manualmente
3. Capital: Con 2% risk × 2 grids = 4% total exposure
4. Rate limiting: 2 grids × 15 órdenes = 30 órdenes/updates
```

### Escenario: 3 Grids

```
Status: RECHAZADO
Error: "Max concurrent grids reached (2)"
Solución: Cierra una grid antes de crear otra
```

---

## Leverage (Recomendación: 1x)

### ❌ NO USAR LEVERAGE

```
❌ Leverage 5x:
   Capital: 200 USDT
   Exposición real: 1000 USDT (5x)
   SL 2%: Pérdida 20 USDT (10% del capital)
   → Demasiado riesgo
   
✅ Leverage 1x:
   Capital: 200 USDT
   Exposición real: 200 USDT (1x)
   SL 2%: Pérdida 4 USDT (2% del capital)
   → Aceptable
```

### Configuración Binance

```
Settings → Risk Management
Leverage: 1x
Margin Type: ISOLATED (aísla riesgo por símbolo)
```

---

## Validaciones Implementadas

### Step Mínimo Rentable

```
Min Step % = 5 × 2 × Maker Fee

Ejemplo (Binance):
Maker Fee: 0.1%
Min Step %: 5 × 2 × 0.1% = 1%

Tu Grid Step: 0.4%
Validación: 0.4% < 1% → ⚠️ Warning, pero aceptado
           0.1% < 1% → ❌ RECHAZADO
```

**Lógica:** Si el paso es menor a 0.2% (5 × 2 × fees), las comisiones consumen toda la ganancia.

### Min Notional (Tamaño Mínimo)

```
Min Notional: ~10 USDT por orden

Ejemplo:
BTC Price: 62500
Min Quantity: 10 / 62500 = 0.00016 BTC

Si tu grid genera cantidad < 0.00016 BTC:
→ ❌ RECHAZADO
Solución: Aumenta capital o reduce niveles
```

### Max Duration (Expiración)

```
Max Duration = 4 × (kline_interval_hours × atr_period)

Ejemplo:
Interval: 4h
ATR Period: 14
Max Duration: 4 × (4 × 14) = 224 horas

Si grid tiene 224 horas:
→ ⚠️ Warning: Próxima expiración
→ Si > 224 horas: Automáticamente cierre
```

---

## Diversificación de Riesgo

### Un Grid

```
Symbol: BTCUSDT
Risk: 2%
Capital: 200 USDT

Riesgo: Si BTC falla, pierdo todo
```

### Dos Grids (Recomendado)

```
Grid 1:
  Symbol: BTCUSDT
  Risk: 2%
  Capital: 200 USDT

Grid 2:
  Symbol: ETHUSDT
  Risk: 2%
  Capital: 200 USDT

Total Risk: 4% (distribuido)
```

### No Correlacionado

```
✅ BTC + ETH (correlacionados ~70%, OK)
❌ BTC + BTC (100% corr, no diversifica)
❌ BTC + BTCUSDT (mismo precio)
✅ BTC + SOL (correlación baja)
```

---

## Simulación: Peor Caso

### Escenario

```
Balance: 10,000 USDT
Risk %: 2% por grid
Grids activos: 2
Total exposición: 4%

Grid 1 (BTC): Stop Loss ejecutado → Pérdida 200 USDT
Grid 2 (ETH): Stop Loss ejecutado → Pérdida 200 USDT

Total pérdida: 400 USDT (4% del balance)
Balance restante: 9,600 USDT

¿Sigo funcionando? SÍ, sistem está vivo
Recuperar pérdida: Necesito ~4 ciclos ganadores
```

---

## Checklist de Riesgo

- [ ] Risk % ≤ 2% por grid
- [ ] Max grids: 2 simultáneos
- [ ] SL setado (recomendado 2%)
- [ ] TP setado (recomendado 5%)
- [ ] Leverage: 1x (sin apalancamiento)
- [ ] Margin: ISOLATED
- [ ] Step %: ≥ 0.2%
- [ ] Notional: ≥ 10 USDT por orden
- [ ] Max duration: ≤ 224 horas
- [ ] 2 símbolos diferentes (no correlacionados 100%)

---

## Próximas Secciones

- [Fees & PnL](03-fees-pnl.md)
- [Grid Basics](01-grid-basics.md)
