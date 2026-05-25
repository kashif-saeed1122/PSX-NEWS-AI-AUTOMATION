"""
analysis_agent.py
-----------------
A specialized GPT-4.1-mini trading analyst agent for PSX.

What it does:
  1. Loads yesterday's + today's news from the JSON data files
  2. Loads all PSX stock data (480 stocks, OHLCV)
  3. Reads the last 7 days of past analyses + their real outcomes (learning memory)
  4. Calls GPT-4.1-mini with a detailed trader system prompt
  5. Returns a structured JSON analysis: BUY / WATCH / AVOID with reasoning
  6. Saves the analysis to data/analysis_history.json for future learning

Learning loop:
  - Each day's analysis is saved with predictions
  - The NEXT run automatically checks actual price changes for past BUY/AVOID calls
  - These outcomes (correct/wrong/partial) are fed back as context to the agent
  - Over time the agent sees its own track record and adjusts its reasoning style

Usage:
    from analysis_agent import run_analysis
    result = run_analysis()
"""

import os
import json
import logging
from datetime import datetime, timedelta, timezone
from openai import OpenAI
from dotenv import load_dotenv
import price_history as ph

load_dotenv()
logger = logging.getLogger(__name__)

DATA_DIR        = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend", "data")
HISTORY_FILE    = os.path.join(DATA_DIR, "analysis_history.json")
LEARNING_WINDOW = 7          # days of history to feed back to the agent
MAX_STOCKS_IN_PROMPT = 150   # cap prompt size; sorted by volume desc

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# ── SYSTEM PROMPT ────────────────────────────────────────────────

SYSTEM_PROMPT = """
You are a senior Pakistani stock market trader and analyst with 15+ years of
experience on the PSX (Pakistan Stock Exchange). You trade KSE-100 and broader
ALLSHR stocks daily.

Your analysis style:
- You combine fundamental news catalysts with price+volume technicals
- You look for high-volume moves as confirmation (not just price direction)
- You weigh macro factors: PKR/USD, SBP rate policy, IMF conditions,
  commodity prices (oil, gas, cement, steel), and political stability
- You prefer sector rotation: you find the sectors news is flowing into
- You understand PSX-specific quirks: circuit breakers, T+2 settlement,
  speculative mid-caps, institutional vs retail flows
- You are conservative: you mark uncertainty clearly and always recommend
  stop-losses
- You are honest: if data is thin or the market is risky, you say so

Output rules:
- Respond ONLY with valid JSON matching the schema below — no markdown, no extra text
- All price fields must be numeric strings as they appear in the data
- Reasoning must be specific (reference actual news + price/volume data)
- Maximum 5 BUY picks, 5 WATCH picks, 5 AVOID picks
- Confidence: "HIGH" | "MEDIUM" | "LOW"
- Action: "BUY" | "WATCH" | "AVOID"

JSON schema:
{
  "analysis_date": "YYYY-MM-DD",
  "generated_at": "ISO timestamp",
  "market_overview": {
    "sentiment": "BULLISH | BEARISH | NEUTRAL | CAUTIOUS",
    "kse100_level": "...",
    "kse100_change_pct": "...",
    "breadth": "X stocks up, Y stocks down",
    "summary": "2-3 sentence market summary"
  },
  "key_news_drivers": [
    {"headline": "...", "impact": "POSITIVE | NEGATIVE | NEUTRAL", "sectors_affected": ["..."]}
  ],
  "recommendations": [
    {
      "symbol": "...",
      "company_name": "...",
      "action": "BUY | WATCH | AVOID",
      "current_price": "...",
      "entry_range": "...",
      "target_price": "...",
      "stop_loss": "...",
      "sector": "...",
      "volume_today": "...",
      "change_pct_today": "...",
      "confidence": "HIGH | MEDIUM | LOW",
      "reasoning": "specific 2-3 sentence reasoning citing news or price/volume data",
      "risk": "key risk to this call in 1 sentence"
    }
  ],
  "sectors_to_watch": ["sector name", ...],
  "sectors_to_avoid": ["sector name", ...],
  "macro_note": "Brief note on macro factors (PKR, SBP, IMF, commodities) relevant today",
  "disclaimer": "For educational purposes only. Not financial advice. Always do your own research."
}
"""


