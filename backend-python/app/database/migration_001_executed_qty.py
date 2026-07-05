"""
Migration 001: Backfill executed_qty for existing FILLED orders.

Context: The executed_qty column was added to track actual fills (Fase 2).
Previous FILLED orders don't have executed_qty set, which breaks PnL calculation.
This migration sets executed_qty = quantity for all FILLED orders with executed_qty = 0.

Run before first deployment if the database is NOT being reset.
Safe to run multiple times (idempotent).
"""

import sqlite3
from typing import Optional
import logging

logger = logging.getLogger("migration")


def migrate_executed_qty(db_path: str = "grid_trading.db") -> bool:
    """
    Backfill executed_qty for existing FILLED orders.

    Args:
        db_path: Path to SQLite database (default: grid_trading.db)

    Returns:
        True if migration succeeded, False otherwise.
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Backfill executed_qty for FILLED orders
        cursor.execute("""
            UPDATE grid_orders
            SET executed_qty = quantity
            WHERE status = 'FILLED' AND (executed_qty IS NULL OR executed_qty = 0)
        """)

        rows_affected = cursor.rowcount
        conn.commit()
        conn.close()

        logger.info(f"✅ Migration 001 complete: {rows_affected} orders backfilled")
        return True

    except Exception as e:
        logger.error(f"❌ Migration 001 failed: {str(e)}")
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success = migrate_executed_qty()
    exit(0 if success else 1)
