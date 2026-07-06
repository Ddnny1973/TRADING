# TRADING - Grid Trading Bot Binance Futures

## ¿Qué es TRADING?

**TRADING** es un **sistema autónomo de grid trading** para Binance Futures que:

✅ **Crea grids automáticamente** con parámetros dinámicos basados en IA  
✅ **Ejecuta ciclos continuos** (BUY→SELL→BUY...) sin intervención manual  
✅ **Cierra grids** automáticamente por Stop Loss, Take Profit, o Expiración  
✅ **Maneja 1-2 grids simultáneamente** con exposición controlada (max 4% del capital)  
✅ **Opera 24/7** con monitoreo automático cada 15 minutos  
✅ **Calcula PnL neto** incluyendo comisiones reales de Binance

---

## Composición del Sistema

```
┌──────────────────────────────────────┐
│        n8n Workflows (UI)             │
│  - Workflow 1: Market Decision        │
│  - Workflow 2: Grid Monitor           │
└────────────────┬─────────────────────┘
                 │
         ┌───────▼────────┐
         │ Backend FastAPI │
         │   (Python)      │
         └───────┬────────┘
                 │
    ┌────────────┼────────────┐
    │            │            │
┌───▼──┐  ┌─────▼────┐  ┌────▼──────┐
│SQLite│  │PostgreSQL│  │ Binance   │
│ (BD) │  │(opt.)    │  │ Futures   │
└──────┘  └──────────┘  └──────────┘
```

---

## Comienza Aquí

**Eres nuevo?** Sigue esta ruta en orden:

1. **[Inicio Rápido](docs/00-START/01-inicio-rapido.md)** — Setup en 30 minutos (recomendado)
2. **[Flujos por Rol](docs/00-START/03-flujos-por-rol.md)** — Elige tu camino según tu rol
3. **[Tabla de Contenidos](docs/00-START/02-tabla-contenidos.md)** — Navega toda la documentación

---

## Tabla de Contenidos

### 📖 Documentación

| Sección | Contenido | Para Quién |
|---------|-----------|-----------|
| **[00-START](docs/00-START/)** | Inicio rápido, tabla de contenidos, flujos por rol | Todos |
| **[10-ARQUITECTURA](docs/10-ARQUITECTURA/)** | Componentes del sistema, arquitectura | Arquitectos, Developers |
| **[20-SETUP](docs/20-SETUP/)** | Instalación completa | DevOps, Usuarios nuevos |
| **[30-API-REFERENCE](docs/30-API-REFERENCE/)** | Endpoints, error codes | Developers, n8n builders |
| **[40-OPERACIONAL](docs/40-OPERACIONAL/)** | Troubleshooting, comandos, QA | Operadores, QA |
| **[50-WORKFLOWS](docs/50-WORKFLOWS/)** | Explicación de workflows n8n | Usuarios, Operadores |
| **[60-TRADING-LOGIC](docs/60-TRADING-LOGIC/)** | Grid trading basics, risk, PnL | Traders, QA |
| **[70-DEVELOPMENT](docs/70-DEVELOPMENT/)** | Code structure, testing | Developers |
| **[80-CHANGELOG](docs/80-CHANGELOG/)** | Historial de cambios | Todos |
| **[90-APPENDICES](docs/90-APPENDICES/)** | FAQ, glossary, metrics | Referencia |

---

## Flujos por Rol (Quick Links)

### 🟢 Usuario Nuevo
→ [Inicio Rápido](docs/00-START/01-inicio-rapido.md) (30 min)

### 📊 Operador (Daily Trading)
→ [Visión General de Workflows](docs/50-WORKFLOWS/01-vision-general.md)  
→ [Risk Management](docs/60-TRADING-LOGIC/02-risk-management.md)

### ✅ QA/Tester
→ [QA Quick Reference](docs/40-OPERACIONAL/03-qa-quick-reference.md)  
→ [Verificación](docs/20-SETUP/03-verificacion.md)

### 💻 Developer
→ [Code Structure](docs/70-DEVELOPMENT/01-code-structure.md)  
→ [API Reference](docs/30-API-REFERENCE/01-request-response.md)

### 🛡️ Mantenedor (Production)
→ [Troubleshooting](docs/40-OPERACIONAL/01-troubleshooting.md)  
→ [Comandos Comunes](docs/40-OPERACIONAL/02-comandos-comunes.md)

---

## Estructura del Repositorio

