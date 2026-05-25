"""
trading_agent.py  —  Agent 2: Trading Analyst
-----------------------------------------------
Takes the deep news briefing from Agent 1 and live PSX stock data,
then produces two complete portfolios:

  CONVENTIONAL PORTFOLIO  — any KSE-100 / KSE-100PR stock
  SHARIAH PORTFOLIO       — only KMI-30 / KMIALLSHR stocks

Each portfolio gets:
  - 10 stocks to BUY  (entry, target, stop-loss, reason)
  - 10 stocks to AVOID (reason, risk)

Shariah compliance is derived from the PSX LISTED IN field:
  Stock is Shariah-compliant if LISTED IN contains "KMI30" or "KMIALLSHR"
"""

import os
import json
import logging
from datetime import datetime, timedelta
from openai import OpenAI
from dotenv import load_dotenv
from scrapers import price_history as ph

# Dual-write to Postgres alongside the JSON-based history.
try:
    from db.repository import (
        save_pipeline_run,
        save_news_briefing,
        save_trading_report_with_picks,
        update_pick_outcomes,
        safe,
    )
    _DB_ENABLED = True
except Exception:
    _DB_ENABLED = False
    def safe(fn, *a, **k): pass  # noqa

load_dotenv()
logger        = logging.getLogger(__name__)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR      = os.path.join(_PROJECT_ROOT, "backend", "data")
HISTORY_FILE  = os.path.join(DATA_DIR, "trading_history.json")
LEARNING_DAYS = 7

INSIDER_FILE  = os.path.join(DATA_DIR, "06_nccpl_insider.json")
FIPI_FILE     = os.path.join(DATA_DIR, "07_nccpl_fipi.json")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ── SYSTEM PROMPT ────────────────────────────────────────────────

SYSTEM_PROMPT = """
You are a senior PSX (Pakistan Stock Exchange) proprietary trader with 15+
years of experience. You manage two portfolios simultaneously:
  1. CONVENTIONAL portfolio — any KSE-100 or KSE-100PR stock
  2. SHARIAH portfolio      — only KMI-30 or KMIALLSHR tagged stocks

You receive:
  A) A deeply-reasoned news briefing with story-by-story analysis
  B) Live stock data tagged with index membership and Shariah status

Your reasoning process for picking stocks:
  1. Check Section I (Sector Snapshot) first — identify which sectors have momentum today.
  2. Read the news catalyst. Which sector does it benefit or hurt? Cross-reference with Section I.
  3. Look at individual stocks in that sector — check TECH signals in stock rows:
       - GOLDEN_CROSS or ABOVE_SMA20 + UPTREND = technically strong setup
       - VOLX ≥ 2.0x (HIGH_SPIKE/VERY_HIGH_SPIKE) = institutional interest / breakout confirmation
       - RSI OVERSOLD (< 30) + positive news = mean-reversion buy opportunity
       - RSI OVERBOUGHT (> 70) = caution on new entries, prefer as AVOID candidate
       - DEATH_CROSS or BELOW_SMA20 + DOWNTREND = avoid unless very strong news
  4. For Shariah portfolio: is the stock in KMI30 or KMIALLSHR?
  5. Check price action: is it breaking out (near 52w high), pulling back to support, or in freefall?
  6. Use Section G (your past accuracy) to calibrate confidence — if HIGH confidence has underperformed, be more selective.
  7. Set realistic targets (5-15% upside) and stop-losses (5-8% below entry)

PSX-specific rules you always follow:
  - Circuit breaker: ±7.5% per session. Targets beyond that need multiple sessions.
  - T+2 settlement. Don't recommend illiquid stocks with tiny volumes.
  - Shariah stocks: NEVER recommend conventional banks, tobacco, interest-based
    insurance or leasing companies in the Shariah portfolio
  - A stock moving on extremely high volume with positive news = strongest buy signal
  - Avoid stocks already up >5% today unless momentum is exceptional

NCCPL signal rules (Section H in your data):
  - Insider BUY (VERY_HIGH/HIGH strength) = very strong bullish catalyst; prioritise
    in BUY picks and reference it in news_catalyst field
  - Insider SELL (VERY_HIGH/HIGH) = very strong bearish signal; include in AVOID
    and note "Insider selling pressure" in reason field
  - Foreign NET BUY (FIPI, VERY_HIGH/HIGH) = institutional accumulation; adds HIGH
    confidence to BUY picks for that stock
  - Foreign NET SELL (FIPI, VERY_HIGH/HIGH) = institutional exit; flag in AVOID list
  - When both insider BUY and foreign buying align on one stock = exceptional signal,
    mark confidence HIGH and note dual confirmation
  - NCCPL signals override weak news catalysts — a director buying Rs 10M of shares
    is more reliable than a vague news story

Respond ONLY with valid JSON matching this exact schema — no markdown, no extra text:

{
  "report_date": "YYYY-MM-DD",

  "market_overview": {
    "kse100_level": "...",
    "kse100_change_pct": "...",
    "kse100pr_level": "...",
    "kmi30_level": "...",
    "market_breadth": "X advancing, Y declining out of Z",
    "session_bias": "BULLISH | BEARISH | NEUTRAL | CAUTIOUS",
    "summary": "3-4 sentence overview connecting news to price action"
  },

  "conventional_portfolio": {
    "note": "Based on KSE-100 and KSE-100PR stocks — includes all sectors",
    "buy_picks": [
      {
        "rank": 1,
        "symbol": "TICKER",
        "company": "Full name",
        "sector": "sector",
        "shariah_compliant": true or false,
        "current_price": "00.00",
        "entry_range": "low-high",
        "target_price": "00.00",
        "stop_loss": "00.00",
        "upside_pct": "X%",
        "holding_period": "intraday | 1-3 days | 1 week | 2+ weeks",
        "volume_today": "...",
        "volume_signal": "very high | high | average | low",
        "confidence": "HIGH | MEDIUM | LOW",
        "news_catalyst": "exact news story driving this — must reference Agent 1 briefing",
        "price_volume_reason": "what the price and volume data specifically show",
        "second_order_play": "any indirect benefit beyond the obvious catalyst",
        "risk": "main risk for this trade"
      }
    ],
    "avoid_picks": [
      {
        "rank": 1,
        "symbol": "TICKER",
        "company": "Full name",
        "sector": "sector",
        "shariah_compliant": true or false,
        "current_price": "00.00",
        "reason": "specific news + price/volume reason to avoid",
        "risk_if_held": "what specifically could go wrong"
      }
    ]
  },

  "shariah_portfolio": {
    "note": "Only KMI-30 / KMIALLSHR stocks — excludes conventional banks, tobacco, interest-based entities",
    "buy_picks": [
      {
        "rank": 1,
        "symbol": "TICKER",
        "company": "Full name",
        "sector": "sector",
        "kmi_index": "KMI30 | KMIALLSHR",
        "current_price": "00.00",
        "entry_range": "low-high",
        "target_price": "00.00",
        "stop_loss": "00.00",
        "upside_pct": "X%",
        "holding_period": "intraday | 1-3 days | 1 week | 2+ weeks",
        "volume_today": "...",
        "volume_signal": "very high | high | average | low",
        "confidence": "HIGH | MEDIUM | LOW",
        "news_catalyst": "specific news catalyst",
        "price_volume_reason": "price and volume observation",
        "risk": "main risk"
      }
    ],
    "avoid_picks": [
      {
        "rank": 1,
        "symbol": "TICKER",
        "company": "Full name",
        "sector": "sector",
        "kmi_index": "KMI30 | KMIALLSHR",
        "current_price": "00.00",
        "reason": "specific reason to avoid",
        "risk_if_held": "what could go wrong"
      }
    ]
  },

  "sector_rotation": {
    "buy_sectors":  [{"sector": "...", "shariah_compliant": true/false, "reason": "..."}],
    "avoid_sectors":[{"sector": "...", "shariah_compliant": true/false, "reason": "..."}]
  },

  "macro_watch": "Key macro factors to monitor today and their direct stock implications",
  "disclaimer": "For educational purposes only. Not financial advice. Consult a licensed advisor."
}
"""

