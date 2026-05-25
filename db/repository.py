"""Dual-write repository — all DB writes go through this module.

Every function is **idempotent** (upsert / dedupe-on-key) and wrapped by the
caller in try/except so a Postgres outage never breaks the JSON-based path.

Shapes accepted here match what the scrapers and agents currently produce —
no transformation needed at the call site.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import date as _date, datetime, timezone
from typing import Any, Iterable

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError

from db.session import SessionLocal
from db.models import (
    AlertDelivery,
    IndexSnapshot,
    NccplSignal,
    NewsArticle,
    NewsBriefing,
    NewsStory,
    Pick,
    PickOutcome,
    PipelineRun,
    Stock,
    StockPrice,
    TradingReport,
)

logger = logging.getLogger(__name__)


# ─── helpers ─────────────────────────────────────────────────────

def _pf(v) -> float | None:
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "").replace("%", "").strip())
    except (ValueError, TypeError):
        return None


def _pi(v) -> int | None:
    f = _pf(v)
    return int(f) if f is not None else None


def _parse_date(s: str) -> _date | None:
    """Accept 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS' — return date."""
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _hash(*parts: str) -> str:
    h = hashlib.sha1()
    for p in parts:
        h.update(str(p or "").encode("utf-8"))
    return h.hexdigest()[:32]


def _shariah_listed(listed_in: str) -> tuple[bool, list[str]]:
    """Return (is_shariah, listed_in_array)."""
    items = [x.strip() for x in (listed_in or "").split(",") if x.strip()]
    shariah = any(x in ("KMI30", "KMIALLSHR") for x in items)
    return shariah, items


# ═══════════════════════════════════════════════════════════════════
#   A.  MARKET DATA  (called by scrapers/fetch_and_save.py)
# ═══════════════════════════════════════════════════════════════════


def upsert_stocks_from_psx(all_stocks: Iterable[dict]) -> int:
    """Upsert one row per symbol in `stocks`. Returns count touched."""
    rows = []
    for s in all_stocks:
        sym = (s.get("SYMBOL") or "").strip()
        if not sym:
            continue
        shariah, listed = _shariah_listed(s.get("LISTED IN", ""))
        rows.append({
            "symbol":    sym,
            "company":   s.get("COMPANY NAME") or s.get("COMPANY") or "",
            "sector":    s.get("SECTOR") or "",
            "listed_in": listed,
            "shariah":   shariah,
        })
    if not rows:
        return 0

    with SessionLocal() as session:
        stmt = pg_insert(Stock).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["symbol"],
            set_={
                "company":   stmt.excluded.company,
                "sector":    stmt.excluded.sector,
                "listed_in": stmt.excluded.listed_in,
                "shariah":   stmt.excluded.shariah,
            },
        )
        session.execute(stmt)
        session.commit()
    return len(rows)


def upsert_stock_prices(all_stocks: Iterable[dict], on: _date | None = None) -> int:
    """Insert today's OHLCV row per stock (replaces any existing row for the day)."""
    day = on or _date.today()
    rows = []
    for s in all_stocks:
        sym = (s.get("SYMBOL") or "").strip()
        if not sym:
            continue
        close = _pf(s.get("CURRENT") or s.get("LDCP"))
        if not close:
            continue
        rows.append({
            "symbol":     sym,
            "ts":         day,
            "open":       _pf(s.get("LDCP")) or close,
            "high":       _pf(s.get("HIGH")) or close,
            "low":        _pf(s.get("LOW"))  or close,
            "close":      close,
            "ldcp":       _pf(s.get("LDCP")),
            "volume":     _pi(s.get("VOLUME")),
            "change_pct": _pf(s.get("CHANGE (%)")),
        })
    if not rows:
        return 0

    with SessionLocal() as session:
        stmt = pg_insert(StockPrice).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["symbol", "ts"],
            set_={
                "open":       stmt.excluded.open,
                "high":       stmt.excluded.high,
                "low":        stmt.excluded.low,
                "close":      stmt.excluded.close,
                "ldcp":       stmt.excluded.ldcp,
                "volume":     stmt.excluded.volume,
                "change_pct": stmt.excluded.change_pct,
            },
        )
        session.execute(stmt)
        session.commit()
    return len(rows)


