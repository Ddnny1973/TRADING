-- Migration 002: Monitoring tables for grid performance analysis
--
-- Context: historical_grid_logs (existing) only stores the final total_pnl
-- of a grid at close time. It cannot answer "how many cycles has the bot
-- completed", "how much do fees eat into profit", or "what does the equity
-- curve look like over time". These two tables cover that gap.
--
-- These tables mirror the SQLAlchemy models added in
-- backend-python/app/database/models.py (GridCycle, PnlSnapshot). They will
-- ALSO be auto-created by the backend on next restart via
-- Base.metadata.create_all() (see database/connection.py::init_postgres_tables),
-- but this script lets you create them manually right now, independent of
-- when the backend gets redeployed.
--
-- Run against the backend's own trading Postgres (postgres-trading, NOT the
-- separate n8n Postgres that holds metricas_personalizadas).
-- Safe to run multiple times (IF NOT EXISTS guards).

CREATE TABLE IF NOT EXISTS grid_cycles (
    id              SERIAL PRIMARY KEY,
    grid_id         VARCHAR NOT NULL,
    symbol          VARCHAR NOT NULL,
    cycle_number    INTEGER NOT NULL,
    buy_order_id    VARCHAR NOT NULL,
    sell_order_id   VARCHAR NOT NULL,
    buy_price       NUMERIC NOT NULL,
    sell_price      NUMERIC NOT NULL,
    quantity        NUMERIC NOT NULL,
    fee_paid        NUMERIC NOT NULL,
    gross_pnl       NUMERIC NOT NULL,
    net_pnl         NUMERIC NOT NULL,
    completed_at    TIMESTAMP NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_grid_cycles_grid_id ON grid_cycles (grid_id);
CREATE INDEX IF NOT EXISTS idx_grid_cycles_symbol ON grid_cycles (symbol);
CREATE INDEX IF NOT EXISTS idx_grid_cycles_completed_at ON grid_cycles (completed_at);

CREATE TABLE IF NOT EXISTS pnl_snapshots (
    id                  SERIAL PRIMARY KEY,
    grid_id             VARCHAR NOT NULL,
    symbol              VARCHAR NOT NULL,
    taken_at            TIMESTAMP NOT NULL DEFAULT NOW(),
    realized_pnl        NUMERIC NOT NULL,
    unrealized_pnl      NUMERIC NOT NULL,
    total_pnl           NUMERIC NOT NULL,
    account_balance     NUMERIC,
    open_orders_count   INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_pnl_snapshots_grid_id ON pnl_snapshots (grid_id);
CREATE INDEX IF NOT EXISTS idx_pnl_snapshots_taken_at ON pnl_snapshots (taken_at);

-- Verification queries (run manually after creating the tables):
-- SELECT COUNT(*) FROM grid_cycles;
-- SELECT COUNT(*) FROM pnl_snapshots;