# ── SHARIAH TAGGER ───────────────────────────────────────────────

def tag_shariah(stock: dict) -> bool:
    """A stock is Shariah-compliant if listed in KMI30 or KMIALLSHR."""
    listed = stock.get("LISTED IN", "")
    return "KMI30" in listed or "KMIALLSHR" in listed


# ── HISTORY / LEARNING ───────────────────────────────────────────

def load_history() -> list:
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_to_history(report: dict):
    history = load_history()
    history.append(report)
    history = history[-90:]
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    logger.info(f"Trading history saved ({len(history)} entries)")


def update_outcomes(psx_data: dict):
    """Record actual next-session price changes against past calls."""
    history = load_history()
    if not history:
        return

    price_map = {
        s.get("SYMBOL", ""): s.get("CHANGE (%)", "N/A")
        for s in psx_data.get("all_stocks", [])
    }

    today   = datetime.now().strftime("%Y-%m-%d")
    changed = False

    for entry in history:
        if entry.get("report_date") == today or entry.get("outcomes_recorded"):
            continue

        outcomes = []
        for portfolio in ["conventional_portfolio", "shariah_portfolio"]:
            for call_type, call_list in [
                ("BUY",   entry.get(portfolio, {}).get("buy_picks", [])),
                ("AVOID", entry.get(portfolio, {}).get("avoid_picks", [])),
            ]:
                for pick in call_list:
                    sym    = pick.get("symbol", "")
                    chg    = price_map.get(sym, "N/A")
                    result = "UNKNOWN"
                    try:
                        v = float(chg.replace("%","").replace(",",""))
                        if call_type == "BUY":
                            result = "CORRECT" if v >= 1.5 else ("WRONG" if v < -1.5 else "NEUTRAL")
                        else:
                            result = "CORRECT" if v <= -1.5 else ("WRONG" if v > 1.5 else "NEUTRAL")
                    except Exception:
                        pass
                    outcomes.append({
                        "portfolio": portfolio,
                        "call": call_type,
                        "symbol": sym,
                        "actual_change": chg,
                        "result": result,
                    })

        entry["outcomes"]          = outcomes
        entry["outcomes_recorded"] = True
        changed = True

    if changed:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        logger.info("Outcomes updated in trading history")