def upsert_index_snapshots(indices_live: dict, on: _date | None = None) -> int:
    """`indices_live` is the dict-of-dicts shape from fetch_psx_portal."""
    day = on or _date.today()
    rows = []
    for name, idx in (indices_live or {}).items():
        if not name:
            continue
        rows.append({
            "index_name": name[:32],
            "ts":         day,
            "level":      _pf(idx.get("level")),
            "change_pct": _pf(idx.get("change_pct")),
        })
    if not rows:
        return 0

    with SessionLocal() as session:
        stmt = pg_insert(IndexSnapshot).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["index_name", "ts"],
            set_={"level": stmt.excluded.level, "change_pct": stmt.excluded.change_pct},
        )
        session.execute(stmt)
        session.commit()
    return len(rows)


def upsert_news_articles(articles: Iterable[dict], source_label: str) -> int:
    """Dedupe by url_hash (sha1 of title+url+source). Accepts a flat list of dicts
    with keys: title, summary, link/url, published/date, sectors?, companies?
    """
    rows = []
    for a in articles or []:
        title = (a.get("title") or "").strip()
        if not title:
            continue
        url = a.get("link") or a.get("url") or ""
        url_hash = _hash(title, url, source_label)
        published_at = None
        for k in ("published", "date", "pub_date"):
            v = a.get(k)
            if v:
                try:
                    from email.utils import parsedate_to_datetime
                    published_at = parsedate_to_datetime(v)
                except Exception:
                    try:
                        published_at = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
                    except Exception:
                        published_at = None
                if published_at:
                    if published_at.tzinfo is None:
                        published_at = published_at.replace(tzinfo=timezone.utc)
                    break

        rows.append({
            "source":       source_label[:64],
            "title":        title,
            "summary":      (a.get("summary") or "")[:2000],
            "url":          url,
            "published_at": published_at,
            "sectors":      a.get("sectors")   or [],
            "companies":    a.get("companies") or [],
            "url_hash":     url_hash,
        })
    if not rows:
        return 0

    with SessionLocal() as session:
        stmt = pg_insert(NewsArticle).values(rows)
        # On duplicate url_hash — leave the original. (Avoids overwriting older
        # published_at metadata with re-scraped versions.)
        stmt = stmt.on_conflict_do_nothing(index_elements=["url_hash"])
        session.execute(stmt)
        session.commit()
    return len(rows)


# ═══════════════════════════════════════════════════════════════════
#   B.  NCCPL  (called by scrapers/fetch_and_save.py after nccpl scrape)
# ═══════════════════════════════════════════════════════════════════


def save_nccpl_signals(insider: dict, fipi: dict) -> int:
    """Flatten the insider + FIPI signal sets into nccpl_signals rows.
    Idempotent — dedupes on (source, doc_id) where doc_id is hashed.
    """
    now = datetime.now(timezone.utc)
    rows: list[dict] = []

    def _emit(items: list[dict] | None, source: str, direction: str):
        for it in items or []:
            sym = (it.get("symbol") or "").strip().upper()
            if not sym:
                continue
            summary = (it.get("summary") or "")[:500]
            strength = (it.get("signal_strength") or "MEDIUM")[:16]
            doc_id = _hash(source, direction, sym, summary, now.strftime("%Y-%m-%d"))
            rows.append({
                "symbol":    sym,
                "source":    source,
                "direction": direction,
                "strength":  strength,
                "summary":   summary,
                "filed_at":  now,
                "doc_id":    doc_id,
            })

    _emit(insider.get("buy_signals")      if insider else None, "insider", "BUY")
    _emit(insider.get("sell_signals")     if insider else None, "insider", "SELL")
    _emit(insider.get("activity_signals") if insider else None, "insider", "ACTIVITY")
    _emit(fipi.get("foreign_buying")      if fipi    else None, "fipi",    "BUY")
    _emit(fipi.get("foreign_selling")     if fipi    else None, "fipi",    "SELL")

    if not rows:
        return 0

    with SessionLocal() as session:
        stmt = pg_insert(NccplSignal).values(rows)
        stmt = stmt.on_conflict_do_nothing(index_elements=["source", "doc_id"])
        session.execute(stmt)
        session.commit()
    return len(rows)


