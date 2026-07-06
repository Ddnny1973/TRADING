# FAQ - Preguntas Frecuentes

## Setup & Instalación

**P: ¿Cómo instalo el sistema?**
R: Lee [Inicio Rápido](../00-START/01-inicio-rapido.md). En 30 minutos tendrás todo corriendo.

**P: ¿Necesito credenciales reales de Binance?**
R: No para empezar. Usa Testnet: https://testnet.binancefuture.com

**P: ¿Puedo usar Windows/Mac?**
R: Sí. Necesitas Docker y Docker Compose instalados.

**P: ¿Qué pasa si no tengo Python instalado?**
R: No necesitas. Docker maneja todo. Solo necesitas Docker + n8n.

---

## Operación

**P: ¿Con qué frecuencia corro Workflow 1?**
R: Cada 4 horas (o manualmente). Valida mercado y crea nuevas grids si es bullish.

**P: ¿Y Workflow 2?**
R: Cada 15 minutos automáticamente. Monitorea grids activas, sincroniza fills, replenish.

**P: ¿Cuántas grids puedo tener?**
R: Máximo 2 simultáneas. Esto evita riesgo concentrado.

**P: ¿Cuál es el máximo de capital en riesgo?**
R: Con 2% risk × 2 grids = 4% del balance total. Para 10,000 USDT: máx 400 USDT.

**P: ¿Qué pasa si el mercado cae?**
R: Stop Loss se ejecuta automáticamente. Grid cierra con pérdida limitada.

---

## Grid Trading

**P: ¿Qué es exactamente un grid?**
R: Conjunto de órdenes distribuidas entre un precio bajo y alto. Cuando se ejecutan, crea ciclos automáticos de compra-venta.

**P: ¿Cómo funciona el ciclo?**
R: BUY @ 62500 → SELL @ 62710 → BUY @ 62500 → ... Repetidas veces.

**P: ¿Funciona en mercado bajista?**
R: No. Grid trading funciona mejor en mercados alcistas o laterales. En bajista, espera o cierra.

**P: ¿Cuánto debo poner de capital inicial?**
R: Mínimo ~1000 USDT para que tenga sentido (~50-100 USDT por grid). Mejor 5000+ USDT.

**P: ¿Cuáles son los riesgos?**
R: Mercado bearish (SL se ejecuta), bugs de software (mitigados con tests), Binance API issues (mitigados con reintentos).

---

## Ganancias

**P: ¿Cuánto gano por ciclo?**
R: Depende del step. Con 0.4% step y 0.02% comisiones: ~0.38% neto.

**P: ¿Cuántos ciclos por día?**
R: 3-10 ciclos depende volatilidad. En mercado caliente: más ciclos.

**P: ¿Realista esperar 1-2% diario?**
R: No. Grid trading es estrategia de bajo retorno + bajo riesgo. Espera 0.3-1% diario.

**P: ¿Y semanal?**
R: Si tienes 10 ciclos semanales × 0.38% = 3.8% por semana (caso optimista).

**P: ¿Debo usar leverage?**
R: NO. Leverage aumenta pérdidas potenciales. Stay at 1x.

---

## Problemas Comunes

**P: Mi grid no se crea. ¿Qué hago?**
R: 
1. Verifica `/health`: `curl http://localhost:8000/health`
2. Revisa logs: `docker-compose logs backend-python`
3. Lee [Troubleshooting](../40-OPERACIONAL/01-troubleshooting.md)

**P: Órdenes se crean pero no se ejecutan.**
R:
1. Verifica balance en Testnet
2. Verifica API key/secret
3. Verifica IP whitelist en Binance

**P: Workflow 2 no replenish.**
R:
1. Verifica que hay fills (órdenes ejecutadas)
2. Verifica logs de n8n
3. Ejecuta `refresh-grid` manualmente

**P: Backend está lento.**
R:
1. Reinicia: `docker-compose restart backend-python`
2. Verifica CPU/memoria: `docker stats`
3. Limpia BD vieja si es necesario

---

## Binance & API