def _build_learning_context(history: list) -> str:
    recorded = [h for h in history if h.get("outcomes_recorded")]
    recent   = recorded[-LEARNING_DAYS:]

    if not recent:
        return "=== PAST RECORD: No outcomes recorded yet. ==="

    lines = ["=== YOUR PAST TRADE CALL ACCURACY (last 7 sessions) ==="]
    for entry in recent:
        outcomes = entry.get("outcomes", [])
        correct  = sum(1 for o in outcomes if o.get("result") == "CORRECT")
        lines.append(f"\n{entry.get('report_date')}  ({correct}/{len(outcomes)} correct)")
        for o in outcomes:
            lines.append(
                f"  [{o['portfolio'][:4]}] {o['call']:5s} {o['symbol']:8s} "
                f"actual: {o['actual_change']:>8s}  -> {o['result']}"
            )

    # ── Sector win-rate (last 30 days) ──────────────────────────────
    sector_stats  = {}   # sector → [correct, total]
    conf_stats    = {"HIGH": [0, 0], "MEDIUM": [0, 0], "LOW": [0, 0]}

    for entry in recorded[-30:]:
        outcome_map = {o["symbol"]: o.get("result", "UNKNOWN") for o in entry.get("outcomes", [])}
        for portfolio in ["conventional_portfolio", "shariah_portfolio"]:
            for pick in entry.get(portfolio, {}).get("buy_picks", []):
                sym    = pick.get("symbol", "")
                sector = pick.get("sector", "Unknown")
                conf   = pick.get("confidence", "MEDIUM")
                result = outcome_map.get(sym, "UNKNOWN")

                bucket = sector_stats.setdefault(sector, [0, 0])
                bucket[1] += 1
                if conf in conf_stats:
                    conf_stats[conf][1] += 1
                if result == "CORRECT":
                    bucket[0] += 1
                    if conf in conf_stats:
                        conf_stats[conf][0] += 1

    qualifying = [(sec, c, t) for sec, (c, t) in sector_stats.items() if t >= 3]
    if qualifying:
        qualifying.sort(key=lambda x: x[1] / x[2], reverse=True)
        lines.append("\n=== SECTOR WIN-RATE — BUY calls, last 30 days (sectors with ≥3 calls) ===")
        for sec, correct, total in qualifying[:12]:
            pct = round(correct / total * 100)
            bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
            lines.append(f"  {sec[:26]:26s} {bar} {pct:3d}%  ({correct}/{total})")

    # ── Confidence calibration ───────────────────────────────────────
    conf_rows = [(c, v[0], v[1]) for c, v in conf_stats.items() if v[1] >= 3]
    if conf_rows:
        lines.append("\n=== CONFIDENCE CALIBRATION ===")
        for conf, correct, total in conf_rows:
            pct = round(correct / total * 100)
            lines.append(f"  {conf:6s}: {pct:3d}% hit rate ({correct}/{total})")
            if conf == "HIGH" and pct < 55:
                lines.append("  ⚠️  HIGH confidence underperforming — raise your bar today.")
            elif conf == "LOW" and pct > 65:
                lines.append("  ℹ️  LOW confidence outperforming — don't dismiss weak signals.")

    lines.append("\nUse this to calibrate your confidence levels today.")
    return "\n".join(lines)


# ── NCCPL DATA LOADERS ───────────────────────────────────────────

def load_nccpl_insider() -> dict:
    if not os.path.exists(INSIDER_FILE):
        return {"buy_signals": [], "sell_signals": [], "by_symbol": {}, "error": "File not found"}
    try:
        with open(INSIDER_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"buy_signals": [], "sell_signals": [], "by_symbol": {}, "error": "Parse error"}


def load_nccpl_fipi() -> dict:
    if not os.path.exists(FIPI_FILE):
        return {"foreign_buying": [], "foreign_selling": [], "by_symbol": {}, "error": "File not found"}
    try:
        with open(FIPI_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"foreign_buying": [], "foreign_selling": [], "by_symbol": {}, "error": "Parse error"}


def _build_nccpl_prompt(insider: dict, fipi: dict) -> str:
    """Build Section H: NCCPL signals for the trading prompt."""
    lines = []
    lines.append("=" * 65)
    lines.append("SECTION H — NCCPL SIGNALS (Insider + Foreign Investor Flows)")
    lines.append("These are the highest-conviction signals available. Use them.")
    lines.append("=" * 65)

    # Insider transactions
    buy_sigs  = insider.get("buy_signals",  [])
    sell_sigs = insider.get("sell_signals", [])
    insider_err = insider.get("error")

    lines.append("\n--- INSIDER TRANSACTIONS (last 7 days) ---")
    if insider_err:
        lines.append(f"[UNAVAILABLE: {insider_err}]")
    elif not buy_sigs and not sell_sigs:
        lines.append("[No insider transactions recorded this week]")
    else:
        if buy_sigs:
            lines.append("INSIDER BUYING (BULLISH — directors declared a BUY):")
            for s in buy_sigs:
                lines.append(f"  BUY  [{s['signal_strength']:9s}] {s['symbol']:8s}  {s['summary']}")
        if sell_sigs:
            lines.append("INSIDER SELLING (BEARISH — directors declared a SELL):")
            for s in sell_sigs:
                lines.append(f"  SELL [{s['signal_strength']:9s}] {s['symbol']:8s}  {s['summary']}")
        activity = insider.get("activity_signals", [])
        if activity:
            lines.append("INSIDER ACTIVITY DETECTED (direction unknown — watch these stocks):")
            for s in activity:
                lines.append(f"  ACT  [{s['signal_strength']:9s}] {s['symbol']:8s}  {s['summary']}")

    # FIPI/LIPI
    fb = fipi.get("foreign_buying",  [])
    fs = fipi.get("foreign_selling", [])
    fipi_err = fipi.get("error")

    lines.append("\n--- FIPI/LIPI (Foreign Investor Portfolio Flows — today) ---")
    if fipi_err:
        lines.append(f"[UNAVAILABLE: {fipi_err}]")
    elif not fb and not fs:
        lines.append("[No FIPI/LIPI data available]")
    else:
        if fb:
            lines.append("FOREIGN NET BUYING (institutional accumulation — bullish):")
            for s in fb[:15]:
                lines.append(
                    f"  {s['symbol']:8s} [{s['signal_strength']:9s}] {s['summary']}"
                )
        if fs:
            lines.append("FOREIGN NET SELLING (institutional exit — bearish):")
            for s in fs[:15]:
                lines.append(
                    f"  {s['symbol']:8s} [{s['signal_strength']:9s}] {s['summary']}"
                )

    lines.append("")
    lines.append(
        "INSTRUCTION: Stocks with VERY_HIGH or HIGH insider BUY signals should appear\n"
        "in your BUY picks with news_catalyst noting the insider activity. Stocks with\n"
        "strong SELL signals or strong foreign selling must appear in AVOID picks."
    )
    lines.append("")
    return "\n".join(lines)


