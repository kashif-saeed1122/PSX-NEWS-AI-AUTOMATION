"""SQLAlchemy models for the PSX dashboard.

Five domains:
    A. Market data           — stocks, stock_prices, intraday_ticks, index_snapshots
    B. NCCPL + News          — nccpl_signals, news_articles
    C. AI outputs            — pipeline_runs, news_briefings, news_stories,
                               trading_reports, picks, pick_outcomes
    D. Users + billing       — users, subscriptions, payments
    E. Alerts + watchlists   — watchlists, alerts, alert_deliveries, user_portfolios
"""
from __future__ import annotations

import uuid
from datetime import datetime, date
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base for every model. Alembic discovers tables via this."""
    pass


# ═══════════════════════════════════════════════════════════════════
#   A.  MARKET DATA
# ═══════════════════════════════════════════════════════════════════


class Stock(Base):
    __tablename__ = "stocks"

    symbol:    Mapped[str]            = mapped_column(String(20),  primary_key=True)
    company:   Mapped[Optional[str]]  = mapped_column(String(255))
    sector:    Mapped[Optional[str]]  = mapped_column(String(64))
    listed_in: Mapped[list[str]]      = mapped_column(ARRAY(String), default=list)
    shariah:   Mapped[bool]           = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime]      = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class StockPrice(Base):
    """Daily OHLCV. Replaces price_history.json."""
    __tablename__ = "stock_prices"

    symbol:     Mapped[str]   = mapped_column(String(20), ForeignKey("stocks.symbol"), primary_key=True)
    ts:         Mapped[date]  = mapped_column(Date, primary_key=True)
    open:       Mapped[Optional[float]] = mapped_column(Numeric(12, 4))
    high:       Mapped[Optional[float]] = mapped_column(Numeric(12, 4))
    low:        Mapped[Optional[float]] = mapped_column(Numeric(12, 4))
    close:      Mapped[Optional[float]] = mapped_column(Numeric(12, 4))
    ldcp:       Mapped[Optional[float]] = mapped_column(Numeric(12, 4))
    volume:     Mapped[Optional[int]]   = mapped_column(BigInteger)
    change_pct: Mapped[Optional[float]] = mapped_column(Numeric(6, 2))

    __table_args__ = (
        Index("ix_stock_prices_symbol_ts_desc", "symbol", ts.desc()),
    )


class IntradayTick(Base):
    """Minute-level prices for the alerts engine. Add monthly partitions later."""
    __tablename__ = "intraday_ticks"

    id:     Mapped[int]      = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    symbol: Mapped[str]      = mapped_column(String(20), ForeignKey("stocks.symbol"))
    ts:     Mapped[datetime] = mapped_column(DateTime(timezone=True))
    price:  Mapped[float]    = mapped_column(Numeric(12, 4))
    volume: Mapped[Optional[int]] = mapped_column(BigInteger)

    __table_args__ = (
        Index("ix_intraday_ticks_symbol_ts_desc", "symbol", ts.desc()),
    )


class IndexSnapshot(Base):
    __tablename__ = "index_snapshots"

    index_name: Mapped[str]            = mapped_column(String(32), primary_key=True)
    ts:         Mapped[date]           = mapped_column(Date, primary_key=True)
    level:      Mapped[Optional[float]] = mapped_column(Numeric(14, 4))
    change_pct: Mapped[Optional[float]] = mapped_column(Numeric(6, 2))


# ═══════════════════════════════════════════════════════════════════
#   B.  NCCPL  +  NEWS
# ═══════════════════════════════════════════════════════════════════


class NccplSignal(Base):
    """Combined insider + FIPI signals."""
    __tablename__ = "nccpl_signals"

    id:        Mapped[int]      = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    symbol:    Mapped[str]      = mapped_column(String(20), ForeignKey("stocks.symbol"))
    source:    Mapped[str]      = mapped_column(String(16))   # 'insider' | 'fipi'
    direction: Mapped[str]      = mapped_column(String(16))   # 'BUY' | 'SELL' | 'ACTIVITY'
    strength:  Mapped[str]      = mapped_column(String(16))   # VERY_HIGH | HIGH | MEDIUM | LOW
    value_pkr: Mapped[Optional[int]] = mapped_column(BigInteger)
    summary:   Mapped[str]      = mapped_column(Text)
    filed_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True))
    doc_id:    Mapped[str]      = mapped_column(String(64))

    __table_args__ = (
        UniqueConstraint("source", "doc_id", name="uq_nccpl_source_doc"),
        Index("ix_nccpl_symbol_filed_at_desc", "symbol", filed_at.desc()),
    )


class NewsArticle(Base):
    __tablename__ = "news_articles"

    id:           Mapped[int]      = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source:       Mapped[str]      = mapped_column(String(64))
    title:        Mapped[str]      = mapped_column(Text)
    summary:      Mapped[Optional[str]]  = mapped_column(Text)
    url:          Mapped[Optional[str]]  = mapped_column(Text)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    sectors:      Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    companies:    Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    url_hash:     Mapped[str]      = mapped_column(String(64), unique=True)
    ingested_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_news_published_at_desc", published_at.desc()),
        Index("ix_news_sectors_gin",   "sectors",   postgresql_using="gin"),
        Index("ix_news_companies_gin", "companies", postgresql_using="gin"),
    )


# ═══════════════════════════════════════════════════════════════════
#   C.  AI OUTPUTS  (the track record lives here)
# ═══════════════════════════════════════════════════════════════════


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id:          Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_at:      Mapped[datetime]  = mapped_column(DateTime(timezone=True), server_default=func.now())
    mode:        Mapped[str]       = mapped_column(String(16))   # 'legacy' | 'crewai'
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer)
    status:      Mapped[str]       = mapped_column(String(16), default="ok")
    error:       Mapped[Optional[str]] = mapped_column(Text)


class NewsBriefing(Base):
    __tablename__ = "news_briefings"

    id:                  Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pipeline_run_id:     Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("pipeline_runs.id"))
    briefing_date:       Mapped[date]      = mapped_column(Date)
    overall_sentiment:   Mapped[str]       = mapped_column(String(16))
    sentiment_reasoning: Mapped[Optional[str]] = mapped_column(Text)
    macro_factors:       Mapped[dict]      = mapped_column(JSONB, default=dict)
    shariah_market_note: Mapped[Optional[str]] = mapped_column(Text)
    key_risks:           Mapped[list]      = mapped_column(JSONB, default=list)
    key_opportunities:   Mapped[list]      = mapped_column(JSONB, default=list)

    __table_args__ = (
        Index("ix_briefings_date_desc", briefing_date.desc()),
    )


class NewsStory(Base):
    __tablename__ = "news_stories"

    id:               Mapped[int]      = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    briefing_id:      Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("news_briefings.id", ondelete="CASCADE"))
    headline:         Mapped[str]      = mapped_column(Text)
    source:           Mapped[Optional[str]] = mapped_column(String(64))
    impact:           Mapped[str]      = mapped_column(String(16))     # POSITIVE | NEGATIVE | NEUTRAL
    impact_score:     Mapped[Optional[int]] = mapped_column(SmallInteger)
    reasoning_chain:  Mapped[list]     = mapped_column(JSONB, default=list)  # 5-step chain
    what:             Mapped[Optional[str]] = mapped_column(Text)
    why_it_matters:   Mapped[Optional[str]] = mapped_column(Text)
    second_order:     Mapped[Optional[str]] = mapped_column(Text)
    shariah_lens:     Mapped[Optional[str]] = mapped_column(Text)
    trader_action:    Mapped[Optional[str]] = mapped_column(Text)
    sectors:          Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    companies:        Mapped[list[str]] = mapped_column(ARRAY(String), default=list)

    __table_args__ = (
        Index("ix_news_stories_briefing", "briefing_id"),
    )


class TradingReport(Base):
    __tablename__ = "trading_reports"

    id:                Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pipeline_run_id:   Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("pipeline_runs.id"))
    report_date:       Mapped[date]      = mapped_column(Date)
    session_bias:      Mapped[Optional[str]] = mapped_column(String(16))
    kse100_level:      Mapped[Optional[str]] = mapped_column(String(32))
    kse100_change_pct: Mapped[Optional[str]] = mapped_column(String(16))
    kmi30_level:       Mapped[Optional[str]] = mapped_column(String(32))
    market_breadth:    Mapped[Optional[str]] = mapped_column(String(64))
    summary:           Mapped[Optional[str]] = mapped_column(Text)
    macro_watch:       Mapped[Optional[str]] = mapped_column(Text)
    disclaimer:        Mapped[Optional[str]] = mapped_column(Text)

    __table_args__ = (
        Index("ix_trading_reports_date_desc", report_date.desc()),
    )


class Pick(Base):
    """Both BUYs and AVOIDs, both portfolios. One row per pick per report."""
    __tablename__ = "picks"

    id:                Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_id:         Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("trading_reports.id", ondelete="CASCADE"))
    portfolio:         Mapped[str]       = mapped_column(String(16))   # 'conventional' | 'shariah'
    call_type:         Mapped[str]       = mapped_column(String(8))    # 'BUY' | 'AVOID'
    rank:              Mapped[int]       = mapped_column(SmallInteger)
    symbol:            Mapped[str]       = mapped_column(String(20), ForeignKey("stocks.symbol"))
    sector:            Mapped[Optional[str]] = mapped_column(String(64))
    shariah_compliant: Mapped[bool]      = mapped_column(Boolean, default=False)
    kmi_index:         Mapped[Optional[str]] = mapped_column(String(16))   # KMI30 | KMIALLSHR | ''
    current_price:     Mapped[Optional[str]] = mapped_column(String(32))
    entry_range:       Mapped[Optional[str]] = mapped_column(String(64))
    target_price:      Mapped[Optional[str]] = mapped_column(String(32))
    stop_loss:         Mapped[Optional[str]] = mapped_column(String(32))
    upside_pct:        Mapped[Optional[str]] = mapped_column(String(16))
    holding_period:    Mapped[Optional[str]] = mapped_column(String(32))
    volume_today:      Mapped[Optional[str]] = mapped_column(String(32))
    volume_signal:     Mapped[Optional[str]] = mapped_column(String(32))
    confidence:        Mapped[Optional[str]] = mapped_column(String(16))   # HIGH | MEDIUM | LOW
    news_catalyst:     Mapped[Optional[str]] = mapped_column(Text)
    price_volume_reason: Mapped[Optional[str]] = mapped_column(Text)
    second_order_play: Mapped[Optional[str]] = mapped_column(Text)
    reasoning_chain:   Mapped[list]      = mapped_column(JSONB, default=list)  # 6-step chain (BUYs only)
    risk:              Mapped[Optional[str]] = mapped_column(Text)
    reason:            Mapped[Optional[str]] = mapped_column(Text)   # AVOID only
    risk_if_held:      Mapped[Optional[str]] = mapped_column(Text)   # AVOID only
    created_at:        Mapped[datetime]  = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_picks_symbol_created_desc", "symbol", created_at.desc()),
        Index("ix_picks_report_portfolio_type", "report_id", "portfolio", "call_type"),
        Index("ix_picks_confidence_call", "confidence", "call_type"),
    )


class PickOutcome(Base):
    """Result of each pick, updated by a daily cron after the next session closes."""
    __tablename__ = "pick_outcomes"

    pick_id:           Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("picks.id", ondelete="CASCADE"), primary_key=True)
    evaluated_on:      Mapped[date]      = mapped_column(Date)
    actual_change_pct: Mapped[Optional[float]] = mapped_column(Numeric(6, 2))
    result:            Mapped[str]       = mapped_column(String(16))   # CORRECT | WRONG | NEUTRAL | UNKNOWN
    hit_target:        Mapped[bool]      = mapped_column(Boolean, default=False)
    hit_stop_loss:     Mapped[bool]      = mapped_column(Boolean, default=False)
    days_to_target:    Mapped[Optional[int]] = mapped_column(SmallInteger)


# ═══════════════════════════════════════════════════════════════════
#   D.  USERS  +  BILLING
# ═══════════════════════════════════════════════════════════════════


class User(Base):
    __tablename__ = "users"

    id:            Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email:         Mapped[Optional[str]] = mapped_column(String(255), unique=True)
    phone:         Mapped[Optional[str]] = mapped_column(String(32),  unique=True)
    name:          Mapped[Optional[str]] = mapped_column(String(128))
    tier:          Mapped[str]       = mapped_column(String(16), default="free")  # free | basic | pro
    password_hash: Mapped[Optional[str]] = mapped_column(String(255))
    created_at:    Mapped[datetime]  = mapped_column(DateTime(timezone=True), server_default=func.now())


class Subscription(Base):
    __tablename__ = "subscriptions"

    id:         Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id:    Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    tier:       Mapped[str]       = mapped_column(String(16))
    started_at: Mapped[datetime]  = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime]  = mapped_column(DateTime(timezone=True))
    status:     Mapped[str]       = mapped_column(String(16), default="active")  # active | expired | cancelled

    __table_args__ = (
        Index("ix_subs_user_expires_desc", "user_id", expires_at.desc()),
    )


class Payment(Base):
    __tablename__ = "payments"

    id:         Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id:    Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    amount_pkr: Mapped[int]       = mapped_column(Integer)
    method:     Mapped[str]       = mapped_column(String(16))    # jazzcash | easypaisa | bank | card
    txn_ref:    Mapped[str]       = mapped_column(String(128), unique=True)
    status:     Mapped[str]       = mapped_column(String(16), default="pending")
    paid_at:    Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


# ═══════════════════════════════════════════════════════════════════
#   E.  ALERTS  +  WATCHLISTS
# ═══════════════════════════════════════════════════════════════════


class Watchlist(Base):
    __tablename__ = "watchlists"

    user_id:  Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    symbol:   Mapped[str]       = mapped_column(String(20), ForeignKey("stocks.symbol"), primary_key=True)
    added_at: Mapped[datetime]  = mapped_column(DateTime(timezone=True), server_default=func.now())


class Alert(Base):
    __tablename__ = "alerts"

    id:            Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id:       Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    symbol:        Mapped[str]       = mapped_column(String(20), ForeignKey("stocks.symbol"))
    condition:     Mapped[str]       = mapped_column(String(32))  # entry_zone | stop_loss | target | price_above | price_below
    params:        Mapped[dict]      = mapped_column(JSONB, default=dict)
    active:        Mapped[bool]      = mapped_column(Boolean, default=True)
    last_fired_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at:    Mapped[datetime]  = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_alerts_active_symbol", "active", "symbol"),
        Index("ix_alerts_user", "user_id"),
    )


class AlertDelivery(Base):
    __tablename__ = "alert_deliveries"

    id:        Mapped[int]      = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    alert_id:  Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("alerts.id", ondelete="CASCADE"))
    fired_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    channel:   Mapped[str]      = mapped_column(String(16))    # push | whatsapp | email
    status:    Mapped[str]      = mapped_column(String(16), default="sent")


class UserPortfolio(Base):
    __tablename__ = "user_portfolios"

    user_id:               Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    capital_pkr:           Mapped[Optional[int]]   = mapped_column(BigInteger)
    risk_per_trade_pct:    Mapped[Optional[float]] = mapped_column(Numeric(4, 2))
    default_stop_loss_pct: Mapped[Optional[float]] = mapped_column(Numeric(4, 2))
    preferences:           Mapped[dict]      = mapped_column(JSONB, default=dict)
    updated_at:            Mapped[datetime]  = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
