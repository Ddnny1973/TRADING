---
title: "Arranque con capital real (~100 USD): qué funciona, qué falta y cripto vs bolsa"
type: analisis
status: propuesta — decisiones del dueño marcadas con 🔴
started: 2026-10-25
related: ["03-plan-mejoras-rentabilidad.md", "04-estrategia-y-portafolio.md"]
---

# Arranque con capital real (~100 USD)

Meta declarada por el dueño (2026-10-25): empezar a operar con **~100 USD reales**,
hacer crecer la cuenta con utilidades pequeñas pero sostenidas y, como primer
hito, **que el bot pague la suscripción de Claude**.

> Esto es análisis cuantitativo del sistema, no asesoría de inversión
> personalizada. La decisión de poner dinero real, y cuánto, es del dueño.

## 1. Qué dicen los datos hoy (snapshot 2026-10-25, n8n WF2 ejecución 830526)

Los 4 grids RUNNING, con el PnL reconstruido desde sus órdenes FILLED
(efectivo + inventario al precio medio actual − fee maker 0,02 %):

| Grid | Edad | Fills | Nocional/orden | PnL neto | PnL/día | Margen aprox. |
|---|---|---|---|---|---|---|
| BTCUSDT 5x | 0,9 d | 21 | 55,5 USD | +1,28 | +1,46 | ~124 USD |
| ETHUSDT 3x | 0,9 d | 68 | 22,9 USD | +1,59 | +1,79 | ~148 USD |
| HYPEUSDT 3x | 1,1 d | 64 | 5,8 USD | +0,42 | +0,38 | ~41 USD |
| SOLUSDT 3x | 11,8 d | 88 | 5,9 USD | +2,21 | +0,19 | ~41 USD |

Lectura correcta (y sus trampas):

- ✅ **La mecánica ya funciona después de T1–T5**: hay reposición (fills BUY y
  SELL balanceados), el inventario neto es chico y todos los grids vivos están
  en verde. En agosto los grids morían con 0 ciclos.
- ✅ **Rendimiento sobre margen en régimen lateral: 0,5–1,2 %/día**. SOL (12 días,
  la muestra más representativa) da **~0,48 %/día**.
- ⚠️ **Sesgo de supervivencia**: solo se ven los grids vivos. Los que cerraron
  (con pérdida o no) no aparecen aquí. El número que manda es `strategy_pnl`
  del dashboard desde el 2026-09-06 (post-fixes). **Pendiente de leer** (el
  agente no tiene acceso a Postgres).
- ⚠️ **Régimen favorable**: ER actual 0,06–0,12 (mercado muy lateral, ideal
  para un grid). En tendencia esto cambia de signo. Ver `04` §2: el grid es
  short-vol.
- ⚠️ **Demo/testnet ≠ mainnet**: `demo-fapi.binance.com` usa precios reales
  pero simula el matching: no hay cola de órdenes ni competencia por el fill.
  Un grid vive de los fills, así que el testnet **sobrestima** el resultado.
  La única forma de medir esa brecha es operar en real con poco dinero.

## 2. La matemática del capital pequeño

### 2.1 Qué puede operar el bot con 100 USD

`pair_selector.filter_by_capital` y `derive_risk_pct_and_levels` ya filtran por
balance usando el `exchangeInfo` **de mainnet**:

- Margen por grid = `MAX_RISK_PCT` (15 %) × 100 = **15 USD**.
- Orden mínima ≈ `min_notional × 1,1` = **5,5 USD** en la mayoría de alts.
  En mainnet **BTCUSDT exige 100 USD y ETHUSDT 20 USD** de nocional mínimo →
  **quedan fuera**. Solo se pueden operar alts (SOL, HYPE, DOGE, XRP…).
- Con 3x: 5,5 / 3 = 1,83 USD de margen por nivel → **~8 niveles** por grid
  (5 si la volatilidad baja el apalancamiento a 2x).

### 2.2 Cuánto puede rendir (escenarios honestos)

Supuesto: 2 grids de alts, ~30–50 USD de margen desplegado.

