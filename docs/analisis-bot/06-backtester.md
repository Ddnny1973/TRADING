---
title: "Backtester offline (N6): qué simula, cómo usarlo y qué dijo la primera corrida"
type: analisis
status: herramienta lista — resultados de línea base en §5
started: 2026-11-11
updated: 2026-11-11
related: ["04-estrategia-y-portafolio.md", "05-arranque-capital-real-100usd.md"]
---

# Backtester offline (N6)

Tarea N6 / A7 del [doc 05](05-arranque-capital-real-100usd.md). Motivo: cada
hipótesis costaba 4 semanas de demo y dejaba ~13 grids cerrados, una muestra que
no se distingue de cero (doc 05 §11). El backtester corre meses de historia en
segundos, sobre velas reales de **mainnet**, sin tocar el bot ni la medición en
curso.

> Esto es análisis cuantitativo del sistema, no asesoría de inversión. Un
> backtest positivo no garantiza resultado en real.

## 1. Cómo usarlo

Desde `backend-python/` (con las dependencias de `requirements.txt` instaladas):

```bash
python -m app.backtest --days 180
```

```bash
python -m app.backtest --days 180 --sl-pct 0.03 --label "SL 3 %"
```

```bash
python -m app.backtest --source demo --start "2026-10-26 23:45" --end "2026-11-08 12:00" --fill-mode touch
```

- Solo usa endpoints **públicos** de Binance (velas, `exchangeInfo`, ticker).
  No necesita API key ni toca Binance demo, SQLite o Postgres.
- La primera corrida descarga velas de 5 min (≈ 10 s por símbolo cada 180 días)
  y las guarda en `backend-python/backtest_data/` (en `.gitignore`). Las
  siguientes son casi instantáneas; `--offline` fuerza a usar solo la caché.
- `--json ruta` guarda el resumen, cada grid y la curva de capital horaria.
- `python -m app.backtest --help` lista todos los parámetros.

Parámetros que cambian la política (lo que se quiere experimentar):

| Flag | Qué cambia | Por defecto |
|---|---|---|
| `--balance`, `--max-grids`, `--max-risk` | Perfil de capital | 100 / 2 / 0,25 (perfil A2) |
| `--sl-pct`, `--tp-pct` | SL/TP como fracción del balance | los del código (1 % / 3 %) |
| `--er-max` | ER máximo para lanzar | el del código (0,35) |
| `--policy`, `--max-recenters` | Qué hacer ante `OUT_OF_RANGE` | `RECENTER`, sin tope |
| `--fill-mode` | `through`: el precio debe cruzar el nivel; `touch`: basta tocarlo | `through` |
| `--slippage-bps` | Slippage del cierre a mercado | 3 |
| `--source` | Precios de `mainnet` o del exchange `demo` | `mainnet` |

## 2. Qué simula

Código en `backend-python/app/backtest/`:

| Archivo | Qué hace |
|---|---|
| `data.py` | Descarga y caché de velas. `HistoricalMarket` responde "como Binance a la hora t": las velas de 1h/4h/1d se agregan desde las de 5 min, con la vela en formación incluida, **sin mirar el futuro**. |
| `grid_sim.py` | Un grid en memoria: fills, reposición, PnL y condiciones de cierre. Espejo de `GridService`. |
| `engine.py` | El reloj: hace de WF1 (lanzar) y de WF2 (monitorear), con re-centrados y kill-switch. |
| `report.py` | Métricas iguales a las que se miran en el demo. |

Lo que **no se copió, se reusa tal cual** (si cambia el código del bot, cambia
el backtest):

- `auto_derive_params` completo: intervalo por ER, multiplicador, niveles,
  apalancamiento, cantidad por orden, `risk_pct`, SL/TP. Se le pasa un cliente
  que sirve velas históricas.
- `pair_selector._evaluate_candidate` y `score_candidate` para elegir el par.
- `GridEngine` (niveles), `validate_grid_step`, `calculate_atr`.
- Todas las constantes de `config_auto_params.py`.

Lo que se reimplementó (porque en producción vive pegado a Binance y SQLite) y
está cubierto por tests de equivalencia (`tests/test_backtest_grid_sim.py`):

- PnL del bot (`calculate_grid_pnl`), tope de inventario, duración máxima.
- Reposición (`replenish_filled_orders`), incluida la pausa del lado que acumula.
- `close_grid_if_triggered`: `EXPIRED`, `OUT_OF_RANGE` (gracia de 30 min, buffer
  de 0,5 ATR, 2 strikes), `MAX_POSITION`, `STOP_LOSS`, `TAKE_PROFIT`.
