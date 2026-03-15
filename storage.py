import os
from datetime import datetime

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, inspect, text
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
    mode = Column(String(20), index=True, nullable=True)  # PUMP / DIP

    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=True)

    entry_time = Column(DateTime, nullable=False, default=datetime.utcnow)
    exit_time = Column(DateTime, nullable=True)

    cross_time = Column(DateTime, nullable=True)
    cross_price = Column(Float, nullable=True)

    quote_volume_24h = Column(Float, nullable=True, default=0.0)
    cross_candle_volume = Column(Float, nullable=True, default=0.0)
    ema_distance = Column(Float, nullable=True, default=0.0)
    volume_ratio = Column(Float, nullable=True, default=0.0)
    market_cap = Column(Float, nullable=True)

    ema_fast = Column(Integer, nullable=True)
    ema_mid = Column(Integer, nullable=True)
    ema_trend = Column(Integer, nullable=True)

    entry_reason = Column(String(255), nullable=True)
    exit_reason = Column(String(255), nullable=True)

    status = Column(String(20), index=True, default="OPEN")
    pnl_pct = Column(Float, nullable=True, default=0.0)
    timeframe = Column(String(20), nullable=True, default="15m")

    max_profit_pct = Column(Float, nullable=True, default=0.0)
    max_drawdown_pct = Column(Float, nullable=True, default=0.0)
    duration_minutes = Column(Float, nullable=True, default=0.0)
    rr_ratio = Column(Float, nullable=True, default=0.0)


def format_duration_from_minutes(minutes):
    if minutes is None:
        return "-"

    total_minutes = int(round(minutes))
    days = total_minutes // (24 * 60)
    rem = total_minutes % (24 * 60)
    hours = rem // 60
    mins = rem % 60
    return f"{days}g {hours}s {mins}dk"


def _add_missing_columns():
    inspector = inspect(engine)
    if "trades" not in inspector.get_table_names():
        return

    existing_columns = {col["name"] for col in inspector.get_columns("trades")}

    missing_columns = {
        "cross_time": "TIMESTAMP NULL",
        "cross_price": "FLOAT NULL",
        "quote_volume_24h": "FLOAT NULL DEFAULT 0.0",
        "cross_candle_volume": "FLOAT NULL DEFAULT 0.0",
        "ema_distance": "FLOAT NULL DEFAULT 0.0",
        "volume_ratio": "FLOAT NULL DEFAULT 0.0",
        "mode": "VARCHAR(20) NULL",
        "market_cap": "FLOAT NULL",
        "ema_fast": "INTEGER NULL",
        "ema_mid": "INTEGER NULL",
        "ema_trend": "INTEGER NULL",
        "entry_reason": "VARCHAR(255) NULL",
        "exit_reason": "VARCHAR(255) NULL",
    }

    with engine.begin() as conn:
        for col_name, col_type in missing_columns.items():
            if col_name not in existing_columns:
                conn.execute(text(f"ALTER TABLE trades ADD COLUMN {col_name} {col_type}"))


def init_db():
    Base.metadata.create_all(bind=engine)
    _add_missing_columns()


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
    mode=None,
    market_cap=None,
    ema_fast=None,
    ema_mid=None,
    ema_trend=None,
    entry_reason=None,
):
    session = SessionLocal()
    try:
        trade = Trade(
            symbol=symbol,
            side=side,
            mode=mode,
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
            market_cap=market_cap,
            ema_fast=ema_fast,
            ema_mid=ema_mid,
            ema_trend=ema_trend,
            entry_reason=entry_reason,
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


def update_trade_metrics(trade_id, max_profit_pct, max_drawdown_pct, duration_minutes, rr_ratio):
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

        long_total = session.query(Trade).filter(Trade.side == "LONG").count()
        short_total = session.query(Trade).filter(Trade.side == "SHORT").count()

        long_closed = session.query(Trade).filter(
            Trade.side == "LONG",
            Trade.status == "CLOSED",
        ).all()
        short_closed = session.query(Trade).filter(
            Trade.side == "SHORT",
            Trade.status == "CLOSED",
        ).all()

        long_pnl = sum((t.pnl_pct or 0) for t in long_closed)
        short_pnl = sum((t.pnl_pct or 0) for t in short_closed)

        pump_closed = session.query(Trade).filter(
            Trade.mode == "PUMP",
            Trade.status == "CLOSED",
        ).all()
        dip_closed = session.query(Trade).filter(
            Trade.mode == "DIP",
            Trade.status == "CLOSED",
        ).all()

        pump_total = session.query(Trade).filter(Trade.mode == "PUMP").count()
        dip_total = session.query(Trade).filter(Trade.mode == "DIP").count()

        pump_win_rate = (
            sum(1 for t in pump_closed if (t.pnl_pct or 0) > 0) / len(pump_closed) * 100
            if pump_closed else 0.0
        )
        dip_win_rate = (
            sum(1 for t in dip_closed if (t.pnl_pct or 0) > 0) / len(dip_closed) * 100
            if dip_closed else 0.0
        )

        pump_pnl = sum((t.pnl_pct or 0) for t in pump_closed)
        dip_pnl = sum((t.pnl_pct or 0) for t in dip_closed)

        coin_rows = {}
        for t in closed_trades:
            if t.symbol not in coin_rows:
                coin_rows[t.symbol] = {
                    "symbol": t.symbol,
                    "trades": 0,
                    "total_pnl": 0.0,
                }
            coin_rows[t.symbol]["trades"] += 1
            coin_rows[t.symbol]["total_pnl"] += (t.pnl_pct or 0)

        coin_ranking = []
        for row in coin_rows.values():
            avg_profit = row["total_pnl"] / row["trades"] if row["trades"] > 0 else 0.0
            coin_ranking.append({
                "symbol": row["symbol"],
                "trades": row["trades"],
                "avg_profit": avg_profit,
                "total_pnl": row["total_pnl"],
            })

        coin_ranking.sort(key=lambda x: x["avg_profit"], reverse=True)

        recent_trades = (
            session.query(Trade)
            .order_by(Trade.id.desc())
            .limit(200)
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
            "long_total": long_total,
            "short_total": short_total,
            "long_pnl": long_pnl,
            "short_pnl": short_pnl,
            "pump_total": pump_total,
            "dip_total": dip_total,
            "pump_win_rate": pump_win_rate,
            "dip_win_rate": dip_win_rate,
            "pump_pnl": pump_pnl,
            "dip_pnl": dip_pnl,
            "coin_ranking": coin_ranking[:30],
            "recent_trades": recent_trades,
        }
    finally:
        session.close()
