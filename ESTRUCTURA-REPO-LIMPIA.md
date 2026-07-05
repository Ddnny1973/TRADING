# 🗂️ Estructura Limpia del Repositorio

**Actualizado:** 2026-07-05

---

## ✅ USAR ESTOS

### Workflows n8n (Producción)

**Ubicación:** `n8n-workflows/`

```
n8n-workflows/
├── README.md                      # ⭐ Leer primero (setup + config)
├── workflow1-market-decision.json # ⭐ Importar en n8n
└── workflow2-monitor.json         # ⭐ Importar en n8n
```

**Estos están:**
- ✅ Corregidos (bugs arreglados)
- ✅ En producción
- ✅ Listos para importar directamente en n8n
- ✅ Con propagación de `symbol` correcta
- ✅ Con ramas invertidas en Workflow 2 corregidas
- ✅ Con proveedor de IA actualizado

**Cómo usar:**
```bash
# 1. Lee la guía de setup
cat n8n-workflows/README.md

# 2. Importa en n8n UI
# Workflows → Create New → Import from File
# Selecciona: workflow1-market-decision.json y workflow2-monitor.json

# 3. Configura credenciales en n8n
# Backend URL, Telegram, OpenAI API key
```

---

## ❌ NO USAR ESTOS (Eliminados)

**Ubicación anterior:** `docs/n8n-templates/` (ELIMINADO)

**Por qué se eliminaron:**
- ❌ Históricos (v1, sin correcciones)
- ❌ Causaban confusión al tener dos versiones
- ❌ Tenían bugs conocidos
- ❌ No estaban en producción

---

## 📂 Estructura Actual del Repo

```
TRADING/
├── backend-python/                # FastAPI (implementado ✅)
│   ├── app/
│   │   ├── main.py               # Endpoints
│   │   ├── services/             # Grid logic, Binance client
│   │   ├── core/                 # Config, security
│   │   └── database/             # SQLite + PostgreSQL
│   ├── requirements.txt
│   └── .env.example
│
├── n8n-workflows/                 # ⭐ WORKFLOWS OPERATIVOS
│   ├── README.md                  # Setup guide
│   ├── workflow1-market-decision.json
│   └── workflow2-monitor.json
│
├── docs/                           # Documentación técnica
│   ├── api-endpoints.md           # Referencia de API
│   ├── manual-qa-runbook.md       # QA paso a paso ⭐
│   ├── qa-quick-reference.md      # Comandos rápidos
│   ├── workflow1-market-decision.md  # Especificación lógica
│   ├── workflow2-monitor.md          # Especificación lógica
│   ├── n8n-integration-strategy.md   # Estrategia de reintentos
│   └── position-sizing-formula.md    # Fórmulas
│
├── docker-compose.yml             # Orquestación
├── readme.md                       # Visión general
├── PROYECTO-COMPLETADO.md         # Sumario del proyecto
└── ESTRUCTURA-REPO-LIMPIA.md      # Este archivo
```

---

## 🎯 Flujo de Trabajo Recomendado

### 1️⃣ Primero: Leer
```
readme.md                        (5 min, visión general)
    ↓
n8n-workflows/README.md         (10 min, setup n8n)
```

### 2️⃣ Segundo: Setup
```
docker-compose up -d            (backend)
    ↓
Importar workflows en n8n       (desde n8n-workflows/*.json)
    ↓
Configurar credenciales         (Backend URL, Telegram, OpenAI)
```

### 3️⃣ Tercero: Validar
```
curl http://localhost:8000/health
    ↓
docs/manual-qa-runbook.md       (10 tests paso a paso)
    ↓
Ejecutar QA en testnet          (2-4 semanas)
```

---

## 📖 Documentación de Referencia Rápida

| Necesidad | Documento |
|-----------|-----------|
| Setup de n8n | `n8n-workflows/README.md` |
| Comandos rápidos (curl, valores) | `docs/qa-quick-reference.md` |
| Tests manuales paso a paso | `docs/manual-qa-runbook.md` |
| Endpoints API | `docs/api-endpoints.md` |
| Especificación de Workflow 1 | `docs/workflow1-market-decision.md` |
| Especificación de Workflow 2 | `docs/workflow2-monitor.md` |
| Fórmulas de sizing | `docs/position-sizing-formula.md` |

---

## ✨ Cambios Hechos en Esta Limpieza

- ✅ **Eliminado:** `docs/n8n-templates/` (histórico, duplicado)
- ✅ **Actualizado:** `readme.md` (referencias a n8n-workflows)
- ✅ **Actualizado:** `PROYECTO-COMPLETADO.md` (referencias a n8n-workflows)
- ✅ **Actualizado:** `docs/qa-quick-reference.md` (referencias a n8n-workflows)
- ✅ **Creado:** Este documento (orientación clara)

---

## 🚀 Próximas Mejoras en n8n-workflows/

Las mejoras al sistema deben hacerse en `n8n-workflows/` (los operativos), no en lugares históricos:

**Cambios en Backend → Actualizar Workflows:**
1. Si cambias un endpoint → actualiza la URL en los nodos HTTP
2. Si cambias parámetros de respuesta → actualiza los nodos que los consumen
3. Si agregas campos → actualiza los nodos de notificación/decisión

**Cambios en Workflows → Actualiza n8n-workflows/*.json:**
1. Edita el workflow en n8n UI
2. Descarga el JSON actualizado
3. Reemplaza en `n8n-workflows/workflow*.json`
4. Comitea al repo

---

## ❓ Preguntas Frecuentes

**P: ¿Dónde importo los workflows?**  
R: `n8n-workflows/workflow1-market-decision.json` y `n8n-workflows/workflow2-monitor.json`

**P: ¿Hay dos versiones diferentes?**  
R: No, solo una (la operativa). Los duplicados fueron eliminados para evitar confusión.

**P: ¿Puedo seguir usando los templates viejos?**  
R: No, fueron eliminados porque tenían bugs. Usa solo los operativos.

**P: ¿Dónde está el archivo de setup de n8n?**  
R: En `n8n-workflows/README.md`

**P: ¿Qué cambió en los workflows operativos?**  
R: Propagación de `symbol`, ramas invertidas corregidas en Workflow 2, IA actualizada a Gemini (o la que uses).

---

## ✅ Checklist: Repositorio Limpio

- [x] `docs/n8n-templates/` eliminado (histórico)
- [x] Referencias en `readme.md` apuntan a `n8n-workflows/`
- [x] Referencias en `PROYECTO-COMPLETADO.md` apuntan a `n8n-workflows/`
- [x] Referencias en `qa-quick-reference.md` apuntan a `n8n-workflows/`
- [x] Estructura clara: un solo lugar para cada cosa
- [x] Documentación de orientación (`ESTRUCTURA-REPO-LIMPIA.md`)

---

**El repositorio está limpio. Úsalo con confianza. 🎯**