- `recenter_grid` (hereda inventario, modo LONG/SHORT) y `cancel_grid`.
- Orquestación de n8n: WF1 cada 4 h, relanzado al cerrar un grid, watchdog a
  los 15 min sin grids, WF2 cada 5 min, puerta determinista (A3).

Cada grid reporta **dos resultados**:

- `bot`: lo que ve el bot (comisión maker en todo). Es el que dispara SL/TP y
  el que queda en `historical_grid_logs`.
- `real`: caja de verdad. Comisión taker (0,05 %) en las órdenes que cruzan el
  mercado y en el cierre, más slippage.

## 3. Aproximaciones (leer antes de creer un número)

| Aproximación | Efecto probable |
|---|---|
| **Universo = lista de símbolos de hoy** (top por volumen actual, o `--symbols`). El bot real escanea todos los perpetuos del momento. | Sesgo de supervivencia: se excluyen pares que perdieron volumen o se deslistaron. Favorece al backtest. |
| **Fills con velas de 5 min.** Una orden se llena si la vela cruza su precio; no hay cola de órdenes ni fills parciales. | `through` es la versión prudente; `touch` es la optimista (parecida al demo). La verdad en real está cerca de `through` o por debajo. |
| **Sin filtro de spread y funding = 0** en la selección de par. | Menor: el funding pesa 10 % del score y T22 lo midió como no material. |
| **Filtros del exchange de hoy** (`min_notional`, tick, step) aplicados a toda la historia. | Menor. |
| **Precio de decisión = cierre de la vela de 5 min.** El bot usa el mark price del instante. | Menor. |
| **Kill-switch**: se asume que el dueño lo rearma al día UTC siguiente. | Si en la práctica tarda más, el backtest sobrestima el tiempo operando. |
| **LLM ignorado.** | Ninguno desde A3: ya no decide. |
| **Sin liquidaciones ni posiciones residuales.** | Menor con SL de 1 % del balance. |

## 4. Hallazgos del propio código al escribir el espejo

Salieron al leer `grid_service.py` línea por línea. No se tocó nada (la ventana
de medición sigue abierta); quedan como pendientes.

1. **`MAX_RECENTERS_PER_GRID = 2` no se aplica.** La constante se importa en
   `grid_service.py` pero ninguna rama la consulta: un grid puede re-centrarse
   sin límite. El backtester replica el comportamiento real (sin tope) y ofrece
   `--max-recenters` para medir qué pasaría si se aplicara.
2. **Un re-centrado que falla deja inventario sin dueño.** `recenter_grid()`
   cancela las órdenes y marca el padre `CANCELED` **antes** de llamar a
   `create_grid()`. Si esa creación lanza (paso del grid por debajo del piso de
   comisiones, kill-switch activo, nocional mínimo), el padre ya está cerrado,
   no se registra cierre y la posición queda abierta sin grid que la vigile.
   `close_grid_if_triggered` solo cubre el caso en que `recenter_grid` devuelve
   sin `new_grid_id`, no el de la excepción. Es un candidato a explicar
   residuales como el de ETH del 2026-11-04. En el backtest aparece como
   trigger `RECENTER_FAILED` (ahí se liquida la posición para poder contarla).
3. **El grid re-centrado no usa los parámetros derivados.** `recenter_grid()`
   no pasa `klines_interval` ni `atr_multiplier`, así que el hijo siempre se
   arma con ATR(14) de 4 h × 2,0, aunque el padre se hubiera derivado en 1h o
   1d con otro multiplicador. Además el check `OUT_OF_RANGE` siempre calcula su
   buffer con velas de 4 h, porque `grids` no guarda `klines_interval`.
4. **Órdenes duplicadas por nivel.** Al llenarse un BUY en el nivel *i* se
   repone un SELL en *i+1*, donde ya descansa el SELL inicial. Si el precio
   llega, se llenan los dos y el grid queda corto una unidad. Es parte de por
   qué un grid "neutral" acumula inventario direccional.

## 5. Validación contra el bot real (ventana A2, 27-oct → 8-nov)

Se corrió el simulador con las velas **del propio exchange demo**
(`--source demo --fill-mode touch`) y se comparó con lo medido en vivo
(doc 05 §11 y `historical_grid_logs`):

