---
title: "Estrategia y portafolio — qué hace falta para que el bot sea rentable"
type: analisis-estrategico
app: trading-grid-bot
repo: TRADING
tags: [estrategia, portafolio, grid-trading, breakout, riesgo]
related:
  - "[[analisis-bot-monitoreo]]"
  - "[[decisiones-tecnicas]]"
updated: 2026-08-31
owner: dueño del repo
audiencia: agente de IA que continúe el trabajo de estrategia
---

# Estrategia y portafolio

> Complemento de [03-plan-mejoras-rentabilidad.md](03-plan-mejoras-rentabilidad.md).
> Ese documento cubre **cómo arreglar lo que está roto**; este cubre **qué
> estrategia seguir** una vez arreglado. Leer el 03 primero: sin sus Fases 1-2
> ninguna decisión de estrategia se puede evaluar con datos.

---

## 1. Conclusión de partida: no hay un problema de estrategia

Con los datos del 2026-08-31 (30 ciclos, 43 grids cerrados, ~2 meses):

- El grid **tiene edge bruto positivo**: todos los ciclos cerraron en ganancia y
  las fees son solo el **4,4 % del bruto**. La mecánica funciona.
- El P&L real es **≈ −8 USD** porque la lógica de cierre destruye lo ganado
  (ver el "closure drag" de −15,43 USD en el doc 03).
- Aun arreglando el 100 % del drag: 30 ciclos × ~0,43 USD = **0,43 % bruto en
  dos meses** sobre 3000 USD ≈ **2,5 % anualizado**. Por debajo del activo libre
  de riesgo.

**Implicación para quien continúe: añadir estrategias nuevas NO resuelve esto.**
El cuello de botella es la frecuencia de ciclos y el destrozo en la salida, no
la falta de estrategias.

### La ecuación que gobierna la rentabilidad

$$\text{PnL}_{\text{grid}} = N_{\text{ciclos}} \times (\text{step} - 2f) \times \text{nocional}$$

| Variable | Estado | ¿Hay espacio? |
|---|---|---|
| `step` | ~0,65 %, con piso de 5× fees (`MIN_STEP_FEE_MULTIPLE`) | ❌ Ya está bien calibrado. No tocar. |
| `f` (fees) | 4,4 % del bruto | ❌ No es el problema. No optimizar aquí. |
| `nocional` | Limitado por balance y `min_notional` de Binance | 🟡 Poco, hasta escalar capital. |
| $N_{\text{ciclos}}$ | **0,5 ciclos/día** | ✅ **Aquí está todo el espacio.** |

Palancas reales sobre $N_{\text{ciclos}}$, en orden de impacto/esfuerzo:
1. Que la reposición funcione (T1 — ✅ hecho).
2. Que los grids no mueran a los 3 fills (T3 — ✅ hecho).
3. **Más símbolos en paralelo** (`MAX_CONCURRENT_GRIDS` — ✅ subido a 4).
4. Rangos de timeframe más corto (1h en vez de 4h) en pares de mayor volatilidad.

---

## 2. Naturaleza de la estrategia: el grid es short-vol

**Este es el concepto central para cualquier decisión de portafolio.**

El grid trading es una estrategia **short volatility / short gamma**. Su perfil
de pagos es equivalente al de vender opciones: muchas ganancias pequeñas y
consistentes, con pérdidas raras y grandes.

Los datos lo confirman con precisión de manual:

- Win rate de ciclos: 100 % (y es **estructural**, ver doc 03 §1.4).
- Pérdidas concentradas en los cierres: −5,04 / −3,46 / −2,57 / −2,26.
- Los dos triggers dominantes (`MAX_POSITION`, `OUT_OF_RANGE`) **son los dos la
  misma cosa**: el mercado dejó de ser lateral.

### Consecuencia para el portafolio

El complemento correcto de una estrategia short-vol **no es otra estrategia
direccional cualquiera**. Es algo cuyo P&L sea **negativamente correlacionado**:
que gane exactamente cuando el grid pierde, es decir, en rupturas de rango.

