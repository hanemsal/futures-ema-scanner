from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///signals.db")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class Signal(Base):
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, index=True)

    symbol = Column(String)
    side = Column(String)  # LONG / SHORT

    signal_group = Column(String)  # DIP / PUMP / NEW
    entry_type = Column(String)  # cross / bounce

    entry = Column(Float)
    exit = Column(Float)

    status = Column(String)  # OPEN / CLOSED

    pnl = Column(Float)
    max_profit = Column(Float)

    score = Column(Float)
    quality = Column(String)

    rsi_monthly = Column(Float)
    rsi_weekly = Column(Float)
    rsi_daily = Column(Float)
    rsi_4h = Column(Float)

    change_1h = Column(Float)
    change_4h = Column(Float)

    ema_set = Column(String)

    entry_reason = Column(String)
    exit_reason = Column(String)

    cooldown_until = Column(DateTime)

    created_at = Column(DateTime, default=datetime.utcnow)
    exit_time = Column(DateTime)

Base.metadata.create_all(bind=engine)