| Medida | Bot en vivo | Simulador con velas demo |
|---|---|---|
| Grids cerrados | 13 | 11 |
| Cosecha de ciclos | ≈ +15,3 USD | +14,0 USD |
| Arrastre de cierres | ≈ −17,7 USD | −14,1 USD |
| Resultado | −1,2 (bot) / +1,4 (Binance, con residual) | −0,1 (real) / 0,0 (bot) |
| `STOP_LOSS` / `TAKE_PROFIT` / `RECENTERED` | 6 / 2 / 5 | 4 / 1 / 6 |
| Grids con 0 ciclos | 31 % | 36 % |

La cadena de ETH del 2 al 4 de noviembre sale **casi al minuto**:

| Grid en vivo (UTC) | Duración | Cierre | Simulado | Duración | Cierre |
|---|---|---|---|---|---|
| `bba9bcbf` 02-nov 21:01 | 18,9 h | RECENTERED −0,31 | 02-nov 19:40 | 17,9 h | RECENTERED −0,17 |
| `07a70e39` 03-nov 15:55 | 11,2 h | RECENTERED 0,00 | 03-nov 13:35 | 13,6 h | RECENTERED −0,02 |
| `124ded28` 04-nov 03:10 | 4,2 h | RECENTERED +0,37 | 04-nov 03:10 | 4,2 h | RECENTERED +0,09 |
| `d2ad45ac` 04-nov 07:20 | 7,5 h | STOP_LOSS −1,16 | 04-nov 07:20 | 7,6 h | STOP_LOSS −1,21 |

Lo que **no** coincide es qué pares se eligen (el simulador operó ADA y ZEC
donde el bot operó SOL, HYPE y ENA): la selección depende de spread, funding y
del minuto exacto, que aquí son aproximados. La mecánica del grid, que es lo
que se quiere medir, sí reproduce al bot.

Nota de medición confirmada de paso: `historical_grid_logs.opened_at` va 5 h
por delante de UTC; restándole 5 h, los grids en vivo calzan con el simulador.

### Hallazgo: el demo no sigue los precios de mainnet

Comparación vela a vela (5 min) de la misma ventana, demo vs mainnet:

| Símbolo | Velas con mecha del demo > 0,5 % fuera de mainnet | Desvío máximo |
|---|---|---|
| SOLUSDT | 1,7 % | 10,8 % |
| ZECUSDT | 1,3 % | 11,1 % |
| HYPEUSDT | 1,9 % | 0,8 % |
| SUIUSDT | 5,5 % | 3,2 % |

Ejemplo concreto: el grid de SOL `3ba5ba34` cerró ciclos comprando a 89,93
entre el 30-oct y el 1-nov; en mainnet SOL no bajó de 92,25 en esos días. El
demo llena órdenes (y dispara stops) a precios que nunca existieron. Por eso la
misma ventana simulada con velas de mainnet da la mitad de cosecha (+7,7 USD
contra +14,0). **El demo sirve para validar que el bot funciona, no para medir
cuánto gana.**

## 6. Línea base: 180 días en mainnet (15-may → 11-nov 2026)

Perfil A2 (100 USDT, 2 grids, riesgo 25 %), universo de 61 símbolos, política
actual del código, fills `through`:

| Métrica | Valor |
|---|---|
| Resultado real | **−3,6 USD (−0,6 %/mes)** |
| Cosecha de ciclos | +160,2 USD (1.047 ciclos) |
| Arrastre de cierres | −163,8 USD |
| Comisiones | 2,7 USD |
| Drawdown máximo | 12,3 USD (12,3 % del balance) |
| Grids cerrados | 77 (38 % rentables, 10 % con 0 ciclos) |
| Semanas positivas | 12 de 26 |

Por trigger: `STOP_LOSS` 34 grids −41,6 · `TAKE_PROFIT` 9 grids +27,5 ·
`RECENTERED` 29 grids +6,5 · `EXPIRED` 3 grids +3,5 · `RECENTER_FAILED` 2 grids −1,2.

Es el mismo patrón de las tres mediciones en vivo (docs 04 §1, 05 §10 y §11),
ahora con 77 grids en vez de 13: **la cosecha y el arrastre se cancelan casi
exactamente.** No es mala suerte de un mes: es la forma de la estrategia.

### Cuánto ruido tiene ese número

Mismo perfil, corriendo la ventana unos días (cambia en qué minuto se lanza
cada grid) y partiendo el periodo en dos:

| Corrida | `through` | `touch` |
|---|---|---|
| 5 ventanas de 175 días desplazadas 1–5 días | −5,4 a −7,8 USD | +8,0 a +17,7 USD |
| 180 días (la de arriba) | −3,6 | +17,8 |
| Primera mitad (90 días hasta 13-ago) | −4,8 | +9,1 |
| Segunda mitad (90 días hasta 11-nov) | −13,8 | −7,5 |

