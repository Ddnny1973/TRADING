---
title: "Resumen ejecutivo — para revisar con la compañera"
type: resumen
status: para discutir / decisiones pendientes marcadas explícitamente
started: 2026-07-31
related: ["01-estado-actual-vs-futuro.md", "02-vision-orquestador-multiestrategia.md"]
---

# Resumen ejecutivo — Bot de Trading (Grid Trading + n8n + Binance)

Documento corto pensado para leer juntos y aclarar ideas. El detalle técnico
completo está en `01-estado-actual-vs-futuro.md` y
`02-vision-orquestador-multiestrategia.md`, en esta misma carpeta.

## 1. ¿Qué hay hoy funcionando?

- El bot opera **una sola estrategia: Grid Trading** (malla de órdenes de
  compra/venta), sobre **Binance testnet** (dinero ficticio, a propósito —
  todavía no se ha decidido pasar a dinero real).
- Un LLM (**Gemini**) decide, cada cierto tiempo, si lanzar un grid nuevo y
  con qué parámetros, en base a indicadores que calcula el backend
  (volatilidad/ATR, viabilidad de margen). El LLM **no calcula** los
  indicadores ni coloca órdenes directamente — solo decide "lanzar o no" y
  el resto lo ejecuta código determinístico en Python.
- Un segundo proceso automático monitorea los grids activos cada ~15 min
  (refresca órdenes, repone las que se llenan, cierra por stop-loss/take
  profit o por vencimiento).
- Notificaciones y comandos por Telegram ya funcionan (`/lanzar`,
  `/monitorear`).

## 2. El documento original proponía 5 estrategias — solo 1 está hecha

| Estrategia | Estado |
|---|---|
| Grid Trading | ✅ Implementada (la única) |
| Breakout primera vela (apertura NY) | ❌ No implementada |
| Ruptura Rango Asiático | ❌ No implementada |
| Optimización con IA (HMM / regímenes) | ❌ No implementada |
| Cruce de Medias Móviles (EMA) | ❌ No implementada |

**Pregunta para decidir juntas:** ¿vale la pena implementar alguna de las
otras 4, o nos enfocamos en madurar bien Grid Trading primero?

## 3. ¿Cómo sabemos si el bot realmente gana dinero?

Antes de esta semana, **no había forma clara de medirlo** — solo existía el
PnL final de cada grid al cerrarse, sin detalle de comisiones ni de cuántos
"ciclos" completos (compra+venta) hizo. Ya se corrigió: se crearon dos
tablas nuevas en la base de datos (`grid_cycles` y `pnl_snapshots`) que
registran, automáticamente, cada ciclo ganador/perdedor y la evolución del
PnL en el tiempo.

**Con esto, en unas semanas podremos calcular:**
- Ganancia neta acumulada (después de comisiones).
- % de ciclos ganadores.
- Cuánto se comen las comisiones de la ganancia bruta.
- Peor caída (drawdown).

## 4. ¿Cuándo pasamos a dinero real? (criterio propuesto, a validar)

- Ganancia neta positiva sostenida por 2-4 semanas seguidas (no solo un
  pico afortunado).
- Que ese resultado sea estable, no un caso aislado.
- Que el bot no se auto-cancele seguido por fallas de sincronización con
  Binance.
- Que la peor caída observada sea algo que estemos dispuestas a asumir con
  capital real.

**Pregunta para decidir juntas:** ¿estos criterios les parecen razonables,
o prefieren otros umbrales (ej. más semanas, % mínimo de ganancia)?

## 5. La "IA que decide qué estrategia usar" — aclarando conceptos

- Un LLM (Gemini/Claude) **no aprende** de los resultados pasados del bot —
  cada vez que se le pregunta, razona solo con la información que se le
  manda en ese momento. Es útil para combinar señales y decidir con
  contexto, pero no mejora solo con el tiempo.
- Machine Learning "de verdad" (que sí aprende de resultados históricos)
  **recién ahora es posible**, porque necesita datos — y las tablas del
  punto 3 son justo eso: la materia prima para entrenar un modelo más
  adelante (por ejemplo, para detectar el "estado de ánimo" del mercado, o
  para sugerir qué parámetros de grid funcionan mejor según las
  condiciones).
- **No es algo para implementar ya** — hace falta acumular semanas/meses de
  datos reales de operación primero.

## 6. Próximos pasos concretos

1. Validar en vivo que el registro de ciclos/PnL funciona bien (técnico, en
   curso).
2. **Reunión con la compañera** para decidir el punto 2 (más estrategias o
   no) y el punto 4 (criterio de paso a dinero real).
3. Dejar correr el bot en testnet varias semanas acumulando datos.
4. Con esos datos, revisar objetivamente si Grid Trading es rentable y
   decidir el paso a producción.
