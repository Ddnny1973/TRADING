---
title: "Seguimiento de tendencia: backtest de 4 años y por qué no alcanza"
type: analisis
status: hipótesis probada — resultado no robusto, no se implementa
started: 2026-11-12
updated: 2026-11-12
related: ["04-estrategia-y-portafolio.md", "06-backtester.md"]
---

# Seguimiento de tendencia (hipótesis)

**Resultado: no es una ventaja demostrable.** En 4 años la regla base gana
+61 % (12,7 %/año) con 100 USD, pero el número no resiste ninguna de las pruebas
de robustez: depende de 3 operaciones entre 531, cambia de signo con parámetros
vecinos, da ≈ 0 con 1.000 USD y ≈ 0 en el año reservado. No se implementa en el
bot.

Contexto: tras el doc 06 (el grid neutral da ≈ 0 y ningún ajuste lo arregla) se
probó la apuesta contraria, que en vez de vender volatilidad la compra.

## 1. Qué se probó

Código: `backend-python/app/backtest/trend.py` (`python -m app.backtest.trend`).
Es un simulador aparte del grid; no comparte lógica con el bot.

- **Regla** (canal de Donchian, velas diarias UTC): si el cierre supera el máximo
  de los N días previos entra largo; si cae bajo el mínimo, corto. Ejecuta a la
  apertura del día siguiente.
- **Salida:** el cierre cruza el canal contrario de M días, o se toca un stop
  fijo a 2 × ATR(20) de la entrada (si el día abre más allá del stop, sale a la
  apertura).
- **Tamaño:** cada operación arriesga el 1 % del capital hasta su stop. Máximo
  10 posiciones, apalancamiento total 2×, una posición ≤ 50 % del capital.
- **Universo:** cada día, los 20 perpetuos USDT con más volumen en los 30 días
  previos, con ≥ 90 días de historia (ranking a esa fecha).
- **Costos:** comisión taker 0,05 % y 5 bps de slippage por lado, más el funding
  real de Binance. Filtros de mainnet (`min_notional`, `step_size`).
- **Datos:** velas diarias de 520 perpetuos y funding de 241, del 2022-11-11 al
  2026-11-11. Caché en `backend-python/backtest_data/trend/` (ignorada por git).
- **Disciplina:** los últimos 12 meses (2025-11-11 → 2026-11-11) se corrieron
  aparte, con capital inicial fresco, como tramo reservado.

## 2. Resultado

Base (canal 20/10, largo y corto, 100 USD), 4 años:

| Medida | Valor |
|---|---|
| Capital final | 161,28 USD (+61,3 %; +12,7 %/año) |
| Drawdown máximo | 45,4 % |
| Sharpe (diario, anualizado) | 0,49 |
| Por año | 2022 +6 %, 2023 +22 %, 2024 +30 %, 2025 −7 %, 2026 +3 % |
| Operaciones | 531; 32 % de aciertos; factor de beneficio 1,16 |
| Largos / cortos | +99,0 / −37,7 USD |
| Comisiones / funding | 5,4 / −12,2 USD |
| Entradas descartadas por nocional mínimo | 654 (más que las ejecutadas) |

Referencia, comprar y mantener en el mismo periodo: BTC +332 % (drawdown 53 %),
ETH +59 % (drawdown 68 %). En el año reservado: BTC −28 %, ETH −40 %.

### Variantes (rentabilidad total; "reservado" = último año, corrida aparte)

| Variante | 4 años | %/año | Drawdown | Sharpe | 3 años de desarrollo (%/año) | Reservado |
|---|---|---|---|---|---|---|
| **Base 20/10** | +61 % | +12,7 | 45 % | 0,49 | +12,5 | −1,1 % |
| Canal 10/5 | +19 % | +4,5 | 52 % | 0,31 | +0,4 | +16,1 % |
| Canal 40/20 | +136 % | +23,9 | 43 % | 0,65 | +6,4 | +3,4 % |
| Canal 55/20 | +139 % | +24,4 | 41 % | 0,66 | +7,6 | +1,1 % |
| Canal 80/40 | −10 % | −2,6 | 45 % | 0,15 | +2,7 | −15,4 % |
| Canal 120/60 | −27 % | −7,6 | 53 % | 0,02 | −3,3 | −16,7 % |
| Solo largo 20/10 | +97 % | +18,5 | 47 % | 0,62 | +24,3 | −3,0 % |
| Solo largo 40/20 | +179 % | +29,3 | 40 % | 0,74 | +19,2 | −3,5 % |
| Solo largo 80/40 | −9 % | −2,3 | 45 % | 0,15 | +3,2 | −12,4 % |
| Stop 3 × ATR | +110 % | +20,4 | 34 % | 0,71 | +18,5 | +5,2 % |
| Stop 1,5 × ATR | +32 % | +7,1 | 59 % | 0,40 | +6,4 | −12,9 % |
| Universo 10 | +52 % | +11,1 | 33 % | 0,51 | +8,5 | +13,1 % |
| Universo 40 | +80 % | +15,8 | 42 % | 0,54 | +16,5 | +3,3 % |
| Riesgo 0,5 % | +46 % | +10,0 | 20 % | 0,69 | +11,0 | +8,4 % |
| Riesgo 2 % | −33 % | −9,4 | 76 % | 0,24 | −4,8 | −4,2 % |
| 5 posiciones | −1 % | −0,3 | 37 % | 0,11 | −4,6 | +5,5 % |
| **Capital 1.000, 20/10** | +5 % | +1,2 | 49 % | 0,24 | +0,8 | +3,4 % |
| Capital 1.000, 40/20 | +66 % | +13,6 | 50 % | 0,49 | −4,3 | +67,9 % |
| Slippage 15 bps | +60 % | +12,5 | 45 % | 0,49 | +14,2 | −2,4 % |
| Sin funding | +64 % | +13,2 | 48 % | 0,50 | +15,9 | −0,1 % |