# ── DATA LOADERS ─────────────────────────────────────────────────

def load_news(days_back: int = 1) -> list[dict]:
    """Load news articles from yesterday only (last `days_back` days)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    all_articles = []

    news_files = [
        os.path.join(DATA_DIR, "01_google_news.json"),
        os.path.join(DATA_DIR, "02_dawn_business.json"),
        os.path.join(DATA_DIR, "03_profit_pakistan.json"),
    ]

    for path in news_files:
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.warning(f"Could not load {path}: {e}")
            continue

        source = data.get("source", os.path.basename(path))

        # Google News style
        articles = data.get("articles", [])
        # Dawn / Profit style (nested under rss)
        if not articles:
            articles = data.get("rss", {}).get("articles", [])

        for a in articles:
            pub_raw = a.get("published") or a.get("date") or ""
            # Try to parse date — accept any format, fallback to include if unparseable
            include = True
            try:
                from email.utils import parsedate_to_datetime
                pub_dt = parsedate_to_datetime(pub_raw)
                include = pub_dt >= cutoff
            except Exception:
                # If we can't parse the date, include it (better to have more context)
                pass

            if include:
                all_articles.append({
                    "source": source,
                    "title": a.get("title", ""),
                    "summary": a.get("summary", ""),
                    "date": pub_raw,
                    "link": a.get("link", ""),
                })

    # Also add scraped headlines from direct scrapes
    for path in news_files:
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            source = data.get("source", "")
            for h in data.get("direct_scrape", {}).get("headlines", []):
                if h:
                    all_articles.append({"source": source + " (headline)", "title": h, "summary": "", "date": "", "link": ""})
        except Exception:
            pass

    logger.info(f"Loaded {len(all_articles)} news items (last {days_back} days)")
    return all_articles


def load_psx_data() -> dict:
    """Load PSX market data from the JSON file."""
    path = os.path.join(DATA_DIR, "04_psx_data_portal.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"PSX data not found at {path}. Run fetch_and_save.py first.")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_history() -> list[dict]:
    """Load past analyses from the history file."""
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_to_history(analysis: dict):
    """Append today's analysis to history. Cap at 90 days."""
    history = load_history()
    history.append(analysis)
    history = history[-90:]  # keep last 90 days
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    logger.info(f"Analysis saved to history ({len(history)} total entries)")


def update_outcomes_in_history(psx_data: dict):
    """
    For the most recent past analyses that have BUY/AVOID recommendations
    but no outcomes yet, check today's price data and record what happened.

    This is the learning feedback loop: agent sees whether its calls were right.
    """
    history = load_history()
    if not history:
        return

    # Build a symbol -> current price map from today's data
    price_map = {}
    for stock in psx_data.get("all_stocks", []):
        sym = stock.get("SYMBOL", "")
        cur = stock.get("CURRENT", "")
        ldcp = stock.get("LDCP", "")  # Last Day's Closing Price
        chg_pct = stock.get("CHANGE (%)", "")
        if sym:
            price_map[sym] = {
                "current": cur,
                "ldcp": ldcp,
                "change_pct": chg_pct,
            }

    today = datetime.now().strftime("%Y-%m-%d")
    updated = False

    for entry in history:
        # Only update entries that don't yet have outcomes and are from a past date
        if entry.get("analysis_date") == today:
            continue
        if entry.get("outcomes_recorded"):
            continue

        outcomes = []
        for rec in entry.get("recommendations", []):
            sym = rec.get("symbol", "")
            action = rec.get("action", "")
            predicted_target = rec.get("target_price", "")
            predicted_stop = rec.get("stop_loss", "")

            actual = price_map.get(sym, {})
            actual_price = actual.get("current", "N/A")
            actual_change = actual.get("change_pct", "N/A")

            outcome = {
                "symbol": sym,
                "action_called": action,
                "predicted_target": predicted_target,
                "predicted_stop_loss": predicted_stop,
                "actual_price_next_session": actual_price,
                "actual_change_pct": actual_change,
                "result": "UNKNOWN",
            }

            # Simple outcome evaluation
            try:
                chg = float(actual_change.replace("%", "").replace(",", ""))
                if action == "BUY":
                    if chg >= 2.0:
                        outcome["result"] = "CORRECT (strong up)"
                    elif chg >= 0.5:
                        outcome["result"] = "CORRECT (moderate up)"
                    elif chg < -2.0:
                        outcome["result"] = "WRONG (significant down)"
                    else:
                        outcome["result"] = "NEUTRAL"
                elif action == "AVOID":
                    if chg <= -2.0:
                        outcome["result"] = "CORRECT (fell as expected)"
                    elif chg >= 2.0:
                        outcome["result"] = "WRONG (rose despite avoid)"
                    else:
                        outcome["result"] = "NEUTRAL"
            except (ValueError, AttributeError):
                pass

            outcomes.append(outcome)

        if outcomes:
            entry["outcomes"] = outcomes
            entry["outcomes_recorded"] = True
            updated = True

    if updated:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        logger.info("Outcomes updated in history (learning feedback applied)")


