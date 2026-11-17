---
title: "Funding extremo como señal de dirección: backtest de 4 años"
type: analisis
status: hipótesis probada — no pasa los criterios fijados de antemano; línea cerrada
started: 2026-11-17
updated: 2026-11-17
related: ["06-backtester.md", "07-seguimiento-tendencia.md", "08-funding-cubierto.md"]
---

# Funding extremo como señal de dirección (hipótesis)

**Resultado: no pasa.** De los siete criterios fijados antes de correr, cumple
cinco y falla dos, y el +25 % de la base se explica casi por completo con **una
sola operación**. Se cierra la línea "funding como señal de dirección" sin
afinar parámetros para rescatarla.

## 1. Hipótesis

Un funding muy alto significa que hay demasiados compradores apalancados pagando
por mantener sus largos; uno muy negativo, lo contrario. Ese posicionamiento
suele deshacerse con un movimiento contrario al de la multitud. A diferencia del
doc 08, aquí el funding no es el ingreso sino la **información**: se opera la
dirección del precio.

- Funding alto sostenido → **corto** en el perpetuo (además, el corto cobra el
  funding mientras dura).
- Funding muy negativo sostenido → **largo**.

## 2. Diseño (fijado antes de correr)

Código: `backend-python/app/backtest/fundsig.py` (`python -m app.backtest.fundsig`).
Reusa el motor del doc 07 (`trend.py`: ejecución a la apertura siguiente, stop por
ATR, tamaño por riesgo, universo por volumen a cada fecha, comisiones, slippage y
funding real). Solo cambia la señal, mediante el gancho `_decide`. Es un
simulador aparte; no comparte lógica con el bot.

Configuración base:

| Parámetro | Valor |
|---|---|
| Señal | funding medio de 3 días, anualizado, supera ±50 %/año (≈ ±0,046 % por 8 h) |
| Lados | corto con funding alto, largo con funding negativo |
| Salida | a los 5 días, o al tocar el stop de 2,5 × ATR(20) |
| Entradas | hasta 3 nuevas por lado y día, 10 posiciones, nocional ≤ 50 % del capital por posición |
| Riesgo | 1 % del capital por operación, 100 USD, apalancamiento total ≤ 2× |
| Universo | 20 perpetuos con más volumen en los 30 días previos |
| Costos | taker 0,05 % + 5 bps de slippage por lado, funding real (el día de entrada cuenta 2 de 3 cobros) |

Periodos (iguales a los docs 07 y 08): total 2022-11-11 → 2026-11-11; desarrollo
2022-11-11 → 2025-11-11; **reservado** 2025-11-11 → 2026-11-11 (capital inicial
fresco, no se usa para elegir nada).

Rejilla de vecinos (27 celdas): umbral {30 %, 50 %, 100 %} × media de {1, 3, 7}
días × permanencia de {3, 5, 10} días.

Controles (placebos), con la misma regla y los mismos costos:

- **Funding desfasado** 90, 180 y 270 días (se usa el funding de otro momento del
  periodo, dando la vuelta al final): una señal sin información.
- **Señal invertida:** largo con funding alto y corto con funding negativo.

## 3. Criterio de aprobación (fijado antes de correr)

La hipótesis pasa **solo si se cumplen las siete condiciones**:

1. La configuración base es positiva, neta de costos, en el desarrollo **y** en el
   periodo reservado.
2. En la rejilla de 27 celdas, al menos 2/3 son positivas en el desarrollo y al
   menos 2/3 en el reservado.
3. El resultado base de los 4 años, quitando sus 3 mejores operaciones, sigue
   siendo positivo.
4. Con 1.000 USD la base sigue siendo positiva en los 4 años.
5. El drawdown máximo de la base en los 4 años es menor a 25 %.
6. La base de los 4 años rinde más que cada uno de los tres placebos de
   funding desfasado.
7. La base de los 4 años rinde más que la señal invertida.

Si falla cualquiera, se da por cerrada la línea "funding como señal de dirección"
y no se afinan parámetros para rescatarla.

## 4. Resultado

### Veredicto por criterio (evaluado por código, `fundsig_grid.json`)

| # | Criterio | Resultado | Valor |
|---|---|---|---|
| 1 | Base positiva en desarrollo y reservado | ✅ | +6,2 % y +20,3 % |
| 2 | ≥ 2/3 de las 27 celdas positivas en ambos | ❌ | desarrollo 17 de 27 (63 %), reservado 27 de 27 |
| 3 | Sin sus 3 mejores operaciones sigue positiva | ❌ | −1,1 USD |
| 4 | Con 1.000 USD positiva | ✅ | +43,1 % |
| 5 | Drawdown < 25 % | ✅ | 3,8 % |
| 6 | Mejor que cada placebo desfasado | ✅ | +25,2 % contra +1,2 %, −0,7 % y +11,0 % |
| 7 | Mejor que la señal invertida | ✅ | +25,2 % contra −11,0 % |