```
TRADING/
├── README.md                        # Este archivo (índice maestro)
├── docker-compose.yml               # Orquestación de contenedores
│
├── backend-python/                  # Backend FastAPI
│   ├── app/
│   │   ├── main.py                 # FastAPI + endpoints
│   │   ├── core/                   # Config, security
│   │   ├── services/               # Grid logic
│   │   ├── database/               # Models, BD
│   │   └── schemas/                # Pydantic validation
│   ├── tests/                      # 54 tests unitarios
│   ├── requirements.txt            # Dependencies
│   └── grid_trading.db             # BD SQLite
│
├── n8n-workflows/                   # Workflows n8n
│   ├── workflow1-market-decision.json
│   ├── workflow2-monitor.json
│   └── README.md
│
└── docs/                            # Documentación (TÚ ESTÁS AQUÍ)
    ├── 00-START/                   # Inicio rápido
    ├── 10-ARQUITECTURA/            # Diseño del sistema
    ├── 20-SETUP/                   # Instalación
    ├── 30-API-REFERENCE/           # Endpoints
    ├── 40-OPERACIONAL/             # Troubleshooting
    ├── 50-WORKFLOWS/               # Workflows n8n
    ├── 60-TRADING-LOGIC/           # Lógica de trading
    ├── 70-DEVELOPMENT/             # Code + tests
    ├── 80-CHANGELOG/               # Historial
    └── 90-APPENDICES/              # FAQ, glossary
```

---

## Primeros Pasos

### 1️⃣ Clonar y Entrar

```bash
git clone <repo-url> TRADING
cd TRADING
```

### 2️⃣ Configurar .env

```bash
cp backend-python/.env.example backend-python/.env
# Edita backend-python/.env con tus API keys de Binance Testnet
```

### 3️⃣ Iniciar Docker

```bash
docker-compose up -d
```

Verifica que está corriendo:
```bash
curl http://localhost:8000/health
```

### 4️⃣ Configurar n8n

```
Abre http://localhost:5678
Settings → Environment Variables
BACKEND_URL=http://backend-python:8000
N8N_BLOCK_ENV_ACCESS_IN_NODE=false
TELEGRAM_CHAT_ID=<tu-chat-id>
Reinicia n8n
```

### 5️⃣ Importar Workflows

```
n8n → Create New → Import from File
Importa:
- n8n-workflows/workflow1-market-decision.json
- n8n-workflows/workflow2-monitor.json
```

### 6️⃣ Ejecutar Primer Test

```bash
curl -X POST http://localhost:8000/market-analysis \
  -H "Content-Type: application/json" \
  -d '{"symbol": "BTCUSDT", "interval": "4h"}'
```

### 7️⃣ Leer Documentación

[Lee el Inicio Rápido completo](docs/00-START/01-inicio-rapido.md)

---

## Características Principales

### ✅ FASE 1: Correctitud
- Cierre real de grids (0 órdenes, 0 posición)
- Leverage 1× y Margin ISOLATED automático
- Expiración automática por edad
- Stop Loss / Take Profit reales

### ✅ FASE 2: Rentabilidad
- Comisiones reales de Binance (maker/taker)
- Validación: paso mínimo 0.2% (rentable tras fees)
- PnL neto de comisiones
- Usa executedQty y avgPrice reales

### ✅ FASE 3: Estrategia
- Reposición automática (ciclos continuos)
- Refresh eficiente (1 llamada por símbolo)
- Grid opera indefinidamente hasta cierre

### ✅ FASE 4: Robustez
- Límite de grids simultáneos (max 2)
- Sesión HTTP reutilizable
- Manejo de rate limits (429/418)
- Mark price real para PnL
- Logging estructurado
- Índice anti-race en BD
- Health check mejorado

---

## Configuración Recomendada

```env
# Binance
BINANCE_TESTNET_URL=https://demo-fapi.binance.com

# Grid Trading
DEFAULT_RISK_PCT=0.02           # 2% por grid
DEFAULT_LEVERAGE=1              # Sin leverage
DEFAULT_MARGIN_TYPE=ISOLATED    # Aisla riesgo
MAX_CONCURRENT_GRIDS=2          # Max 2 simultáneos

# n8n
BACKEND_URL=http://backend-python:8000
TELEGRAM_BOT_TOKEN=<tu-token>

# Logs
LOG_LEVEL=INFO
```

---

## Casos de Uso

✅ **Grid Trading Alcista (BULLISH)**
- Mercado sube: BUY se ejecutan, SELL se ejecutan, ciclos
- Rentabilidad: 0.3-1% diario

✅ **Grid Trading Lateral (SIDEWAYS)**
- Mercado en rango: ciclos repetidos arriba-abajo
- Rentabilidad: 0.2-0.8% diario

❌ **Grid Trading Bajista (BEARISH)**
- Mercado baja: BUY se ejecutan pero SELL no
- Stop Loss se activa, pérdida controlada

---

## Limitaciones Conocidas

| Limitación | Razón | Impacto |
|-----------|-------|--------|
| Max 2 grids | Diversificación + control de riesgo | Exposure limitado a 4% |
| No WebSocket | Simplifica deployment | Polling cada 15 min |
| Leverage 1x | Reduce liquidations | Retorno limitado |
| Solo Binance | Liquidez + documentación | No soporta otros exchanges |

