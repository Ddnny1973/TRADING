-- Migration 003: Bot health & execution monitoring tables
--
-- Context: grid_cycles + pnl_snapshots (migration_002) answer "how well is the
-- grid strategy doing". These two tables answer "is the bot itself healthy and
-- running": uptime/errors of the n8n orchestration (bot_executions) and
-- business-level incidents that affect PnL (bot_health_events).
--
-- bot_executions: ONE row per n8n workflow execution (WF1 market decision,
-- WF2 monitor/refresh/check-close). Lets us compute real uptime of the
-- orchestration, error rate per workflow, and mean duration. Filled by n8n
-- (Workflow 1/2) at the start/end of each run.
--
-- bot_health_events: business incidents the grid logic surfaces, each mapped
-- to a known event_type so dashboards can filter/aggregate:
--   RECONCILIATION_FAILED  - a grid could not resync with Binance (T14)
--   AUTO_CANCEL            - an order got canceled externally / auto-canceled
--   REPLENISH_PAUSED       - replenishment paused by MAX_POSITION guard
--   RECENTERED             - T2 recenter fired on an OUT_OF_RANGE grid
-- Filled by the backend (grid_service.py) or by n8n (WF2) as they happen.
--
-- Run against the backend's own trading Postgres (postgres-trading, NOT the
-- separate n8n Postgres that holds metricas_personalizadas). Safe to run
-- multiple times (IF NOT EXISTS guards).

CREATE TABLE IF NOT EXISTS bot_executions (
    id              SERIAL PRIMARY KEY,
    workflow_id     VARCHAR NOT NULL,
    workflow_name   VARCHAR,
    status          VARCHAR NOT NULL,             -- 'success' | 'error'
    trigger_source  VARCHAR,                      -- 'cron' | 'manual' | 'sub-workflow'
    error_message   TEXT,
    started_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMP,
    duration_ms     INTEGER,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bot_executions_workflow_started
    ON bot_executions (workflow_id, started_at);
CREATE INDEX IF NOT EXISTS idx_bot_executions_status
    ON bot_executions (status);
CREATE INDEX IF NOT EXISTS idx_bot_executions_started_at
    ON bot_executions (started_at);

CREATE TABLE IF NOT EXISTS bot_health_events (
    id              SERIAL PRIMARY KEY,
    event_type      VARCHAR NOT NULL,  -- see header comment for known values
    grid_id         VARCHAR,
    symbol          VARCHAR,
    severity        VARCHAR NOT NULL DEFAULT 'warning',  -- 'info'|'warning'|'critical'
    message         TEXT,
    details         JSONB,
    occurred_at     TIMESTAMP NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bot_health_events_type_occurred
    ON bot_health_events (event_type, occurred_at);
CREATE INDEX IF NOT EXISTS idx_bot_health_events_grid
    ON bot_health_events (grid_id);
CREATE INDEX IF NOT EXISTS idx_bot_health_events_occurred_at
    ON bot_health_events (occurred_at);

-- Verification queries (run manually after creating the tables):
-- SELECT COUNT(*) FROM bot_executions;
-- SELECT COUNT(*) FROM bot_health_events;
