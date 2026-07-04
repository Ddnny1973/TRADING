# n8n Workflows — fuente única de verdad

Estos son los archivos **operativos** para importar en n8n. Reemplazan a las plantillas antiguas en `docs/n8n-templates/` (que quedan solo como referencia narrativa/histórica; ver nota al inicio de `docs/n8n-templates/SETUP.md`).

Cambios respecto a las plantillas originales de `docs/n8n-templates/`:

1. **Proveedor de IA:** Gemini (`gemini-2.5-flash`) vía HTTP Request directo a la API de Google, en vez de un nodo `openAi` mal referenciado con modelo `claude-opus-4-8`. Se usa `responseSchema` de Gemini para forzar la salida JSON estructurada (`reasoning`, `launch`, `lowerLimit`, `upperLimit`, `gridCount`). (`gemini-2.0-flash` fue probado primero pero la API respondió "model no longer available"; `gemini-2.5-flash` es la versión estable vigente al momento de escribir esto — verifica `GET https://generativelanguage.googleapis.com/v1beta/models` si vuelve a fallar).
2. **Fix: propagación de `symbol`.** En la plantilla original, el nodo IA no devolvía `symbol` y el POST `/grids` intentaba leer `{{ $json.symbol }}` de la salida de la IA (bug — quedaría `undefined`). Ahora un nodo Code (`Build Gemini Request` / `Parse AI Decision`) conserva `symbol`, `suggested_quantity_per_order`, `atr_period`, `atr_multiplier` y `klines_interval` a través de todo el flujo.
3. **Fix: manejo de "already exists" (Workflow 1).** Se agregó `Interpret Grid Result` + IF, siguiendo [n8n-integration-strategy.md](../docs/n8n-integration-strategy.md): un 400 "already exists" ya NO dispara la notificación de error, se notifica como informativo.
4. **Fix: ramas invertidas en IFs (Workflow 2).** La plantilla original conectaba el output "true" (hay error) hacia el camino de éxito y viceversa en los nodos `IF: Refresh failed?` / `IF: Check-close failed?`. Corregido.
5. **Fix: loop de `Split in Batches` (Workflow 2).** La plantilla original creaba un segundo nodo `splitInBatches` ficticio como "loop back", lo cual no es el patrón real de n8n. Ahora el nodo `Wait` se conecta de vuelta al mismo nodo `Split in Batches (Sequential)` (patrón nativo de dos salidas: `done` / `loop`).
6. **Trigger nodes actualizados:** `n8n-nodes-base.trigger` (no existe) → `manualTrigger`; `n8n-nodes-base.cron` (deprecado) → `scheduleTrigger`.
7. Se quitó el nodo `IF: ¿hay grids activos?` de Workflow 2 — si `GET /grids?status=RUNNING` devuelve 0 grids, el loop simplemente no itera (comportamiento nativo de n8n), sin necesidad de un chequeo de longitud frágil.
8. **Fix: `quantity_per_order` por debajo del `minNotional` de Binance (Workflow 1).** El `suggested_quantity_per_order` calculado por `/market-analysis` puede quedar por debajo del mínimo de 50 USDT de notional por orden, sobre todo con `levels` altos. El nodo `Create Grid (POST)` ahora aplica un piso: `Math.max(suggested_quantity_per_order, 65 / precio_promedio)` (buffer de 30% sobre el mínimo real, para absorber el truncamiento por `stepSize` que hace el backend). Si tu balance testnet es bajo, considera también reducir `levels` en el nodo `Config`.

**Workflow 1 ya fue probado end-to-end con éxito** contra el backend real y Binance Futures Testnet (Gemini decide, crea el grid, coloca órdenes, notifica por Telegram). **Workflow 2 aún no se ha probado en vivo con un ciclo completo** (refresh + check-close contra un grid `RUNNING` real) — solo se confirmó que `List Running Grids` responde correctamente.

## Fix relacionado en el backend (no es parte de n8n)

Durante las pruebas de Workflow 1 se detectó que **todas** las órdenes de un grid podían fallar con el código de Binance `-1007` ("Timeout waiting for response... status unknown") dentro de una respuesta HTTP 200 de `/fapi/v1/batchOrders`. `place_batch_orders()` en [`backend-python/app/services/binance_client.py`](../backend-python/app/services/binance_client.py) solo reintentaba por status HTTP (502/429/418), nunca por errores per-orden embebidos en un 200. Se corrigió para que cada orden con código ambiguo (`-1007`, `-1021`) se confirme vía `clientOrderId` antes de decidir si reintentar, evitando tanto duplicar órdenes como perder órdenes que sí se habían colocado. **Pendiente:** correr la suite de pytest del backend (`backend-python/tests/`) para confirmar que el cambio no rompe nada existente — no se pudo ejecutar en esta sesión por falta de dependencias en el entorno local.

