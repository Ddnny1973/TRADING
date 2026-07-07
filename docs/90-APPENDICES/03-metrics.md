# Metrics - KPIs y Métricas Esperadas

## Performance Endpoints

### Health Check (`/health`)

| Métrica | Esperado | Rango Aceptable | Acción |
|---------|----------|-----------------|--------|
| Response Time | < 100 ms | 50-200 ms | Si > 500ms: reinicia |
| Status | "healthy" | - | Si != "healthy": debug |
| Database Status | "connected" | - | Si != "connected": reinicia BD |
| Binance API Status | "reachable" | - | Si != "reachable": network error |

### Endpoints API

| Endpoint | Time | Rango | Acción |
|----------|------|-------|--------|
| `/api/v1/market-analysis/{symbol}` | < 500 ms | 200-1000 ms | Si > 2s: revisar Binance API |
| `/api/v1/grids` | < 200 ms | 100-500 ms | Si > 1s: optimizar BD query |
| `POST /api/v1/grids` | < 2 s | 1-5 s | Normal, depende de órdenes |
| `POST /api/v1/grids/{id}/refresh` | < 1 s | 500-2000 ms | Normal (incluye replenish) |
| `POST /api/v1/grids/{id}/check-close` | < 500 ms | 200-1000 ms | Normal |

---

## Workflow Metrics

### Workflow 1 (Market Decision)

| Métrica | Esperado | Rango | Nota |
|---------|----------|-------|------|
| Duración | 15-30 s | 10-60 s | Incluye IA call |
| Calls a Backend | 1-2 | - | GET market-analysis + POST /api/v1/grids (si launch=true) |
| Success Rate | > 90% | > 80% | Falla por IA, network, etc. |
| Frequency | Cada 4h | - | Manual o cron |

### Workflow 2 (Monitor)

| Métrica | Esperado | Rango | Nota |
|---------|----------|-------|------|
| Duración | 3-5 s | 2-10 s | Muy rápido |
| Grids procesadas | 1-2 | - | Max concurrent = 2 |
| Orders refreshed | 4-30 | - | Depende de levels × grids |
| Orders replenished | 0-5 | - | Depende de fills (backend lo hace en /refresh) |
| Frequency | Cada 5 min | - | Automático |
| Uptime | > 99% | - | Debe ejecutarse siempre |

---

## Trading Metrics

### Por Grid

| Métrica | Esperado | Rango Realista | Mal Señal |
|---------|----------|----------------|-----------|
| Órdenes creadas | = Levels | 15 | < 10 |
| Tiempo hasta 1er fill | 1-30 min | Depende mercado | > 1 hora = no activo |
| Ciclos por día | 3-10 | 1-20 | 0 = mercado muerto |
| PnL por ciclo | +0.38% | +0.20% a +0.50% | Negativo = SL hit |
| Max duration | 224 h | - | Auto-cierre después |

### Por Semana

| Métrica | Esperado | Rango | Nota |
|---------|----------|-------|------|
| PnL realizado | 2-5% | 0.5-10% | Conservador = bajo retorno |
| Ciclos totales | 50-100 | 30-200 | Mercado volátil = más |
| SL hits | 0-1 | 0-2 | > 2 = SL agresivo |
| Drawdown máximo | 2-5% | 0-10% | > 10% = revisar riesgo |

---

## Risk Metrics

### Por Grid

| Métrica | Máximo | Recomendado | Si Excede |
|---------|--------|-------------|-----------|
| Risk % | 10% | 2% | Reduce capital |
| Capital en riesgo | 5% balance | 2% balance | Reduce risk_pct |
| Leverage | 1x | 1x | NO USES LEVERAGE |
| Max grids | 2 | 2 | Cierra uno |
| Max duration | 224 h | - | Auto-cierre |
| Min step | >= 0.2% | >= 0.4% | Aumenta range (ver validate_grid_step) |

### Posición

| Métrica | Aceptable | Alerta | Crítico |
|---------|-----------|--------|---------|
| Posición abierta | < 0.1 BTC | > 0.1 BTC | > 0.2 BTC |
| Unrealized PnL | ± 5% | ± 10% | ± 15% |
| Liquidation distance | > 50% | < 50% | < 20% |