Esto descarta de entrada cualquier estrategia que también sufra en tendencia, y
prioriza las de tipo breakout/momentum **no por su rendimiento aislado, sino por
su correlación**.

---

## 3. Veredicto sobre las 5 estrategias del documento raíz

Referencia: `Estrategias de Trading Automatizado con n8n y Binance.md`.

| # | Estrategia | Veredicto | Razón |
|---|---|---|---|
| 1 | **Grid Trading** | ✅ Única implementada. Mantener y arreglar. | Tiene edge bruto demostrado. |
| 2 | **Breakout apertura NY** | 🟡 Sí, pero **no como bot separado** | Ver §4: implementarlo como flip de `OUT_OF_RANGE`. |
| 3 | **Ruptura rango asiático** | 🟡 Igual que el 2 | Misma familia. Elegir uno, no los dos. |
| 4 | **Regímenes con HMM** | ❌ No ahora | La más atractiva intelectualmente y la menos probable de pagar. Necesita mucha data, validación fuera de muestra y es un imán para el sobreajuste. **Sin arnés de backtesting es imposible de evaluar.** Fase 3. |
| 5 | **Cruce de EMAs** | ❌ Descartar | Peor relación esfuerzo/retorno. En cripto 24/7 los cruces tienen win rate 35-40 % y viven de pocas tendencias grandes. **Sangra en mercado lateral, que es donde el grid gana: suma varianza sin descorrelacionar.** |

⚠️ **Regla para quien continúe:** no implementar 4 ni 5 hasta que exista un
arnés de backtesting. Una estrategia direccional sin backtest no se puede
evaluar, solo esperar — y eso no es análisis, es apuesta.

---

## 4. La idea de mayor valor: convertir `OUT_OF_RANGE` en la señal de breakout

En vez de construir un segundo bot con su propio pipeline de datos, señales y
gestión de posición, **reutilizar el evento que ya existe**.

Cuando el precio sale del rango del grid, el sistema ya sabe dos cosas:

1. El régimen lateral terminó (información de régimen, gratis).
2. Tiene inventario del lado equivocado (posición ya abierta).

**Comportamientos posibles ante ese evento:**

