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

    status = Column(String(20), index=True, default="OPEN")  # OPEN / CLOSED
    exit_reason = Column(String(255), nullable=True)

    pnl_pct = Column(Float, nullable=True, default=0.0)
    timeframe = Column(String(20), nullable=True, default="15m")


def init_db():
    Base.metadata.create_all(bind=engine)


def create_trade(symbol, side, entry_price, entry_time, timeframe="15m"):
    session = SessionLocal()
    try:
        trade = Trade(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            entry_time=entry_time,
            status="OPEN",
            timeframe=timeframe,
        )
        session.add(trade)
        session.commit()
        session.refresh(trade)
        return trade.id
    finally:
        session.close()


def close_trade(trade_id, exit_price, exit_time, exit_reason, pnl_pct):
    session = SessionLocal()
    try:
        trade = session.query(Trade).filter(Trade.id == trade_id).first()
        if not trade:
            return

        trade.exit_price = exit_price
        trade.exit_time = exit_time
        trade.exit_reason = exit_reason
        trade.pnl_pct = pnl_pct
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

        long_total = session.query(Trade).filter(Trade.side == "LONG").count()
        short_total = session.query(Trade).filter(Trade.side == "SHORT").count()

        long_closed = session.query(Trade).filter(
            Trade.side == "LONG",
            Trade.status == "CLOSED"
        ).all()

        short_closed = session.query(Trade).filter(
            Trade.side == "SHORT",
            Trade.status == "CLOSED"
        ).all()

        long_pnl = sum((t.pnl_pct or 0) for t in long_closed)
        short_pnl = sum((t.pnl_pct or 0) for t in short_closed)

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

        best_coin = coin_ranking[0] if coin_ranking else None
        worst_coin = coin_ranking[-1] if coin_ranking else None

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
            "long_total": long_total,
            "short_total": short_total,
            "long_pnl": long_pnl,
            "short_pnl": short_pnl,
            "best_coin": best_coin,
            "worst_coin": worst_coin,
            "coin_ranking": coin_ranking[:30],
            "recent_trades": recent_trades,
        }
    finally:
        session.close()
