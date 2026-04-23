"""
news_scraper.py
---------------
Scrapes latest PSX / Pakistan finance news from multiple sources:
- Google News RSS (PSX / KSE-100 filter)
- Dawn Business RSS
- Profit by Pakistan Today RSS
- Arif Habib / Topline headlines (fallback)
"""

import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# ─── NEWS SOURCES ──────────────────────────────────────────────
RSS_FEEDS = {
    "Google News PSX": "https://news.google.com/rss/search?q=PSX+KSE-100+Pakistan+stock+market&hl=en-PK&gl=PK&ceid=PK:en",
    "Dawn Business":   "https://www.dawn.com/feeds/business",
    "Profit Pakistan": "https://profit.pakistantoday.com.pk/feed/",
    "The News Business":"https://www.thenews.com.pk/rss/2/6",
}


def fetch_rss_news(max_per_source: int = 3) -> list[dict]:
    """Fetch recent articles from all RSS feeds."""
    articles = []
    for source_name, url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:max_per_source]:
                title   = entry.get("title", "").strip()
                summary = entry.get("summary", entry.get("description", "")).strip()
                link    = entry.get("link", "")
                published = entry.get("published", str(datetime.now().date()))

                # Clean HTML tags from summary
                if summary:
                    soup = BeautifulSoup(summary, "lxml")
                    summary = soup.get_text(separator=" ").strip()

                # Only keep finance-relevant articles
                keywords = ["psx", "kse", "stock", "market", "share", "trading",
                            "economy", "rupee", "pkr", "imf", "sbp", "bank",
                            "cement", "oil", "gas", "pharma", "textile", "invest"]
                text_lower = (title + " " + summary).lower()
                if any(kw in text_lower for kw in keywords):
                    articles.append({
                        "source":    source_name,
                        "title":     title,
                        "summary":   summary[:500],
                        "link":      link,
                        "published": published,
                    })
            logger.info(f"✅ Fetched {min(max_per_source, len(feed.entries))} articles from {source_name}")
        except Exception as e:
            logger.warning(f"⚠️  Could not fetch {source_name}: {e}")

    # Remove duplicates by title similarity
    seen_titles = set()
    unique = []
    for a in articles:
        key = a["title"][:40].lower()
        if key not in seen_titles:
            seen_titles.add(key)
            unique.append(a)

    logger.info(f"📰 Total unique articles fetched: {len(unique)}")
    return unique


def get_kse100_price() -> dict:
    """Scrape current KSE-100 index level from investing.com or fallback."""
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        url = "https://stooq.com/q/l/?s=^kse&f=sd2t2ohlcv&h&e=csv"
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            lines = resp.text.strip().split("\n")
            if len(lines) >= 2:
                parts = lines[1].split(",")
                close = parts[6] if len(parts) > 6 else "N/A"
                return {"index": "KSE-100", "price": close, "date": parts[1]}
    except Exception as e:
        logger.warning(f"Could not fetch KSE-100 price: {e}")
    return {"index": "KSE-100", "price": "N/A", "date": str(datetime.now().date())}


def get_top_news_summary(max_articles: int = 6) -> str:
    """Return a clean text summary of top news for feeding into OpenAI."""
    articles = fetch_rss_news(max_per_source=3)[:max_articles]
    kse      = get_kse100_price()

    lines = [f"KSE-100 Latest: {kse['price']} (as of {kse['date']})", ""]
    for i, a in enumerate(articles, 1):
        lines.append(f"{i}. [{a['source']}] {a['title']}")
        if a["summary"]:
            lines.append(f"   {a['summary'][:200]}")
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(get_top_news_summary())