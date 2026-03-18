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

    # Entry / exit analytics fields
    vol_ratio_entry = Column(Float)
    vol_ratio_exit = Column(Float)
    body_ratio_entry = Column(Float)
    body_ratio_exit = Column(Float)
    candle_type = Column(String)


def ensure_signal_columns():
    inspector = inspect(engine)
    if "signals" not in inspector.get_table_names():
        return

    existing_columns = {col["name"] for col in inspector.get_columns("signals")}

    missing_columns = []
    column_definitions = {
        "risk_level": "VARCHAR",
        "risk_score": "FLOAT",
        "risk_reasons": "VARCHAR",
        "vol_ratio_entry": "FLOAT",
        "vol_ratio_exit": "FLOAT",
        "body_ratio_entry": "FLOAT",
        "body_ratio_exit": "FLOAT",
        "candle_type": "VARCHAR",
    }

    for col_name, col_type in column_definitions.items():
        if col_name not in existing_columns:
            missing_columns.append((col_name, col_type))

    if not missing_columns:
        return

    with engine.begin() as conn:
        for col_name, col_type in missing_columns:
            conn.execute(text(f"ALTER TABLE signals ADD COLUMN {col_name} {col_type}"))


Base.metadata.create_all(bind=engine)
ensure_signal_columns()