def build_learning_context(history: list[dict]) -> str:
    """Format the last N analyses with outcomes into a concise context string."""
    if not history:
        return "No past analyses available yet. This is the first analysis."

    recent = [h for h in history if h.get("outcomes_recorded")][-LEARNING_WINDOW:]
    if not recent:
        return "Past analyses exist but outcomes not yet recorded (need next-day data)."

    lines = ["=== PAST ANALYSIS OUTCOMES (your track record) ==="]
    for entry in recent:
        lines.append(f"\nDate: {entry.get('analysis_date', 'unknown')}")
        sentiment = entry.get("market_overview", {}).get("sentiment", "")
        lines.append(f"Market call: {sentiment}")
        for o in entry.get("outcomes", []):
            r = o.get("result", "UNKNOWN")
            lines.append(
                f"  {o['action_called']:5s} {o['symbol']:8s} -> {r} "
                f"(actual change: {o.get('actual_change_pct', 'N/A')})"
            )

    # ── Sector win-rate ──────────────────────────────────────────────
    sector_stats = {}
    conf_stats   = {"HIGH": [0, 0], "MEDIUM": [0, 0], "LOW": [0, 0]}
    all_recorded = [h for h in history if h.get("outcomes_recorded")]

    for entry in all_recorded[-30:]:
        outcome_map = {o["symbol"]: o.get("result", "UNKNOWN") for o in entry.get("outcomes", [])}
        for rec in entry.get("recommendations", []):
            if rec.get("action") != "BUY":
                continue
            sym    = rec.get("symbol", "")
            sector = rec.get("sector", "Unknown")
            conf   = rec.get("confidence", "MEDIUM")
            result = outcome_map.get(sym, "UNKNOWN")
            bucket = sector_stats.setdefault(sector, [0, 0])
            bucket[1] += 1
            if conf in conf_stats:
                conf_stats[conf][1] += 1
            if "CORRECT" in result:
                bucket[0] += 1
                if conf in conf_stats:
                    conf_stats[conf][0] += 1

    qualifying = [(s, c, t) for s, (c, t) in sector_stats.items() if t >= 3]
    if qualifying:
        qualifying.sort(key=lambda x: x[1] / x[2], reverse=True)
        lines.append("\n=== SECTOR WIN-RATE (BUY calls, last 30 days, ≥3 calls) ===")
        for sec, correct, total in qualifying[:10]:
            pct = round(correct / total * 100)
            bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
            lines.append(f"  {sec[:26]:26s} {bar} {pct:3d}%  ({correct}/{total})")

    conf_rows = [(c, v[0], v[1]) for c, v in conf_stats.items() if v[1] >= 3]
    if conf_rows:
        lines.append("\n=== CONFIDENCE CALIBRATION ===")
        for conf, correct, total in conf_rows:
            pct = round(correct / total * 100)
            lines.append(f"  {conf:6s}: {pct:3d}% hit rate ({correct}/{total})")
            if conf == "HIGH" and pct < 55:
                lines.append("  ⚠️  HIGH confidence underperforming — be more selective today.")
            elif conf == "LOW" and pct > 65:
                lines.append("  ℹ️  LOW confidence outperforming — don't dismiss weak signals.")

    lines.append("\nUse this track record to calibrate your confidence and adjust your analysis style.")
    return "\n".join(lines)


