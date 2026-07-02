# Estrategia de Integración n8n con Grid Trading Backend

## Idempotencia y Reintentos

El backend ya tiene protección contra duplicados (guardia anti-duplicados: solo 1 grid `RUNNING` por símbolo), pero n8n debe ser consciente de cómo manejar fallos de red sin crear grids duplicados.

### Escenario problemático

```
n8n → POST /api/v1/grids → Binance coloca órdenes exitosamente
       ↓ (timeout de red, Binance no confirma el response)
   n8n reintenta automáticamente → POST /api/v1/grids
       ↓
   Backend responde 400: "A RUNNING grid for BTCUSDT already exists"
```

**Resultado incorrecto (sin manejo):** El workflow captura un 400 como error fatal → dispara una alerta falsa → operador ve "ERROR: grid creation failed" cuando en realidad el grid **ya fue creado** en el primer intento.

### Solución: capturar 400 "already exists" como NO-ERROR

En los nodos n8n de creación de grids:

```javascript
// Pseudocódigo del Function node en n8n

try {
  const response = await this.helpers.httpRequest({
    method: 'POST',
    url: 'http://backend:8000/api/v1/grids',
    json: {
      symbol: 'BTCUSDT',
      lower_price: 40000,
      upper_price: 45000,
      levels: 10,
      quantity_per_order: 0.001
    }
  });
  
  return {
    grid_created: true,
    grid_id: response.id,
    status: response.status
  };
} catch (error) {
  if (error.statusCode === 400 && error.response?.detail?.includes('already exists')) {
    // No es error — el grid ya existe del intento anterior
    // Opcionalmente, consulta el estado actual
    const existing = await fetch(
      'http://backend:8000/api/v1/grids?status=RUNNING'
    ).then(r => r.json());
    
    return {
      grid_created: false,
      grid_id: existing.find(g => g.symbol === 'BTCUSDT')?.id,
      reason: 'ALREADY_EXISTS',
      status: 'OK'  // Not an error
    };
  }
  
  // Otros 400/500 sí son errores fatales
  throw error;
}
```

### Reintentos con idempotencia (mejores prácticas)

Si deseas que n8n reintente automáticamente sin duplicar:

1. **POST `/api/v1/grids` no es idempotente por diseño** — solo permite retry si la primera colocación falló **antes** de que Binance confirme. Usa `clientOrderId` para evitar duplicados en Binance, pero en el backend sigue siendo 400 si ya existe.

2. **Alternativa: usa identificadores únicos a nivel n8n**
   - Genera un ID de "creación de grid" (UUID) en n8n
   - Antes de llamar POST, consulta `GET /api/v1/grids?status=RUNNING` y busca uno que coincida con tus parámetros
   - Si existe, reutiliza su ID
   - Si no existe, procede a POST

3. **Monitoreo periódico (recomendado)**
   - En lugar de retries agresivos, usa un trigger cron cada 5 min: `GET /api/v1/grids?status=RUNNING`
   - El query param `?status=RUNNING` reduce payload (n8n solo recibe grids activos)
   - Compara contra el estado esperado
   - Si un grid desapareció inesperadamente o cambió de status, dispara una alerta

### Ejemplo: workflow de creación con captura de "already exists"

```
[Trigger: Webhook o Manual]
  ↓
[Call: POST /api/v1/grids]
  ↓
[Error Handler: If 400 + "already exists"]
  ├→ [Call: GET /api/v1/grids?status=RUNNING]
  └→ [Find: grid matching symbol]
  ↓
[Output: Grid ID + created=true/false]
  ↓
[Notify: Slack/Email]
```

### Monitoreo periódico (workflow cron)

```
[Trigger: Cron 5 min]
  ↓
[Call: GET /api/v1/grids?status=RUNNING]
  ↓
[For Each: grid in response]
  ├→ [Call: POST /api/v1/grids/{id}/refresh]  # Sincroniza órdenes
  ├→ [Call: GET /api/v1/grids/{id}/pnl]       # Calcula PnL
  ├→ [Call: POST /api/v1/grids/{id}/check-close]  # Evalúa SL/TP
  └→ [Log: state changes, alerts if triggered]
```

### Transacciones y consistencia

- **SQLite es transaccional:** si POST `/api/v1/grids` falla después de colocar órdenes en Binance, la transacción DB se revierte → no creas un grid zombie sin órdenes.
- **Postgres es opcional:** `historical_grid_logs` es write-once, non-critical. Si falla, el grid sigue siendo funcional — solo pierdes el log histórico para ese cierre.

### Resumen de reglas para n8n

| Caso | Manejo |
|---|---|
| POST `/api/v1/grids` → 200 | Grid creado con éxito, salvar grid_id |
| POST `/api/v1/grids` → 400 "already exists" | **NO ES ERROR** — grid ya existe del intento anterior, salvar grid_id |
| POST `/api/v1/grids` → 400 (otro) | Error de validación (margen, filtros) — requiere intervención |
| POST `/api/v1/grids` → timeout | Reintenta; si persiste, consulta `GET /api/v1/grids?status=RUNNING` |
| GET `/api/v1/grids?status=RUNNING` | Bajo payload — reutiliza para monitoreo periódico |
| POST `/api/v1/grids/{id}/refresh` + `/check-close` | Polling externo — el backend NO tiene scheduler interno |
