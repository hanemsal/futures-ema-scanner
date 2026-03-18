import os
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, create_engine, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

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

    # Risk fields
    risk_level = Column(String)
    risk_score = Column(Float)
    risk_reasons = Column(String)


def ensure_signal_columns():
    inspector = inspect(engine)
    if "signals" not in inspector.get_table_names():
        return

    existing_columns = {col["name"] for col in inspector.get_columns("signals")}

    missing_columns = []
    if "risk_level" not in existing_columns:
        missing_columns.append(("risk_level", "VARCHAR"))
    if "risk_score" not in existing_columns:
        missing_columns.append(("risk_score", "FLOAT"))
    if "risk_reasons" not in existing_columns:
        missing_columns.append(("risk_reasons", "VARCHAR"))

    if not missing_columns:
        return

    with engine.begin() as conn:
        for col_name, col_type in missing_columns:
            conn.execute(text(f"ALTER TABLE signals ADD COLUMN {col_name} {col_type}"))


Base.metadata.create_all(bind=engine)
ensure_signal_columns()
