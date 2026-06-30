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


# ==========================================
# SQLite Connection (Local Grid Storage)
# ==========================================

SQLITE_DB_PATH = os.path.join(os.getenv("SQLITE_DATA_DIR", "."), "grid_trading.db")


def get_sqlite_connection():
    """Get SQLite connection for local grid storage"""
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ==========================================
# PostgreSQL Connection (Analytics)
# ==========================================

# Create SQLAlchemy engine for PostgreSQL
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
    """
    Initialize databases
    Creates tables if they don't exist
    """
    try:
        # Initialize SQLite tables
        init_sqlite_tables()
        
        # Initialize PostgreSQL tables
        if postgres_engine:
            init_postgres_tables()
        
        print("✅ Databases initialized successfully")
    except Exception as e:
        print(f"❌ Error initializing databases: {e}")


def init_sqlite_tables():
    """Create SQLite tables for grid trading"""
    conn = get_sqlite_connection()
    cursor = conn.cursor()
    
    # Create grids table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS grids (
            id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            lower_price NUMERIC NOT NULL,
            upper_price NUMERIC NOT NULL,
            levels INTEGER NOT NULL,
            status TEXT NOT NULL,
            stop_loss NUMERIC,
            take_profit NUMERIC,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Lightweight migration for DBs created before stop_loss/take_profit existed.
    # No migration framework in this project yet - ALTER TABLE is idempotent-ish
    # here because sqlite3 raises OperationalError if the column already exists.
    for column_def in ("stop_loss NUMERIC", "take_profit NUMERIC"):
        try:
            cursor.execute(f"ALTER TABLE grids ADD COLUMN {column_def}")
        except sqlite3.OperationalError:
            pass
    
    # Create grid_orders table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS grid_orders (
            id TEXT PRIMARY KEY,
            grid_id TEXT NOT NULL,
            price NUMERIC NOT NULL,
            quantity NUMERIC NOT NULL,
            side TEXT NOT NULL,
            type TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (grid_id) REFERENCES grids (id)
        )
    ''')
    
    conn.commit()
    conn.close()


def init_postgres_tables():
    """Create PostgreSQL tables for analytics (historical_grid_logs, etc.)"""
    if postgres_engine is None:
        print("Warning: PostgreSQL engine not available, skipping table creation")
        return
    Base.metadata.create_all(bind=postgres_engine)


def get_db_session():
    """Get PostgreSQL database session"""
    if SessionLocal:
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()
