"""
Database connection management
Handles SQLite and PostgreSQL connections
"""

import os
import sqlite3
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.database.models import Base


SQLITE_DB_PATH = os.path.join(os.getenv("SQLITE_DATA_DIR", "."), "grid_trading.db")


def get_sqlite_connection():
    """Get SQLite connection for local grid storage.

    timeout=20: SQLite will retry for up to 20 s before raising
    OperationalError when another connection holds the write lock.
    WAL mode is enabled once at init_sqlite_tables() startup so
    readers never block writers and vice-versa.
    """
    conn = sqlite3.connect(SQLITE_DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    return conn


try:
    postgres_engine = create_engine(
        settings.POSTGRES_URL,
        echo=settings.DEBUG_MODE,
        pool_pre_ping=True
    )
    SessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=postgres_engine
    )
except Exception as e:
    print(f"Warning: Could not connect to PostgreSQL: {e}")
    postgres_engine = None
    SessionLocal = None


def init_db():
    try:
        init_sqlite_tables()
        if postgres_engine:
            init_postgres_tables()
        print("✅ Databases initialized successfully")
    except Exception as e:
        print(f"❌ Error initializing databases: {e}")


def init_sqlite_tables():
    """Create SQLite tables for grid trading"""
    conn = get_sqlite_connection()
    # WAL mode allows concurrent readers + one writer without "database is
    # locked" errors. Persists on disk - safe to run on every startup.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    cursor = conn.cursor()

    cursor.execute(
        "CREATE TABLE IF NOT EXISTS grids ("
        "id TEXT PRIMARY KEY, "
        "symbol TEXT NOT NULL, "
        "lower_price NUMERIC NOT NULL, "
        "upper_price NUMERIC NOT NULL, "
        "levels INTEGER NOT NULL, "
        "status TEXT NOT NULL, "
        "stop_loss NUMERIC, "
        "take_profit NUMERIC, "
        "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    )

    for column_def in ("stop_loss NUMERIC", "take_profit NUMERIC"):
        try:
            cursor.execute(f"ALTER TABLE grids ADD COLUMN {column_def}")
        except sqlite3.OperationalError:
            pass

    cursor.execute(
        "CREATE TABLE IF NOT EXISTS grid_orders ("
        "id TEXT PRIMARY KEY, "
        "grid_id TEXT NOT NULL, "
        "price NUMERIC NOT NULL, "
        "quantity NUMERIC NOT NULL, "
        "side TEXT NOT NULL, "
        "type TEXT NOT NULL, "
        "status TEXT NOT NULL, "
        "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
        "FOREIGN KEY (grid_id) REFERENCES grids (id))"
    )

    conn.commit()
    conn.close()


def init_postgres_tables():
    if postgres_engine is None:
        print("Warning: PostgreSQL engine not available, skipping table creation")
        return 
    Base.metadata.create_all(bind=postgres_engine)


def get_db_session():
    if SessionLocal:
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()