## 3. Por qué no alcanza

1. **Depende de un puñado de operaciones.** Quitando solo las 3 mejores de 531,
   la base pasa de +61 a −38 USD; el canal 40/20, de +136 a −7. En el 40/20, una
   sola posición de 5 USD en AKEUSDT (0,0014 → 0,0239, ×16) aporta +95 USD de
   los +136. Eso es acertar una lotería, no una ventaja repetible.

   | Variante | Total | Sin la mejor | Sin las 3 mejores | Sin las 5 mejores |
   |---|---|---|---|---|
   | 20/10 | +61,3 | +7,9 | −38,0 | −79,8 |
   | 40/20 | +135,9 | +41,2 | −7,3 | −44,0 |
   | Solo largo 40/20 | +179,3 | +65,0 | +10,7 | −31,8 |
   | Stop 3 × ATR | +110,1 | +70,2 | +29,3 | −6,5 |
   | Riesgo 0,5 % | +46,4 | +19,6 | −3,7 | −15,4 |

2. **No es estable entre parámetros vecinos.** Canal 55/20 da +139 % y 80/40 da
   −10 %; con 10 posiciones +61 % y con 5, −1 %; con 1 % de riesgo +61 % y con
   2 %, −33 %. Una ventaja real cambia suave al mover un parámetro.
3. **Con 1.000 USD la base da +5 %.** Con 100 USD el nocional mínimo descarta 654
   entradas (las de monedas más volátiles o con mínimo alto); con 1.000 USD casi
   todas entran y el resultado se va a cero. El +61 % de la cuenta chica es, en
   buena parte, un filtro accidental.
4. **El año reservado da ≈ 0.** Entre −17 % y +16 % según la variante, sin
   patrón. No perdió en un año en que BTC cayó 28 % y ETH 40 %, que es la
   propiedad útil del seguimiento de tendencia, pero tampoco ganó.
5. **Los cortos pierden en casi todas las variantes** y los largos ganan en un
   periodo en que BTC subió 332 %. Buena parte de lo ganado es exposición al
   mercado alcista de 2023–2024, no selección.
6. **El drawdown es de 35–50 %** con Sharpe de 0,5–0,7 en las mejores variantes.
   Para un objetivo de "rendir más que un banco" es demasiado riesgo por unidad
   de retorno, aun dando el número por bueno.

## 4. Límites del backtest

- **Sesgo de supervivencia:** solo incluye perpetuos que hoy siguen listados.
  Faltan los deslistados (LUNA, FTT y similares), que habrían sido tanto cortos
  ganadores como largos perdedores.
- **Un solo ciclo de mercado** (bajista de fin de 2022, alcista 2023–2024,
  lateral-bajista 2025–2026). Cuatro años son pocas tendencias grandes.
- **Velas diarias:** el stop se evalúa contra el máximo/mínimo del día; no modela
  mechas de liquidez ni el orden intradía.
- **Filtros de hoy** aplicados a toda la historia, igual que en el doc 06.
- **Varias pruebas sobre los mismos datos:** con 20 variantes, alguna sale bien
  por azar; por eso se mira el conjunto y no la mejor.

## 5. Qué se concluye

- **No se implementa.** El seguimiento de tendencia simple no muestra una ventaja
  que justifique construirlo en el bot.
- Lo que sí deja: en este periodo fue menos malo que el grid (no perdió en el
  año bajista y tuvo esperanza ligeramente positiva en la mayoría de variantes),
  pero "ligeramente positiva, con 45 % de drawdown y dependiente de 3 aciertos"
  no es un resultado sobre el que arriesgar dinero.
- Van dos familias opuestas (vender volatilidad con el grid, comprarla con
  tendencia) sin ventaja medible con reglas simples sobre precio. Eso es lo
  esperable: son las reglas más conocidas y las más arbitradas.
- **Siguiente hipótesis a probar: cobro de funding con posición cubierta** (spot
  largo + perpetuo corto). Es la única de la lista cuyo ingreso no depende de
  predecir el precio; el funding de 241 símbolos ya está descargado en la caché.
  Requiere además precios spot y modelar el costo de entrar y salir de las dos
  patas. **Probado el mismo día: ver [08-funding-cubierto.md](08-funding-cubierto.md).**
