"""
post_generator.py
-----------------
Uses OpenAI GPT-4.1-mini to convert raw PSX news into
3 ready-to-post Facebook posts per day.

Post types:
  MORNING  (8:30 AM)  — Market briefing + watchlist
  MIDDAY   (1:00 PM)  — Live market update + sector insight
  EVENING  (7:00 PM)  — Recap + FOMO / WhatsApp group CTA
"""

import os
import json
import logging
from openai import OpenAI
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

PAGE_NAME          = os.getenv("PAGE_NAME", "PSX Insider Edge")
WHATSAPP_LINK      = os.getenv("WHATSAPP_GROUP_LINK", "https://chat.whatsapp.com/your-link")

# ─── PROMPTS FOR EACH POST TYPE ─────────────────────────────────

SYSTEM_PROMPT = f"""
You are an expert Pakistani stock market analyst and social media content writer
for the Facebook page "{PAGE_NAME}".

Your job is to write highly engaging Facebook posts that:
1. Start with a POWERFUL hook (first line must stop the scroll)
2. Are based on real, current PSX/KSE-100 news provided
3. Include relevant emojis naturally
4. End with a clear Call-To-Action (CTA) mentioning the paid WhatsApp group
5. Include 4-6 relevant hashtags at the bottom
6. Are written in English
7. Sound human, confident, and like a trusted financial expert

WhatsApp group link for CTAs: {WHATSAPP_LINK}

NEVER make up specific stock prices or fake gains. Use only the news provided.
ALWAYS add a note that this is for educational purposes, not financial advice.
Keep posts between 150-300 words.
"""

POST_PROMPTS = {
    "morning": """
Write a MORNING BRIEFING post (to be posted at 8:30 AM Pakistan time).

Structure:
- Hook: A bold market insight or question that creates curiosity
- 3 bullet points: Key things to watch in today's session
- Watchlist: 2-3 stock tickers worth watching today (from the news context)
- CTA: Follow the page for updates, join WhatsApp group for deep analysis
- Hashtags: #PSXMorningBriefing #KSE100 #PSXInsiderEdge + 3 more

News context:
{news}
""",

    "midday": """
Write a MIDDAY MARKET UPDATE post (to be posted at 1:00 PM Pakistan time).

Structure:
- Hook: A surprising or urgent market fact from today's news
- What's moving and WHY (based on news provided)
- Which sector is hot right now and which to avoid
- Tease: "Our paid group called this move this morning..."
- CTA: Join WhatsApp group link for next alert
- Hashtags: #PSXUpdate #StockMarketPakistan #KSE100 + 3 more

News context:
{news}
""",

    "evening": """
Write an EVENING RECAP + FOMO post (to be posted at 7:00 PM Pakistan time).

Structure:
- Hook: Start with a result, a number, or a "did you know" that creates FOMO
- Recap of what happened in the market today
- What smart traders did vs what average traders did
- Tease 1-2 things the paid WhatsApp group got right today
- Urgency CTA: Limited seats, join tonight
- Hashtags: #PSXInsiderEdge #PaidGroup #StockMarket #Investing + 2 more

News context:
{news}
""",
}


def generate_post(post_type: str, news_summary: str) -> dict:
    """
    Generate a single Facebook post using OpenAI.
    Returns dict with keys: type, content, generated_at
    """
    if post_type not in POST_PROMPTS:
        raise ValueError(f"post_type must be one of: {list(POST_PROMPTS.keys())}")

    user_prompt = POST_PROMPTS[post_type].format(news=news_summary)

    logger.info(f"🤖 Generating {post_type} post via OpenAI...")

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt},
        ],
        temperature=0.85,
        max_tokens=600,
    )

    content = response.choices[0].message.content.strip()

    logger.info(f"✅ {post_type.capitalize()} post generated ({len(content)} chars)")

    return {
        "type":         post_type,
        "content":      content,
        "generated_at": datetime.now().isoformat(),
        "tokens_used":  response.usage.total_tokens,
    }


def generate_all_three_posts(news_summary: str) -> list[dict]:
    """Generate all 3 posts (morning, midday, evening) in one call."""
    posts = []
    for post_type in ["morning", "midday", "evening"]:
        try:
            post = generate_post(post_type, news_summary)
            posts.append(post)
        except Exception as e:
            logger.error(f"❌ Failed to generate {post_type} post: {e}")
    return posts


def save_posts_to_file(posts: list[dict], filepath: str = "logs/today_posts.json"):
    """Save generated posts to a JSON file for review."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(posts, f, indent=2, ensure_ascii=False)
    logger.info(f"💾 Posts saved to {filepath}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from news_scraper import get_top_news_summary
    news = get_top_news_summary()
    posts = generate_all_three_posts(news)
    for p in posts:
        print(f"\n{'='*60}")
        print(f"📌 {p['type'].upper()} POST")
        print('='*60)
        print(p["content"])
    save_posts_to_file(posts)