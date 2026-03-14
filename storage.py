import os
from datetime import datetime

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///ema_scanner.db")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

Base = declarative_base()


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(50), index=True)
    side = Column(String(10), index=True)  # LONG / SHORT

    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=True)

    entry_time = Column(DateTime, nullable=False, default=datetime.utcnow)
    exit_time = Column(DateTime, nullable=True)

    # ANALİZ İÇİN EKLENENLER
    cross_time = Column(DateTime, nullable=True)
    cross_price = Column(Float, nullable=True)

    quote_volume_24h = Column(Float, nullable=True, default=0.0)
    cross_candle_volume = Column(Float, nullable=True, default=0.0)

    ema_distance = Column(Float, nullable=True, default=0.0)
    volume_ratio = Column(Float, nullable=True, default=0.0)

    status = Column(String(20), index=True, default="OPEN")

    exit_reason = Column(String(255), nullable=True)

    pnl_pct = Column(Float, nullable=True, default=0.0)

    timeframe = Column(String(20), nullable=True, default="15m")

    max_profit_pct = Column(Float, nullable=True, default=0.0)
    max_drawdown_pct = Column(Float, nullable=True, default=0.0)

    duration_minutes = Column(Float, nullable=True, default=0.0)

    rr_ratio = Column(Float, nullable=True, default=0.0)


def init_db():
    Base.metadata.create_all(bind=engine)


def create_trade(
    symbol,
    side,
    entry_price,
    entry_time,
    timeframe="15m",
    cross_time=None,
    cross_price=None,
    quote_volume_24h=0.0,
    cross_candle_volume=0.0,
    ema_distance=0.0,
    volume_ratio=0.0,
):

    session = SessionLocal()

    try:

        trade = Trade(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            entry_time=entry_time,
            status="OPEN",
            timeframe=timeframe,
            cross_time=cross_time,
            cross_price=cross_price,
            quote_volume_24h=quote_volume_24h,
            cross_candle_volume=cross_candle_volume,
            ema_distance=ema_distance,
            volume_ratio=volume_ratio,
            max_profit_pct=0.0,
            max_drawdown_pct=0.0,
            duration_minutes=0.0,
            rr_ratio=0.0,
        )

        session.add(trade)
        session.commit()
        session.refresh(trade)

        return trade.id

    finally:
        session.close()


def update_trade_metrics(
    trade_id,
    max_profit_pct,
    max_drawdown_pct,
    duration_minutes,
    rr_ratio,
):

    session = SessionLocal()

    try:

        trade = session.query(Trade).filter(Trade.id == trade_id).first()

        if not trade:
            return

        trade.max_profit_pct = max_profit_pct
        trade.max_drawdown_pct = max_drawdown_pct
        trade.duration_minutes = duration_minutes
        trade.rr_ratio = rr_ratio

        session.commit()

    finally:
        session.close()


def close_trade(
    trade_id,
    exit_price,
    exit_time,
    exit_reason,
    pnl_pct,
    max_profit_pct,
    max_drawdown_pct,
    duration_minutes,
    rr_ratio,
):

    session = SessionLocal()

    try:

        trade = session.query(Trade).filter(Trade.id == trade_id).first()

        if not trade:
            return

        trade.exit_price = exit_price
        trade.exit_time = exit_time
        trade.exit_reason = exit_reason
        trade.pnl_pct = pnl_pct

        trade.max_profit_pct = max_profit_pct
        trade.max_drawdown_pct = max_drawdown_pct

        trade.duration_minutes = duration_minutes
        trade.rr_ratio = rr_ratio

        trade.status = "CLOSED"

        session.commit()

    finally:
        session.close()


def get_dashboard_stats():

    session = SessionLocal()

    try:

        total_signals = session.query(Trade).count()
        total_closed = session.query(Trade).filter(Trade.status == "CLOSED").count()
        total_open = session.query(Trade).filter(Trade.status == "OPEN").count()

        closed_trades = session.query(Trade).filter(Trade.status == "CLOSED").all()

        wins = sum(1 for t in closed_trades if (t.pnl_pct or 0) > 0)

        total_pnl = sum((t.pnl_pct or 0) for t in closed_trades)

        avg_pnl = (total_pnl / total_closed) if total_closed > 0 else 0.0

        win_rate = (wins / total_closed * 100) if total_closed > 0 else 0.0

        avg_duration = (
            sum((t.duration_minutes or 0) for t in closed_trades) / total_closed
            if total_closed > 0 else 0.0
        )

        avg_mfe = (
            sum((t.max_profit_pct or 0) for t in closed_trades) / total_closed
            if total_closed > 0 else 0.0
        )

        avg_mae = (
            sum((t.max_drawdown_pct or 0) for t in closed_trades) / total_closed
            if total_closed > 0 else 0.0
        )

        avg_rr = (
            sum((t.rr_ratio or 0) for t in closed_trades) / total_closed
            if total_closed > 0 else 0.0
        )

        recent_trades = (
            session.query(Trade)
            .order_by(Trade.id.desc())
            .limit(30)
            .all()
        )

        return {
            "total_signals": total_signals,
            "total_closed": total_closed,
            "total_open": total_open,
            "win_rate": win_rate,
            "total_pnl": total_pnl,
            "avg_pnl": avg_pnl,
            "avg_duration": avg_duration,
            "avg_mfe": avg_mfe,
            "avg_mae": avg_mae,
            "avg_rr": avg_rr,
            "recent_trades": recent_trades,
        }

    finally:
        session.close()
