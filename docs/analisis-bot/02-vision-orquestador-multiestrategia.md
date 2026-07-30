---
title: "Análisis 02 — Visión: orquestador multi-estrategia con IA + indicadores NRT"
type: vision
status: borrador / brainstorm, no decidido
started: 2026-07-30
related: ["01-estado-actual-vs-futuro.md", "../brain/analisis-bot-monitoreo.md"]
---

# Visión: agente que decide qué estrategia usar según el mercado

Este documento captura el "sueño" planteado por el usuario el 2026-07-30: un
agente que revise datos de mercado, genere indicadores, **decida qué
estrategia usar** (de varias posibles, no solo Grid) y lance el bloque de
órdenes correspondiente. Es una visión a futuro, **no una decisión tomada
todavía** — depende de si se retoman las otras estrategias del documento
raíz (ver sección 1 de `01-estado-actual-vs-futuro.md`), lo cual está
pendiente de conversar con la compañera del usuario.

## 1. Qué existe hoy (punto de partida real)

Workflow 1 (n8n) + Gemini **ya hacen una versión mínima de esto**, pero
limitada a una sola estrategia:

```
Backend calcula indicadores (ATR, bounds, viabilidad de margen)
        ↓
Gemini recibe esos indicadores YA calculados (no los calcula él)
        ↓
Gemini decide: launch: true/false + parámetros (gridCount, etc.)
        ↓
Si true → POST /api/v1/grids (lanza Grid Trading)
```

Es decir: el patrón "IA decide sobre indicadores ya calculados, con
`responseSchema` forzando JSON estructurado" **ya está probado y
funcionando**. Lo que falta para el sueño completo es (a) más estrategias
entre las cuales elegir, y (b) que la decisión sea "cuál estrategia" y no
solo "lanzar o no la única que existe".

## 2. Cómo ayudaría un modelo como este (LLM) en la selección de estrategia

### Lo que un LLM hace bien aquí
- **Combinar múltiples señales con razonamiento contextual**: ej. "ATR% alto
  + funding rate negativo + estamos cerca de un CPI release" es el tipo de
  síntesis cualitativa que un LLM maneja mejor que un puñado de `if/else`
  (aunque esto último ya existe y funciona para casos simples — no
  reemplazar sin necesidad).
- **Explicar su decisión en lenguaje natural** para las notificaciones de
  Telegram (ya se hace: Workflow 1 notifica el razonamiento de Gemini).
- **Adaptarse a reglas de negocio nuevas sin reescribir código** — cambiar
  el prompt/system instructions es más rápido que cambiar Python + redeploy,
  útil en la fase de pruebas actual.

### Lo que un LLM NO debe hacer
- **Calcular los indicadores.** Igual que hoy, el LLM debe recibir
  indicadores ya calculados de forma determinística en Python (ATR, ADX/
  fuerza de tendencia, rango de sesión asiática, EMA cross, régimen HMM si
  se implementa) — nunca pedirle que "calcule" ATR o haga matemática de
  mercado él mismo (no es determinístico, no es auditable, puede alucinar).
- **Colocar órdenes directamente.** El LLM decide *qué* estrategia y con
  *qué parámetros*, pero la ejecución (cálculo de niveles, cantidades,
  Decimal/tickSize/stepSize, batch orders) sigue siendo 100% el motor
  Python determinístico que ya existe (`grid_engine.py` y equivalentes
  futuros por estrategia).
- **Ser la única capa de decisión sin guardas.** Igual que el tope
  `gridCount = min(IA_gridCount, Config.levels)` ya implementado, cualquier
  decisión de estrategia de la IA debe pasar por validaciones de negocio en
  Python antes de ejecutarse (ej.: no cambiar de estrategia si ya hay una
  RUNNING en ese símbolo, límites de exposición, símbolos permitidos).

## 2.1 Dónde entra el Machine Learning real (distinto de usar un LLM)

Pregunta clave que no debe quedar mezclada con lo anterior: **Gemini/Claude
NO son Machine Learning con aprendizaje** en el sentido de la estrategia #4
del documento original (HMM). Son modelos pre-entrenados y congelados —
cada llamada es independiente, no ajustan pesos con los resultados del bot,
no "recuerdan" si la decisión de hace un mes ganó o perdió. Eso es
razonamiento sobre contexto puntual, no aprendizaje.