| Escenario | Rend. diario sobre margen | USD/mes con 100 USD | % mensual |
|---|---|---|---|
| Pesimista (tendencia, brecha de testnet) | ≤ 0 % | 0 a −5 | 0 a −5 % |
| Base | 0,25 % | ~3–4 | ~3–4 % |
| Optimista (lateral como hoy) | 0,5 % | ~6–8 | ~6–8 % |

**Conclusión incómoda pero necesaria: 100 USD no pagan la suscripción.**
Capital necesario para cubrirla con el escenario base/optimista (3–8 %/mes):

| Suscripción | Capital necesario |
|---|---|
| 20 USD/mes | ~250–700 USD |
| 100 USD/mes | ~1.300–3.300 USD |
| 200 USD/mes | ~2.500–6.700 USD |

Sin edge probado en real, esas cifras no valen. Y una meta de ingreso fija
sobre un capital chico empuja a subir el apalancamiento, que es justo lo que
quiebra cuentas.

### 2.3 Lo que de verdad hace crecer una cuenta chica: los aportes

| Plan 12 meses | Al 5 %/mes | Al 0 %/mes |
|---|---|---|
| 100 USD, sin aportes | ~180 USD | 100 USD |
| 100 USD + 50 USD/mes | ~975 USD | 700 USD |

A esta escala, aportar pesa más que rendir. **Propuesta**: usar los 100 USD como
**piloto de medición** (¿cuánto del resultado de testnet sobrevive en real?) y
escalar con aportes solo si el piloto pasa el criterio de la §6.

## 3. ¿Bolsa en vez de cripto?

| Criterio | Cripto (Binance Futures) | Bolsa EE. UU. (p. ej. IBKR / Alpaca) |
|---|---|---|
| Orden mínima | ~5 USD | Acciones fraccionadas: ~1 USD |
| Comisión | **% del nocional** (0,02 % maker) | Mínimo por orden (IBKR Pro ~0,35 USD) o spread/PFOF |
| Grid con órdenes de 5 USD | Viable (0,002 USD de fee) | **Inviable**: 0,35 USD = 7 % por orden |
| Horario | 24/7 (el bot ya está hecho para esto) | ~6,5 h/día, 5 días: medio bot parado |
| Volatilidad diaria | 2–5 % (lo que alimenta un grid) | 0,5–2 % en índices: pocos ciclos |
| Apalancamiento | Hasta 125x (aquí 2–5x, aislado) | Margen limitado. Restricciones de day-trading (regla PDT; verificar si sigue vigente) |
| Riesgo de plataforma | Exchange cripto, regulación cambiante | Broker regulado, protección SIPC |
| Lo ya construido | Todo el repo | Habría que reescribir el conector y la estrategia |

**Veredicto para *este* bot y *este* capital: cripto.** El grid necesita
comisiones proporcionales, órdenes mínimas chicas, volatilidad y mercado 24/7,
y la bolsa falla en las cuatro.

La bolsa sí sirve como **referencia**: comprar y mantener un ETF del S&P 500 rindió
históricamente ~10 %/año con cero trabajo. Si el bot, ajustado por riesgo, no
le gana a eso, no vale el esfuerzo. Conviene mostrar esa comparación en el
reporte mensual.

🔴 Verificar con fuentes oficiales: que la cuenta de Binance del dueño tenga
habilitados los **futuros USDⓈ-M** desde Colombia, y el tratamiento tributario
de las ganancias en la DIAN.

## 4. Pertinencia de las 22 tareas con capital real

Las 19 hechas **siguen siendo válidas**: son la base que hoy hace funcionar los
grids. Lo que hay que revisar:

| Tarea | Estado | Pertinencia con 100 USD reales |
|---|---|---|
| T4 SL/TP = 1 % / 3 % del balance | ✅ | **Recalibrar.** Con 100 USD el SL es **1 USD por grid**: puede saltar antes de salir del rango. Expresarlo según el margen o el rango del grid, no según el balance. |
| T19 4 grids concurrentes | ✅ | **Bajar a 2** con 100 USD (4 × 15 % = 60 % del capital comprometido en un régimen adverso común). |
| T15 kill-switch 3 %/día | ✅ | Válido. Con 100 USD son 3 USD: razonable. |
| T22 funding no material | ✅ | **Re-medir en mainnet** (el funding real difiere del de testnet). Script ya existe. |
| T11 cron de WF1 más frecuente | ❌ | **Descartar.** T10 (relanzar al cerrar) + T12 (watchdog) ya cubren la continuidad. |
| T13 paso 2 sacar el LLM del camino crítico | 🟡 | **Crítica, la primera.** El LLM aprobó el 100 % de las veces y dos veces dejó al bot sin operar por modelos retirados. Con dinero real, un punto único de falla sin valor añadido es inaceptable. |
| T20 paso 2 actuar ante tendencia | 🟡 | **Alta.** Propuesta concreta: ante `TREND_REGIME`, **pausar la reposición del lado que acumula** (mecanismo de T3, ya probado). No cerrar. Es barato y no cristaliza pérdidas. |
| T21 flip a breakout | ❌ | **Postergar** hasta tener más de ~500 USD: no hay capital para dos patas. |

## 5. Tareas nuevas para operar en real

### Fase A — antes de poner un dólar (1–2 semanas)

| # | Tarea | Por qué |
|---|---|---|
| N1 | **Switch testnet/mainnet por variable de entorno** (`BINANCE_BASE_URL`), hoy `BINANCE_TESTNET_URL` está fijo en `config.py` | Poder correr una instancia demo y otra real en paralelo con el mismo código. |
| N2 | **Perfil microcapital**: constantes según el balance (`MAX_CONCURRENT_GRIDS=2`, `MAX_RISK_PCT≈0,20–0,25`, SL según el grid) | El perfil actual está pensado para 5.000 USD. |
| N3 | **Órdenes post-only (`timeInForce: GTX`)** en `place_batch_orders`, hoy `GTC` | Garantiza fee maker. Una reposición que cruce el spread pagaría taker (2,5×) sin aviso. Manejar el rechazo `-5022` re-precio. ⚠️ Toca `place_batch_orders`: cambio mínimo + tests. |
| N4 | **Stop de emergencia en el exchange** (`STOP_MARKET reduceOnly` por grid) | Si el backend o n8n se caen con inventario abierto, hoy no hay freno. Con dinero real es obligatorio. |
| N5 | **Seguridad de la API key real**: solo futuros, **sin retiros**, whitelist de la IP pública del servidor | Higiene básica de dinero real. |
| N6 | **Backtester offline con velas de mainnet** que reuse `auto_params` y la lógica del grid | Es lo que más falta. Permite probar parámetros sobre 6–12 meses de historia real en vez de esperar semanas de testnet. Es la base de cualquier "inteligencia" seria (ver §7). |

### Fase B — piloto real de 100 USD (4–6 semanas)

- Instancia real con 2 grids en alts. La instancia demo **sigue corriendo en
  paralelo** con los mismos parámetros → la diferencia entre ambas mide la
  brecha testnet↔real.
- Reporte diario por Telegram: PnL real, PnL demo, drawdown y comparación con
  "no hacer nada".

## 6. Criterio de go/no-go del piloto (propuesta 🔴 a validar)

Tras 4 semanas en real:

- `strategy_pnl` > 0, con al menos 2 de 4 semanas positivas.
- Drawdown máximo < 10 % del capital (10 USD).
- Brecha real/demo: el real logra **≥ 50 %** del PnL del demo.
- 0 incidentes de infraestructura con inventario sin protección.

Si pasa: escalar con aportes por escalones (100 → 300 → 1.000), repitiendo el
criterio en cada escalón. Si no pasa: el problema es de estrategia o de
ejecución, no de capital. Escalar solo perdería más rápido.

## 7. "Más inteligencia": qué sí y qué no

Lo que **no** aporta: un LLM decidiendo "lanzar sí/no" en cada corrida (ya se
vio: 100 % de aprobaciones). Un LLM no aprende de los resultados del bot.

Lo que **sí** aporta, en orden de valor:

1. **Detección de régimen que actúa** (T20 paso 2): el mayor enemigo del grid
   es la tendencia. Reglas deterministas (ER, volatilidad realizada) que pausan
   el lado que acumula.
2. **Selección de símbolos por desempeño propio** (aprendizaje real y con poco
   riesgo de sobreajuste): con `grid_cycles`, medir **PnL/día por USD de margen
   por símbolo** y asignar los grids a los que mejor rinden, con algo de
   exploración (bandit tipo Thompson sampling). Así el bot aprende de *sus* datos.