# ── PROMPT BUILDERS ──────────────────────────────────────────────

def _sector_snapshot(psx_data: dict) -> str:
    """Pre-compute sector momentum table to guide stock selection."""
    by_sector = psx_data.get("by_sector", {})
    if not by_sector:
        return ""
    rows = []
    for sector, stocks in by_sector.items():
        adv = dec = 0
        changes, vol_total = [], 0
        for s in stocks:
            try:
                chg = float(str(s.get("CHANGE (%)","0")).replace("%","").replace(",","").strip() or "0")
                vol = int(str(s.get("VOLUME","0")).replace(",","").strip() or "0")
                changes.append(chg)
                vol_total += vol
                if chg > 0: adv += 1
                elif chg < 0: dec += 1
            except Exception:
                pass
        if not changes:
            continue
        rows.append((sector, len(stocks), adv, dec, round(sum(changes)/len(changes), 2), vol_total))
    rows.sort(key=lambda x: x[4], reverse=True)
    lines = ["=== SECTOR MOMENTUM SNAPSHOT ===",
             "Use this first to identify where money is flowing before picking stocks.",
             "SECTOR | STOCKS | ADV | DEC | AVG_CHG% | TOTAL_VOL"]
    for r in rows:
        icon = "[UP]" if r[4] > 0.5 else ("[DN]" if r[4] < -0.5 else "[--]")
        lines.append(f"{icon} {r[0][:28]:28s} | {r[1]:3d} | ADV:{r[2]:3d} DEC:{r[3]:3d} | {r[4]:+.2f}% | {r[5]:>14,}")
    return "\n".join(lines)


