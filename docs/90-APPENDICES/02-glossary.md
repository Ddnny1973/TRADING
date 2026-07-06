# Glossary - Glosario de Términos

## A

**API Key/Secret**
Credenciales para conectar a Binance. API Key = user ID, Secret = contraseña. Nunca compartir.

**ATR (Average True Range)**
Indicador que mide volatilidad del mercado. Rango promedio en X candles. Usado para calcular tamaño de grid.

**Avg Price (Average Price)**
Precio promedio de ejecución de una orden. Si compré 0.01 BTC en 2 fills (0.006 @ 62500, 0.004 @ 62700), avg = 62580.

---

## B

**Balance**
USDT disponible en tu cuenta Binance.

**Binance Futures**
Mercado de derivados con leverage. Acá funciona grid trading.

**Bullish**
Mercado alcista. Precio tiende a subir. Ideal para grid trading.

---

## C

**Cancelado (CANCELED)**
Orden que fue cancelada antes de ejecutarse. Status final.

**Close Grid**
Cerrar una grid = cancelar todas las órdenes abiertas + vender posición.

**Comisión (Fee)**
Lo que Binance cobra por cada orden. Maker: 0.01%, Taker: 0.05%.

**Corrected Orders**
Órdenes que requieren ajustes (paso, notional, etc.)

**Crypto / USDT**
Crypto = Bitcoin, Ethereum, etc. USDT = dólar stablecoin.

**Cycle**
Ciclo completo: BUY → SELL (o SELL → BUY). Un ciclo = una ganancia.

---

## D

**Derivado / Futures**
Contrato de precio futuro. Permite short (vender antes de comprar).

**Drawdown**
Pérdida máxima desde peak. Ej. peak 1000 USDT, baja a 900 = 10% drawdown.

---

## E

**Ejecutada (FILLED)**
Orden que fue completamente ejecutada. Status final.

**Expiración**
Grid se cierra automáticamente por edad (max 224 horas).

**Exposure**
Capital total expuesto al mercado. Con leverage: mayor exposure que capital.

---

## F

**Fees (Comisiones)**
Lo que pagas a Binance. Calculadas en cada ejecución.

**Fill / Filled**
Orden se ejecutó (completamente). BUY 0.01 BTC se ejecutó = filled.

**Futures**
Ver "Derivado".

---

## G

**Ganancia Realizada (Realized PnL)**
Dinero que ganarme tras cerrar posición. BUY @ 62500, SELL @ 62710 = ganancia realizada.

**Ganancia No Realizada (Unrealized PnL)**
Dinero que ganaría SI vendo ahora (pero no he vendido). Mark price 63500 vs avg 62500 = unrealized 1000 USDT.

**Grid / Grid Trading**
Sistema de órdenes distribuidas. Múltiples BUY/SELL en rango de precios.

---

## H

**Health Check**
Endpoint `/health` que valida sistema está vivo. Responde OK si BD + Binance OK.

---

## I

**ISOLATED (Margin Type)**
Cada grid tiene su propio collateral separado. No afecta otros símbolos. Recomendado.

---

## J

**JSON**
Formato de datos. API usa JSON para request/response.

---

## K

**Kline / Candle**
Vela de OHLC (Open, High, Low, Close) en período (4h, 1d, etc.)

---

## L

**Leverage**
Apalancamiento. 5x = 5 veces más capital. ⚠️ Aumenta riesgo y fees.

**Level**
Uno de los precios donde hay órdenes en el grid. Grid 15 niveles = 15 órdenes.

**Límite de Grids (Max Concurrent)**
Máximo 2 grids activas simultáneamente.

**Liquidación (Liquidation)**
Cuando con leverage se pierde todo. Evita con leverage 1x.

**Liquidez**
Cuántos USD/BTC se pueden comprar/vender sin mover precio. Alta liquidez = fácil trade.

---

## M

**Maker**
Orden LIMIT que se agrega al book. Fee: 0.01% (más barato).

