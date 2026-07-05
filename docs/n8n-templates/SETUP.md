# n8n Workflow Templates Setup Guide

> **Nota (2026-07-04):** Los archivos operativos/actualizados para importar viven ahora en [`n8n-workflows/`](../../n8n-workflows/README.md) en la raíz del repo (corrigen varios bugs de estas plantillas: propagación de `symbol`, ramas invertidas en Workflow 2, proveedor de IA cambiado a Gemini, etc.). Este documento se conserva como referencia narrativa/histórica.

## Overview

This directory contains two production-ready n8n workflow templates for the Grid Trading system:

1. **Workflow 1** — Market Decision (AI-driven grid launch with dynamic sizing)
2. **Workflow 2** — Grid Monitor (periodic order refresh and SL/TP evaluation)

Both workflows are fully configured and can be imported directly into n8n.

---

## Prerequisites

- **n8n instance** running (Docker or self-hosted)
- **Backend API** (FastAPI) running and accessible at `${BACKEND_URL}`
- **Environment variables** configured (see below)
- **Telegram Bot** token and Chat ID (for notifications)

### Required Credentials

1. **OpenAI API Key** (for Claude/AI Decision node in Workflow 1)
   - Needed for node type: `openAi`
   - Model: `claude-opus-4-8`

2. **Telegram Bot Token + Chat ID** (for notifications)
   - Get from BotFather on Telegram
   - Chat ID of your notification target channel

---

## Environment Variables Setup

Before importing, configure these in your n8n environment (Settings → Credentials or via `.env`):

```env
BACKEND_URL=http://backend-python:8000
TELEGRAM_BOT_TOKEN=YOUR_TELEGRAM_TOKEN
TELEGRAM_CHAT_ID=YOUR_CHAT_ID
SLACK_WEBHOOK=https://hooks.slack.com/services/...  (optional)
```

Or store them as n8n credentials:
- **Backend API Base URL:** `http://backend-python:8000`
- **Telegram:** Bot token and Chat ID
- **Slack:** Webhook URL (if using Slack instead of Telegram)

---

## How to Import Workflows

### Option 1: Direct File Import (Recommended)

1. Open your n8n dashboard: `http://<n8n-host>:5678`
2. Click **Workflows** → **Create New** → **Import**
3. Select **From File**
4. Choose one of the JSON files:
   - `workflow1-market-decision.json`
   - `workflow2-monitor.json`
5. Click **Import**

### Option 2: Copy-Paste JSON

1. Open the `.json` file in a text editor
2. In n8n, create a new workflow
3. Copy the entire JSON content
4. Go to **Workflow Settings** → **Code** (or use API)
5. Paste the JSON and save

### Option 3: API Import

```bash
curl -X POST http://localhost:5678/api/v1/workflows \
  -H "Content-Type: application/json" \
  -d @workflow1-market-decision.json
```

---

## Workflow 1: Market Decision

### What it does:
- **Trigger:** Manual or webhook call every 4 hours (can be changed to Cron)
- **Flow:**
  1. Call `/api/v1/market-analysis/{symbol}?risk_pct=0.02&levels=10`
  2. Pass market data to Claude AI (OpenAI node)
  3. AI decides whether to launch grid based on ATR conditions
  4. If `launch=true`, POST to `/api/v1/grids` with dynamic parameters
  5. Notify result via Telegram

### Configuration Required:

1. **Node 1 (Start):** Change to Cron trigger if you want 4-hour scheduling
   - Rule: `Every 4 hours`
   - Or keep as Manual/Webhook for external triggering

2. **Node 2 (Market Analysis):** Verify `BACKEND_URL` is set in environment

3. **Node 3 (AI Decision):** 
   - Select OpenAI Credentials (requires API key)
   - Model: `claude-opus-4-8`
   - System prompt is pre-configured (explains grid trading criteria to AI)

4. **Node 6a (Telegram Notification):** 
   - Create/select Telegram credentials
   - Chat ID from environment: `{{ $env.TELEGRAM_CHAT_ID }}`

### Test Plan:

1. Enable the workflow and manually trigger Nodo 1
2. Check that `/market-analysis` endpoint returns data (Nodo 2)
3. Verify AI Decision node executes and returns `launch: true/false`
4. If `launch=true`, verify grid creation on Binance testnet
5. Check Telegram notification arrives

---

## Workflow 2: Grid Monitor

### What it does:
- **Trigger:** Every 15 minutes (Cron)
- **Flow:**
  1. Fetch all `RUNNING` grids from backend
  2. For each grid (sequential):
     - POST `/refresh` to sync Binance order status
     - POST `/check-close` to evaluate SL/TP
     - Notify errors or successful closes via Telegram
     - Wait 1.5s before next grid (rate limit safety)

### Configuration Required:

1. **Node 1 (Cron):** Pre-configured for 15 minutes
   - Change interval if needed (e.g., 30 min for lower API usage)

2. **Node 2 (List Running Grids):** Verify `BACKEND_URL` is set