3. **Step y rango adaptativos** calibrados con el backtester (N6) mediante
   walk-forward, no ajustados a mano.
4. **Claude como analista semanal fuera del camino crítico**: una rutina
   programada que lee el dashboard, compara contra el benchmark, detecta
   anomalías y **propone** cambios de parámetros para aprobación humana. Usa la
   suscripción para lo que mejor hace: analizar y explicar.
5. **Breakout / cobertura** (T21): cuando el capital lo permita.

## 8. Orden recomendado

1. Leer `strategy_pnl` y la tasa de grids rentables desde 2026-09-06 en el
   dashboard → confirma (o no) que la base es rentable en demo.
2. T13 paso 2 + N3 (GTX) + N1 (switch de entorno) + N5 (API key).
3. N4 (stop en el exchange) + N2 (perfil microcapital) + recalibrar T4.
4. Piloto real de 100 USD (Fase B), con el demo en paralelo.
5. En paralelo al piloto: N6 backtester → T20 paso 2 → selección por desempeño.

> ⚠️ El orden de esta sección queda reemplazado por la §9.

## 9. Decisión 2026-10-25: nada de dinero real hasta validar en demo

El dueño decidió **no poner los 100 USD** hasta que la operación esté clara y se
vea que gana algo de forma sostenida, aunque sea poco. Por eso la Fase A pasa a
ser **validación en demo con el mismo perfil que tendría la cuenta real**.

Problema de fondo: hoy el demo opera ~5.000 USD con grids de BTC/ETH que en
real no existirían. Lo que gane ese demo no predice lo que ganarían 100 USD.

| # | Tarea | Resultado esperado |
|---|---|---|
| A0 | **Acceso de lectura a los datos** (dashboard vía nginx + rol Postgres solo lectura) | El agente puede medir sin pedirle consultas al dueño. |
| A1 | **Línea base** desde 2026-09-06: `strategy_pnl`, PnL por trigger, PnL/día por símbolo y por USD de margen, LLM vs determinista (`bot_health_events`) | Saber si la base post-fixes ya es rentable en demo. |
| A2 | **Perfil microcapital en demo**: `BALANCE_CAP_USDT=100` (auto-params usa `min(balance real, cap)`), 2 grids concurrentes y `min_notional` tomado de mainnet (en testnet BTC pide 50, en real 100) | El demo se comporta exactamente como la cuenta real de 100 USD. |
| A3 | **T13 paso 2**: puerta determinista decide, LLM solo notifica | Sin punto único de falla. |
| A4 | **N3 órdenes post-only (GTX)** + medir % de fills taker | Fees reales garantizados. |
| A5 | **Recalibrar SL/TP (T4)** al margen/rango del grid + **N4 stop de emergencia en el exchange** | Pérdida acotada aun con el backend caído. |
| A6 | **T20 paso 2**: ante `TREND_REGIME`, pausar el lado que acumula | Menos daño en tendencia. |
| A7 | **N6 backtester** con velas de mainnet (en paralelo) | Validar parámetros contra 6–12 meses, no solo contra el régimen del mes. |

**Criterio para desbloquear los 100 USD reales** (4 semanas seguidas con el
perfil A2 activo):

- `strategy_pnl` > 0 **incluyendo grids cerrados**, con ≥ 3 de 4 semanas positivas.
- ROI ≥ 2 %/mes sobre el capital simulado. Así queda margen para absorber la
  brecha demo→real (se asume que el real logra ~50 % del demo).
- Drawdown máximo < 10 % del capital simulado.
- 0 periodos > 15 min sin grids por fallas propias, y 0 inventarios sin protección.

**Escalado "seguro" después**: piloto real de 100 USD con el demo en paralelo
(Fase B). Luego escalones 100 → 300 → 1.000, cada uno con 4 semanas cumpliendo el
mismo criterio. Nunca se reponen pérdidas para "recuperar". Si un escalón falla,
se vuelve al anterior.

## 10. Línea base A1 (dashboard en vivo, 2026-10-25)

Primera lectura directa de `/api/v1/dashboard/data`, con datos del 2026-08-02 al 2026-10-25:

| Métrica | Valor | Lectura |
|---|---|---|
| Ciclos completados | 2.045 | El motor cosecha: ~35–65 USD/semana en las semanas normales |
| PnL neto de ciclos | **+290,6 USD** (fees 6,8 % del bruto) | ≈ 3–5 %/mes sobre ~4.900 USD **antes** de las pérdidas de inventario |
| `strategy_pnl` del dashboard | **−49,6 USD** | Ciclos ganados menos inventario perdido. **No fiable**, ver abajo |
| Closure drag (51 grids cerrados) | −54,3 USD | Peor trigger: `MAX_POSITION` (11, −8,6). `EXPIRED` es el mejor (4, +21) |
| Grids cerrados rentables | 27 % (14/51) | Objetivo del plan 03: > 60 % |
| Grids con 0 ciclos | 36 % (37/103) | Objetivo: < 10 % |
| Drawdown máximo | 15,7 USD (07→15 sep) | 0,3 % del balance |
| Por símbolo (ciclos) | BTC +126,7 · ETH +119,8 · FIL +27,1 · HYPE +8,4 · SOL +5,5 · DOGE +2,6 | El 85 % sale de BTC/ETH, que **no se pueden operar con 100 USD** |

Semanas 40–41 (29 sep–12 oct): 63 y 12 ciclos. Fue la caída del modelo LLM
(HTTP 410), que costó ~2 semanas de cosecha. Es evidencia directa del valor
económico de T13 paso 2.

### Hallazgo: el dashboard no sabe contar los grids re-centrados

- 48 grids aparecen como "RUNNING" en el dashboard, pero **solo 4 lo están**.
  Son grids re-centrados (T2): `recenter_grid()` los marca CANCELED en SQLite,
  pero **no escribe `historical_grid_logs`** en Postgres. El dashboard toma su
  último `pnl_snapshot` como PnL "vivo" para siempre.
- Esos 48 suman realizado **+145,3** y no realizado **−219,0** en su último
  snapshot. Ese inventario **pasó al grid hijo**, así que no es una pérdida
  cristalizada. Pero la contabilidad no lo sigue: el `open_pnl` (−67,8) es
  un fantasma, y no se sabe cuánto de ese inventario se recuperó después.
- El `account_balance` (4.912 → 4.628) es `availableBalance`: descuenta el margen
  de las órdenes abiertas (~345 USD hoy). Una corrección gruesa ubica el
  resultado real de los 3 meses **entre ≈ −100 y +60 USD, o sea cerca de cero**.

**Conclusión de la línea base:** el motor de ciclos gana (+290), pero el
inventario acumulado en movimientos direccionales se come casi todo. Es lo
que predice la tesis short-vol del doc 04. **La prioridad no es cosechar más,
es manejar mejor el inventario (T20 paso 2, A5) y medirlo bien.**

### Tareas que salen de aquí (se suman a la Fase A)

- **A1a — Fix del dashboard** (🟡 PR 2026-10-25, rama `feat/a1-recenter-dashboard-income-20261025`; además corrige el costo base heredado del grid hijo, ver `decisiones-tecnicas.md`): los grids re-centrados deben salir del PnL
  "vivo" (escribir su cierre `RECENTERED` en `historical_grid_logs`, o excluir
  los CANCELED de SQLite), y la cadena padre→hijo debe sumarse como una sola
  operación.
- **A1b — Verdad desde Binance** (🟡 mismo PR, `GET /api/v1/account/income-summary`): endpoint de solo lectura que resuma
  `GET /fapi/v1/income` (`REALIZED_PNL` + `COMMISSION` + `FUNDING_FEE`) por
  período, más el PnL no realizado de las posiciones abiertas. Así se obtiene un
  resultado neto que no depende de la contabilidad del bot. Reusa
  `get_income_history()` (T22).
- **Ajuste a A2:** como BTC/ETH generan el 85 % de la cosecha y quedan fuera con
  100 USD, el demo con perfil de 100 USD es aún más necesario. Puede que la
  conclusión sea que hacen falta ~300 USD (nocional mínimo de ETH: 20 USD) para
  que la estrategia tenga los pares que realmente le rinden.