| Opción | Qué hace | Estado |
|---|---|---|
| A — Cerrar a mercado | Liquida el inventario en la excursión adversa máxima | ❌ Comportamiento actual. Es el que produce el drag. |
| B — RECENTER | Cancela órdenes, **conserva** el inventario y reconstruye el grid alrededor del precio actual | Especificado como [T2](03-plan-mejoras-rentabilidad.md#t2) |
| C — **Flip a breakout** | Cierra el grid y abre una posición direccional pequeña en el sentido de la ruptura | 🎯 **Propuesta de este documento (T21)** |

La opción C es elegante porque **el stop del grid se convierte en la entrada de
la tendencia**: un solo sistema cubre los dos regímenes, sin pipeline nuevo, sin
credenciales nuevas, sin otro workflow de n8n. Y es exactamente la cobertura
negativamente correlacionada que le falta al portafolio.

**No implementar C antes que B.** Orden correcto: primero B (conservar
inventario ya elimina la mayor parte del drag y es reversible), medir 2-4
semanas, y solo entonces evaluar C con datos reales de cuántos `OUT_OF_RANGE`
resultan en tendencia sostenida vs. falsa ruptura. **Ese dato hoy no existe y es
imprescindible**: si la mayoría son falsas rupturas, C pierde dinero y B es la
respuesta final.

---

## 5. ¿Operar varias estrategias a la vez?

### ✅ Varios símbolos en paralelo — sí, es la mejor palanca disponible

`pair_selector.py` ya rankea candidatos por ER, volumen, ATR y funding, y
`/auto-params` ya excluye símbolos con grid RUNNING para diversificar. Subir
`MAX_CONCURRENT_GRIDS` multiplica $N_{\text{ciclos}}$ casi linealmente sin código
nuevo.

**Límite real:** el margen. Con `MAX_RISK_PCT = 0.15` por grid, N grids pueden
comprometer hasta N×15 % del balance. Con 4 grids el techo teórico es 60 %.
Subir más allá de 4-6 exige antes un **tope de exposición agregada** (que hoy no
existe: la guarda es por grid, no de portafolio). Ver [T15](03-plan-mejoras-rentabilidad.md#t15).

### ❌ Varias estrategias sobre el MISMO símbolo — no con esta arquitectura

Binance netea posiciones por símbolo en **one-way mode**, y `create_grid()`
rechaza explícitamente hedge mode. Dos estrategias sobre BTCUSDT compartirían el
mismo `positionAmt`, así que:

- El guard NEUTRAL de `replenish_filled_orders()` leería posición ajena y
  pausaría la pata equivocada.
- El cap de inventario (`_max_net_position_qty`) contaría exposición que no es
  suya y cerraría el grid por error.
- `cancel_grid()` hace `cancel_all_open_orders(symbol)` — **cancelaría las
  órdenes de la otra estrategia**.

**Regla dura: una estrategia por símbolo a la vez.** Convivir requeriría una
capa de atribución de posición por estrategia, que es trabajo serio y no está
justificado todavía.

---

## 6. Hallazgo pendiente de verificar: el funding no está en el P&L

El bot opera **perpetuos**, y un grid NEUTRAL carga posición neta durante horas.
El funding se liquida cada 8h.

- `pair_selector.py` pondera el funding al 10 % **al elegir el par**.
- `calculate_grid_pnl()` en [indicators.py](../../backend-python/app/services/indicators.py)
  **solo descuenta fees de trading. El funding no aparece en ningún cálculo, ni
  en `grid_cycles`, ni en `pnl_snapshots`, ni en el dashboard.**

En una estrategia que gana ~0,43 USD por ciclo, el funding puede consumir el
edge completo sin dejar rastro en ninguna métrica. **Es una fuga potencialmente
comparable al closure drag y hoy es invisible.**

Verificación sugerida: consultar `GET /fapi/v1/income?incomeType=FUNDING_FEE`
para el período y compararlo contra el PnL de ciclos del mismo período. Si es
material, incorporarlo a `pnl_snapshots` y al dashboard.

---

## 7. Expectativa realista (para no perseguir fantasmas)

Con ~3000 USD, 5-13 niveles y 50-80 USD por orden, un grid bien ejecutado rinde
**1-3 % mensual bruto en condiciones favorables**. Cualquier objetivo muy por
encima de eso implica subir apalancamiento o tamaño, es decir, cambiar el perfil
de riesgo — no "mejorar la estrategia".

**El objetivo correcto no es encontrar la estrategia mágica: es llegar a +1 %
mensual neto sostenido durante 2-3 meses y entonces escalar capital.** Un
sistema que no es rentable a escala pequeña, a escala grande solo pierde más
rápido.

---

## 8. Hoja de ruta de estrategia (resumen ejecutable)

| Orden | Acción | Tarea en el plan | Estado |
|---|---|---|---|
| 1 | Que la reposición funcione | [T1](03-plan-mejoras-rentabilidad.md#t1) | ✅ |
| 2 | Que el inventario no mate el grid | [T3](03-plan-mejoras-rentabilidad.md#t3) | ✅ |
| 3 | Escalar símbolos en paralelo | T19 | ✅ (`MAX_CONCURRENT_GRIDS = 4`) |
| 4 | Dejar de liquidar en el peor momento | [T2](03-plan-mejoras-rentabilidad.md#t2) | ❌ **siguiente** |
| 5 | Medir bien (drag, PnL por trigger) | [T6](03-plan-mejoras-rentabilidad.md#t6) | ❌ |
| 6 | Filtro de régimen **continuo** (ER en cada ciclo de WF2, no solo al lanzar) | T20 | ❌ |
| 7 | Verificar el impacto del funding | T22 | ❌ |
| 8 | Flip `OUT_OF_RANGE` → breakout | T21 | ❌ (solo tras 4+ semanas de grid positivo) |
| 9 | Tope de exposición agregada + kill-switch | [T15](03-plan-mejoras-rentabilidad.md#t15) | ❌ (bloqueante para dinero real) |
| — | HMM y EMA Cross | — | ❌ Descartadas hasta tener backtesting |
