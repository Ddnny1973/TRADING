# Arquitectura del Sistema - Grid Trading Híbrido

## Descripción General

El **Grid Trading Híbrido** es un sistema autónomo distribuido diseñado para ejecutar estrategias de grid trading en Binance Futures. Utiliza una arquitectura de microservicios en Docker que separa las responsabilidades de ejecución financiera, orquestación lógica y analítica de datos.

## Componentes Principales

### 1. Backend Python (FastAPI)
**Responsabilidades:**
- Ejecución de órdenes en Binance Futures
- Cálculo exacto de niveles de grid
- Gestión de firmas criptográficas HMAC-SHA256
- Control de estado local de órdenes (SQLite)

**Tecnologías:**
- FastAPI (framework web)
- Uvicorn (ASGI server)
- SQLAlchemy (ORM)
- Pydantic (validación)

### 2. Orquestador n8n
**Responsabilidades:**
- Automatización de flujos lógicos
- Ingestión de datos de mercado externos
- Ejecución de comandos de control
- Notificaciones a usuarios

**Integraciones:**
- PostgreSQL (persistencia de datos)
- Telegram Bot API
- WhatsApp API

### 3. Redis
**Responsabilidades:**
- Caché distribuida
- Gestión de rate limits en tiempo real
- Sincronización de estado entre servicios

### 4. PostgreSQL
**Responsabilidades:**
- Almacenamiento histórico de trades
- Análisis de rendimiento
- Logs de ejecución

### 5. SQLite (Local)
**Responsabilidades:**
- Almacenamiento de grid activos
- Estado de órdenes en caliente
- Baja latencia

## Flujo de Datos

```
[Usuario/Webhook]
        ↓
[Proxy Inverso - Nginx/Traefik]
        ↓
[n8n - Orquestación]
        ↓
[Backend Python - Ejecución]
        ↓
[Binance Futures API]
```

## Seguridad

- ✅ **Centralización de Firmas:** Todas las firmas HMAC-SHA256 se generan en el backend
- ✅ **Aislamiento de Credenciales:** API Keys almacenadas en variables de entorno seguras
- ✅ **Proxy Inverso:** Protege el backend del acceso público directo
- ✅ **Validación de Timestamps:** Sincronización con servidores Binance (recvWindow ≤ 5000ms)

## Requerimientos Técnicos

### R-01: Autenticación y Criptografía
- Centralización absoluta de firmas HMAC-SHA256
- Validación de `recvWindow` según estándares Binance

### R-02: Precisión Matemática
- Uso de `Decimal` en lugar de floats
- Redondeo hacia abajo (ROUND_DOWN) según filtros de Binance

### R-03: Motor de Grid Autónomo
- Cálculo local de grillas (geométrica o aritmética)
- Envío individual de órdenes LIMIT
- Gestión automática de fills parciales

## Diagrama de Infraestructura

```
┌─────────────────────────────────────────────┐
│         Red Externa                         │
│  ├─ Binance Futures API (Testnet)          │
│  ├─ Telegram Bot API                       │
│  └─ WhatsApp API                           │
└─────────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────────┐
│      Proxy Inverso (Nginx/Traefik)          │
│     (Terminación SSL + Enrutamiento)        │
└─────────────────────────────────────────────┘
              ↓
┌──────────────────────────────────────────────────────────────────┐
│                    Docker Compose Network                         │
│                                                                   │
│  ┌──────────────────┐  ┌──────────────────┐  ┌─────────────┐   │
│  │  Backend Python  │  │  n8n Orchestrator│  │    Redis    │   │
│  │  (FastAPI)       │  │  (n8n)           │  │  (Cache)    │   │
│  │                  │  │                  │  │             │   │
│  │  Port: 8000      │  │  Port: 5678      │  │  Port: 6379 │   │
│  │  SQLite (Local)  │  │                  │  │             │   │
│  └──────────────────┘  └──────────────────┘  └─────────────┘   │
│           ↕                      ↕                   ↕            │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │         PostgreSQL (Data Warehouse)                     │    │
│  │         Port: 5432                                      │    │
│  │         DB: trading_history                             │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

## Próximas Fases

**Fase 1:** Implementación del Backend Python y Grid Engine
**Fase 2:** Integración de n8n Workflows
**Fase 3:** Sistema de Notificaciones Avanzadas
**Fase 4:** Dashboard de Monitoreo
**Fase 5:** Optimización y Escalabilidad
