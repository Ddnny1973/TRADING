# Flujos por Rol - Qué Leer y Hacer

## 1. USUARIO NUEVO (Quiero empezar ya)

**Meta:** Setup en 30 minutos y hacer primer trade.

**Ruta:**
1. [Inicio Rápido](01-inicio-rapido.md) — Setup paso a paso
2. [Setup de n8n](../20-SETUP/01-setup-n8n.md) — Configurar workflows
3. [Setup del Backend](../20-SETUP/02-setup-backend.md) — Docker y .env
4. [Verificación](../20-SETUP/03-verificacion.md) — Validar que funciona
5. [QA Quick Reference](../40-OPERACIONAL/03-qa-quick-reference.md) — Primeros tests
6. ¡Ejecuta Workflow 1 manualmente en n8n!

**Tiempo estimado:** 30 minutos

---

## 2. OPERADOR (Quiero operar diariamente)

**Meta:** Entender qué hacer cada día, cómo monitorear, qué vigilar.

**Ruta:**
1. [Grid Basics](../60-TRADING-LOGIC/01-grid-basics.md) — Entender qué es un grid
2. [Visión General de Workflows](../50-WORKFLOWS/01-vision-general.md) — Flujo del sistema
3. [Workflow 1: Market Decision](../50-WORKFLOWS/02-workflow1.md) — Cómo crea grids
4. [Workflow 2: Monitor](../50-WORKFLOWS/03-workflow2.md) — Cómo monitorea
5. [Risk Management](../60-TRADING-LOGIC/02-risk-management.md) — Stop Loss, TP, límites
6. [Comandos Comunes](../40-OPERACIONAL/02-comandos-comunes.md) — Consultar estado
7. [Troubleshooting](../40-OPERACIONAL/01-troubleshooting.md) — Si algo falla

**Tiempo estimado:** 1-2 horas

---

## 3. QA/TESTER (Quiero validar que funciona)

**Meta:** Ejecutar tests, documentar resultados, validar estabilidad.

**Ruta:**
1. [QA Quick Reference](../40-OPERACIONAL/03-qa-quick-reference.md) — Referencia rápida
2. [Verificación](../20-SETUP/03-verificacion.md) — Health checks
3. [Troubleshooting](../40-OPERACIONAL/01-troubleshooting.md) — Resolver problemas
4. [Metrics](../90-APPENDICES/03-metrics.md) — Qué esperar
5. **Documento tus resultados** en un archivo `qa-results-{DATE}.md`

**Tests a ejecutar:**
- TEST 1-10: Validación de componentes
- Escenario 48h: Sistema estable

**Tiempo estimado:** Depende del escenario (4h a 48h)

---

## 4. DESARROLLADOR (Quiero contribuir código)

**Meta:** Entender la arquitectura, cómo agregar funciones, dónde hacer cambios.

**Ruta:**
1. [Componentes](../10-ARQUITECTURA/01-componentes.md) — Visión general
2. [Code Structure](../70-DEVELOPMENT/01-code-structure.md) — Archivos y módulos
3. [API Reference](../30-API-REFERENCE/01-request-response.md) — Endpoints existentes
4. [Testing Strategy](../70-DEVELOPMENT/02-testing-strategy.md) — Cómo escribir tests
5. Lee el código en `backend-python/app/`
6. **Haz cambios → Escribe tests → Commit**

**Tiempo estimado:** 2-4 horas para entender; luego depende del cambio

---

## 5. DBA (Quiero entender la base de datos)

**Meta:** Esquema, índices, queries útiles, backups.

**Ruta:**
1. [Componentes → Base de Datos](../10-ARQUITECTURA/01-componentes.md#base-de-datos)
2. [Code Structure → Database](../70-DEVELOPMENT/01-code-structure.md#database)
3. Lee `backend-python/app/database/models.py`
4. **Queries útiles:**
   ```sql
   SELECT * FROM grids WHERE status IN ('ACTIVE', 'REFRESHING');
   SELECT * FROM orders WHERE grid_id = 'XXX' ORDER BY created_at DESC;
   SELECT * FROM pnl_history ORDER BY timestamp DESC LIMIT 100;
   ```

**Tiempo estimado:** 1 hora

---

## 6. MANTENEDOR (Quiero mantener el sistema en producción)

**Meta:** Uptime, monitoreo, alertas, actualizaciones, backups.

**Ruta:**
1. [Componentes](../10-ARQUITECTURA/01-componentes.md) — Arquitectura completa
2. [Troubleshooting](../40-OPERACIONAL/01-troubleshooting.md) — Problemas y soluciones
3. [Comandos Comunes](../40-OPERACIONAL/02-comandos-comunes.md) — Operaciones útiles
4. **Setup alertas en n8n:** Notificaciones a Telegram/Email
5. **Backup diario:** `docker-compose exec backend-python sqlite3 grid_trading.db ".dump" > backup.sql`
6. **Health checks cada 5 min:** `/health` endpoint

**Tiempo estimado:** 2-4 horas para setup inicial

---

## Resumen Rápido

| Rol | Documento Principal | Tiempo |
|-----|-------------------|--------|
| Usuario Nuevo | [Inicio Rápido](01-inicio-rapido.md) | 30 min |
| Operador | [Visión General de Workflows](../50-WORKFLOWS/01-vision-general.md) | 1-2h |
| QA | [QA Quick Reference](../40-OPERACIONAL/03-qa-quick-reference.md) | 4h-48h |
| Desarrollador | [Code Structure](../70-DEVELOPMENT/01-code-structure.md) | 2-4h |
| DBA | [Models.py](../70-DEVELOPMENT/01-code-structure.md) | 1h |
| Mantenedor | [Troubleshooting](../40-OPERACIONAL/01-troubleshooting.md) | 2-4h |

---

## ¿No sabes qué leer?

**Responde:**
- ¿Quién eres? → Ve a tu sección arriba
- ¿Qué error tienes? → [Troubleshooting](../40-OPERACIONAL/01-troubleshooting.md)
- ¿No encuentras algo? → [FAQ](../90-APPENDICES/01-faq.md)
- ¿Qué significa esto? → [Glossary](../90-APPENDICES/02-glossary.md)
