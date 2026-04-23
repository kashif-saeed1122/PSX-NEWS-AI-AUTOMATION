"""
fetch_and_save.py
-----------------
Run this script to fetch raw data from every target website
and save each source to a separate .txt file in the /data folder.

Usage:
    python fetch_and_save.py

Output files (in ./data/ folder):
    01_google_news.txt
    02_dawn_business.txt
    03_profit_pakistan.txt
    04_thenews_business.txt
    05_psx_data_portal.txt
    06_arif_habib.txt
    COMBINED_for_LLM.txt   <-- THIS is what gets sent to OpenAI
"""

import os
import json
import requests
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime

# ── CONFIG ──────────────────────────────────────────────────────
OUTPUT_DIR = "data"
os.makedirs(OUTPUT_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

TIMESTAMP = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# ── HELPER ──────────────────────────────────────────────────────

def save(filename: str, content: str):
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    size = len(content)
    print(f"  ✅ Saved → {path}  ({size} chars)")
    return content


def section(title: str) -> str:
    line = "=" * 70
    return f"\n{line}\n{title}\nFetched at: {TIMESTAMP}\n{line}\n"


# ── SOURCE 1: GOOGLE NEWS RSS ────────────────────────────────────
def fetch_google_news():
    print("\n[1/6] Google News RSS...")
    url = (
        "https://news.google.com/rss/search"
        "?q=PSX+KSE-100+Pakistan+stock+market"
        "&hl=en-PK&gl=PK&ceid=PK:en"
    )
    out = section("SOURCE: Google News RSS — PSX / KSE-100")
    try:
        feed = feedparser.parse(url)
        entries = feed.entries
        out += f"Total articles found: {len(entries)}\n\n"
        for i, e in enumerate(entries[:10], 1):
            out += f"--- Article {i} ---\n"
            out += f"Title     : {e.get('title', 'N/A')}\n"
            out += f"Published : {e.get('published', 'N/A')}\n"
            out += f"Link      : {e.get('link', 'N/A')}\n"
            summary = BeautifulSoup(e.get('summary', ''), 'lxml').get_text()
            out += f"Summary   : {summary[:500]}\n\n"
        if not entries:
            out += "⚠️  No entries returned (possible block or empty feed)\n"
            out += f"Raw HTTP status: checking...\n"
            r = requests.get(url, headers=HEADERS, timeout=10)
            out += f"HTTP Status: {r.status_code}\n"
            out += f"Raw response (first 500 chars):\n{r.text[:500]}\n"
    except Exception as e:
        out += f"❌ ERROR: {e}\n"
    return save("01_google_news.txt", out)


# ── SOURCE 2: DAWN BUSINESS RSS + PAGE ──────────────────────────
def fetch_dawn():
    print("\n[2/6] Dawn Business...")
    out = section("SOURCE: Dawn.com — Business Section")

    # RSS feed
    out += "\n--- DAWN RSS FEED ---\n"
    try:
        rss_url = "https://www.dawn.com/feeds/business"
        feed = feedparser.parse(rss_url)
        out += f"RSS entries found: {len(feed.entries)}\n\n"
        for i, e in enumerate(feed.entries[:8], 1):
            out += f"[{i}] {e.get('title', 'N/A')}\n"
            out += f"    Date   : {e.get('published', 'N/A')}\n"
            out += f"    Link   : {e.get('link', 'N/A')}\n"
            summary = BeautifulSoup(e.get('summary', ''), 'lxml').get_text()
            out += f"    Summary: {summary[:300]}\n\n"
        if not feed.entries:
            out += "⚠️  RSS returned 0 entries\n"
    except Exception as e:
        out += f"❌ RSS Error: {e}\n"

    # Direct page scrape
    out += "\n--- DAWN DIRECT PAGE SCRAPE ---\n"
    try:
        r = requests.get(
            "https://www.dawn.com/business",
            headers=HEADERS, timeout=15
        )
        out += f"HTTP Status: {r.status_code}\n"
        soup = BeautifulSoup(r.text, 'lxml')
        headlines = soup.find_all(['h2', 'h3', 'h4'], limit=20)
        out += f"Headlines scraped: {len(headlines)}\n\n"
        for i, h in enumerate(headlines, 1):
            text = h.get_text(strip=True)
            if len(text) > 10:
                out += f"[{i}] {text}\n"
    except Exception as e:
        out += f"❌ Scrape Error: {e}\n"

    return save("02_dawn_business.txt", out)


# ── SOURCE 3: PROFIT BY PAKISTAN TODAY ──────────────────────────
def fetch_profit_pk():
    print("\n[3/6] Profit by Pakistan Today...")
    out = section("SOURCE: profit.pakistantoday.com.pk")

    # RSS
    out += "\n--- PROFIT.PK RSS FEED ---\n"
    try:
        rss_url = "https://profit.pakistantoday.com.pk/feed/"
        feed = feedparser.parse(rss_url)
        out += f"RSS entries found: {len(feed.entries)}\n\n"
        for i, e in enumerate(feed.entries[:8], 1):
            out += f"[{i}] {e.get('title', 'N/A')}\n"
            out += f"    Date   : {e.get('published', 'N/A')}\n"
            out += f"    Link   : {e.get('link', 'N/A')}\n"
            summary = BeautifulSoup(e.get('summary', ''), 'lxml').get_text()
            out += f"    Summary: {summary[:300]}\n\n"
        if not feed.entries:
            out += "⚠️  RSS returned 0 entries\n"
    except Exception as e:
        out += f"❌ RSS Error: {e}\n"

    # Direct page scrape
    out += "\n--- PROFIT.PK DIRECT SCRAPE ---\n"
    try:
        r = requests.get(
            "https://profit.pakistantoday.com.pk/",
            headers=HEADERS, timeout=15
        )
        out += f"HTTP Status: {r.status_code}\n"
        soup = BeautifulSoup(r.text, 'lxml')
        articles = soup.find_all(['h1', 'h2', 'h3'], limit=20)
        out += f"Headlines scraped: {len(articles)}\n\n"
        for i, a in enumerate(articles, 1):
            text = a.get_text(strip=True)
            if len(text) > 10:
                out += f"[{i}] {text}\n"
    except Exception as e:
        out += f"❌ Scrape Error: {e}\n"

    return save("03_profit_pakistan.txt", out)


# ── SOURCE 4: THE NEWS BUSINESS ──────────────────────────────────
def fetch_thenews():
    print("\n[4/6] The News Business...")
    out = section("SOURCE: thenews.com.pk — Business Section")

    # RSS
    out += "\n--- THE NEWS RSS FEED ---\n"
    try:
        rss_url = "https://www.thenews.com.pk/rss/2/6"
        feed = feedparser.parse(rss_url)
        out += f"RSS entries found: {len(feed.entries)}\n\n"
        for i, e in enumerate(feed.entries[:8], 1):
            out += f"[{i}] {e.get('title', 'N/A')}\n"
            out += f"    Date   : {e.get('published', 'N/A')}\n"
            out += f"    Link   : {e.get('link', 'N/A')}\n"
            summary = BeautifulSoup(e.get('summary', ''), 'lxml').get_text()
            out += f"    Summary: {summary[:300]}\n\n"
        if not feed.entries:
            out += "⚠️  RSS returned 0 entries\n"
    except Exception as e:
        out += f"❌ RSS Error: {e}\n"

    # Direct scrape
    out += "\n--- THE NEWS DIRECT SCRAPE ---\n"
    try:
        r = requests.get(
            "https://www.thenews.com.pk/business",
            headers=HEADERS, timeout=15
        )
        out += f"HTTP Status: {r.status_code}\n"
        soup = BeautifulSoup(r.text, 'lxml')
        headlines = soup.find_all(['h1', 'h2', 'h3'], limit=20)
        out += f"Headlines scraped: {len(headlines)}\n\n"
        for i, h in enumerate(headlines, 1):
            text = h.get_text(strip=True)
            if len(text) > 10:
                out += f"[{i}] {text}\n"
    except Exception as e:
        out += f"❌ Scrape Error: {e}\n"

    return save("04_thenews_business.txt", out)


# ── SOURCE 5: PSX DATA PORTAL ────────────────────────────────────
def fetch_psx_portal():
    print("\n[5/6] PSX Data Portal...")
    out = section("SOURCE: dps.psx.com.pk — Live Index Data")

    endpoints = {
        "Indices"       : "https://dps.psx.com.pk/indices",
        "Market Summary": "https://dps.psx.com.pk/summary",
        "Sector Summary": "https://dps.psx.com.pk/sector-summary",
        "Top Movers"    : "https://dps.psx.com.pk/market-watch",
    }

    for label, url in endpoints.items():
        out += f"\n--- {label} ({url}) ---\n"
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            out += f"HTTP Status: {r.status_code}\n"
            soup = BeautifulSoup(r.text, 'lxml')

            # grab tables if any
            tables = soup.find_all('table')
            if tables:
                out += f"Tables found: {len(tables)}\n"
                for t in tables[:2]:
                    rows = t.find_all('tr')
                    for row in rows[:15]:
                        cells = [c.get_text(strip=True) for c in row.find_all(['td','th'])]
                        if any(cells):
                            out += "  |  ".join(cells) + "\n"
            else:
                # grab all text
                text = soup.get_text(separator="\n", strip=True)
                lines = [l for l in text.splitlines() if len(l.strip()) > 2]
                out += "\n".join(lines[:60]) + "\n"
        except Exception as e:
            out += f"❌ Error: {e}\n"

    return save("05_psx_data_portal.txt", out)


# ── SOURCE 6: ARIF HABIB / TOPLINE SEARCH ───────────────────────
def fetch_arif_habib():
    print("\n[6/6] Arif Habib Market Reports...")
    out = section("SOURCE: arifhabibltd.com — Research / Market Reports")

    urls = [
        "https://arifhabibltd.com/research/market-update",
        "https://arifhabibltd.com/research",
        "https://topline.com.pk/media-publications/morning-note/",
    ]

    for url in urls:
        out += f"\n--- {url} ---\n"
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            out += f"HTTP Status: {r.status_code}\n"
            soup = BeautifulSoup(r.text, 'lxml')
            headlines = soup.find_all(['h1', 'h2', 'h3', 'h4', 'p'], limit=30)
            for h in headlines:
                text = h.get_text(strip=True)
                if len(text) > 15:
                    out += f"  → {text[:200]}\n"
        except Exception as e:
            out += f"❌ Error: {e}\n"

    return save("06_arif_habib.txt", out)


# ── COMBINE ALL FOR LLM ──────────────────────────────────────────
def build_llm_input(all_data: dict):
    print("\n[+] Building COMBINED_for_LLM.txt...")
    out = f"""================================================================================
COMBINED PSX NEWS DATA — INPUT TO LLM
Generated: {TIMESTAMP}
This file shows EXACTLY what will be sent to OpenAI/GPT-4o
================================================================================

"""
    for source_name, content in all_data.items():
        # Strip down to clean text only — no error logs
        lines = content.splitlines()
        clean = [l for l in lines if l.strip() and "❌" not in l]
        out += f"\n{'─'*60}\n"
        out += f"FROM: {source_name}\n"
        out += f"{'─'*60}\n"
        out += "\n".join(clean[:80])   # max 80 lines per source
        out += "\n"

    out += "\n================================================================================\n"
    out += "END OF DATA — THIS IS WHAT GOES INTO THE LLM PROMPT\n"
    out += "================================================================================\n"

    save("COMBINED_for_LLM.txt", out)


# ── MAIN ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("PSX DATA FETCHER — Saving raw output from each source")
    print(f"Time: {TIMESTAMP}")
    print(f"Output folder: ./{OUTPUT_DIR}/")
    print("=" * 60)

    all_data = {}
    all_data["Google News"]      = fetch_google_news()
    all_data["Dawn Business"]    = fetch_dawn()
    all_data["Profit Pakistan"]  = fetch_profit_pk()
    all_data["The News"]         = fetch_thenews()
    all_data["PSX Data Portal"]  = fetch_psx_portal()
    all_data["Arif Habib"]       = fetch_arif_habib()

    build_llm_input(all_data)

    print("\n" + "=" * 60)
    print("DONE. Check your ./data/ folder:")
    print("=" * 60)
    for f in sorted(os.listdir(OUTPUT_DIR)):
        path = os.path.join(OUTPUT_DIR, f)
        size = os.path.getsize(path)
        print(f"  📄 {f:40s}  {size:,} bytes")
    print()