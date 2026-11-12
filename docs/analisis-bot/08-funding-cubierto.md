---
title: "Cobro de funding con posición cubierta: backtest de 4 años"
type: analisis
status: hipótesis probada — ingreso real pero pequeño y en descenso; no se implementa
started: 2026-11-12
updated: 2026-11-12
related: ["04-estrategia-y-portafolio.md", "06-backtester.md", "07-seguimiento-tendencia.md"]
---

# Cobro de funding con posición cubierta (hipótesis)

**Resultado: es la primera de las tres hipótesis con un ingreso real y estable,
pero es pequeño y viene cayendo.** Mantener ETH cubierto dio +4,6 %/año en 4
años con drawdown de 0,6 %; en el último año, +1,2 %. No alcanza la meta de
rendir más que un banco y no justifica construirlo en el bot hoy.

## 1. Qué se probó

Código: `backend-python/app/backtest/carry.py` (`python -m app.backtest.carry`).
Simulador aparte; no comparte lógica con el bot.

- **Posición:** comprar el activo en spot y vender la misma cantidad en el
  perpetuo. Lo que gana una pata lo pierde la otra; queda el funding que cobra el
  corto cuando la tasa es positiva.
- **Capital:** 2/3 compra el spot y 1/3 es margen del perpetuo (apalancamiento
  2×). Solo 2/3 del capital genera funding.
- **Reequilibrio:** cuando el precio se aleja ±30 % de la entrada, el nocional se
  devuelve a su objetivo (el spot está totalmente pagado y el margen es finito),
  pagando comisión y slippage sobre lo que se mueve.
- **Dos formas de usarlo:**
  - *Siempre dentro* de un activo grande (BTC, ETH), sin señal.
  - *Con selección:* cada día, entre los 30 perpetuos más líquidos con par spot,
    entrar en los de mayor funding medio de 7 días si supera 10 %/año y salir
    cuando cae bajo 0 % (mínimo 7 días dentro). Hasta 3 posiciones.
- **Costos:** spot 0,10 % y perpetuo 0,05 % por lado, más 5 bps de slippage por
  pata y por lado: una ida y vuelta cuesta ≈ 0,5 % del nocional.
- **Datos:** velas diarias spot y de perpetuos y funding real de 184 símbolos,
  del 2022-11-11 al 2026-11-11. El último año se corrió aparte como tramo
  reservado.

## 2. Resultado

Funding medio anualizado (lo que cobra un corto, antes de costos):

| | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|
| BTC | +7,9 % | +11,9 % | +5,1 % | +3,3 % |
| ETH | +8,3 % | +13,0 % | +4,9 % | +2,2 % |
| SOL | +1,3 % | +13,6 % | +0,4 % | −0,3 % |

Rentabilidad sobre el capital total, neta de costos:

| Variante | %/año (4 años) | Drawdown | 2023 | 2024 | 2025 | 2026 | Año reservado |
|---|---|---|---|---|---|---|---|
| **ETH siempre (100 USD)** | +4,6 | 0,6 % | +5,9 | +8,7 | +3,1 | +0,8 | +1,2 % |
| BTC siempre (1.000 USD) | +4,5 | 0,3 % | +5,3 | +8,0 | +3,2 | +1,3 | +1,5 % |
| BTC+ETH+SOL siempre (1.000) | +3,1 | 3,3 % | +3,7 | +8,5 | +2,1 | +0,6 | +0,6 % |
| ETH con señal | +3,7 | 0,9 % | +5,2 | +8,4 | +1,2 | +0,3 | +0,3 % |
| **Selección base (3 pos., ≥ 10 %)** | +3,5 | 5,3 % | +5,8 | +10,4 | +0,6 | −2,2 | −2,4 % |
| Selección, entra ≥ 5 % | +5,1 | 1,1 % | +6,4 | +10,8 | +2,0 | +1,4 | +1,0 % |
| Selección, entra ≥ 20 % | +3,7 | 1,1 % | +4,4 | +9,3 | −0,6 | +2,2 | +2,2 % |
| Selección, media de 30 días | +5,0 | 0,4 % | +5,5 | +9,0 | +2,7 | +3,0 | +3,2 % |
| Selección, media de 14 días | +1,8 | 13,1 % | +6,2 | +10,7 | +2,7 | −11,1 | −11,0 % |
| Selección, media de 3 días | −0,8 | 10,3 % | −0,4 | +8,0 | −1,1 | −8,9 | −9,6 % |
| Selección, sale < 5 % | +1,3 | 7,1 % | +3,0 | +9,4 | 0,0 | −6,2 | −6,4 % |
| Selección, 1 posición | +6,4 | 1,2 % | +6,7 | +12,1 | +1,7 | +5,3 | +4,9 % |
| Selección, universo 60 | +5,8 | 0,4 % | +6,3 | +10,3 | +2,2 | +4,4 | +4,1 % |
| Selección, 1.000 USD y 10 pos. | +4,4 | 0,4 % | +5,4 | +10,1 | +1,0 | +1,3 | +1,3 % |
| Selección base, costos × 2 | +2,0 | 6,0 % | +4,1 | +9,6 | −1,2 | −3,7 | −4,1 % |

