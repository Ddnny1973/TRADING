"""
Database connection management
Handles SQLite and PostgreSQL connections
"""

import sqlite3
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings


# ==========================================
# SQLite Connection (Local Grid Storage)
# ==========================================

def get_sqlite_connection():
    """Get SQLite connection for local grid storage"""
    conn = sqlite3.connect('grid_trading.db')
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
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
    """Create PostgreSQL tables for analytics"""
    # TODO: Implement PostgreSQL table creation
    pass


def get_db_session():
    """Get PostgreSQL database session"""
    if SessionLocal:
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()