# ── PSX DATA + STOCK PREP ────────────────────────────────────────

def load_psx_data() -> dict:
    path = os.path.join(DATA_DIR, "04_psx_data_portal.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"{path} not found — run fetch_and_save.py first")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def prepare_stocks(psx_data: dict) -> dict:
    """
    Returns tagged stock sets ready for the prompt:
      kse100       — 100 stocks, Shariah tagged + technical signals
      kse100pr     — 100 stocks, Shariah tagged + technical signals
      kmi30        — 30 Shariah-compliant stocks
      kmi_allshr   — all Shariah stocks (broader universe)
    """
    by_index  = psx_data.get("by_index", {})
    all_stocks = psx_data.get("all_stocks", [])

    # Build symbol → stock map for quick lookup
    stock_map = {s.get("SYMBOL", ""): s for s in all_stocks}

    # Load pre-computed technical signals (graceful if history file absent)
    try:
        signals = ph.get_all_signals()
    except Exception:
        signals = {}

    def enrich(symbols: list) -> list:
        enriched = []
        for sym in symbols:
            s = stock_map.get(sym)
            if not s:
                continue
            s = dict(s)
            s["SHARIAH"]  = "YES" if tag_shariah(s) else "NO"
            s["_signals"] = signals.get(sym, {})
            enriched.append(s)
        return enriched

    kse100_syms   = [s.get("SYMBOL","") for s in by_index.get("KSE100", [])]
    kse100pr_syms = [s.get("SYMBOL","") for s in by_index.get("KSE100PR", [])]
    kmi30_syms    = [s.get("SYMBOL","") for s in by_index.get("KMI30", [])]
    kmi_all_syms  = [s.get("SYMBOL","") for s in by_index.get("KMIALLSHR", [])]

    def vol_sort(stocks_list):
        def vol_key(s):
            try: return int(s.get("VOLUME","0").replace(",",""))
            except: return 0
        return sorted(stocks_list, key=vol_key, reverse=True)

    return {
        "kse100":     vol_sort(enrich(kse100_syms)),
        "kse100pr":   vol_sort(enrich(kse100pr_syms)),
        "kmi30":      vol_sort(enrich(kmi30_syms)),
        "kmi_allshr": vol_sort(enrich(kmi_all_syms))[:50],
    }


# ── PROMPT BUILDER ───────────────────────────────────────────────

def _stock_row(s: dict) -> str:
    sig = s.get("_signals", {})
    shariah_tag = f"[SHARIAH:{s.get('SHARIAH','?')}]"

    rsi       = sig.get("rsi14")
    vol_ratio = sig.get("vol_ratio")
    sma_sig   = sig.get("sma_signal", "")
    trend     = sig.get("trend", "")
    rsi_lbl   = sig.get("rsi_label", "")
    vol_lbl   = sig.get("vol_label", "")
    days      = sig.get("days_of_data", 0)

    rsi_str  = f"RSI:{rsi:.0f}({rsi_lbl})" if rsi is not None else "RSI:--"
    volx_str = f"VOLX:{vol_ratio:.1f}x({vol_lbl})" if vol_ratio is not None else "VOLX:--"
    tech_str = f"{rsi_str}|{volx_str}|SMA:{sma_sig}|{trend}|{days}d" if days > 0 else "NO_HISTORY"

    return (
        f"{s.get('SYMBOL',''):8s} {shariah_tag} | "
        f"LDCP:{s.get('LDCP',''):>8s} | "
        f"CUR:{s.get('CURRENT',''):>8s} | "
        f"CHG%:{s.get('CHANGE (%)','').strip():>7s} | "
        f"VOL:{s.get('VOLUME',''):>13s} | "
        f"H:{s.get('HIGH',''):>8s} L:{s.get('LOW',''):>8s} | "
        f"TECH:[{tech_str}] | "
        f"IDX:{s.get('LISTED IN','')[:40]}"
    )


def _build_sector_snapshot(psx_data: dict) -> str:
    """Section I: sector-level momentum aggregated from all stocks."""
    by_sector = psx_data.get("by_sector", {})
    if not by_sector:
        return ""

    sector_stats = []
    for sector, stocks in by_sector.items():
        adv = dec = 0
        changes, total_vol = [], 0
        for s in stocks:
            try:
                chg = float(str(s.get("CHANGE (%)","0")).replace("%","").replace(",","").strip() or "0")
                vol = int(str(s.get("VOLUME","0")).replace(",","").strip() or "0")
                changes.append(chg)
                total_vol += vol
                if chg > 0: adv += 1
                elif chg < 0: dec += 1
            except Exception:
                pass
        if not changes:
            continue
        avg_chg = round(sum(changes) / len(changes), 2)
        sector_stats.append({
            "sector": sector, "n": len(stocks),
            "adv": adv, "dec": dec,
            "avg_chg": avg_chg, "total_vol": total_vol,
        })

    sector_stats.sort(key=lambda x: x["avg_chg"], reverse=True)

    lines = ["=" * 65,
             "SECTION I — SECTOR MOMENTUM SNAPSHOT (pre-computed from all stocks)",
             "Columns: ADV=advancing  DEC=declining  AVG_CHG=sector avg %  TOT_VOL=total volume",
             "Use this to identify sector rotation before picking individual stocks.",
             "=" * 65]

    for ss in sector_stats:
        icon = "[UP]" if ss["avg_chg"] > 0.5 else ("[DN]" if ss["avg_chg"] < -0.5 else "[--]")
        lines.append(
            f"{icon} {ss['sector'][:28]:28s} | "
            f"ADV:{ss['adv']:3d} DEC:{ss['dec']:3d} | "
            f"AVG:{ss['avg_chg']:+.2f}% | "
            f"VOL:{ss['total_vol']:>14,}"
        )
    lines.append("")
    return "\n".join(lines)


def _build_trading_prompt(news_briefing: dict, stocks: dict,
                           indices: list, learning_ctx: str,
                           insider: dict = None, fipi: dict = None,
                           sector_snapshot: str = "") -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    parts = []

    # ── News briefing ──
    parts.append("=" * 65)
    parts.append("SECTION A — DEEP NEWS BRIEFING (from News Analyst Agent)")
    parts.append("=" * 65)
    parts.append(f"Overall Sentiment : {news_briefing.get('overall_sentiment','N/A')}")
    parts.append(f"Reasoning         : {news_briefing.get('sentiment_reasoning','')}")
    parts.append("")

    for s in news_briefing.get("top_stories", []):
        parts.append(f"[{s.get('impact','?')} | score {s.get('impact_score','?')}/10]  {s.get('headline','')}")
        parts.append(f"  WHAT            : {s.get('what','')}")
        parts.append(f"  WHY IT MATTERS  : {s.get('why_it_matters','')}")
        parts.append(f"  SECOND ORDER    : {s.get('second_order_effect','')}")
        parts.append(f"  SHARIAH LENS    : {s.get('shariah_lens','')}")
        parts.append(f"  TRADER ACTION   : {s.get('trader_action','')}")
        parts.append(f"  Sectors         : {', '.join(s.get('sectors_affected',[]))}")
        companies = s.get('companies_mentioned', [])
        if companies:
            parts.append(f"  Stocks          : {', '.join(companies)}")
        parts.append("")

    macro = news_briefing.get("macro_factors", {})
    if any(v for v in macro.values() if v and v != "N/A"):
        parts.append("MACRO FACTORS:")
        for k, v in macro.items():
            if v and v != "N/A":
                parts.append(f"  {k}: {v}")
        parts.append("")

    shariah_note = news_briefing.get("shariah_market_note", "")
    if shariah_note:
        parts.append(f"SHARIAH MARKET NOTE: {shariah_note}")
        parts.append("")

    risks = news_briefing.get("key_risks", [])
    opps  = news_briefing.get("key_opportunities", [])
    if risks:
        parts.append("KEY RISKS:")
        for r in risks:
            parts.append(f"  - {r}")
    if opps:
        parts.append("KEY OPPORTUNITIES:")
        for o in opps:
            parts.append(f"  + {o}")
    parts.append("")

    # ── Market indices ──
    parts.append("=" * 65)
    parts.append("SECTION B — LIVE MARKET INDICES")
    parts.append("=" * 65)
    for rec in indices:
        if isinstance(rec, dict):
            parts.append("  " + " | ".join(f"{k}:{v}" for k, v in rec.items()))
    parts.append("")

    fmt_header = "SYMBOL [SHARIAH:YES/NO] | LDCP | CUR | CHG | CHG% | VOLUME | HIGH | LOW | INDICES"

    # ── KSE-100 stocks ──
    parts.append("=" * 65)
    parts.append(f"SECTION C — KSE-100 STOCKS ({len(stocks['kse100'])} stocks, sorted by volume)")
    parts.append(fmt_header)
    parts.append("=" * 65)
    for s in stocks["kse100"]:
        parts.append(_stock_row(s))
    parts.append("")

    # ── KSE-100PR stocks ──
    parts.append("=" * 65)
    parts.append(f"SECTION D — KSE-100PR STOCKS ({len(stocks['kse100pr'])} stocks, sorted by volume)")
    parts.append("KSE-100PR = price-return variant of KSE-100. Same 100 stocks, different return calc.")
    parts.append(fmt_header)
    parts.append("=" * 65)
    for s in stocks["kse100pr"]:
        parts.append(_stock_row(s))
    parts.append("")

    # ── KMI-30 Shariah stocks ──
    parts.append("=" * 65)
    parts.append(f"SECTION E — KMI-30 SHARIAH STOCKS ({len(stocks['kmi30'])} stocks) — ALL SHARIAH COMPLIANT")
    parts.append(fmt_header)
    parts.append("=" * 65)
    for s in stocks["kmi30"]:
        parts.append(_stock_row(s))
    parts.append("")

    # ── KMI All-Share broader Shariah universe ──
    parts.append("=" * 65)
    parts.append(f"SECTION F — KMIALLSHR BROADER SHARIAH UNIVERSE (top {len(stocks['kmi_allshr'])} by volume)")
    parts.append("Use this for Shariah picks beyond KMI-30")
    parts.append(fmt_header)
    parts.append("=" * 65)
    for s in stocks["kmi_allshr"]:
        parts.append(_stock_row(s))
    parts.append("")

    # ── NCCPL signals ──
    if insider is not None or fipi is not None:
        parts.append(_build_nccpl_prompt(
            insider or {"buy_signals": [], "sell_signals": [], "error": "Not loaded"},
            fipi    or {"foreign_buying": [], "foreign_selling": [], "error": "Not loaded"},
        ))

    # ── Sector snapshot ──
    if sector_snapshot:
        parts.append(sector_snapshot)

    # ── Learning context ──
    parts.append("=" * 65)
    parts.append("SECTION G — YOUR PAST ACCURACY (LEARNING MEMORY)")
    parts.append("=" * 65)
    parts.append(learning_ctx)
    parts.append("")

    # ── Task ──
    parts.append("=" * 65)
    parts.append(f"YOUR TASK — {today}")
    parts.append("=" * 65)
    parts.append(
        "You MUST produce EXACTLY the following — no more, no less:\n\n"
        "CONVENTIONAL PORTFOLIO (pick from KSE-100 Sections C & D):\n"
        "  conventional_portfolio.buy_picks  = array of EXACTLY 10 objects\n"
        "  conventional_portfolio.avoid_picks = array of EXACTLY 10 objects\n"
        "  Tag each with shariah_compliant: true or false\n\n"
        "SHARIAH PORTFOLIO (pick ONLY from KMI-30/KMIALLSHR Sections E & F):\n"
        "  shariah_portfolio.buy_picks  = array of EXACTLY 10 objects\n"
        "  shariah_portfolio.avoid_picks = array of EXACTLY 10 objects\n"
        "  NEVER include conventional banks, tobacco, or interest-based financials\n\n"
        "IMPORTANT — You must fill all 40 picks. If news catalysts are limited,\n"
        "use volume + price action as the basis for picks. A stock with unusually\n"
        "high volume and a clear price direction is always worth including.\n\n"
        "Keep each reasoning field to 1-2 concise sentences to save space.\n"
        "Return ONLY valid JSON matching your system prompt schema exactly."
    )

    return "\n".join(parts)


# ── JSON REPAIR ──────────────────────────────────────────────────

def _repair_truncated_json(raw: str) -> str:
    """
    When GPT-4.1-mini hits max_tokens mid-JSON, the string is cut off.
    We close all open brackets/braces so json.loads can at least
    parse what was completed, rather than crashing entirely.
    """
    # Remove any trailing partial token (e.g. half-written string)
    for i in range(len(raw) - 1, -1, -1):
        if raw[i] in ('"', '}', ']', '0123456789'):
            raw = raw[:i + 1]
            break

    # Count open structures and close them in reverse order
    open_stack = []
    in_string  = False
    escape     = False
    for ch in raw:
        if escape:
            escape = False
            continue
        if ch == '\\' and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if not in_string:
            if ch in ('{', '['):
                open_stack.append(ch)
            elif ch in ('}', ']'):
                if open_stack:
                    open_stack.pop()

    # Close in reverse
    closing = {'{': '}', '[': ']'}
    suffix  = ''.join(closing[c] for c in reversed(open_stack))
    repaired = raw + suffix
    logger.warning(f"JSON repair: appended '{suffix}' to close {len(open_stack)} open structure(s)")
    return repaired


# ── MAIN FUNCTION ────────────────────────────────────────────────

def run_trading_analysis(news_briefing: dict, save_history: bool = True,
                          pipeline_run_id=None) -> dict:
    psx_data = load_psx_data()
    update_outcomes(psx_data)
    if _DB_ENABLED:
        safe(update_pick_outcomes, psx_data)

    history      = load_history()
    learning_ctx = _build_learning_context(history)
    stocks       = prepare_stocks(psx_data)
    insider      = load_nccpl_insider()
    fipi         = load_nccpl_fipi()

    logger.info(
        f"NCCPL loaded | Insider: {len(insider.get('buy_signals',[]))} BUY / "
        f"{len(insider.get('sell_signals',[]))} SELL | "
        f"FIPI: {len(fipi.get('foreign_buying',[]))} foreign buying"
    )

    sector_snapshot = _build_sector_snapshot(psx_data)

    prompt = _build_trading_prompt(
        news_briefing, stocks, psx_data.get("indices", []),
        learning_ctx, insider=insider, fipi=fipi,
        sector_snapshot=sector_snapshot,
    )

    logger.info(
        f"Trading agent -> GPT-4.1-mini  ({len(prompt):,} chars | "
        f"KSE100:{len(stocks['kse100'])} | KMI30:{len(stocks['kmi30'])})"
    )

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        temperature=0.2,
        max_tokens=8000,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
    )

    raw_content  = response.choices[0].message.content
    finish_reason = response.choices[0].finish_reason

    if finish_reason == "length":
        logger.warning("Response was cut off (finish_reason=length). Attempting JSON repair...")
        raw_content = _repair_truncated_json(raw_content)

    report = json.loads(raw_content)
    report["report_date"]     = datetime.now().strftime("%Y-%m-%d")
    report["generated_at"]    = datetime.now().isoformat()
    report["tokens_used"]     = response.usage.total_tokens
    report["finish_reason"]   = finish_reason
    report["stocks_analyzed"] = {
        "kse100":     len(stocks["kse100"]),
        "kmi30":      len(stocks["kmi30"]),
        "kmi_allshr": len(stocks["kmi_allshr"]),
    }

    logger.info(
        f"Trading agent done | Tokens: {response.usage.total_tokens} | "
        f"Conv buys: {len(report.get('conventional_portfolio',{}).get('buy_picks',[]))} | "
        f"Shariah buys: {len(report.get('shariah_portfolio',{}).get('buy_picks',[]))}"
    )

    if save_history:
        save_to_history(report)

    # Dual-write to Postgres. Create a pipeline_run if one wasn't supplied,
    # so this works both standalone and from the orchestrator.
    if _DB_ENABLED:
        run_id = pipeline_run_id
        if run_id is None:
            run_id = safe(save_pipeline_run, "legacy", response.usage.total_tokens, "ok")
            if run_id is not None and news_briefing and news_briefing.get("top_stories"):
                safe(save_news_briefing, run_id, news_briefing)
        if run_id is not None:
            report_id = safe(save_trading_report_with_picks, run_id, report)
            if report_id is not None:
                report["_db_meta"] = {
                    "pipeline_run_id": str(run_id),
                    "trading_report_id": str(report_id),
                }

    return report


