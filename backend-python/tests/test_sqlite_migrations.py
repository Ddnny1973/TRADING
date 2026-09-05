"""
Unit tests para la auto-migración SQLite (migration_004 self-healing).

Cubre que init_sqlite_tables() agregue sobre bases preexistentes las
columnas que se añadieron a grid_closures después de su primer despliegue
('failure_reason' y 'parent_grid_id'); sin esto, el INSERT best-effort de
cancel_grid/recenter falla en silencio y deja de loguear los cierres.
"""

import sqlite3

import pytest

from app.database import connection


@pytest.fixture
def legacy_db(tmp_path, monkeypatch):
    """SQLite con grid_closures 'legacy' (schema pre-migration_004, sin
    failure_reason ni parent_grid_id), como la base del servidor."""
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE grid_closures ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "grid_id TEXT NOT NULL, "
            "symbol TEXT NOT NULL, "
            "trigger_condition TEXT NOT NULL, "
            "total_pnl TEXT, "
            "position_amt_at_close TEXT, "
            "closed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
        conn.commit()
    finally:
        conn.close()
    monkeypatch.setattr(connection, "SQLITE_DB_PATH", str(db_path))
    return db_path


def _columns(db_path, table):
    conn = sqlite3.connect(db_path)
    try:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    finally:
        conn.close()


def test_init_sqlite_tables_migrates_legacy_grid_closures(legacy_db):
    connection.init_sqlite_tables()
    cols = _columns(legacy_db, "grid_closures")
    assert "failure_reason" in cols
    assert "parent_grid_id" in cols


def test_closure_insert_with_failure_reason_works_after_migration(legacy_db):
    connection.init_sqlite_tables()
    conn = sqlite3.connect(legacy_db)
    try:
        conn.execute(
            "INSERT INTO grid_closures "
            "(grid_id, symbol, trigger_condition, failure_reason, total_pnl) "
            "VALUES ('g1', 'BTCUSDT', 'REFRESH_FAILED', "
            "'openOrders call failed (network/API error)', '0')"
        )
        conn.commit()
        row = conn.execute(
            "SELECT failure_reason, parent_grid_id FROM grid_closures WHERE grid_id = 'g1'"
        ).fetchone()
    finally:
        conn.close()
    assert row[0] == "openOrders call failed (network/API error)"
    assert row[1] is None


def test_init_sqlite_tables_is_idempotent(legacy_db):
    connection.init_sqlite_tables()
    connection.init_sqlite_tables()  # no debe lanzar
    assert "failure_reason" in _columns(legacy_db, "grid_closures")