ML real significa un modelo que **aprende de los datos históricos propios
del bot** para mejorar una decisión repetible. Con lo que se acaba de
construir (`grid_cycles` + `pnl_snapshots`, ver
`01-estado-actual-vs-futuro.md` sección 4) ya existe la materia prima
necesaria — sin esos datos, ningún ML tiene sentido (no hay con qué
entrenar). Posibles usos, de más simple a más ambicioso:

1. **Clasificador de régimen de mercado** (la idea original de HMM/estrategia
   #4): entrenar con features históricas (ATR%, volumen, Efficiency Ratio,
   funding rate) para etiquetar "Calma / Tendencia / Estrés" de forma
   aprendida en vez de umbrales fijos como hoy (`config_auto_params.py`).
   Requiere bastante historial etiquetado para ser mejor que reglas fijas.
2. **Optimización de parámetros por régimen** (el uso más directamente
   ligado a `grid_cycles`): un modelo simple (ej. regresión / gradient
   boosting) entrenado con "dado este régimen + estos parámetros de grid
   (levels, multiplier, risk_pct), ¿qué `net_pnl` resultó?" para sugerir
   parámetros que históricamente funcionaron mejor en condiciones
   similares — esto SÍ aprende de los resultados reales del bot, a
   diferencia del LLM.
3. **Reinforcement Learning** (mucho más ambicioso, no recomendado a corto
   plazo): el bot ajusta su propia política de decisión maximizando
   `net_pnl` como recompensa. Necesita un entorno de simulación robusto,
   mucho volumen de datos, y overhead de MLOps desproporcionado para el
   estado actual del proyecto.

### Camino práctico sugerido (fases)

- **Fase A (hoy):** reglas determinísticas + LLM razonando sobre contexto,
  sin aprendizaje real. Es donde está el bot ahora.
- **Fase B (en curso):** recolectar datos reales de resultados via
  `grid_cycles`/`pnl_snapshots` — sin esto, ninguna fase de ML siguiente es
  posible. Necesita semanas/meses de operación (aunque sea con dinero
  ficticio en testnet, el aprendizaje de patrones no depende de que el
  dinero sea real).
- **Fase C (futuro, una vez haya suficiente historial):** entrenar un
  modelo supervisado simple (opción 1 o 2 arriba) y usarlo como una señal
  más — ya sea alimentando su sugerencia al prompt del LLM (como otro
  indicador más), o reemplazando directamente algún umbral fijo de
  `auto_params.py`/`config_auto_params.py` que hoy es hardcodeado.
- **Fase D (opcional, alto esfuerzo):** Reinforcement Learning — solo si
  las fases anteriores muestran que vale la pena la inversión adicional.

No tiene sentido saltar a la Fase C sin haber acumulado suficiente
histórico real de ciclos en distintas condiciones de mercado — es la razón
por la que priorizamos `grid_cycles`/`pnl_snapshots` antes de hablar de ML.

### Patrón propuesto (extensión del que ya existe)

```
1. Backend Python calcula, por símbolo candidato:
   - Indicadores de régimen: ATR%, ADX/Efficiency Ratio (ya existe en
     pair_selector.py), volumen, funding rate
   - Indicadores específicos por estrategia candidata: EMA20/EMA50 (EMA
     Cross), rango de sesión asiática (Ruptura Asiática), rango primera
     vela post-apertura NY (Breakout), viabilidad de Grid (ya existe)

2. n8n arma un payload consolidado y se lo pasa a Gemini/Claude con un
   responseSchema que fuerza:
   { "strategy": "GRID" | "BREAKOUT_NY" | "ASIAN_RANGE" | "EMA_CROSS" | "NONE",
     "confidence": 0-1,
     "reasoning": "...",
     "params": { ...específicos de la estrategia elegida... } }

3. n8n interpreta la respuesta con un Switch (igual que ya hace con
   comandos de Telegram) y llama al endpoint del backend correspondiente
   a esa estrategia (cada estrategia necesitaría su propio
   POST /api/v1/<estrategia> con su propio motor Python, análogo a
   grid_service.py).

4. Guardas de negocio en Python (no en el prompt): 1 estrategia activa por
   símbolo, límites de exposición, validación de parámetros contra
   filtros de Binance — igual que ya existe para Grid.
```