---

## Roadmap Futuro

| Mejora | Prioridad | Estado |
|--------|-----------|--------|
| WebSocket User Data Stream | P1 | Pendiente |
| Stop MARKET nativo | P1 | Pendiente |
| Redis rate limiting | P2 | Pendiente |
| Múltiples símbolos | P2 | Pendiente |
| Dashboard web | P3 | Pendiente |
| Backtesting | P3 | Pendiente |

---

## Soporte & Troubleshooting

### Problemas Comunes

| Problema | Solución |
|----------|----------|
| Backend no responde | `docker-compose restart backend-python` |
| Órdenes no se crean | Verifica balance en Testnet |
| Workflow falla | Revisa logs: `docker-compose logs n8n` |
| "Max grids exceeded" | Cierra una grid: `curl -X POST /close-grid/ID` |

### Documentación Rápida

- **Error técnico?** → [Troubleshooting](docs/40-OPERACIONAL/01-troubleshooting.md)
- **Pregunta?** → [FAQ](docs/90-APPENDICES/01-faq.md)
- **Definición?** → [Glossary](docs/90-APPENDICES/02-glossary.md)
- **Cómo usar API?** → [API Reference](docs/30-API-REFERENCE/01-request-response.md)

---

## Métricas Esperadas

| Métrica | Esperado | Rango |
|---------|----------|-------|
| Tiempo respuesta /health | < 100ms | 50-200ms |
| Tiempo respuesta /grids | < 500ms | 200-1000ms |
| Workflow 1 duración | < 30s | 15-60s |
| Workflow 2 duración | < 5s | 3-10s |
| Ciclos por grid/día | 3-10 | Depende volatilidad |
| PnL realizado/grid/semana | +0.2% a +2% | Tras fees |
| Uptime del sistema | > 99% | Excepto mantenimiento |

---

## Checklist para Pasar a Producción

- [ ] ✅ LEE [Inicio Rápido](docs/00-START/01-inicio-rapido.md)
- [ ] ✅ LEE [Flujos por Rol](docs/00-START/03-flujos-por-rol.md) (tu rol)
- [ ] ✅ Completa [Setup Backend](docs/20-SETUP/02-setup-backend.md)
- [ ] ✅ Completa [Setup n8n](docs/20-SETUP/01-setup-n8n.md)
- [ ] ✅ Ejecuta [Verificación](docs/20-SETUP/03-verificacion.md) (14 tests)
- [ ] ✅ Ejecuta [QA Quick Reference](docs/40-OPERACIONAL/03-qa-quick-reference.md) (10 tests)
- [ ] ✅ Escenario 48 horas con PnL positivo
- [ ] ✅ Cambia `.env` a Mainnet (si estás listo)
- [ ] ✅ Comienza con capital pequeño (1-2%)
- [ ] ✅ Monitorea primeras 2 semanas

---

## Próximos Pasos

1. **Opción A (Usuario):** [Inicio Rápido](docs/00-START/01-inicio-rapido.md)
2. **Opción B (Developer):** [Code Structure](docs/70-DEVELOPMENT/01-code-structure.md)
3. **Opción C (QA):** [Verificación](docs/20-SETUP/03-verificacion.md)
4. **Opción D (Producción):** [Troubleshooting](docs/40-OPERACIONAL/01-troubleshooting.md)

---

## Licencia & Créditos

Este proyecto es código abierto. Úsalo libremente, pero **bajo tu propio riesgo**.

**No hay garantía de ganancias.** Trading conlleva riesgo de pérdida.

---

## Contacto & Feedback

- 📖 **Documentación:** Ver `/docs/`
- 🐛 **Bug reports:** Abre issue en GitHub
- 💡 **Sugerencias:** PR bienvenidos
- ❓ **Preguntas:** Ver [FAQ](docs/90-APPENDICES/01-faq.md)

---

## Última Actualización

**Fecha:** 2026-07-05  
**Estado:** ✅ Implementación completada y documentada  
**Versión:** 1.0 (Producción)

---

## Quick Links

| Link | Descripción |
|------|-------------|
| [Inicio Rápido](docs/00-START/01-inicio-rapido.md) | Setup en 30 min |
| [API Reference](docs/30-API-REFERENCE/01-request-response.md) | Endpoints |
| [Troubleshooting](docs/40-OPERACIONAL/01-troubleshooting.md) | Errores comunes |
| [Grid Trading Basics](docs/60-TRADING-LOGIC/01-grid-basics.md) | Aprende trading |
| [Code Structure](docs/70-DEVELOPMENT/01-code-structure.md) | Código |
| [FAQ](docs/90-APPENDICES/01-faq.md) | Preguntas |

---

**¡Bienvenido a TRADING! 🚀**

Comienza con [Inicio Rápido](docs/00-START/01-inicio-rapido.md) y estará operativo en 30 minutos.