**Mark Price**
Precio actual del mercado. Usado para calcular unrealized PnL.

**Max Duration**
Tiempo máximo que puede vivir una grid. Si > 224h → cierre automático.

**Min Notional**
Tamaño mínimo de orden. Binance: ~10 USDT.

**Min Step**
Paso mínimo entre órdenes para ser rentable (después de fees). 0.2%.

---

## N

**n8n**
Plataforma de automatización. Crea workflows que orquestan backend.

**Notional**
Valor total de orden. 0.01 BTC @ 62500 = 625 USDT notional.

---

## O

**Orden (Order)**
Instrucción a Binance. BUY 0.01 BTC @ 62500 = una orden.

**Orden Abierta (OPEN)**
Orden que está en el book, esperando ejecutarse.

---

## P

**PnL**
Profit & Loss = ganancia o pérdida.

**Posición (Position)**
Cuánto BTC tengo ahora. 0.05 BTC abierto.

---

## Q

**QA**
Quality Assurance. Tests manuales para validar sistema funciona.

---

## R

**Rate Limit**
Máximo de requests a Binance. 1200 req/min. Sistema respeta.

**Realized PnL**
Ver "Ganancia Realizada".

**Refresh**
Sincronizar órdenes con Binance. Actualizar BD con estado actual.

**Replenish**
Crear nuevas órdenes en posiciones ejecutadas. Crea ciclos.

**Risk %**
Porcentaje del balance a arriesgar por grid. Default 2%.

---

## S

**Sesgo del Mercado (Bias)**
Tendencia: bullish (sube), bearish (baja), neutral (lateral).

**Sesgo Lateral (Sideways)**
Mercado en rango. No sube ni baja. Grid funciona bien.

**SL (Stop Loss)**
Precio donde grid se cierra automáticamente si baja. Limita pérdidas.

**SMA (Simple Moving Average)**
Promedio de precios últimos N candles. Usado para detectar trend.

**Spot Trading**
Mercado al contado (compra/venta física). No leverage.

**Step / Step %**
Espaciamiento entre órdenes. 0.4% = cada orden 0.4% diferencia de precio.

---

## T

**Taker**
Orden MARKET que toma liquidez del book. Fee: 0.05% (más caro).

**Testnet**
Ambiente de prueba Binance. Dinero fake. Ideal para QA.

**TP (Take Profit)**
Ganancia objetiva. Si alcanza → grid se cierra. Ej. TP 5%.

**Trading**
Comprar/vender activos buscando ganancias.

---

## U

**Unrealized PnL**
Ver "Ganancia No Realizada".

**Uptime**
% de tiempo que sistema está online. >99% = muy bueno.

---

## V

**Volatilidad**
Cuánto se mueve el precio. Alta volatilidad = más ciclos posibles.

**Volatilidad Implícita (IV)**
Volatilidad esperada. No usamos en grid trading.

---

## W

**Webhook**
URL que n8n llama para ejecutar acción. Backend = webhook de n8n.

**Workflow**
Automatización en n8n. Workflow 1 = decisión, Workflow 2 = monitoreo.

---

## X-Z

**Xi Jing Ping**
No está en glossary de trading 😄

**Yield / Rendimiento**
Retorno esperado. 1% diario = 30% mensual (aprox).

**Zona de Confort (Comfort Zone)**
Rango de precios donde grid funciona mejor.

---

## Símbolos Comunes

| Símbolo | Significado |
|---------|------------|
| BTC | Bitcoin |
| ETH | Ethereum |
| USDT | USD stablecoin |
| BTCUSDT | Par BTC/USDT |
| 4h | 4-hour candle |
| 1d | 1-day candle |
| API | Application Programming Interface |
| DB / BD | Database |
| OK ✅ | Funciona correctamente |
| ❌ | Error / No funciona |
| ⚠️ | Advertencia / Cuidado |

---

¿Falta un término? Actualiza este glossary o abre issue.
