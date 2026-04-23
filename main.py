"""
main.py
-------
PSX Marketing Bot — Main Orchestrator

Runs 3 scheduled posts per day:
  08:30 AM → Morning Briefing
  01:00 PM → Midday Market Update
  07:00 PM → Evening Recap + FOMO

Usage:
  python main.py              # Run scheduler (keeps running 24/7)
  python main.py --test       # Generate posts but DON'T post to FB (safe test)
  python main.py --post now   # Generate and post all 3 RIGHT NOW
  python main.py --post morning   # Post only morning post right now
"""

import os
import sys
import json
import logging
import schedule
import time
from datetime import datetime
from dotenv import load_dotenv

from news_scraper     import get_top_news_summary
from post_generator   import generate_post, generate_all_three_posts, save_posts_to_file
from facebook_poster  import post_to_facebook, verify_page_access

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/bot.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)

AUTO_POST    = os.getenv("AUTO_POST", "false").lower() == "true"
POST_TIME_1  = os.getenv("POST_TIME_1", "08:30")
POST_TIME_2  = os.getenv("POST_TIME_2", "13:00")
POST_TIME_3  = os.getenv("POST_TIME_3", "19:00")

POST_SCHEDULE = {
    POST_TIME_1: "morning",
    POST_TIME_2: "midday",
    POST_TIME_3: "evening",
}


# ─── CORE FUNCTION ──────────────────────────────────────────────

def run_post_job(post_type: str, test_mode: bool = False):
    """Full pipeline: fetch news → generate post → post to Facebook."""
    logger.info(f"\n{'='*55}")
    logger.info(f"🚀 Starting {post_type.upper()} post job")
    logger.info(f"{'='*55}")

    # 1. Fetch latest news
    logger.info("📰 Fetching latest PSX news...")
    try:
        news_summary = get_top_news_summary(max_articles=6)
        logger.info("✅ News fetched successfully")
    except Exception as e:
        logger.error(f"❌ News fetch failed: {e}")
        news_summary = "KSE-100 market is active today. Pakistan economy news ongoing."

    # 2. Generate post content
    logger.info(f"🤖 Generating {post_type} post via OpenAI...")
    try:
        post = generate_post(post_type, news_summary)
        content = post["content"]
    except Exception as e:
        logger.error(f"❌ Post generation failed: {e}")
        return

    # 3. Save draft to file
    log_file = f"logs/{post_type}_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    save_posts_to_file([post], log_file)

    # 4. Print preview
    logger.info(f"\n{'─'*55}")
    logger.info(f"📋 POST PREVIEW ({post_type.upper()}):")
    logger.info(f"{'─'*55}")
    print(f"\n{content}\n")
    logger.info(f"{'─'*55}")

    # 5. Post to Facebook (if not test mode and AUTO_POST is on)
    if test_mode:
        logger.info("🧪 TEST MODE — Skipping Facebook post. Draft saved.")
        return

    if AUTO_POST:
        logger.info("📤 AUTO_POST=true — Posting to Facebook...")
        result = post_to_facebook(content)
        if result["success"]:
            logger.info(f"✅ Posted! ID: {result['post_id']}")
        else:
            logger.error(f"❌ Facebook post failed: {result.get('error')}")
    else:
        logger.info("⏸️  AUTO_POST=false — Draft saved. Set AUTO_POST=true in .env to post automatically.")


def run_all_three(test_mode: bool = False):
    """Generate and post all 3 posts back to back."""
    for post_type in ["morning", "midday", "evening"]:
        run_post_job(post_type, test_mode=test_mode)
        if not test_mode:
            time.sleep(5)


# ─── SCHEDULER SETUP ────────────────────────────────────────────

def setup_schedule():
    """Set up the daily schedule."""
    for time_str, post_type in POST_SCHEDULE.items():
        schedule.every().day.at(time_str).do(run_post_job, post_type=post_type)
        logger.info(f"⏰ Scheduled: {post_type.upper()} post at {time_str}")

    logger.info("\n✅ Scheduler is running. Press Ctrl+C to stop.\n")

    while True:
        schedule.run_pending()
        time.sleep(30)


# ─── ENTRY POINT ────────────────────────────────────────────────

if __name__ == "__main__":
    os.makedirs("logs", exist_ok=True)

    args = sys.argv[1:]

    # python main.py --test
    if "--test" in args:
        logger.info("🧪 Running in TEST MODE — no Facebook posts will be made")
        run_all_three(test_mode=True)

    # python main.py --post now
    elif "--post" in args:
        idx = args.index("--post")
        target = args[idx + 1] if idx + 1 < len(args) else "all"

        if target == "now" or target == "all":
            run_all_three(test_mode=False)
        elif target in ["morning", "midday", "evening"]:
            run_post_job(target, test_mode=False)
        else:
            print(f"Unknown target: {target}. Use: morning | midday | evening | now")

    # python main.py → start scheduler
    else:
        logger.info("🤖 PSX Marketing Bot Starting...")
        logger.info(f"   AUTO_POST = {AUTO_POST}")
        logger.info(f"   Schedule  = {POST_TIME_1} | {POST_TIME_2} | {POST_TIME_3}")

        if AUTO_POST:
            if not verify_page_access():
                logger.error("❌ Facebook credentials invalid. Fix .env and restart.")
                sys.exit(1)

        setup_schedule()