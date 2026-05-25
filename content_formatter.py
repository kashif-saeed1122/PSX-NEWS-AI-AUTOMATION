"""
content_formatter.py  —  4-Tier Content Funnel
------------------------------------------------
  TIER 1  format_facebook_post()        — Public FB teaser, no stock names
  TIER 2  format_free_whatsapp_post()   — Free WA group: top 3 picks, entry only
  TIER 3  format_paid_whatsapp_post()   — Paid subscribers: full 10+10 report
  TIER 4  format_comprehensive_report() — Deep-dive document: all data, full reasoning
"""

import json
import os
from datetime import datetime

_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend", "data")


def _load_nccpl() -> tuple[dict, dict]:
    """Load NCCPL insider and FIPI data files if available."""
    def _read(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    insider = _read(os.path.join(_DATA_DIR, "06_nccpl_insider.json"))
    fipi    = _read(os.path.join(_DATA_DIR, "07_nccpl_fipi.json"))
    return insider, fipi


# ── TIER 1: FACEBOOK POST ────────────────────────────────────────

def format_facebook_post(report: dict, news_briefing: dict,
                          free_group_link: str = "") -> str:
    """
    Teaser post for the Facebook Page.
    - No individual stock names
    - Market sentiment + top sector hints
    - CTA to join free WhatsApp group
    """
    today    = report.get("report_date", datetime.now().strftime("%Y-%m-%d"))
    overview = report.get("market_overview", {})
    bias     = overview.get("session_bias", "NEUTRAL")
    kse      = overview.get("kse100_level", "N/A")
    kse_chg  = overview.get("kse100_change_pct", "N/A")
    breadth  = overview.get("market_breadth", "")
    summary  = overview.get("summary", "")

    bias_line = {
        "BULLISH":  "Markets are looking BULLISH today.",
        "BEARISH":  "Markets are under pressure today — be careful.",
        "NEUTRAL":  "Mixed signals in the market today.",
        "CAUTIOUS": "Market is flashing caution signs today.",
    }.get(bias, "Markets are active today.")

    # Pick up to 2 buy sectors from sector_rotation
    buy_sectors = report.get("sector_rotation", {}).get("buy_sectors", [])
    sector_teaser = ""
    if buy_sectors:
        names = [s.get("sector", "") for s in buy_sectors[:2] if s.get("sector")]
        if names:
            sector_teaser = f"Sectors in focus: {' & '.join(names)}."

    # Top stories headlines (max 3, no stock picks revealed)
    stories = news_briefing.get("top_stories", [])[:3]
    news_lines = []
    for s in stories:
        icon = {"POSITIVE": "🟢", "NEGATIVE": "🔴", "NEUTRAL": "⚪"}.get(
            s.get("impact", ""), "•"
        )
        news_lines.append(f"{icon} {s.get('headline', '')}")

    cta = (
        f"\nJoin our FREE WhatsApp group to get today's top stock picks:\n{free_group_link}"
        if free_group_link
        else "\nDM us to join our FREE WhatsApp group for today's top stock picks."
    )

    parts = [
        f"📊 PSX Market Update — {today}",
        "",
        bias_line,
        f"KSE-100: {kse} ({kse_chg})   |   {breadth}",
        "",
        summary,
        "",
    ]

    if news_lines:
        parts.append("Today's key developments:")
        parts.extend(news_lines)
        parts.append("")

    if sector_teaser:
        parts.append(sector_teaser)
        parts.append("")

    # NCCPL teaser — mention insider activity without naming stocks
    insider, fipi = _load_nccpl()
    insider_buy_count  = len(insider.get("buy_signals",  []))
    insider_sell_count = len(insider.get("sell_signals", []))
    foreign_buy_count  = len(fipi.get("foreign_buying",  []))

    if insider_buy_count > 0 or foreign_buy_count > 0:
        nccpl_line = []
        if insider_buy_count > 0:
            nccpl_line.append(
                f"Company insiders made BUY moves on {insider_buy_count} stock(s) this week."
            )
        if foreign_buy_count > 0:
            nccpl_line.append(
                f"Foreign institutional investors are actively buying {foreign_buy_count} stock(s) today."
            )
        parts.append("Insider & Institutional Activity:")
        parts.extend(nccpl_line)
        parts.append("")

    parts.append("Our analysts have identified stocks to WATCH and AVOID for today's session.")
    parts.append(cta)
    parts.append("")
    parts.append("#PSX #KSE100 #PakistanStocks #StockMarket #Trading #Investing")

    return "\n".join(parts)


# ── TIER 2: FREE WHATSAPP GROUP ──────────────────────────────────

def format_free_whatsapp_post(report: dict, news_briefing: dict,
                               paid_channel_link: str = "") -> str:
    """
    Summary for the free WhatsApp group.
    - Market overview + sentiment
    - Top 3 conventional BUY picks: symbol + entry range only (no targets/SL)
    - Top 2 Shariah BUY picks: symbol + entry range
    - CTA to paid channel for full analysis
    """
    today    = report.get("report_date", datetime.now().strftime("%Y-%m-%d"))
    overview = report.get("market_overview", {})
    bias     = overview.get("session_bias", "NEUTRAL")
    kse      = overview.get("kse100_level", "N/A")
    kse_chg  = overview.get("kse100_change_pct", "N/A")
    kmi      = overview.get("kmi30_level", "N/A")
    summary  = overview.get("summary", "")

    s_icon = {"BULLISH": "📈", "BEARISH": "📉", "NEUTRAL": "➡️", "CAUTIOUS": "⚠️"}.get(bias, "📊")

    lines = []
    lines.append(f"📊 *PSX Free Signal — {today}*")
    lines.append(f"{s_icon} *{bias}*  |  KSE-100: {kse} ({kse_chg})  |  KMI-30: {kmi}")
    lines.append(f"\n{summary}")

    # Top 3 news headlines only
    stories = news_briefing.get("top_stories", [])[:3]
    if stories:
        lines.append("\n*Key News:*")
        for s in stories:
            icon = {"POSITIVE": "🟢", "NEGATIVE": "🔴", "NEUTRAL": "⚪"}.get(
                s.get("impact", ""), "•"
            )
            lines.append(f"{icon} {s.get('headline', '')}")

    # Top 3 conventional buys — entry range only, NO targets or SL
    conv_buys = report.get("conventional_portfolio", {}).get("buy_picks", [])[:3]
    if conv_buys:
        lines.append("\n*🟢 Stocks to Watch (Entry Zone):*")
        for b in conv_buys:
            sc = " ☪️" if b.get("shariah_compliant") else ""
            lines.append(
                f"• *{b.get('symbol', '')}*{sc}  "
                f"Entry: Rs{b.get('entry_range', '?')}  "
                f"[{b.get('confidence', '')}]"
            )

    # Top 2 Shariah buys — entry range only
    shar_buys = report.get("shariah_portfolio", {}).get("buy_picks", [])[:2]
    if shar_buys:
        lines.append("\n*☪️ Shariah Picks (Entry Zone):*")
        for b in shar_buys:
            lines.append(
                f"• *{b.get('symbol', '')}*  "
                f"Entry: Rs{b.get('entry_range', '?')}  "
                f"[{b.get('confidence', '')}]"
            )

    # NCCPL hint — tease insider data without full details
    insider, fipi = _load_nccpl()
    insider_buys  = insider.get("buy_signals",  [])
    foreign_buys  = fipi.get("foreign_buying",  [])
    activity_sigs  = insider.get("activity_signals", [])
    strong_insider = [s for s in insider_buys
                      if s.get("signal_strength") in ("VERY_HIGH", "HIGH")]
    strong_foreign = [s for s in foreign_buys
                      if s.get("signal_strength") in ("VERY_HIGH", "HIGH")]
    any_activity   = bool(strong_insider or activity_sigs)

    if any_activity or strong_foreign:
        lines.append("\n" + "─" * 35)
        lines.append("*NCCPL Alert:*")
        if strong_insider:
            lines.append(
                f"Director/Executive BUY on *{len(strong_insider)}* stock(s) this week."
            )
        elif activity_sigs:
            lines.append(
                f"Insider disclosure filings on *{len(activity_sigs)}* stock(s) this week "
                f"— directors changing their positions."
            )
        if strong_foreign:
            lines.append(
                f"Foreign institutional buying on *{len(strong_foreign)}* stock(s) today."
            )
        lines.append("_Full details + which stocks in paid channel only._")

    lines.append("\n" + "─" * 35)
    lines.append(
        "*Want full targets, stop-loss, 10+10 picks & Shariah analysis?*"
    )
    if paid_channel_link:
        lines.append(f"Join our paid channel: {paid_channel_link}")
    else:
        lines.append("Reply *PAID* to get access to the full daily report.")

    lines.append("\n_For educational purposes only. Not financial advice._")
    return "\n".join(lines)


# ── TIER 3: PAID WHATSAPP ────────────────────────────────────────

def format_paid_whatsapp_post(report: dict, news_briefing: dict) -> str:
    """Full report for paid subscribers — delegates to trading_agent formatter."""
    from trading_agent import format_whatsapp_report
    return format_whatsapp_report(report, news_briefing)


# ── TIER 4: COMPREHENSIVE REPORT ─────────────────────────────────

def format_comprehensive_report(report: dict, news_briefing: dict) -> str:
    """
    Deep-dive document format — complete analysis for reading, not messaging.
    Includes full macro context, story-by-story analysis, both portfolios,
    sector rotation, and risk/opportunity breakdown.
    """
    today   = report.get("report_date", datetime.now().strftime("%Y-%m-%d"))
    gen_at  = report.get("generated_at", datetime.now().isoformat())[:19]
    SEP     = "═" * 62
    sep     = "─" * 62
    lines   = []

    def h(title):
        lines.append(f"\n{SEP}")
        lines.append(f"  {title}")
        lines.append(SEP)

    # ── HEADER ────────────────────────────────────────────────────
    lines.append(SEP)
    lines.append(f"  PSX COMPREHENSIVE DAILY REPORT — {today}")
    lines.append(f"  Generated: {gen_at}")
    lines.append(SEP)

    # ── EXECUTIVE SUMMARY ─────────────────────────────────────────
    ov          = report.get("market_overview", {})
    brief_ov    = news_briefing.get("overall_sentiment", "")
    bias        = ov.get("session_bias", "N/A")
    kse100      = ov.get("kse100_level", "N/A")
    kse100_chg  = ov.get("kse100_change_pct", "")
    kmi30       = ov.get("kmi30_level", "N/A")
    breadth     = ov.get("market_breadth", "")
    summary     = ov.get("summary", "")
    brief_reason = news_briefing.get("sentiment_reasoning", "")

    h("EXECUTIVE SUMMARY")
    lines.append(f"  Session Bias  : {bias}")
    lines.append(f"  News Sentiment: {brief_ov}")
    lines.append(f"  KSE-100       : {kse100}  {kse100_chg}")
    lines.append(f"  KMI-30        : {kmi30}")
    lines.append(f"  Market Breadth: {breadth}")
    if summary:
        lines.append(f"\n  {summary}")
    if brief_reason:
        lines.append(f"\n  {brief_reason}")

    # ── MACRO ENVIRONMENT ─────────────────────────────────────────
    macro = news_briefing.get("macro_factors", {})
    if macro:
        h("MACRO ENVIRONMENT")
        for label, key in [
            ("PKR/USD",     "pkr_usd"),
            ("SBP Policy",  "sbp_policy_rate"),
            ("IMF Status",  "imf_status"),
            ("Inflation",   "inflation"),
            ("Oil Prices",  "oil_prices"),
        ]:
            val = macro.get(key, "")
            if val:
                lines.append(f"  {label:<14}: {val}")
        for other in macro.get("other", []):
            if other:
                lines.append(f"  • {other}")

    # ── KEY NEWS ANALYSIS ─────────────────────────────────────────
    stories = news_briefing.get("top_stories", [])
    if stories:
        h(f"KEY NEWS ANALYSIS  ({len(stories)} stories)")
        for i, s in enumerate(stories, 1):
            impact = s.get("impact", "")
            score  = s.get("impact_score", "")
            icon   = {"POSITIVE": "🟢", "NEGATIVE": "🔴", "NEUTRAL": "⚪"}.get(impact, "•")
            lines.append(f"\n  [{i}] {icon} {s.get('headline', '')}  [{impact}  score:{score}/10]")
            lines.append(f"      Source: {s.get('source', '')}")
            if s.get("what"):
                lines.append(f"\n      WHAT            : {s['what']}")
            if s.get("why_it_matters"):
                lines.append(f"      WHY IT MATTERS  : {s['why_it_matters']}")
            if s.get("second_order_effect"):
                lines.append(f"      SECOND ORDER    : {s['second_order_effect']}")
            if s.get("shariah_lens") and s["shariah_lens"].upper() != "N/A":
                lines.append(f"      SHARIAH LENS    : {s['shariah_lens']}")
            if s.get("trader_action"):
                lines.append(f"      TRADER ACTION   : {s['trader_action']}")
            sectors = ", ".join(s.get("sectors_affected", []))
            if sectors:
                lines.append(f"      Sectors         : {sectors}")
            companies = ", ".join(s.get("companies_mentioned", []))
            if companies:
                lines.append(f"      Companies       : {companies}")
            lines.append(f"      {sep[:55]}")

    # ── SECTOR OUTLOOK ────────────────────────────────────────────
    sector_outlook = news_briefing.get("sector_outlook", [])
    if sector_outlook:
        h("SECTOR OUTLOOK")
        for so in sector_outlook:
            icon   = {"POSITIVE": "✅", "NEGATIVE": "❌", "NEUTRAL": "⚠️"}.get(so.get("outlook",""), "•")
            shariah = "  ☪" if so.get("shariah_compliant") else ""
            lines.append(f"\n  {icon}  {so.get('sector','')}{shariah}  [{so.get('outlook','')}]")
            if so.get("reasoning"):
                lines.append(f"     {so['reasoning']}")

    # ── helper: format portfolio ──────────────────────────────────
    def _portfolio_block(portfolio: dict, title: str):
        if not portfolio:
            return
        h(title)
        note = portfolio.get("note", "")
        if note:
            lines.append(f"  {note}\n")

        buys   = portfolio.get("buy_picks",   [])
        avoids = portfolio.get("avoid_picks", [])

        if buys:
            lines.append(f"  🟢  BUY PICKS  ({len(buys)} stocks)")
            lines.append(f"  {sep}")
            for b in buys:
                sc = "  ☪" if b.get("shariah_compliant") else ""
                lines.append(f"\n  #{b.get('rank','')}  {b.get('symbol',''):8s}{sc}  {b.get('company_name','')}")
                lines.append(f"      Price   : Rs {b.get('current_price','?')}   Entry: Rs {b.get('entry_range','?')}")
                lines.append(f"      Target  : Rs {b.get('target_price','?')}   Stop Loss: Rs {b.get('stop_loss','?')}")
                lines.append(f"      Sector  : {b.get('sector','')}   Volume: {b.get('volume_today','')}   Chg: {b.get('change_pct_today','')}")
                lines.append(f"      Confidence: {b.get('confidence','')}")
                if b.get("reasoning"):
                    lines.append(f"      Reasoning : {b['reasoning']}")
                if b.get("risk"):
                    lines.append(f"      Risk      : ⚠ {b['risk']}")
                lines.append(f"      {sep[:55]}")

        if avoids:
            lines.append(f"\n  🔴  AVOID  ({len(avoids)} stocks)")
            lines.append(f"  {sep}")
            for a in avoids:
                lines.append(f"\n  #{a.get('rank','')}  {a.get('symbol',''):8s}  Rs {a.get('current_price','?')}")
                if a.get("reasoning") or a.get("reason"):
                    lines.append(f"      {a.get('reasoning') or a.get('reason','')}")
                lines.append(f"      {sep[:55]}")

    _portfolio_block(report.get("conventional_portfolio"), "CONVENTIONAL PORTFOLIO  (KSE-100 / KSE-100PR)")
    _portfolio_block(report.get("shariah_portfolio"),      "SHARIAH PORTFOLIO  (KMI-30 / KMIALLSHR)")

    # ── KEY RISKS & OPPORTUNITIES ─────────────────────────────────
    risks = news_briefing.get("key_risks", [])
    opps  = news_briefing.get("key_opportunities", [])
    if risks or opps:
        h("RISKS & OPPORTUNITIES")
        if risks:
            lines.append("  KEY RISKS:")
            for r in risks:
                lines.append(f"  ⚠  {r}")
        if opps:
            lines.append("\n  KEY OPPORTUNITIES:")
            for o in opps:
                lines.append(f"  ★  {o}")

    # ── SHARIAH NOTE ──────────────────────────────────────────────
    shariah_note = news_briefing.get("shariah_market_note", "")
    if shariah_note:
        h("SHARIAH MARKET NOTE  ☪")
        lines.append(f"  {shariah_note}")

    # ── FOOTER ────────────────────────────────────────────────────
    h("DISCLAIMER")
    lines.append(f"  {report.get('disclaimer', 'For educational purposes only. Not financial advice. Always do your own research.')}")
    lines.append(f"\n  Tokens used: {report.get('tokens_used', 'N/A')}")
    lines.append(SEP)

    return "\n".join(lines)
