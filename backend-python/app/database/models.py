"""
SQLAlchemy ORM models for PostgreSQL analytics database
"""

from sqlalchemy import Column, String, Numeric, Integer, DateTime, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime


Base = declarative_base()


class HistoricalGridLog(Base):
    """Historical grid trading logs for analytics"""
    
    __tablename__ = "historical_grid_logs"
    
    log_id = Column(Integer, primary_key=True, autoincrement=True)
    grid_id = Column(String, unique=True, nullable=False)
    symbol = Column(String, nullable=False)
    total_pnl = Column(Numeric, nullable=False)
    trigger_condition = Column(String, nullable=False)
    opened_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<HistoricalGridLog {self.grid_id} - {self.symbol} - PnL: {self.total_pnl}>"


class GridCycle(Base):
    """
    One completed buy->sell (or sell->buy) round-trip within a grid.

    This is the real unit of "did the bot make money": a cycle is closed
    when the opposite order to a fill gets filled too. Fees are tracked
    separately from gross_pnl so we can see how much of the profit is
    eaten by commissions (see docs/60-TRADING-LOGIC/03-fees-pnl.md).

    Written by grid_service.py whenever replenish_filled_orders() detects
    a matching opposite fill (see docs/analisis-bot/ for the monitoring
    analysis this table supports).
    """

    __tablename__ = "grid_cycles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    grid_id = Column(String, nullable=False, index=True)
    symbol = Column(String, nullable=False)
    cycle_number = Column(Integer, nullable=False)
    buy_order_id = Column(String, nullable=False)
    sell_order_id = Column(String, nullable=False)
    buy_price = Column(Numeric, nullable=False)
    sell_price = Column(Numeric, nullable=False)
    quantity = Column(Numeric, nullable=False)
    fee_paid = Column(Numeric, nullable=False)
    gross_pnl = Column(Numeric, nullable=False)
    net_pnl = Column(Numeric, nullable=False)
    completed_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<GridCycle grid={self.grid_id} #{self.cycle_number} net_pnl={self.net_pnl}>"


class PnlSnapshot(Base):
    """
    Point-in-time PnL/equity reading for a RUNNING grid.

    Meant to be written on every Workflow 2 refresh cycle (every ~15 min),
    so the equity curve can be reconstructed later instead of only knowing
    the final total_pnl at grid close (historical_grid_logs).
    """

    __tablename__ = "pnl_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    grid_id = Column(String, nullable=False, index=True)
    symbol = Column(String, nullable=False)
    taken_at = Column(DateTime, default=datetime.utcnow, index=True)
    realized_pnl = Column(Numeric, nullable=False)
    unrealized_pnl = Column(Numeric, nullable=False)
    total_pnl = Column(Numeric, nullable=False)
    account_balance = Column(Numeric, nullable=True)
    open_orders_count = Column(Integer, nullable=False, default=0)

    def __repr__(self):
        return f"<PnlSnapshot grid={self.grid_id} at={self.taken_at} total_pnl={self.total_pnl}>"