---

## Database Metrics

### Tamaño

| Tabla | Esperado (1 mes) | Esperado (3 meses) | Acción |
|-------|------------------|-------------------|--------|
| grids | < 100 filas | < 300 filas | OK |
| orders | 1000-5000 | 3000-15000 | Índices importantes |
| pnl_history | 1000-5000 | 3000-15000 | Prune viejo si > 50MB |

### Performance

| Query | Time | Rango | Si Excede |
|-------|------|-------|-----------|
| SELECT active grids | < 10 ms | 5-50 ms | Index falta |
| SELECT orders for grid | < 50 ms | 20-100 ms | Index falta |
| SELECT pnl history | < 100 ms | 50-200 ms | Agregate/prune |

---

## Binance API Metrics

### Rate Limiting

| Métrica | Esperado | Máximo | Acción |
|---------|----------|--------|--------|
| Requests/min | < 100 | 1200 | Si > 800: optimize |
| 429 errors | 0 | 5/día | Si > 5: reduce frequency |
| Rate limit hits | 0 | - | Implementar retry backoff |

### Latency

| Endpoint | Esperado | Rango | Acción |
|----------|----------|-------|--------|
| Market data | < 500 ms | 200-1000 ms | Normal |
| Place order | < 1 s | 500-2000 ms | Normal |
| Query orders | < 500 ms | 200-1000 ms | Normal |
| Get balance | < 300 ms | 100-800 ms | Normal |

---

## System Health

### Uptime

| Componente | Esperado | Aceptable | Crítico |
|-----------|----------|-----------|---------|
| Backend | > 99% | > 95% | < 90% = restart |
| n8n | > 99% | > 95% | < 90% = restart |
| Database | > 99.9% | > 99% | Cualquier downtime |
| Binance API | Varía | > 99% | < 95% = externa |

### Resource Usage

| Recurso | Normal | Alerta | Crítico |
|---------|--------|--------|---------|
| CPU | < 30% | 30-70% | > 70% |
| Memory | < 300 MB | 300-800 MB | > 800 MB |
| Disk | < 100 MB | 100-500 MB | > 1 GB |

---

## Monitoring Checklist

### Diario

- [ ] `/health` devuelve OK
- [ ] N0 errores en logs de backend
- [ ] N0 errores en n8n executions
- [ ] Workflows ejecutados > 2 veces

### Semanal

- [ ] PnL positivo
- [ ] Ciclos > 10
- [ ] SL hits <= 1
- [ ] BD size < 100 MB

### Mensual

- [ ] Uptime > 99%
- [ ] Total PnL > 1%
- [ ] 0 crashes/restarts
- [ ] Documentar resultados

---

## Alertas Automáticas

### Critical

```
Trigger: /health status != "healthy"
Action: Telegram notification + restart
```

### High

```
Trigger: Workflow 2 fails 3x en a row
Action: Telegram notification + manual check
```

### Medium

```
Trigger: PnL negative after 50 cycles
Action: Telegram notification + review SL
```

### Low

```
Trigger: DB size > 500 MB
Action: Email reminder to prune old data
```

---

## Dashboard Template

Si tienes dashboard web, monitorea:

```
┌─ HEALTH ─────────────┐
│ Backend: ✅ 120ms     │
│ n8n: ✅ 300ms         │
│ DB: ✅ Connected      │
└──────────────────────┘

┌─ TRADING ────────────┐
│ Active Grids: 2      │
│ Open Orders: 30      │
│ Cycles Today: 8      │
│ PnL Today: +0.52%    │
└──────────────────────┘

┌─ WORKFLOWS ──────────┐
│ WF1 Last Run: 4h ago │
│ WF2 Last Run: <5 min │
│ WF2 Uptime: 99.8%    │
└──────────────────────┘

┌─ RISK ───────────────┐
│ Exposure: 4% balance │
│ Max Leverage: 1x     │
│ Unrealized: +1.2%    │
└──────────────────────┘
```

---

Ver también: [Troubleshooting](../40-OPERACIONAL/01-troubleshooting.md)