**P: ¿Es seguro dar API key/secret?**
R: No a extraños. En tu máquina: seguro. En producción: IP whitelist en Binance.

**P: ¿Qué permisos necesita la API key?**
R: Futures Trading (place/cancel orders) + Read (consultar posición).

**P: ¿Rate limiting es un problema?**
R: No. Sistema respeta 1200 req/min de Binance. Con 2 grids no hay problema.

**P: ¿Y si Binance API cae?**
R: Sistema reintenta automáticamente. Workflow maneja 503/429 errors.

---

## Pasaje a Producción

**P: ¿Cómo paso de Testnet a Mainnet?**
R:
1. Haz QA completa en Testnet (48h mínimo)
2. Cambia `.env` BINANCE_TESTNET_URL → https://fapi.binance.com
3. Comienza con capital pequeño (1-2% de tu balance)
4. Monitorea 2 semanas

**P: ¿Puedo pasar sin QA?**
R: NO. QA es mandatorio. Ejecuta [manual-qa-runbook.md](../40-OPERACIONAL/03-qa-quick-reference.md)

**P: ¿Necesito VPS/servidor?**
R: Para Testnet/desarrollo: tu máquina. Para producción: recomendado un VPS 24/7.

**P: ¿Puedo dejar corriendo en mi laptop?**
R: Técnicamente sí, pero risky. Si la laptop se apaga → grids desaparecen.

---

## Desarrollo

**P: ¿Cómo agrego una nueva feature?**
R: Lee [Code Structure](../70-DEVELOPMENT/01-code-structure.md) y [Testing](../70-DEVELOPMENT/02-testing-strategy.md).

**P: ¿Dónde está la lógica de grid?**
R: `backend-python/app/services/grid_service.py` y `grid_engine.py`

**P: ¿Cómo escribo un test?**
R: Usa pytest. Lee tests existentes en `tests/` y copia estructura.

**P: ¿Puedo modificar los workflows?**
R: Sí. Abre en n8n UI y edita. Pero cuidado: cambios deben ser validados.

---

## Soporte & Contacto

**P: ¿Dónde encuentro ayuda?**
R:
1. [FAQ](01-faq.md) (este archivo)
2. [Troubleshooting](../40-OPERACIONAL/01-troubleshooting.md)
3. [Glossary](02-glossary.md) (términos)
4. Logs: `docker-compose logs -f`

**P: ¿Quién mantiene el código?**
R: Este proyecto. Lee [CHANGELOG](../80-CHANGELOG/01-audit-fixes.md) para cambios.

**P: ¿Hay un Discord/Slack?**
R: No (proyecto personal). Pero código está documentado.

---

## Límites Conocidos

**P: ¿Por qué máximo 2 grids?**
R: Balance entre diversificación y riesgo de concentración.

**P: ¿Por qué sin leverage?**
R: Reduce riesgo de liquidación. Leverage = peligro.

**P: ¿Por qué sin WebSocket?**
R: Simplifica deployment. REST API polling es suficiente para 15 min cron.

**P: ¿Por qué solo Binance Futures?**
R: Liquidez + documentación. Spot trading es diferente (no hay short).

---

## Mejoras Futuras

**P: ¿Habrá WebSocket?**
R: Posiblemente. Daría fills en tiempo real (hoy: 15 min polling).

**P: ¿Habrá múltiples símbolos?**
R: Tal vez. Hoy: máx 2 simultáneos (limitación de riesgo).

**P: ¿Dashboard web?**
R: No en roadmap actual. Usa Binance UI para monitoreo.

**P: ¿Backtesting?**
R: No. Sistema es para live trading.

---

## Tips Finales

1. **Empieza pequeño.** 1-2% de tu balance en Testnet.
2. **Monitorea primeras 2 semanas.** Incluso en producción.
3. **No esperes 10% daily.** Grid = bajo retorno, bajo riesgo.
4. **Lee la docs.** 80% de problemas se resuelven aquí.
5. **Haz backup de BD.** Antes de cambios importantes.

---

¿Tienes pregunta no listada? Abre issue o lee [Glossary](02-glossary.md).