## Instancia real de n8n (referencia para otros agentes/sesiones)

- **URL:** `https://n8n.gestorconsultoria.com.co`
- **IDs reales de los workflows** (obtenidos vía API, confirmados 2026-07-04):

  | Nombre en n8n | ID |
  |---|---|
  | `workflow1-market-decision` | `yggk1wajL1tsmABi` |
  | `workflow2-monitor` | `96qAStQwfrHAVXRd` |

- **Infra multi-servidor:** n8n corre en un servidor (IP privada `10.0.0.5`), el backend en otro (`10.0.0.4`) — ver la nota de `BACKEND_URL` más abajo, es la causa de varios problemas de conectividad ya resueltos en esta sesión.
- **Credenciales ya creadas en esa instancia** (no se pueden reutilizar en otra instancia, hay que recrearlas): Telegram API `"TRADING"` (id `zurDfqIC4Qy17sUA`), Header Auth `"Header Auth GeminiAI"` (id `NQnuuYpP2Pax6Nvr`), Postgres `"Postgres n8n"` (id `6l9jrmQ4BmCnUgXq`, usada para loguear tokens de Gemini en la tabla `public.metricas_personalizadas`).
- **Comandos de Telegram habilitados** (bot "TRADING", un solo Telegram Trigger en Workflow 1 para evitar el conflicto de "un webhook por bot"):
  - `/lanzar` → corre el flujo normal de Workflow 1 (Market Analysis → Gemini → crea grid).
  - `/monitorear` → dispara Workflow 2 bajo demanda vía nodo **Execute Sub-workflow** (`workflowId: 96qAStQwfrHAVXRd`), sin esperar el cron de 15 min.

## API pública de n8n

Habilitada y probada exitosamente en esta sesión. Útil para consultar IDs, y en el futuro para sincronizar sin copiar/pegar manualmente en la UI.

### Habilitar

n8n → **Settings → n8n API → Create an API Key**. Guarda la key de forma segura (nunca en el repo ni en texto plano compartido) — en PowerShell, captúrala así para no dejarla en el historial de comandos:
```powershell
$n8nApiKey = Read-Host "Pega tu n8n API key" -AsSecureString
$cred = New-Object System.Management.Automation.PSCredential("apikey", $n8nApiKey)
$plainApiKey = $cred.GetNetworkCredential().Password
```

### Autenticación

Header `X-N8N-API-KEY: <key>`, base URL `https://n8n.gestorconsultoria.com.co/api/v1`.

### Listar workflows (para encontrar IDs)

```powershell
$workflows = Invoke-RestMethod -Uri "https://n8n.gestorconsultoria.com.co/api/v1/workflows" -Headers @{ "X-N8N-API-KEY" = $plainApiKey }
$workflows.data | Select-Object id, name | Format-Table -AutoSize
```

### Sincronización n8n → repo (PULL — proceso manual, usado durante toda esta sesión)

Hoy el flujo real es: se edita el workflow en la UI de n8n, y luego hay que traer esos cambios de vuelta al JSON del repo para que siga siendo la fuente de verdad documentada. Dos formas de hacerlo:

**Opción A — Manual desde la UI (la usada en la práctica):**
1. En n8n, abre el workflow → menú `⋯` (tres puntos, arriba a la derecha) → **Download**.
2. Reemplaza el archivo correspondiente en `n8n-workflows/` con el JSON descargado.

**Opción B — Vía API (equivalente, sin salir de la terminal):**
```powershell
$id = "yggk1wajL1tsmABi"  # o "96qAStQwfrHAVXRd" para workflow2-monitor
$resp = Invoke-RestMethod -Uri "https://n8n.gestorconsultoria.com.co/api/v1/workflows/$id" -Headers @{ "X-N8N-API-KEY" = $plainApiKey }
$resp | ConvertTo-Json -Depth 20 | Out-File "n8n-workflows/workflow1-market-decision.json" -Encoding utf8
```
Ajusta el nombre del archivo destino según el `$id` que estés trayendo.

### Sincronización repo → n8n (PUSH — NO probado todavía, documentado para cuando se valide)

La idea sería usar `PUT /api/v1/workflows/{id}` con el JSON del repo como body, para actualizar el workflow en n8n sin copiar/pegar nodo por nodo en la UI:

```powershell
$id = "96qAStQwfrHAVXRd"
$body = Get-Content "n8n-workflows/workflow2-monitor.json" -Raw
Invoke-RestMethod -Uri "https://n8n.gestorconsultoria.com.co/api/v1/workflows/$id" -Method PUT -Headers @{ "X-N8N-API-KEY" = $plainApiKey; "Content-Type" = "application/json" } -Body $body
```