def build_user_prompt(news: list, psx_data: dict, learning_ctx: str) -> str:
    today     = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    sections = []

    # ── Market Indices ──
    indices = psx_data.get("indices", [])
    if indices:
        lines = ["=== MARKET INDICES ==="]
        for rec in indices:
            if isinstance(rec, dict):
                lines.append("  " + " | ".join(f"{k}: {v}" for k, v in rec.items()))
        sections.append("\n".join(lines))

    # ── Sector snapshot ──
    snap = _sector_snapshot(psx_data)
    if snap:
        sections.append(snap)

    # ── All Stocks with technical signals (sorted by volume, top N) ──
    stocks = psx_data.get("all_stocks", [])
    def vol_key(s):
        try:
            return int(s.get("VOLUME", "0").replace(",", ""))
        except (ValueError, AttributeError):
            return 0

    stocks_sorted = sorted(stocks, key=vol_key, reverse=True)[:MAX_STOCKS_IN_PROMPT]

    try:
        signals = ph.get_all_signals()
    except Exception:
        signals = {}

    lines = [f"=== STOCK DATA (top {len(stocks_sorted)} by volume, {len(stocks)} total listed) ===",
             "Columns: SYMBOL | SECTOR | LISTED_IN | LDCP | CUR | CHG% | VOL | TECH_SIGNALS"]
    for s in stocks_sorted:
        sym = s.get("SYMBOL", "")
        sig = signals.get(sym, {})
        rsi      = sig.get("rsi14")
        vol_ratio = sig.get("vol_ratio")
        sma_sig  = sig.get("sma_signal", "")
        trend    = sig.get("trend", "")
        rsi_lbl  = sig.get("rsi_label", "")
        vol_lbl  = sig.get("vol_label", "")
        days     = sig.get("days_of_data", 0)

        if days > 0:
            rsi_s  = f"RSI:{rsi:.0f}({rsi_lbl})" if rsi is not None else "RSI:--"
            volx_s = f"VOLX:{vol_ratio:.1f}x({vol_lbl})" if vol_ratio is not None else "VOLX:--"
            tech   = f"{rsi_s}|{volx_s}|{sma_sig}|{trend}|{days}d"
        else:
            tech = "NO_HISTORY"

        lines.append(
            f"{sym} | {s.get('SECTOR','')} | {s.get('LISTED IN','')} | "
            f"{s.get('LDCP','')} | {s.get('CURRENT','')} | "
            f"{s.get('CHANGE (%)','').strip()} | {s.get('VOLUME','')} | [{tech}]"
        )
    sections.append("\n".join(lines))

    # ── News ──
    lines = [f"=== NEWS (from {yesterday} to {today}) ==="]
    if news:
        for i, a in enumerate(news[:60], 1):
            lines.append(f"\n[{i}] [{a['source']}] {a['title']}")
            if a.get("summary"):
                lines.append(f"    {a['summary'][:300]}")
            if a.get("date"):
                lines.append(f"    Date: {a['date']}")
    else:
        lines.append("No recent news available.")
    sections.append("\n".join(lines))

    # ── Learning context ──
    sections.append(learning_ctx)

    # ── Final instruction ──
    sections.append(
        f"=== YOUR TASK ===\n"
        f"Today is {today}. Analyze all the above data as a seasoned PSX trader.\n"
        f"Step 1: Check Sector Snapshot — find sectors with high volume + positive momentum.\n"
        f"Step 2: In those sectors, look for stocks with GOLDEN_CROSS / ABOVE_SMA20 + HIGH_SPIKE volume.\n"
        f"Step 3: Cross-reference with news catalysts for confirmation.\n"
        f"Step 4: Flag OVERBOUGHT stocks (RSI > 70) or DEATH_CROSS stocks as AVOID.\n"
        f"Be specific — reference actual symbols, prices, volumes, and news in your reasoning.\n"
        f"Return ONLY valid JSON matching the schema in your system prompt."
    )

    return "\n\n".join(sections)


# ── MAIN ANALYSIS FUNCTION ───────────────────────────────────────

def run_analysis(save_history: bool = True) -> dict:
    """
    Run the full PSX trading analysis.
    Returns the structured analysis dict.
    """
    logger.info("Starting PSX trading analysis...")

    # Load data
    psx_data = load_psx_data()
    news = load_news(days_back=1)
    history = load_history()

    # Update outcomes for past analyses (learning feedback)
    update_outcomes_in_history(psx_data)
    history = load_history()  # reload after update

    # Build learning context from history
    learning_ctx = build_learning_context(history)

    # Build prompt
    user_prompt = build_user_prompt(news, psx_data, learning_ctx)

    logger.info(f"Sending analysis prompt to GPT-4.1-mini ({len(user_prompt):,} chars)...")

    # Call GPT-4.1-mini
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        temperature=0.3,       # Lower temp for analytical precision
        max_tokens=3000,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt},
        ],
    )

    raw = response.choices[0].message.content
    analysis = json.loads(raw)

    # Stamp metadata
    analysis["analysis_date"] = datetime.now().strftime("%Y-%m-%d")
    analysis["generated_at"]  = datetime.now().isoformat()
    analysis["tokens_used"]   = {
        "prompt": response.usage.prompt_tokens,
        "completion": response.usage.completion_tokens,
        "total": response.usage.total_tokens,
    }
    analysis["news_count"]    = len(news)
    analysis["stocks_count"]  = len(psx_data.get("all_stocks", []))

    logger.info(
        f"Analysis complete. "
        f"Tokens: {response.usage.total_tokens}. "
        f"Recommendations: {len(analysis.get('recommendations', []))}"
    )

    if save_history:
        save_to_history(analysis)

    return analysis