# ═══════════════════════════════════════════════════════════════════
#   C.  AI OUTPUTS  (called by news_agent / trading_agent / crew)
# ═══════════════════════════════════════════════════════════════════


def save_pipeline_run(mode: str, tokens_used: int = 0, status: str = "ok",
                      error: str | None = None) -> uuid.UUID:
    """Create a pipeline_runs row, return its UUID."""
    run = PipelineRun(
        id=uuid.uuid4(),
        mode=mode[:16],
        tokens_used=tokens_used or 0,
        status=status[:16],
        error=error,
    )
    with SessionLocal() as session:
        session.add(run)
        session.commit()
        return run.id


def save_news_briefing(run_id: uuid.UUID, briefing: dict) -> uuid.UUID:
    """Persist a NewsBriefing dict (the legacy shape with top_stories/macro_factors/etc.).
    Returns the new briefing UUID.
    """
    nb = NewsBriefing(
        id=uuid.uuid4(),
        pipeline_run_id=run_id,
        briefing_date=_parse_date(briefing.get("briefing_date") or "") or _date.today(),
        overall_sentiment=(briefing.get("overall_sentiment") or "NEUTRAL")[:16],
        sentiment_reasoning=briefing.get("sentiment_reasoning") or "",
        macro_factors=briefing.get("macro_factors") or {},
        shariah_market_note=briefing.get("shariah_market_note") or "",
        key_risks=briefing.get("key_risks") or [],
        key_opportunities=briefing.get("key_opportunities") or [],
    )
    stories = []
    for s in briefing.get("top_stories") or []:
        stories.append(NewsStory(
            briefing_id=nb.id,
            headline=(s.get("headline") or "")[:500],
            source=(s.get("source") or "")[:64],
            impact=(s.get("impact") or "NEUTRAL")[:16],
            impact_score=_pi(s.get("impact_score")),
            reasoning_chain=s.get("reasoning_chain") or [],
            what=s.get("what"),
            why_it_matters=s.get("why_it_matters"),
            second_order=s.get("second_order_effect") or s.get("second_order"),
            shariah_lens=s.get("shariah_lens"),
            trader_action=s.get("trader_action"),
            sectors=s.get("sectors_affected") or s.get("sectors") or [],
            companies=s.get("companies_mentioned") or s.get("companies") or [],
        ))
    with SessionLocal() as session:
        session.add(nb)
        for st in stories:
            session.add(st)
        session.commit()
        return nb.id