**⚠️ Antes de confiar en esto (pendiente de validar, no probado por falta de tiempo en esta sesión):**
- La API pública de n8n típicamente espera solo `{name, nodes, connections, settings, staticData}` en el body de `PUT /workflows/{id}` — puede que rechace el JSON tal cual si incluye campos de solo lectura (`id`, `versionId`, `meta`, `shared`, `tags`, `active`). Puede requerir limpiar el JSON antes de enviarlo.
- Probar primero contra un workflow de prueba/descartable, **nunca directo contra `workflow1-market-decision` o `workflow2-monitor` en producción** sin backup.
- Hacer un `GET` (backup) antes de cada `PUT`, por si hay que revertir.
- Activar/desactivar el workflow es un endpoint aparte (`POST /workflows/{id}/activate` / `/deactivate`), un `PUT` normal no debería tocar ese estado, pero hay que confirmarlo.

**🔴 Resultado real de la prueba (2026-07-04): el PUT completo NO funciona en esta instancia.**
- `PUT /workflows/{id}` con un body mínimo (`{ name: "..." }`, sin `nodes`) → **400** con JSON válido de n8n (falta `nodes`, esperado) → confirma que el endpoint en sí funciona y la autenticación es correcta.
- `PUT /workflows/{id}` con el JSON completo del workflow (~64 KB, incluye `name`/`nodes`/`connections`/`settings`) → **500 Internal Server Error**, pero la respuesta es una página **HTML genérica** ("Internal Server Error"), no el JSON de error que da n8n normalmente — señal de que el error ocurre en el **proxy inverso** delante de n8n, no en la aplicación n8n misma.
- 64 KB no es un tamaño grande (la mayoría de proxies permiten 1 MB+ por defecto), así que la sospecha más probable es un **WAF/filtro de contenido** en el proxy bloqueando el body por patrones dentro del código JS de los nodos `Code` (comillas anidadas, `throw new Error(...)`, etc.), no un límite de tamaño puro.
- **Conclusión práctica:** por ahora, usar el método manual (Opción A, Download/UI) para sincronizar repo → n8n. El PUT vía API queda documentado pero **no es confiable en esta instancia** hasta que alguien con acceso a la configuración del proxy investigue el filtro que está devolviendo el 500 genérico (revisar logs del proxy, no de n8n, ya que la petición parece no estar llegando siquiera a la app).

## Cómo importar

1. Abre n8n → **Workflows** → **Create New** → **Import from File**.
2. Selecciona `workflow1-market-decision.json` o `workflow2-monitor.json`.
3. Configura credenciales tras importar (ver abajo). n8n marcará en rojo los nodos que requieren credencial.

## Credenciales / variables a configurar en n8n

| Dónde | Qué |
|---|---|
| Variable de entorno `BACKEND_URL` | URL del backend. **En despliegues multi-servidor, usa IP privada + puerto publicado** (ej. `http://10.0.0.4:8043`), NO el nombre del contenedor — una red Docker bridge con el mismo nombre en dos hosts distintos NO es la misma red y el DNS por nombre de contenedor no va a resolver entre servidores. |
| Variable de entorno `TELEGRAM_CHAT_ID` | Chat ID de destino para notificaciones (obtenlo con `GET https://api.telegram.org/bot<TOKEN>/getUpdates` tras enviarle un mensaje al bot) |
| Variable de entorno `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` | n8n bloquea el acceso a `$env` en expresiones/Code nodes por defecto ("access to env vars denied"). Sin esto, `{{ $env.BACKEND_URL }}` y `{{ $env.TELEGRAM_CHAT_ID }}` fallan. Nota: las **Variables nativas de n8n** (`$vars`) están bloqueadas en instancias Community ("Upgrade to unlock variables") — por eso se usa `$env` en todos lados. |
| Credencial **Telegram API** | Seleccionar en cada nodo `n8n-nodes-base.telegram` |
| Credencial **Header Auth** (nombre sugerido: `Gemini API Key`) | Header `x-goog-api-key` con tu API key de Gemini — seleccionar en el nodo `Gemini: AI Decision` (Workflow 1) |

Cualquier cambio a estas variables de entorno requiere recrear el contenedor de n8n: `docker compose up -d --force-recreate n8n`.

## Pendiente de validar en vivo

- Workflow 2 completo (refresh + check-close + notificaciones) contra un grid RUNNING real.
- Suite de tests del backend tras el fix de `place_batch_orders` (`-1007`).
- Nombres exactos de parámetros de nodos pueden variar levemente según la versión de n8n instalada — si algo no importa limpio, ajusta en la UI (ya nos pasó con el nodo IF y el body JSON).
- Sincronización **repo → n8n vía API** (`PUT /workflows/{id}`) — **probada y bloqueada** (ver sección de arriba: 500 genérico de proxy con el JSON completo). Usar el método manual (Download/UI) mientras tanto.