def format_for_whatsapp(analysis: dict) -> str:
    """Format the analysis dict into a clean, readable WhatsApp message."""
    lines = []
    today = analysis.get("analysis_date", datetime.now().strftime("%Y-%m-%d"))

    # Header
    overview = analysis.get("market_overview", {})
    sentiment = overview.get("sentiment", "N/A")
    sentiment_emoji = {
        "BULLISH": "📈", "BEARISH": "📉",
        "NEUTRAL": "➡️", "CAUTIOUS": "⚠️"
    }.get(sentiment, "📊")

    lines.append(f"📊 *PSX DAILY ANALYSIS — {today}*")
    lines.append(f"{sentiment_emoji} Market: *{sentiment}*")
    lines.append(f"KSE-100: {overview.get('kse100_level','N/A')} ({overview.get('kse100_change_pct','N/A')})")
    lines.append(f"Breadth: {overview.get('breadth','N/A')}")
    lines.append("")
    lines.append(overview.get("summary", ""))

    # News drivers
    drivers = analysis.get("key_news_drivers", [])
    if drivers:
        lines.append("")
        lines.append("*📰 Key News Drivers:*")
        for d in drivers[:4]:
            impact_emoji = {"POSITIVE": "🟢", "NEGATIVE": "🔴", "NEUTRAL": "⚪"}.get(d.get("impact",""), "•")
            lines.append(f"{impact_emoji} {d.get('headline','')}")

    # Recommendations
    recs = analysis.get("recommendations", [])
    buys    = [r for r in recs if r.get("action") == "BUY"]
    watches = [r for r in recs if r.get("action") == "WATCH"]
    avoids  = [r for r in recs if r.get("action") == "AVOID"]

    if buys:
        lines.append("")
        lines.append("*🟢 BUY SIGNALS:*")
        for r in buys:
            conf = r.get("confidence","")
            conf_tag = f" [{conf}]" if conf else ""
            lines.append(
                f"*{r.get('symbol','')}*{conf_tag} — Rs{r.get('current_price','N/A')} "
                f"| Target: Rs{r.get('target_price','N/A')} | SL: Rs{r.get('stop_loss','N/A')}"
            )
            lines.append(f"  _{r.get('reasoning',''[:120])}_")

    if watches:
        lines.append("")
        lines.append("*🟡 WATCHLIST:*")
        for r in watches:
            lines.append(
                f"*{r.get('symbol','')}* — Rs{r.get('current_price','N/A')} "
                f"| {r.get('reasoning','')[:100]}"
            )

    if avoids:
        lines.append("")
        lines.append("*🔴 AVOID:*")
        for r in avoids:
            lines.append(f"*{r.get('symbol','')}* — {r.get('reasoning','')[:100]}")

    # Sector calls
    watch_sectors = analysis.get("sectors_to_watch", [])
    avoid_sectors = analysis.get("sectors_to_avoid", [])
    if watch_sectors or avoid_sectors:
        lines.append("")
        if watch_sectors:
            lines.append(f"*Sectors to Watch:* {', '.join(watch_sectors)}")
        if avoid_sectors:
            lines.append(f"*Sectors to Avoid:* {', '.join(avoid_sectors)}")

    # Macro note
    macro = analysis.get("macro_note","")
    if macro:
        lines.append("")
        lines.append(f"*💱 Macro:* {macro}")

    # Disclaimer
    lines.append("")
    lines.append(f"_{analysis.get('disclaimer','For educational purposes only.')}_")

    return "\n".join(lines)


# ── CLI TEST ─────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    print("Running PSX analysis agent...")
    try:
        result = run_analysis(save_history=True)
        print("\n" + "=" * 60)
        print("ANALYSIS RESULT (JSON):")
        print("=" * 60)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        print("\n" + "=" * 60)
        print("WHATSAPP FORMAT:")
        print("=" * 60)
        print(format_for_whatsapp(result))
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