# ── WHATSAPP FORMATTER ───────────────────────────────────────────

def format_whatsapp_report(report: dict, news_briefing: dict) -> str:
    lines = []
    today = report.get("report_date", datetime.now().strftime("%Y-%m-%d"))

    overview  = report.get("market_overview", {})
    sentiment = overview.get("session_bias", "N/A")
    s_emoji   = {"BULLISH":"📈","BEARISH":"📉","NEUTRAL":"➡️","CAUTIOUS":"⚠️"}.get(sentiment,"📊")

    # ── Header ──
    lines.append(f"📊 *PSX DAILY REPORT — {today}*")
    lines.append(f"{s_emoji} *{sentiment}*  |  KSE-100: {overview.get('kse100_level','?')} ({overview.get('kse100_change_pct','?')})")
    lines.append(f"KMI-30: {overview.get('kmi30_level','N/A')}  |  Breadth: {overview.get('market_breadth','N/A')}")
    lines.append(f"\n{overview.get('summary','')}")

    # ── Top news ──
    stories = news_briefing.get("top_stories", [])[:5]
    if stories:
        lines.append("\n*📰 KEY NEWS & ANALYSIS:*")
        for s in stories:
            icon = {"POSITIVE":"🟢","NEGATIVE":"🔴","NEUTRAL":"⚪"}.get(s.get("impact",""),"•")
            lines.append(f"\n{icon} *{s.get('headline','')}*")
            lines.append(f"  _{s.get('why_it_matters','')}_")
            if s.get("trader_action"):
                lines.append(f"  Action: *{s.get('trader_action','')}*")

    shariah_note = news_briefing.get("shariah_market_note","")
    if shariah_note:
        lines.append(f"\n*☪️ Shariah Market Note:* {shariah_note}")

    # ── Helper: compact buy row (2 lines) ──
    def _buy_row(b: dict, show_kmi: bool = False) -> list:
        sc      = " ☪️" if b.get("shariah_compliant") else ""
        kmi_tag = f"  ({b.get('kmi_index','')})" if show_kmi else ""
        conf    = b.get("confidence","")
        conf_icon = {"HIGH":"🔥","MEDIUM":"✅","LOW":"⚡"}.get(conf, conf)
        row1 = (
            f"*{b.get('rank'):>2}. {b.get('symbol',''):8s}*{sc}{kmi_tag}  "
            f"{conf_icon}  Rs{b.get('current_price','?')}"
        )
        row2 = (
            f"    Entry: Rs{b.get('entry_range','?')}  "
            f"TGT: Rs{b.get('target_price','?')} ({b.get('upside_pct','?')})  "
            f"SL: Rs{b.get('stop_loss','?')}  "
            f"Vol: {b.get('volume_signal','')}"
        )
        catalyst = b.get("news_catalyst","") or b.get("price_volume_reason","")
        row3 = f"    _{catalyst[:90]}_"
        return [row1, row2, row3]

    # ── Helper: compact avoid row (1 line) ──
    def _avoid_row(a: dict, show_kmi: bool = False) -> str:
        sc      = " ☪️" if a.get("shariah_compliant") else ""
        kmi_tag = f" ({a.get('kmi_index','')})" if show_kmi else ""
        reason  = (a.get("reason","") or "")[:80]
        return (
            f"*{a.get('rank'):>2}. {a.get('symbol',''):8s}*{sc}{kmi_tag}  "
            f"Rs{a.get('current_price','?')}  —  _{reason}_"
        )

    # ── Conventional BUY list ──
    conv      = report.get("conventional_portfolio", {})
    conv_buys = conv.get("buy_picks", [])
    if conv_buys:
        lines.append("\n" + "─"*40)
        lines.append(f"*🟢 CONVENTIONAL BUY LIST  ({len(conv_buys)}/10)*")
        lines.append("_🔥 HIGH  ✅ MED  ⚡ LOW_\n")
        for b in conv_buys:
            lines.extend(_buy_row(b))
            lines.append("")

    # ── Conventional AVOID list ──
    conv_avoids = conv.get("avoid_picks", [])
    if conv_avoids:
        lines.append(f"*🔴 CONVENTIONAL AVOID LIST  ({len(conv_avoids)}/10)*\n")
        for a in conv_avoids:
            lines.append(_avoid_row(a))
        lines.append("")

    # ── Shariah BUY list ──
    shar      = report.get("shariah_portfolio", {})
    shar_buys = shar.get("buy_picks", [])
    if shar_buys:
        lines.append("─"*40)
        lines.append(f"*☪️🟢 SHARIAH BUY LIST  ({len(shar_buys)}/10)*")
        lines.append("_🔥 HIGH  ✅ MED  ⚡ LOW_\n")
        for b in shar_buys:
            lines.extend(_buy_row(b, show_kmi=True))
            lines.append("")

    # ── Shariah AVOID list ──
    shar_avoids = shar.get("avoid_picks", [])
    if shar_avoids:
        lines.append(f"*☪️🔴 SHARIAH AVOID LIST  ({len(shar_avoids)}/10)*\n")
        for a in shar_avoids:
            lines.append(_avoid_row(a, show_kmi=True))
        lines.append("")

    # ── Sector rotation ──
    rotation      = report.get("sector_rotation", {})
    buy_sectors   = rotation.get("buy_sectors", [])
    avoid_sectors = rotation.get("avoid_sectors", [])
    if buy_sectors or avoid_sectors:
        lines.append("─"*40)
        if buy_sectors:
            lines.append("*Sectors to BUY:*")
            for s in buy_sectors:
                sc = "☪️ " if s.get("shariah_compliant") else "   "
                lines.append(f"  {sc}*{s.get('sector','')}* — {s.get('reason','')}")
        if avoid_sectors:
            lines.append("*Sectors to AVOID:*")
            for s in avoid_sectors:
                lines.append(f"     *{s.get('sector','')}* — {s.get('reason','')}")

    macro = report.get("macro_watch","")
    if macro:
        lines.append(f"\n*💱 Macro Watch:* {macro}")

    # ── NCCPL Insider + FIPI section ──────────────────────────────
    try:
        import json as _json, os as _os
        def _nccpl_load(path):
            try:
                with open(path, encoding="utf-8") as _f:
                    return _json.load(_f)
            except Exception:
                return {}

        insider = _nccpl_load(os.path.join(DATA_DIR, "06_nccpl_insider.json"))
        fipi    = _nccpl_load(os.path.join(DATA_DIR, "07_nccpl_fipi.json"))

        buy_sigs  = insider.get("buy_signals",  [])
        sell_sigs = insider.get("sell_signals", [])
        fb        = fipi.get("foreign_buying",  [])
        fs        = fipi.get("foreign_selling", [])

        has_insider = bool(buy_sigs or sell_sigs or insider.get("activity_signals"))
        has_fipi    = bool(fb or fs)

        if has_insider or has_fipi:
            lines.append("\n" + "─"*40)
            lines.append("*📋 NCCPL SIGNALS*")

        if has_insider:
            insider_err = insider.get("error")
            if insider_err and not buy_sigs and not sell_sigs:
                lines.append(f"\n*🔍 Insider Transactions:* _{insider_err[:100]}_")
            else:
                lines.append(f"\n*🔍 Insider Transactions (last 7 days):*")
                strength_icon = {"VERY_HIGH": "🚨", "HIGH": "🔴", "MEDIUM": "🟡", "LOW": "⚪"}
                if buy_sigs:
                    lines.append("_Director BUYING (bullish):_")
                    for s in buy_sigs:
                        icon = strength_icon.get(s["signal_strength"], "•")
                        lines.append(f"{icon} *{s['symbol']}* — {s['summary']}")
                if sell_sigs:
                    lines.append("_Director SELLING (bearish):_")
                    for s in sell_sigs:
                        icon = strength_icon.get(s["signal_strength"], "•")
                        lines.append(f"{icon} *{s['symbol']}* — {s['summary']}")
                activity_sigs = insider.get("activity_signals", [])
                if activity_sigs:
                    lines.append("_Insider Activity (watch — direction filing detected):_")
                    for s in activity_sigs:
                        lines.append(f"👁 *{s['symbol']}* — {s['summary']}")

        if has_fipi:
            fipi_err = fipi.get("error")
            if fipi_err:
                lines.append(f"\n*🌍 FIPI/LIPI:* _{fipi_err}_")
            else:
                lines.append(f"\n*🌍 Foreign Investor Flows (FIPI — today):*")
                strength_icon = {"VERY_HIGH": "🚨", "HIGH": "🟢", "MEDIUM": "🟡", "LOW": "⚪"}
                if fb:
                    lines.append("_Foreign NET BUYING (institutional accumulation):_")
                    for s in fb[:10]:
                        icon = strength_icon.get(s["signal_strength"], "•")
                        lines.append(f"{icon} *{s['symbol']}* — {s['summary']}")
                if fs:
                    lines.append("_Foreign NET SELLING (institutional exit):_")
                    for s in fs[:10]:
                        icon = {"VERY_HIGH": "🚨", "HIGH": "🔴", "MEDIUM": "🟡", "LOW": "⚪"}.get(
                            s["signal_strength"], "•")
                        lines.append(f"{icon} *{s['symbol']}* — {s['summary']}")

    except Exception as _e:
        logger.warning(f"NCCPL section in WhatsApp report failed: {_e}")

    lines.append(f"\n_{report.get('disclaimer','For educational purposes only.')}_")
    return "\n".join(lines)


# ── CLI ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    empty_briefing = {
        "overall_sentiment": "NEUTRAL",
        "sentiment_reasoning": "Test run — no news loaded.",
        "top_stories": [], "macro_factors": {},
        "sector_outlook": [], "shariah_market_note": "",
        "key_risks": [], "key_opportunities": [],
    }
    result = run_trading_analysis(empty_briefing)
    print(json.dumps(result, indent=2, ensure_ascii=False))