## 3. Lectura

1. **El ingreso existe y no depende de acertar el precio.** Las versiones
   simples ganan todos los años y su drawdown es menor al 1 %. Es lo contrario
   del grid y de la tendencia: poca varianza, sin dependencia de pocas
   operaciones.
2. **Pero rinde poco: 3–6 %/año en 4 años.** Solo 2/3 del capital trabaja y el
   funding medio de BTC/ETH fue de ≈ 7 %/año.
3. **Y viene bajando.** El grueso salió de 2024 (≈ 9 %); 2025 dio ≈ 3 % y el
   último año ≈ 1–1,5 %. El funding es una prima que se achica cuando hay más
   capital cobrándola y cuando el mercado no está eufórico.
4. **Elegir monedas por funding alto no mejora de forma fiable y añade un riesgo
   nuevo.** Las variantes de selección van de −0,8 a +6,4 %/año sin patrón claro.
   La pérdida grande viene de un solo caso: DEXEUSDT, julio de 2026, cuyo funding
   pasó de muy positivo a muy negativo y costó entre −6 y −13 USD sobre una
   posición de 27 USD en 8 días. En monedas chicas el funding alto puede
   invertirse más rápido de lo que la regla sale.
5. **Rotar cuesta.** Cada ida y vuelta consume ≈ 0,5 % del nocional, unas 2–3
   semanas de funding a 10 %/año. Las variantes que rotan más (media de 3 días,
   salida < 5 %) son las peores.
6. **Con 100 USD:** BTC queda fuera por nocional mínimo (100 USD en el
   perpetuo); ETH sí cabe. 4,6 %/año sobre 100 USD son ≈ 4,6 USD al año.

## 4. Riesgos que el backtest no mide

- **Riesgo de contraparte:** todo el capital queda en el exchange (spot y
  margen). Es el riesgo principal de esta estrategia y no aparece en ningún
  número de arriba.
- **Liquidación entre reequilibrios:** con datos diarios y umbral de ±30 %, una
  subida muy brusca dentro del día podría liquidar el corto antes de mover
  margen (a 2× el corto se liquida cerca de +50 %).
- **Riesgo de la stablecoin:** el resultado está en USDT.
- **Sesgo de supervivencia** y **filtros de hoy** aplicados a toda la historia,
  como en los docs 06 y 07.
- **Ejecución de dos patas:** se asume que spot y perpetuo se ejecutan al mismo
  precio de apertura con 5 bps de slippage cada uno.

## 5. Qué se concluye

- **No se implementa ahora.** Exige operar spot además de futuros (el bot solo
  opera futuros) para un ingreso de ≈ 1–5 %/año que en el último año fue de ≈ 1 %.
  Falta compararlo con la tasa de un instrumento sin riesgo vigente (no se
  consultó), pero con ≈ 1 % es poco probable que la supere.
- **Sí queda como la única hipótesis con ingreso estructural.** Si el funding
  vuelve a niveles de 2024 (> 10 %/año sostenido), la versión simple (un activo
  grande, siempre dentro, sin selección) vuelve a tener sentido. Es fácil de
  vigilar: basta mirar el funding medio de 30 días de BTC/ETH.
- **Resumen de las tres hipótesis** (docs 06, 07, 08): el grid neutral da ≈ 0
  con drawdown de 12 %; la tendencia da un número alto que depende de 3
  operaciones y tiene drawdown de 45 %; el funding cubierto da poco pero cierto.
  Ninguna cumple hoy "rendir más que un banco con riesgo aceptable" usando
  reglas simples sobre datos públicos de precio.
