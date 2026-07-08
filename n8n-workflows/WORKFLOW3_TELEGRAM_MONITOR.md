# Workflow 3: Telegram Monitor (Fase 1)

**Archivo:** `workflow3-telegram-monitor.json` (nombre estándar para CI/CD)

**Estado:** ✅ Fase 1 — solo usa endpoints que ya existen en el backend. No requiere cambios de backend.

---

## 📱 Comandos disponibles

| Comando | Acción | Endpoint usado |
|---|---|---|
| `/grids` | Lista grids RUNNING (símbolo, niveles, rango, edad, ID) | `GET /api/v1/grids?status=RUNNING` |
| `/grid-detail SYMBOL` | Detalle + PnL de la grid más reciente del símbolo | `GET /api/v1/grids` + `/{id}` + `/{id}/pnl` |
| `/trigger-wf1 confirm` | Lanza WF1 (Market Decision). Sin `confirm` solo advierte | Execute Workflow (n8n) |
| `/trigger-wf2` | Ejecuta un ciclo de WF2 (Monitor) | Execute Workflow (n8n) |
| Cualquier otro texto | Mensaje de ayuda con los comandos | — |

**Seguridad:**
- Solo responde a chats cuyo ID esté en `$env.TELEGRAM_CHAT_ID` (soporta varios separados por coma). Mensajes de otros chats se ignoran en silencio (rama `Ignore (Unauthorized)`).
- `/trigger-wf1` exige el argumento `confirm` porque puede crear un grid real.
- La respuesta se envía **solo al chat que preguntó**, no a todos los IDs configurados.

---

## 📊 Flujo

```
Telegram Trigger (mensajes al bot)
   → Parse Command (chatId, command, args, authorized)
   → IF: Authorized? ──false──> Ignore (NoOp)
   → Router (switch por comando)
        ├─ /grids        → GET grids RUNNING → Format → Send
        ├─ /grid-detail  → IF has symbol? → GET grids → pick by symbol
        │                     → IF found? → GET detail → GET pnl → Format → Send
        ├─ /trigger-wf1  → IF confirm? → Execute WF1 → Format → Send
        ├─ /trigger-wf2  → Execute WF2 → Format → Send
        └─ fallback      → Format: Help → Send
   Todos convergen en "Send Telegram Reply" (1 solo nodo Telegram de salida)
```

---

## 🚀 Instalación

1. **Importar** `workflow3-telegram-monitor.json` (CI/CD automático o manual en n8n UI).

2. **Verificar vinculación de sub-workflows:**
   - "Execute WF1" apunta a `yggk1wajL1tsmABi` (workflow1-market-decision).
   - "Execute WF2" apunta a `96qAStQwfrHAVXRd` (workflow2-monitor).
   - IDs tomados de los exports del 2026-07-06. Si en tu instancia los IDs
     cambiaron (p. ej. por re-importación), re-seleccionar el workflow en el
     dropdown de cada nodo.

3. **WF1 actualizado:** `workflow1-market-decision.json` ahora incluye el nodo
   `WF-Trigger-Externo` (Execute Workflow Trigger) conectado a `Config`, necesario
   para poder lanzarlo desde WF3. Re-importar WF1 si ya estaba en n8n.

4. **Credenciales / env:**
   - Credencial Telegram `TRADING` (la misma de WF1/WF2).
   - `BACKEND_URL` y `TELEGRAM_CHAT_ID` ya configurados (los mismos de WF1/WF2).

5. **Activar** el workflow (el Telegram Trigger registra el webhook del bot al activar).

> **Nota:** El Telegram Trigger consume los updates del bot vía webhook. Si otro
> workflow también usa Telegram Trigger con el mismo bot, entrarán en conflicto —
> este debe ser el único workflow con trigger de Telegram para el bot TRADING.

---

## 🧪 Pruebas

Desde el chat autorizado en Telegram:

1. `hola` → debe responder el mensaje de ayuda.
2. `/grids` → lista de grids RUNNING (o "No hay grids RUNNING").
3. `/grid-detail BTCUSDT` → detalle + PnL (o "No se encontraron grids").
4. `/grid-detail` (sin símbolo) → mensaje de uso.
5. `/trigger-wf1` → advertencia pidiendo `confirm`.
6. `/trigger-wf1 confirm` → "WF1 lanzado" + luego la notificación normal de WF1.
7. `/trigger-wf2` → "WF2 ejecutado" + notificaciones normales de WF2.
8. Desde un chat NO autorizado: cualquier mensaje se ignora sin respuesta.

---

## 🔜 Fase 2 (pendiente — requiere backend)

| Comando | Endpoint faltante |
|---|---|
| `/history`, `/history-detail` | `GET /api/v1/grid-closures` (la tabla ya existe por FIX 3) |
| `/stats`, `/perf SYMBOL` | `GET /api/v1/grid-stats` |
| `/last-execution` | API REST de n8n (sin backend) |
| `/config` | `GET /api/v1/config` o valores en el workflow |

Especificación completa en `TELEGRAM_TRIGGERS_GUIDE.md` y `TELEGRAM_TRIGGERS_IMPLEMENTATION.md`.