def save_trading_report_with_picks(run_id: uuid.UUID, report: dict) -> uuid.UUID:
    """Persist the full TradingReport + every BUY / AVOID pick in both portfolios."""
    overview = report.get("market_overview") or {}
    tr = TradingReport(
        id=uuid.uuid4(),
        pipeline_run_id=run_id,
        report_date=_parse_date(report.get("report_date") or "") or _date.today(),
        session_bias=(overview.get("session_bias") or "")[:16],
        kse100_level=(overview.get("kse100_level") or "")[:32],
        kse100_change_pct=(overview.get("kse100_change_pct") or "")[:16],
        kmi30_level=(overview.get("kmi30_level") or "")[:32],
        market_breadth=(overview.get("market_breadth") or "")[:64],
        summary=overview.get("summary") or "",
        macro_watch=report.get("macro_watch") or "",
        disclaimer=report.get("disclaimer") or "",
    )
    picks: list[Pick] = []

    def _emit(portfolio: str, call_type: str, items: list[dict] | None):
        for p in items or []:
            sym = (p.get("symbol") or "").strip().upper()
            if not sym:
                continue
            picks.append(Pick(
                report_id=tr.id,
                portfolio=portfolio,
                call_type=call_type,
                rank=_pi(p.get("rank")) or 0,
                symbol=sym,
                sector=(p.get("sector") or "")[:64],
                shariah_compliant=bool(p.get("shariah_compliant", False)),
                kmi_index=(p.get("kmi_index") or "")[:16],
                current_price=(str(p.get("current_price") or ""))[:32],
                entry_range=(p.get("entry_range") or "")[:64],
                target_price=(str(p.get("target_price") or ""))[:32],
                stop_loss=(str(p.get("stop_loss") or ""))[:32],
                upside_pct=(p.get("upside_pct") or "")[:16],
                holding_period=(p.get("holding_period") or "")[:32],
                volume_today=(str(p.get("volume_today") or ""))[:32],
                volume_signal=(p.get("volume_signal") or "")[:32],
                confidence=(p.get("confidence") or "")[:16],
                news_catalyst=p.get("news_catalyst"),
                price_volume_reason=p.get("price_volume_reason"),
                second_order_play=p.get("second_order_play"),
                reasoning_chain=p.get("reasoning_chain") or [],
                risk=p.get("risk"),
                reason=p.get("reason"),
                risk_if_held=p.get("risk_if_held"),
            ))

    conv = report.get("conventional_portfolio") or {}
    shar = report.get("shariah_portfolio") or {}
    _emit("conventional", "BUY",   conv.get("buy_picks"))
    _emit("conventional", "AVOID", conv.get("avoid_picks"))
    _emit("shariah",      "BUY",   shar.get("buy_picks"))
    _emit("shariah",      "AVOID", shar.get("avoid_picks"))

    with SessionLocal() as session:
        session.add(tr)
        for pk in picks:
            session.add(pk)
        session.commit()
        return tr.id


def update_pick_outcomes(psx_data: dict) -> int:
    """For every pick that doesn't yet have an outcome row, record actual change%
    from today's PSX data. Returns rows touched.

    Called once per day after the next session closes.
    """
    price_map = {
        (s.get("SYMBOL") or "").upper(): _pf(s.get("CHANGE (%)"))
        for s in psx_data.get("all_stocks", [])
    }
    today = _date.today()
    touched = 0

    with SessionLocal() as session:
        # Find picks lacking an outcome row.
        stmt = (
            select(Pick.id, Pick.symbol, Pick.call_type, Pick.report_id)
            .outerjoin(PickOutcome, PickOutcome.pick_id == Pick.id)
            .where(PickOutcome.pick_id.is_(None))
        )
        outcomes: list[PickOutcome] = []
        for pick_id, sym, call_type, _report_id in session.execute(stmt).all():
            chg = price_map.get((sym or "").upper())
            if chg is None:
                continue
            if call_type == "BUY":
                result = "CORRECT" if chg >= 1.5 else ("WRONG" if chg < -1.5 else "NEUTRAL")
            else:  # AVOID
                result = "CORRECT" if chg <= -1.5 else ("WRONG" if chg > 1.5 else "NEUTRAL")
            outcomes.append(PickOutcome(
                pick_id=pick_id,
                evaluated_on=today,
                actual_change_pct=chg,
                result=result,
                hit_target=False,
                hit_stop_loss=False,
            ))
            touched += 1
        for o in outcomes:
            session.add(o)
        session.commit()
    return touched


# ─── Convenience wrapper used by callers ──────────────────────────

def safe(fn, *args, **kwargs):
    """Run a repository call, swallow DB errors with a log line.
    Use this from caller code so a Postgres outage NEVER breaks the JSON path.
    """
    try:
        return fn(*args, **kwargs)
    except SQLAlchemyError as e:
        logger.warning("DB write failed in %s: %s", fn.__name__, e)
    except Exception as e:
        logger.warning("Unexpected error in %s: %s", fn.__name__, e)
    return None
