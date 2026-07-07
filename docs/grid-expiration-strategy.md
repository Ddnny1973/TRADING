# Estrategia de Expiración de Grids

Cada grid tiene un `max_duration_hours` que define cuánto tiempo debe ejecutarse antes de ser reevaluado o cerrado.

---

## Opción A: Regla Determinística (✅ IMPLEMENTADA)

**Enfoque:** Calcular automáticamente basado en los parámetros del ATR.

**Fórmula:**
```
atr_window_hours = klines_interval (en horas) × atr_period
max_duration_hours = atr_window_hours × 4
```

**Justificación:**
- El ATR(14) en velas de 4h representa ~56 horas de historial
- Después de 4 veces ese período (~224h ≈ 9 días), el régimen de mercado probablemente ha evolucionado
- La fórmula es determinística — sin juicio de mercado, pura matemática

**Ejemplos:**
| klines_interval | atr_period | atr_window | max_duration |
|---|---|---|---|
| 4h | 14 | 56h | 224h (~9d) |
| 1h | 14 | 14h | 56h (~2.3d) |
| 1d | 14 | 14d | 56d (~2m) |
| 30m | 14 | 7h | 28h (~1.2d) |

**Implementación:**
```python
def _calculate_max_duration_hours(klines_interval: str, atr_period: int) -> float:
    interval_to_hours = {"1m": 1/60, "5m": 5/60, ..., "1d": 24, ...}
    interval_hours = interval_to_hours.get(klines_interval)
    atr_window_hours = interval_hours * atr_period
    return atr_window_hours * 4  # Multiplicador fijo = 4
```

**API:**
```json
POST /api/v1/grids
{
  "symbol": "BTCUSDT",
  "lower_price": 40000.0,
  "upper_price": 45000.0,
  "levels": 10,
  "quantity_per_order": 0.001,
  "atr_period": 14,
  "atr_multiplier": 2.0,
  "klines_interval": "4h",
  "max_duration_hours": null  // Omit o null → se calcula automáticamente
}
```

**Response:**
```json
{
  "id": "grid-123",
  "symbol": "BTCUSDT",
  "max_duration_hours": 224.0,
  "status": "RUNNING",
  "created_at": "2026-07-02T14:30:00"
}
```

---

## Opción B: Decisión de la IA (📋 PROPUESTA PARA FASE 2)

**Enfoque:** Permitir que la IA (Gemini en n8n) decida la duración basada en su análisis de mercado.

**Justificación:**
- `max_duration_hours` NO es un dato que se derive objetivamente de ATR
- Es una apuesta sobre cuánto tiempo va a durar el régimen de mercado actual
- Exactamente el tipo de decisión cualitativa que ya delegas a la IA con `launch` y `gridCount`

**Ejemplo de razonamiento de IA:**
```json
{
  "atr_pct": 0.3,  // ATR/price muy bajo
  "reasoning": "Mercado calmo en rango muy ajustado. Los regímenes laterales suelen durar más. Doy 36h.",
  "max_duration_hours": 36
}
```

vs.

```json
{
  "atr_pct": 2.5,  // ATR/price alto
  "reasoning": "Volatilidad alta, probablemente tendencia. Reevalúo rápido.",
  "max_duration_hours": 6
}
```

**Migración (cuando esté lista, Phase 2):**

1. **Schema del AI node en n8n:** Agregar campo a la respuesta
   ```json
   {
     "reasoning": "...",
     "launch": true,
     "lowerLimit": 42100.0,
     "upperLimit": 42900.0,
     "gridCount": 12,
     "maxDurationHours": 48  // Nuevo campo
   }
   ```

2. **Backend:** Ya soporta `max_duration_hours` en el POST, no necesita cambios
   ```json
   POST /api/v1/grids
   {
     "symbol": "{{ $json.symbol }}",
     "max_duration_hours": {{ $json.maxDurationHours }},
     ...
   }
   ```

3. **Prompt del AI en n8n:** Extender instrucciones
   ```
   Consideraciones para max_duration_hours:
   - Si atr_pct < 0.5% (mercado muy calmo): +36h a +72h
   - Si atr_pct 0.5% a 2% (normal): +12h a +24h  
   - Si atr_pct > 2% (volátil/tendencia): +6h a +12h
   ```

---

## Uso del campo max_duration_hours

**Ahora (Opción A):** es informativo — se almacena pero no hay scheduler interno que lo aplique
```
GET /api/v1/grids/grid-123 → max_duration_hours: 224.0
```

**Futuro (Workflow 2 mejorado):** Monitoreo periódico chequea si grid expiró
```javascript
// Pseudocódigo en n8n (Workflow 2 Monitor)
const grid = fetch(`/api/v1/grids/${gridId}`);
const age_hours = (Date.now() - grid.created_at) / 3600000;
if (age_hours > grid.max_duration_hours) {
  alert(`Grid ${gridId} expired after ${grid.max_duration_hours}h`);
  // Opcionalmente: POST /api/v1/grids/{gridId}/check-close
}
```

---

## Recomendación

✅ **Opción A ahora:** Valida el flujo end-to-end sin agregar complejidad de IA
⏳ **Opción B en Phase 2:** Una vez que Workflow 1 está estable, agregar decisión de IA es un cambio de ~5 líneas en el prompt n8n + 1 línea en el POST (pasar el campo)

**No hay deuda técnica:** El backend ya soporta ambas opciones. Opción A es un subconjunto de B (IA siempre puede devolver el valor calculado por la fórmula si quiere).