**Costo de esto**: cada estrategia nueva (Breakout NY, Asian Range, EMA
Cross) requiere su propio motor determinístico en Python (equivalente a
`grid_engine.py` + `grid_service.py`), no solo "pedirle a la IA que decida"
— la IA solo reemplaza el `if/else` de selección, no el código de
ejecución. Esto es trabajo real de desarrollo, no solo de prompt.

## 3. Qué se necesita para mantener los indicadores "NRT" (near-real-time)

Hoy el sistema **no es tiempo real, es polling programado**:
- Workflow 1 (decisión) corre por cron — cadencia sugerida original de 4h.
- Workflow 2 (monitoreo) corre cada ~15 min.
- Todo el dato de mercado se obtiene vía REST de Binance (`get_klines`,
  `get_mark_price`) en el momento de cada ejecución — no hay ningún stream
  continuo ni cache de indicadores "vivos".

Para que estrategias más sensibles al timing (Breakout NY, Ruptura
Asiática) funcionen bien, **el polling por cron no alcanza** — un breakout
de la primera vela de 5 min necesita detectarse en minutos, no esperar
horas al próximo cron.

### Opciones (de menor a mayor esfuerzo)

1. **Acortar el cron** (más simple, ningún cambio de arquitectura): correr
   Workflow 1 cada 5-15 min en vez de 4h. Suficiente para EMA Cross o Grid,
   insuficiente para Breakout/Asian Range que dependen de un instante
   preciso (apertura de sesión).
2. **Cron dirigido por evento de calendario**: triggers de n8n programados
   exactamente a las horas de apertura de sesión (NY/Londres/Asia) en vez
   de un intervalo fijo — cubre Breakout NY y Ruptura Asiática sin
   necesitar streaming.
3. **WebSocket de Binance + servicio siempre-activo** (el salto real a
   "NRT"): un proceso Python persistente (no n8n, que es orientado a
   ejecuciones discretas) suscrito a streams de Binance (`kline`,
   `markPrice`, `bookTicker`), que mantiene los indicadores recalculados en
   memoria/Redis y expone un endpoint `GET /indicators/live/{symbol}` para
   que n8n lo consulte cuando decida evaluar. Esto SÍ requiere:
   - Un proceso adicional de larga duración (el backend actual es
     request/response, no tiene un loop de background para esto).
   - **Redis ya está provisionado en la infra** (`redis-trading`, ver
     `docs/brain/infra-multi-servidor.md`) pero no se usa activamente —
     encaja natural como cache de "último indicador calculado" para que
     tanto el websocket-listener como los endpoints REST lean del mismo
     lugar sin recalcular en cada request.
   - Manejo de reconexión de websocket, backpressure, y qué pasa si el
     proceso se cae (debe reconciliar con REST al reconectar, similar al
     patrón de reconciliación que ya existe para órdenes en
     `refresh_order_status()`).

### Recomendación (borrador, a validar)

No saltar directo a websockets si no hay todavía una estrategia que lo
necesite de verdad. Orden sugerido:
1. Definir con la compañera si se implementan más estrategias (decisión de
   producto pendiente).
2. Si se implementa Breakout NY o Asian Range → ahí sí se vuelve necesario
   el streaming (opción 3), porque timing de minutos importa.
3. Si se queda solo con Grid Trading (o se suma EMA Cross) → acortar cron o
   triggers por horario (opciones 1-2) es suficiente, mucho más barato de
   construir y mantener.

## 4. Próximos pasos de esta visión

1. Decisión de producto: ¿se implementan más estrategias? (pendiente con
   la compañera).
2. Si sí: diseñar el motor determinístico Python de la primera estrategia
   adicional (candidata natural: EMA Cross, es la más simple del
   documento — ver `docs/60-TRADING-LOGIC/`).
3. Diseñar el `responseSchema` multi-estrategia para el nodo de IA en n8n
   (extensión del que ya usa Workflow 1).
4. Solo si se necesita timing de minutos: diseñar el servicio de indicadores
   NRT (websocket + Redis).
