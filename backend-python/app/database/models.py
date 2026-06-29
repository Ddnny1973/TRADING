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