El criterio 2 falla por poco (63 % contra 67 %); no se redefine el umbral después
de ver el número.

### Base y controles (4 años)

| Variante | Rentabilidad | %/año | Drawdown | Operaciones | Largos / cortos (USD) |
|---|---|---|---|---|---|
| **Base (100 USD)** | +25,2 % | +5,8 | 3,8 % | 44 | +26,3 / −1,0 |
| Base con 1.000 USD | +43,1 % | +9,4 | 11,5 % | 459 | +439,3 / −8,0 (sobre 1.000) |
| Solo largos | +25,7 % | +5,9 | 4,5 % | 37 | +25,7 / 0 |
| Solo cortos | −0,1 % | 0,0 | 2,0 % | 4 | 0 / −0,1 |
| Placebo desfasado 90 días | +1,2 % | +0,3 | 6,2 % | 50 | |
| Placebo desfasado 180 días | −0,7 % | −0,2 | 4,5 % | 49 | |
| Placebo desfasado 270 días | +11,0 % | +2,6 | 1,8 % | 39 | |
| Señal invertida | −11,0 % | −2,9 | 11,9 % | 31 | |

## 5. Lectura

1. **Una operación explica el 84 % de la ganancia.** `RAVEUSDT`, del 13 al 18 de
   abril de 2026: entró a 5,97 y salió a 21,93 (+267 % en 5 días) y aportó +21,2 de
   los +25,2 USD. Sin ella, la base da +4,0 USD en 4 años (≈ 1 %/año). Con 1.000
   USD, esa misma operación suma 254,8 de 431,3 (59 %); sin ella quedan +176,6
   (≈ 4,4 %/año). Es el mismo patrón del doc 07 (un acierto enorme en una moneda
   pequeña).
2. **Es una estrategia de largos, y la mitad "funding alto → corto" no se pudo
   probar.** Con umbral de 50 %/año hubo 4 operaciones cortas en 4 años: un
   funding sostenido de ese nivel casi no ocurre entre los 20 perpetuos más
   líquidos. Con umbral de 30 %, los cortos pierden en las 9 celdas (entre −2 y
   −8 USD). No hay evidencia a favor de operar en contra del funding alto.
3. **La mitad "funding muy negativo → largo" muestra una ventaja pequeña y
   concentrada.** En los 3 años de desarrollo da +6,2 % (≈ 2 %/año, unas 40
   operaciones); por año de entrada: 2022 −1,1, 2023 +6,4, 2024 +1,2, 2025 −0,2
   y 2026 +19,0 USD, todo este último por RAVE. Con 1.000 USD, 2025 pierde 36 USD.
4. **La señal invertida pierde (−11 %), así que la dirección no es arbitraria**,
   pero con 44 operaciones y un valor atípico eso no distingue de azar: un placebo
   con funding de otro momento llegó a +11 %. Es indicio débil, no resultado.
5. **Con 1.000 USD el resultado depende en parte de cobrar funding, no de
   acertar el precio.** De los +431 USD, +392 son funding cobrado por los largos
   en monedas con tasa muy negativa (RAVE solo, +63); el componente de precio
   neto de costos es +55. Entrar donde el funding es muy negativo paga por estar
   ahí, pero esas son las monedas más castigadas del mercado.
6. **Los stops pesan:** con 1.000 USD, 60 stops suman −652 USD y 397 salidas por
   tiempo suman +1.070.

## 6. Sesgos que favorecen el resultado

- **Sesgo de supervivencia:** el universo son perpetuos que hoy siguen listados.
  Comprar monedas con funding muy negativo (las más castigadas) es justo donde
  más pesa: las que se hundieron y dejaron de cotizar no están. Esto sobreestima
  el resultado de los largos.
- **Ejecución en el valor atípico:** se asume entrada a la apertura con 5 bps de
  slippage en una moneda que subió ×3,7 en 5 días; en la práctica la liquidez de
  ese tipo de moneda es mucho peor.
- **Pocas operaciones:** 44 con 100 USD; el nocional mínimo del exchange descarta
  la mayoría de las señales, y con 1.000 USD el número de operaciones se multiplica
  por diez, así que los dos resultados no son comparables.
- **Varias pruebas sobre los mismos datos:** 27 celdas más controles; no se eligió
  la mejor.

## 7. Qué se concluye

- **La línea queda cerrada**, según el criterio acordado de antemano. No se
  prueban más umbrales, medias o permanencias para rescatarla.
- Lo único que deja es una observación, no un resultado: comprar en funding
  extremadamente negativo pagó levemente en 2023–2024 y casi todo el resto salió
  de una moneda. No es una ventaja que se pueda construir encima.
- **Cuarta hipótesis sin ventaja medible** (grid neutral, seguimiento de
  tendencia, funding cubierto y esta). La excepción parcial es el funding cubierto
  del doc 08, que es la única con ingreso estable, pero pequeño.
- La segunda hipótesis propuesta (reversión tras cascadas de liquidación) exige
  datos intradía de varios años y queda sin probar.
