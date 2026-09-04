-- migration_004_add_failure_reason.sql
-- Agrega la columna failure_reason a grid_closures para almacenar el motivo
-- concreto del cierre (ademas de trigger_condition). Requiere SQLite >= 3.25
-- (ALTER TABLE ADD COLUMN soportado desde 3.35.0, pero SQLite lo acepta desde
-- cualquier version con columnas con DEFAULT).

-- SQLite: ADD COLUMN con DEFAULT
ALTER TABLE grid_closures ADD COLUMN failure_reason TEXT DEFAULT NULL;
