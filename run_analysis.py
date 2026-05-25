"""
run_analysis.py  —  Main Pipeline Trigger
------------------------------------------
Runs the full PSX analysis pipeline from a single command:

  STEP 1  Fetch fresh data         (news + PSX market data)
  STEP 2  News Agent               (extract key stories, macro, sector impacts)
  STEP 3  Trading Agent            (10 BUY + 10 AVOID — conventional + Shariah)
  STEP 4  Facebook Post            (teaser — no stock names, CTA to free group)
  STEP 5  Free WhatsApp Group      (top 3 picks, entry range only, CTA to paid)
  STEP 6  Paid WhatsApp            (full report — 40 picks, targets, stop-loss)

Usage:
    python run_analysis.py                  # full run
    python run_analysis.py --dry-run        # skip all sends, just print
    python run_analysis.py --no-fetch       # skip fetch, use existing data files
    python run_analysis.py --no-fb          # skip Facebook post
    python run_analysis.py --no-free-wa     # skip free WhatsApp group
    python run_analysis.py --no-paid-wa     # skip paid WhatsApp
"""

import os
import sys
import json
import logging

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import argparse
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

_ROOT = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR = os.path.join(_ROOT, "backend", "data")

os.makedirs("logs",                              exist_ok=True)
os.makedirs(os.path.join(_DATA_DIR, "reports"), exist_ok=True)
os.makedirs("posts",                             exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join("logs", "analysis.log"), encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

FREE_WA_GROUP_LINK = os.getenv("FREE_WA_GROUP_LINK", "")
PAID_CHANNEL_LINK  = os.getenv("PAID_CHANNEL_LINK", "")
FREE_WHATSAPP_TO   = os.getenv("FREE_WHATSAPP_TO", "")


def _banner(step: str, total: int, label: str):
    print(f"\n{'='*65}")
    print(f"  STEP {step}/{total}  —  {label}")
    print(f"{'='*65}")


def run_pipeline(fetch: bool = True, dry_run: bool = False,
                 skip_fb: bool = False, skip_free_wa: bool = False,
                 skip_paid_wa: bool = False) -> bool:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*65}")
    print(f"  PSX MULTI-AGENT ANALYSIS PIPELINE")
    print(f"  {ts}")
    print(f"{'='*65}")

    # ── STEP 1: Fetch fresh data ──────────────────────────────────
    _banner(1, 6, "Fetching fresh data")

    if fetch:
        try:
            import fetch_and_save as fas
            fas.TIMESTAMP = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            scraped = {}
            scraped["Google News"]     = fas.fetch_google_news()
            scraped["Dawn Business"]   = fas.fetch_dawn()
            scraped["Profit Pakistan"] = fas.fetch_profit_pk()
            scraped["PSX Data Portal"] = fas.fetch_psx_portal()
            fas.build_llm_input(scraped)
            print("[STEP 1] Done — fresh data saved to ./data/")
        except Exception as e:
            logger.error(f"Data fetch failed: {e}")
            print(f"[WARN] Fetch failed ({e}). Continuing with existing data.")
    else:
        print("[STEP 1] Skipped — using existing data files.")

    # ── STEP 2: News Agent ────────────────────────────────────────
    _banner(2, 6, "News Analyst Agent — extracting key stories")

    try:
        from news_agent import run_news_analysis
        news_briefing = run_news_analysis(days_back=1)

        print(f"\n  Sentiment  : {news_briefing.get('overall_sentiment','N/A')}")
        print(f"  Reasoning  : {news_briefing.get('sentiment_reasoning','')[:100]}")
        stories = news_briefing.get("top_stories", [])
        print(f"  Stories    : {len(stories)} extracted")
        for s in stories[:5]:
            impact_icon = {"POSITIVE": "[+]", "NEGATIVE": "[-]", "NEUTRAL": "[ ]"}.get(
                s.get("impact", ""), "[ ]"
            )
            print(f"    {impact_icon} {s.get('headline','')[:75]}")

        print(f"\n[STEP 2] News analysis complete. "
              f"Tokens: {news_briefing.get('_meta',{}).get('tokens_used','N/A')}")

    except Exception as e:
        logger.error(f"News agent failed: {e}", exc_info=True)
        print(f"[ERROR] News agent failed: {e}")
        return False

    # ── STEP 3: Trading Agent ─────────────────────────────────────
    _banner(3, 6, "Trading Analyst Agent — 10 BUY + 10 AVOID")

    try:
        from trading_agent import run_trading_analysis
        report = run_trading_analysis(news_briefing, save_history=True)

        date_str    = datetime.now().strftime("%Y%m%d_%H%M")
        report_path = os.path.join(_DATA_DIR, "reports", f"report_{date_str}.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump({"news_briefing": news_briefing, "trading_report": report},
                      f, ensure_ascii=False, indent=2)

        overview    = report.get("market_overview", {})
        conv        = report.get("conventional_portfolio", {})
        shar        = report.get("shariah_portfolio", {})
        conv_buys   = conv.get("buy_picks", [])
        conv_avoids = conv.get("avoid_picks", [])
        shar_buys   = shar.get("buy_picks", [])
        shar_avoids = shar.get("avoid_picks", [])

        print(f"\n  Bias       : {overview.get('session_bias','N/A')}")
        print(f"  KSE-100    : {overview.get('kse100_level','N/A')} ({overview.get('kse100_change_pct','N/A')})")
        print(f"  KMI-30     : {overview.get('kmi30_level','N/A')}")

        print(f"\n  [CONVENTIONAL] BUY picks ({len(conv_buys)}):")
        for b in conv_buys:
            sc = "[S]" if b.get("shariah_compliant") else "   "
            print(f"    {b.get('rank',''):>2}.  {sc} {b.get('symbol',''):8s}  "
                  f"Rs{b.get('current_price','?'):>8s}  -> Rs{b.get('target_price','?')}  "
                  f"[{b.get('confidence','')}]")

        print(f"\n  [CONVENTIONAL] AVOID picks ({len(conv_avoids)}):")
        for a in conv_avoids:
            print(f"    {a.get('rank',''):>2}.       {a.get('symbol',''):8s}  Rs{a.get('current_price','?'):>8s}")

        print(f"\n  [SHARIAH KMI] BUY picks ({len(shar_buys)}):")
        for b in shar_buys:
            print(f"    {b.get('rank',''):>2}.  {b.get('symbol',''):8s}  "
                  f"Rs{b.get('current_price','?'):>8s}  -> Rs{b.get('target_price','?')}  "
                  f"[{b.get('confidence','')}]  ({b.get('kmi_index','')})")

        print(f"\n  [SHARIAH KMI] AVOID picks ({len(shar_avoids)}):")
        for a in shar_avoids:
            print(f"    {a.get('rank',''):>2}.  {a.get('symbol',''):8s}  Rs{a.get('current_price','?'):>8s}")

        print(f"\n  Tokens used: {report.get('tokens_used','N/A')}")
        print(f"  Saved to   : {report_path}")
        print(f"\n[STEP 3] Trading analysis complete.")

    except Exception as e:
        logger.error(f"Trading agent failed: {e}", exc_info=True)
        print(f"[ERROR] Trading agent failed: {e}")
        return False

    # ── Format all 3 content tiers ────────────────────────────────
    from content_formatter import (
        format_facebook_post,
        format_free_whatsapp_post,
        format_paid_whatsapp_post,
    )
    fb_post       = format_facebook_post(report, news_briefing, FREE_WA_GROUP_LINK)
    free_wa_post  = format_free_whatsapp_post(report, news_briefing, PAID_CHANNEL_LINK)
    paid_wa_post  = format_paid_whatsapp_post(report, news_briefing)

    # ── Save posts to disk ────────────────────────────────────────
    date_str = datetime.now().strftime("%Y%m%d_%H%M")
    posts = {
        f"posts/{date_str}_facebook.txt":  fb_post,
        f"posts/{date_str}_free_wa.txt":   free_wa_post,
        f"posts/{date_str}_paid_wa.txt":   paid_wa_post,
    }
    for path, content in posts.items():
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    print(f"[POSTS] Saved to posts/{date_str}_facebook.txt / _free_wa.txt / _paid_wa.txt")

    # ── STEP 4: Facebook Post ─────────────────────────────────────
    _banner(4, 6, "Posting teaser to Facebook Page")

    if dry_run or skip_fb:
        reason = "DRY RUN" if dry_run else "SKIPPED (--no-fb)"
        print(f"[{reason}] Facebook post preview:")
        print("-" * 60)
        print(fb_post)
        print("-" * 60)
    else:
        try:
            from fb_poster import post_to_facebook
            result = post_to_facebook(fb_post)
            if result["success"]:
                print(f"[STEP 4] Facebook post published. ID: {result['post_id']}")
            else:
                print(f"[STEP 4] Facebook post failed: {result['error']}")
                logger.error(f"FB post failed: {result['error']}")
        except Exception as e:
            logger.error(f"Facebook post exception: {e}")
            print(f"[ERROR] Facebook post failed: {e}")

    # ── STEP 5: Free WhatsApp Group ───────────────────────────────
    _banner(5, 6, "Sending summary to Free WhatsApp Group")

    if dry_run or skip_free_wa:
        reason = "DRY RUN" if dry_run else "SKIPPED (--no-free-wa)"
        print(f"[{reason}] Free WhatsApp preview:")
        print("-" * 60)
        print(free_wa_post)
        print("-" * 60)
    else:
        try:
            from whatsapp_sender import send_analysis_to_whatsapp
            to = FREE_WHATSAPP_TO
            if not to:
                print("[STEP 5] FREE_WHATSAPP_TO not set in .env — skipping.")
            else:
                ok = send_analysis_to_whatsapp(free_wa_post, to=to)
                if ok:
                    print(f"[STEP 5] Free group message sent to {to}")
                else:
                    print("[STEP 5] Free group send failed — check logs.")
        except Exception as e:
            logger.error(f"Free WA send failed: {e}")
            print(f"[ERROR] Free WA send failed: {e}")

    # ── STEP 6: Paid WhatsApp ─────────────────────────────────────
    _banner(6, 6, "Sending full report to Paid WhatsApp")

    if dry_run or skip_paid_wa:
        reason = "DRY RUN" if dry_run else "SKIPPED (--no-paid-wa)"
        print(f"[{reason}] Paid WhatsApp preview:")
        print("-" * 60)
        print(paid_wa_post)
        print("-" * 60)
    else:
        try:
            from whatsapp_sender import send_analysis_to_whatsapp
            ok = send_analysis_to_whatsapp(paid_wa_post)
            if ok:
                print("[STEP 6] Full report sent to paid subscribers.")
            else:
                print("[STEP 6] Paid WA send failed — check logs.")
        except Exception as e:
            logger.error(f"Paid WA send failed: {e}")
            print(f"[ERROR] Paid WA failed: {e}")

    print(f"\n{'='*65}")
    print(f"  PIPELINE COMPLETE — {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*65}\n")
    return True


# ── ENTRY POINT ──────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PSX Multi-Agent Analysis Pipeline")
    parser.add_argument("--dry-run",     action="store_true",
                        help="Run everything but skip all sends — print previews instead")
    parser.add_argument("--no-fetch",    action="store_true",
                        help="Skip data fetch, use existing files in ./data/")
    parser.add_argument("--no-fb",       action="store_true",
                        help="Skip Facebook post")
    parser.add_argument("--no-free-wa",  action="store_true",
                        help="Skip free WhatsApp group message")
    parser.add_argument("--no-paid-wa",  action="store_true",
                        help="Skip paid WhatsApp send")
    args = parser.parse_args()

    ok = run_pipeline(
        fetch       = not args.no_fetch,
        dry_run     = args.dry_run,
        skip_fb     = args.no_fb,
        skip_free_wa= args.no_free_wa,
        skip_paid_wa= args.no_paid_wa,
    )
    sys.exit(0 if ok else 1)
