-- migration_005_add_system_state.sql
-- Tabla system_state: pequeños flags de estado persistidos (kill-switch T15).
-- CREATE TABLE IF NOT EXISTS hace la migracion idempotente: las bases nuevas la
-- crean en init_sqlite_tables(); las existentes pueden ejecutar este script o
-- dejar que el boot lo haga (por eso se usa IF NOT EXISTS y no ALTER).
CREATE TABLE IF NOT EXISTS system_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);