3. **Nodes 6a, 8a, 9a (Telegram Notifications):**
   - Create/select Telegram credentials
   - Chat ID from environment: `{{ $env.TELEGRAM_CHAT_ID }}`

### Test Plan:

1. Create at least one RUNNING grid manually (via Swagger or Workflow 1)
2. Enable Workflow 2
3. Wait for cron trigger (or manually run Nodo 1)
4. Check that:
   - `/grids?status=RUNNING` returns your grid (Nodo 2)
   - Nodo 5 (`/refresh`) executes successfully
   - Nodo 7 (`/check-close`) executes without triggering SL/TP
   - No error notifications appear (all grids still RUNNING)
5. Simulate a close by:
   - Manually moving price to trigger SL/TP on Binance
   - Or setting a low `take_profit` value when creating grid
   - Verify Nodo 9a notifies that grid was closed

---

## Environment Variable Reference

| Variable | Purpose | Example |
|---|---|---|
| `BACKEND_URL` | Backend API base URL | `http://backend-python:8000` |
| `TELEGRAM_BOT_TOKEN` | Telegram bot authentication | `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11` |
| `TELEGRAM_CHAT_ID` | Telegram chat to notify | `987654321` |
| `SLACK_WEBHOOK` | Slack webhook (optional) | `https://hooks.slack.com/...` |

---

## Node Type Reference

**Workflow 1 Nodes:**
- Nodo 1: `trigger` (Manual start)
- Nodo 2: `httpRequest` (GET /market-analysis)
- Nodo 3: `openAi` (Claude AI decision)
- Nodo 4: `if` (Decision branching)
- Nodo 5: `httpRequest` (POST /grids)
- Nodo 6a: `telegram` (Notify success)
- Nodo 6b: `noOp` (No-op for skipped launch)

**Workflow 2 Nodes:**
- Nodo 1: `cron` (15-minute trigger)
- Nodo 2: `httpRequest` (GET /grids?status=RUNNING)
- Nodo 3: `if` (Check if any grids)
- Nodo 4: `splitInBatches` (Loop each grid)
- Nodo 5: `httpRequest` (POST /refresh)
- Nodo 6: `if` (Check refresh error)
- Nodo 6a: `telegram` (Notify error)
- Nodo 7: `httpRequest` (POST /check-close)
- Nodo 8: `if` (Check close error)
- Nodo 8a: `telegram` (Notify error)
- Nodo 9: `if` (Check if triggered)
- Nodo 9a: `telegram` (Notify close)
- Nodo 10: `wait` (Rate limit safety)

---

## Troubleshooting

### "Connection failed to {{ $env.BACKEND_URL }}"
- Verify `BACKEND_URL` is set in n8n environment
- Check that backend API is running: `curl http://localhost:8000/health`
- Verify firewall/network allows n8n to reach backend

### "Telegram: Invalid credentials"
- Verify `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are correct
- Test token: `https://api.telegram.org/bot<TOKEN>/getMe`
- Ensure chat ID is a number (not username)

### "OpenAI: Invalid API key"
- Add your OpenAI (Claude) API key to n8n Credentials
- Verify model name is `claude-opus-4-8`

### Workflow runs but no notifications
- Check that Telegram node has credentials selected
- Verify chat ID in the node matches `$env.TELEGRAM_CHAT_ID`
- Test Telegram manually: send message to bot first

### `/refresh` or `/check-close` returns error
- Enable "Continue on Fail" on the HTTP nodes (already done in templates)
- Check backend logs: `docker logs backend-python`
- Verify grid ID exists: `GET /api/v1/grids`

---

## Production Checklist

Before deploying to production:

- [ ] Backend API is running in Docker or cloud
- [ ] Environment variables are set securely (not hardcoded in workflows)
- [ ] Telegram credentials are configured and tested
- [ ] API rate limits are understood (Binance: 1200/min, n8n: configurable)
- [ ] Error handling is in place (Continue on Fail, notifications working)
- [ ] Database backups are configured (SQLite + PostgreSQL)
- [ ] Workflows are active and scheduled
- [ ] Monitor logs for errors: `docker logs n8n` and `docker logs backend-python`
- [ ] Test with small position size (1-2% risk) before full deployment

---

## File Reference

```
docs/n8n-templates/
├── SETUP.md                           # This file
├── workflow1-market-decision.json     # Importable template
├── workflow2-monitor.json             # Importable template
```

---

## Related Documentation

- [Workflow 1 Specification](../workflow1-market-decision.md)
- [Workflow 2 Specification](../workflow2-monitor.md)
- [n8n Integration Strategy](../n8n-integration-strategy.md)
- [API Endpoints Reference](../api-endpoints.md)
- [Position Sizing Formula](../position-sizing-formula.md)

---

## Support

For issues or questions:
1. Check the backend logs: `docker logs backend-python`
2. Check n8n logs: `docker logs n8n`
3. Review error messages in the workflow execution history
4. Consult the relevant documentation file above