Dos lecturas:

- **Diferencias menores a ~10 USD entre dos corridas son ruido.** Un cambio de
  parámetro solo vale si gana en varias ventanas, no en una.
- **El supuesto de fills pesa más que cualquier parámetro**: entre `through` y
  `touch` hay 15–20 USD en 6 meses, lo que separa perder ~1 %/mes de ganar
  ~2 %/mes. `touch` regala justo los mejores fills (comprar en el mínimo exacto
  de la vela y que rebote), que en real solo se llevan quienes están primeros
  en la cola. Lo realista está entre ambos y más cerca de `through`. Esto solo
  se resuelve con datos de ejecución real.

### Variantes de un solo parámetro (180 días, `through`)

| Variante | Resultado | Cosecha | Arrastre | Drawdown |
|---|---|---|---|---|
| Base | −3,6 | +160,2 | −163,8 | 12,3 |
| SL 2 % | −20,9 | +161,3 | −182,1 | 23,1 |
| SL 3 % | +1,4 | +164,2 | −162,8 | 19,4 |
| SL 5 % | −25,7 | +173,2 | −198,9 | 28,4 |
| TP 1,5 % | −12,2 | +141,6 | −153,8 | 27,7 |
| TP 6 % | +9,1 | +163,0 | −153,9 | 10,0 |
| `OUT_OF_RANGE` = CLOSE | +0,4 | +153,2 | −152,8 | 12,5 |
| Tope de 2 re-centrados | −13,9 | +168,7 | −182,6 | 16,9 |
| ER máx. 0,25 | −6,9 | +163,5 | −170,5 | 13,1 |
| ER máx. 0,20 | −4,1 | +160,7 | −164,8 | 13,3 |
| Sin kill-switch | −3,6 | (nunca se disparó en 180 días) | | |
| Balance 300 | −16,0 (−5,3 %) | +357,6 | −373,6 | 49,0 |
| Balance 1.000, 4 grids, riesgo 15 % | −127,4 (−12,7 %) | +1.228,0 | −1.355,4 | 147,2 |

Lectura:

- **Ninguna perilla crea ventaja.** En todas las variantes la cosecha y el
  arrastre siguen pegados; el resultado se mueve dentro del ruido y sin
  dirección (SL 2 % pierde, 3 % empata, 5 % pierde). Ajustar SL, TP o el umbral
  de ER es reordenar la misma apuesta.
- **Subir el SL no es gratis**: menos stops, pero cada re-centrado arrastra más
  inventario y el drawdown se duplica.
- **Filtrar más fuerte por ER al lanzar no ayuda.** El ER de las últimas 48
  velas no predice si el rango se va a mantener.
- **Más capital empeora el porcentaje** con la política actual: entran BTC/ETH
  y más niveles, y el arrastre crece más rápido que la cosecha. Escalar no
  arregla una estrategia de expectativa ~0 (doc 04 §7).

## 7. Qué cambia en el plan

1. **El criterio del doc 05 §9 (≥ 2 %/mes en demo) no es alcanzable afinando
   parámetros**, y el demo lo sobrestima por las mechas. Al cierre de la ventana
   (~24-nov) conviene leerla junto con este backtest, no sola.
2. **La "inteligencia" que falta es estructural**, no de calibración. Lo que el
   backtest señala como siguiente experimento, en orden:
   - **A6: actuar ante tendencia mientras el grid corre** (pausar el lado que
     acumula, o reducir inventario antes del stop). El arrastre viene de
     inventario cargado contra la tendencia, no de la entrada.
   - **Sesgo direccional del grid** (no reponer contra una tendencia medida en
     un plazo mayor), que es la versión barata del flip a breakout (T21).
   - **Selección por desempeño propio**: HYPE, SOL y WLD suman; TAO, ADA y NEAR
     restan. Con 1–8 grids por símbolo todavía es ruido; hay que probarlo en
     ventanas separadas.
3. **Cada experimento se evalúa con la misma regla**: mejora en `through` y en
   `touch`, en las dos mitades del periodo y con fechas desplazadas. Si solo
   gana en una corrida, es ruido.
4. **Pendientes de código que salieron de aquí** (§4): aplicar o borrar
   `MAX_RECENTERS_PER_GRID`, y hacer que un re-centrado fallido no deje
   inventario sin dueño.
5. **Mejoras del backtester** cuando hagan falta: universo histórico por fecha
   (quita el sesgo de supervivencia), funding real, y fills con trades (aggTrades)
   en vez de velas para acotar la brecha `through`/`touch`.
