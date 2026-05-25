"""
fetch_and_save.py
-----------------
Fetches raw data from every target source and saves each as a .json file
in the /data folder.

Usage:
    python fetch_and_save.py

Output files (in ./backend/data/ folder):
    01_google_news.json
    02_dawn_business.json
    03_profit_pakistan.json
    04_psx_data_portal.json
    05_general_news.json
    06_nccpl_insider.json       <-- NCCPL insider transactions (director buy/sell)
    07_nccpl_fipi.json          <-- NCCPL FIPI/LIPI (foreign investor flows)
    COMBINED_for_LLM.txt   <-- cleaned text sent to OpenAI
"""

import os
import json
import requests
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime
from nccpl_scraper import fetch_insider_transactions, fetch_fipi_lipi
import price_history as ph

# ── CONFIG ──────────────────────────────────────────────────────
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend", "data")
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

def save_json(filename: str, data: dict):
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    size = os.path.getsize(path)
    print(f"  [OK] Saved -> {path}  ({size:,} bytes)")
    return data


def clean_text(html_str: str, max_len: int = 500) -> str:
    text = BeautifulSoup(html_str, "lxml").get_text(separator=" ", strip=True)
    return text[:max_len].strip()


def parse_table_to_records(table) -> list:
    """Convert an HTML <table> into a list of dicts using header row as keys."""
    rows = table.find_all("tr")
    if not rows:
        return []

    # Find header row (th tags)
    headers = []
    for row in rows:
        ths = row.find_all("th")
        if ths:
            headers = [th.get_text(strip=True) for th in ths]
            break

    records = []
    for row in rows:
        cells = row.find_all("td")
        if not cells:
            continue
        values = [c.get_text(strip=True) for c in cells]
        if headers and len(headers) == len(values):
            records.append(dict(zip(headers, values)))
        elif values:
            # Fallback: use positional keys if headers don't match
            records.append({f"col_{i}": v for i, v in enumerate(values)})

    return records


# ── SOURCE 1: GOOGLE NEWS RSS ────────────────────────────────────
def fetch_google_news():
    print("\n[1/4] Google News RSS...")
    url = (
        "https://news.google.com/rss/search"
        "?q=PSX+KSE-100+Pakistan+stock+market"
        "&hl=en-PK&gl=PK&ceid=PK:en"
    )
    result = {
        "source": "Google News RSS",
        "query": "PSX KSE-100 Pakistan stock market",
        "fetched_at": TIMESTAMP,
        "total_found": 0,
        "articles": []
    }
    try:
        feed = feedparser.parse(url)
        entries = feed.entries
        result["total_found"] = len(entries)
        for i, e in enumerate(entries, 1):
            result["articles"].append({
                "rank": i,
                "title": e.get("title", ""),
                "published": e.get("published", ""),
                "link": e.get("link", ""),
                "summary": clean_text(e.get("summary", ""), max_len=500)
            })
        print(f"  -> {len(entries)} articles found")
        if not entries:
            r = requests.get(url, headers=HEADERS, timeout=10)
            result["http_status"] = r.status_code
            result["error"] = "No entries returned from RSS feed"
    except Exception as e:
        result["error"] = str(e)
        print(f"  [ERROR] Error: {e}")

    return save_json("01_google_news.json", result)


# ── SOURCE 2: DAWN BUSINESS RSS + PAGE ──────────────────────────
def fetch_dawn():
    print("\n[2/4] Dawn Business...")
    result = {
        "source": "Dawn Business",
        "fetched_at": TIMESTAMP,
        "rss": {
            "url": "https://www.dawn.com/feeds/business",
            "total_found": 0,
            "articles": []
        },
        "direct_scrape": {
            "url": "https://www.dawn.com/business",
            "http_status": None,
            "headlines": []
        }
    }

    # RSS feed
    try:
        feed = feedparser.parse("https://www.dawn.com/feeds/business")
        result["rss"]["total_found"] = len(feed.entries)
        for i, e in enumerate(feed.entries, 1):
            result["rss"]["articles"].append({
                "rank": i,
                "title": e.get("title", ""),
                "date": e.get("published", ""),
                "link": e.get("link", ""),
                "summary": clean_text(e.get("summary", ""), max_len=400)
            })
        print(f"  -> RSS: {len(feed.entries)} articles")
    except Exception as e:
        result["rss"]["error"] = str(e)
        print(f"  [ERROR] RSS Error: {e}")

    # Direct page scrape
    try:
        r = requests.get("https://www.dawn.com/business", headers=HEADERS, timeout=15)
        result["direct_scrape"]["http_status"] = r.status_code
        soup = BeautifulSoup(r.text, "lxml")
        headlines = soup.find_all(["h2", "h3", "h4"])
        for h in headlines:
            text = h.get_text(strip=True)
            if len(text) > 10:
                result["direct_scrape"]["headlines"].append(text)
        print(f"  -> Scrape: {len(result['direct_scrape']['headlines'])} headlines (HTTP {r.status_code})")
    except Exception as e:
        result["direct_scrape"]["error"] = str(e)
        print(f"  [ERROR] Scrape Error: {e}")

    return save_json("02_dawn_business.json", result)


# ── SOURCE 3: PROFIT BY PAKISTAN TODAY ──────────────────────────
def fetch_profit_pk():
    print("\n[3/4] Profit by Pakistan Today...")
    result = {
        "source": "Profit Pakistan",
        "fetched_at": TIMESTAMP,
        "rss": {
            "url": "https://profit.pakistantoday.com.pk/feed/",
            "total_found": 0,
            "articles": []
        },
        "direct_scrape": {
            "url": "https://profit.pakistantoday.com.pk/",
            "http_status": None,
            "headlines": []
        }
    }

    # RSS
    try:
        feed = feedparser.parse("https://profit.pakistantoday.com.pk/feed/")
        result["rss"]["total_found"] = len(feed.entries)
        for i, e in enumerate(feed.entries, 1):
            result["rss"]["articles"].append({
                "rank": i,
                "title": e.get("title", ""),
                "date": e.get("published", ""),
                "link": e.get("link", ""),
                "summary": clean_text(e.get("summary", ""), max_len=400)
            })
        print(f"  -> RSS: {len(feed.entries)} articles")
    except Exception as e:
        result["rss"]["error"] = str(e)
        print(f"  [ERROR] RSS Error: {e}")

    # Direct page scrape
    try:
        r = requests.get("https://profit.pakistantoday.com.pk/", headers=HEADERS, timeout=15)
        result["direct_scrape"]["http_status"] = r.status_code
        soup = BeautifulSoup(r.text, "lxml")
        for h in soup.find_all(["h1", "h2", "h3"]):
            text = h.get_text(strip=True)
            if len(text) > 10:
                result["direct_scrape"]["headlines"].append(text)
        print(f"  -> Scrape: {len(result['direct_scrape']['headlines'])} headlines (HTTP {r.status_code})")
    except Exception as e:
        result["direct_scrape"]["error"] = str(e)
        print(f"  [ERROR] Scrape Error: {e}")

    return save_json("03_profit_pakistan.json", result)


# ── SOURCE 4B: GENERAL / MACRO NEWS ─────────────────────────────
# Covers: SBP rate decisions, IMF updates, PKR/dollar, geopolitics,
# government policy, war/conflict — all market-moving non-PSX news.
def fetch_general_news():
    print("\n[3b] General Macro & Geopolitical News...")
    result = {
        "source": "General Pakistan News (Macro & Geopolitical)",
        "fetched_at": TIMESTAMP,
        "total_found": 0,
        "articles": []
    }

    RSS_SOURCES = [
        # Broader Google News queries
        {
            "label": "Google News — Macro Pakistan",
            "url": (
                "https://news.google.com/rss/search"
                "?q=Pakistan+SBP+interest+rate+IMF+dollar+PKR+inflation+economy+budget"
                "&hl=en-PK&gl=PK&ceid=PK:en"
            )
        },
        {
            "label": "Google News — Pakistan Policy & Global",
            "url": (
                "https://news.google.com/rss/search"
                "?q=Pakistan+government+policy+India+war+sanctions+oil+OPEC+Fed+rate"
                "&hl=en-PK&gl=PK&ceid=PK:en"
            )
        },
        # Express Tribune — broad Pakistan news
        {
            "label": "Express Tribune",
            "url": "https://tribune.com.pk/feed/rss/latest"
        },
        # The Nation
        {
            "label": "The Nation Pakistan",
            "url": "https://nation.com.pk/feed/"
        },
        # ARY News
        {
            "label": "ARY News",
            "url": "https://arynews.tv/feed/"
        },
    ]

    all_articles = []
    for src in RSS_SOURCES:
        try:
            feed = feedparser.parse(src["url"])
            count = 0
            for e in feed.entries[:15]:
                title = e.get("title", "").strip()
                if not title:
                    continue
                all_articles.append({
                    "source_label": src["label"],
                    "title":        title,
                    "published":    e.get("published", ""),
                    "link":         e.get("link", ""),
                    "summary":      clean_text(e.get("summary", ""), max_len=400),
                })
                count += 1
            print(f"  -> {src['label']}: {count} articles")
        except Exception as exc:
            print(f"  [WARN] {src['label']}: {exc}")

    result["articles"]    = all_articles
    result["total_found"] = len(all_articles)
    return save_json("05_general_news.json", result)


# ── SOURCE 4: PSX DATA PORTAL — ALL DATA ────────────────────────
def fetch_psx_portal():
    print("\n[4/4] PSX Data Portal (all data)...")

    result = {
        "source": "PSX Data Portal",
        "base_url": "https://dps.psx.com.pk",
        "fetched_at": TIMESTAMP,
        "indices": [],
        "all_stocks": [],
        "by_index": {},
        "by_sector": {},
        "errors": []
    }

    # ── Endpoint 1: Indices ──────────────────────────────────────
    # PSX table headers: Index | High | Low | Current | Change | % Change
    try:
        r = requests.get("https://dps.psx.com.pk/indices", headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "lxml")
        tables = soup.find_all("table")
        raw_index_records = []
        if tables:
            for table in tables:
                raw_index_records.extend(parse_table_to_records(table))

        result["indices"] = raw_index_records

        # Normalise into a clean dict keyed by index name
        indices_live = {}
        for rec in raw_index_records:
            def _strip(v):
                return str(v or "").replace(",", "").replace("%", "").strip()

            name = (rec.get("Index") or rec.get("INDEX") or
                    rec.get("index") or rec.get("col_0") or "").strip()
            if not name:
                continue
            try:
                indices_live[name] = {
                    "name":       name,
                    "level":      float(_strip(rec.get("Current") or rec.get("CURRENT") or rec.get("col_3") or "0")) or None,
                    "high":       float(_strip(rec.get("High")    or rec.get("HIGH")    or rec.get("col_1") or "0")) or None,
                    "low":        float(_strip(rec.get("Low")     or rec.get("LOW")     or rec.get("col_2") or "0")) or None,
                    "change":     float(_strip(rec.get("Change")  or rec.get("CHANGE")  or rec.get("col_4") or "0")),
                    "change_pct": float(_strip(rec.get("% Change") or rec.get("% CHG") or rec.get("col_5") or "0")),
                }
            except (ValueError, TypeError):
                pass

        result["indices_live"] = indices_live
        print(f"  -> Indices: {len(raw_index_records)} records  ({list(indices_live.keys())})")
    except Exception as e:
        result["errors"].append({"endpoint": "indices", "error": str(e)})
        result["indices_live"] = {}
        print(f"  [ERROR] Indices Error: {e}")

    # ── Endpoint 2: Market Watch — All Stocks ────────────────────
    # The server ignores the ?type param and always returns all stocks.
    # We fetch once and split by the LISTED IN field ourselves.
    try:
        r = requests.get("https://dps.psx.com.pk/market-watch", headers=HEADERS, timeout=20)
        soup = BeautifulSoup(r.text, "lxml")
        tables = soup.find_all("table")
        stocks = []
        if tables:
            for table in tables:
                stocks.extend(parse_table_to_records(table))

        result["all_stocks"] = stocks
        print(f"  -> All Stocks: {len(stocks)} records (HTTP {r.status_code})")

        # Group by index (LISTED IN field may contain comma-separated index names)
        by_index = {}
        by_sector = {}
        for s in stocks:
            listed_in = s.get("LISTED IN", "")
            sector = s.get("SECTOR", "UNKNOWN")

            for idx in [x.strip() for x in listed_in.split(",") if x.strip()]:
                by_index.setdefault(idx, []).append(s)

            by_sector.setdefault(sector, []).append(s)

        result["by_index"] = {k: v for k, v in sorted(by_index.items())}
        result["by_sector"] = {k: v for k, v in sorted(by_sector.items())}
        print(f"  -> Grouped into {len(result['by_index'])} indices, {len(result['by_sector'])} sectors")

        # ── Compute reliable index stats from stock data ─────────────
        # (HTML-scraped 'indices' table has unstable field names;
        #  this is computed from the market-watch data we know works.)
        DISPLAY_INDICES = ["KSE100", "KSE100PR", "KMI30", "KMIALLSHR"]
        indices_computed = {}
        for idx_name in DISPLAY_INDICES:
            idx_stocks = by_index.get(idx_name, [])
            if not idx_stocks:
                continue
            adv = dec = unc = 0
            total_vol = 0
            changes = []
            for s in idx_stocks:
                try:
                    def _pf(v):
                        return float(str(v or "0").replace(",", "")) or 0
                    ldcp = _pf(s.get("LDCP") or s.get("Ldcp") or s.get("ldcp") or 0)
                    curr = _pf(s.get("CURRENT") or s.get("Current") or s.get("current") or ldcp)
                    vol  = int(_pf(s.get("VOLUME") or s.get("Volume") or s.get("volume") or 0))
                    total_vol += vol
                    if ldcp > 0:
                        pct_chg = (curr - ldcp) / ldcp * 100
                        changes.append(pct_chg)
                        if curr > ldcp:   adv += 1
                        elif curr < ldcp: dec += 1
                        else:             unc += 1
                except Exception:
                    pass
            avg_chg = round(sum(changes) / len(changes), 2) if changes else 0
            indices_computed[idx_name] = {
                "name":       idx_name,
                "stocks":     len(idx_stocks),
                "advancing":  adv,
                "declining":  dec,
                "unchanged":  unc,
                "avg_chg":    avg_chg,
                "total_vol":  total_vol,
            }
        result["indices_computed"] = indices_computed

    except Exception as e:
        result["errors"].append({"endpoint": "market-watch", "error": str(e)})
        print(f"  [ERROR] Market Watch Error: {e}")

    # Merge actual index levels from PSX /indices scraping into breadth stats
    for idx_name, live_data in result.get("indices_live", {}).items():
        if idx_name in result.get("indices_computed", {}):
            result["indices_computed"][idx_name].update({
                "level":      live_data.get("level"),
                "high":       live_data.get("high"),
                "low":        live_data.get("low"),
                "change":     live_data.get("change"),
                "change_pct": live_data.get("change_pct"),
            })
        elif live_data.get("level"):
            result.setdefault("indices_computed", {})[idx_name] = live_data

    # ── Fetch actual KSE-100 level from Stooq ────────────────────
    try:
        r = requests.get(
            "https://stooq.com/q/l/?s=^kse&f=sd2t2ohlcvc&e=csv",
            headers=HEADERS, timeout=10
        )
        if r.status_code == 200:
            lines = r.text.strip().splitlines()
            if len(lines) >= 2:
                parts = lines[1].split(",")
                # CSV columns: Symbol,Date,Time,Open,High,Low,Close,Volume
                kse100_close = float(parts[6]) if len(parts) > 6 else None
                kse100_open  = float(parts[3]) if len(parts) > 3 else None
                kse100_high  = float(parts[4]) if len(parts) > 4 else None
                kse100_low   = float(parts[5]) if len(parts) > 5 else None
                kse100_date  = parts[1] if len(parts) > 1 else ""

                if kse100_close and "KSE100" in result.get("indices_computed", {}):
                    result["indices_computed"]["KSE100"]["level"]      = round(kse100_close, 2)
                    result["indices_computed"]["KSE100"]["open"]       = round(kse100_open  or kse100_close, 2)
                    result["indices_computed"]["KSE100"]["high"]       = round(kse100_high  or kse100_close, 2)
                    result["indices_computed"]["KSE100"]["low"]        = round(kse100_low   or kse100_close, 2)
                    result["indices_computed"]["KSE100"]["level_date"] = kse100_date
                    print(f"  -> KSE-100 from Stooq: {kse100_close:,.0f} ({kse100_date})")
                elif kse100_close:
                    result.setdefault("indices_computed", {})
                    result["indices_computed"]["KSE100"] = {
                        "name": "KSE100", "level": round(kse100_close, 2),
                        "level_date": kse100_date,
                    }
    except Exception as e:
        result["errors"].append({"endpoint": "stooq_kse100", "error": str(e)})
        print(f"  [WARN] Stooq KSE-100: {e}")

    # ── Endpoint 3: Market Summary ───────────────────────────────
    try:
        r = requests.get("https://dps.psx.com.pk/summary", headers=HEADERS, timeout=15)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "lxml")
            tables = soup.find_all("table")
            summary_records = []
            for table in tables:
                summary_records.extend(parse_table_to_records(table))
            result["market_summary"] = summary_records
            print(f"  -> Market Summary: {len(summary_records)} records")
        else:
            result["market_summary"] = []
            print(f"  [WARN]  Market Summary: HTTP {r.status_code} (endpoint may be unavailable)")
    except Exception as e:
        result["errors"].append({"endpoint": "summary", "error": str(e)})

    return save_json("04_psx_data_portal.json", result)


# ── SOURCE 6: NCCPL INSIDER TRANSACTIONS ─────────────────────────
def fetch_nccpl_insider():
    print("\n[6/7] NCCPL Insider Transactions...")
    data = fetch_insider_transactions(days_back=7)
    return save_json("06_nccpl_insider.json", data)


# ── SOURCE 7: NCCPL FIPI / LIPI ──────────────────────────────────
def fetch_nccpl_fipi():
    print("\n[7/7] NCCPL FIPI/LIPI (Foreign Investor Flows)...")
    data = fetch_fipi_lipi()
    return save_json("07_nccpl_fipi.json", data)


# ── COMBINE ALL FOR LLM ──────────────────────────────────────────
def build_llm_input(all_data: dict):
    print("\n[+] Building COMBINED_for_LLM.txt...")
    lines = [
        "=" * 80,
        "COMBINED PSX NEWS DATA — INPUT TO LLM",
        f"Generated: {TIMESTAMP}",
        "=" * 80,
        ""
    ]

    for source_name, data in all_data.items():
        lines.append("─" * 60)
        lines.append(f"FROM: {source_name}")
        lines.append("─" * 60)

        if isinstance(data, dict):
            # Google News
            if "articles" in data:
                for a in data["articles"]:
                    lines.append(f"[{a.get('rank', '')}] {a.get('title', '')}")
                    if a.get("summary"):
                        lines.append(f"    {a['summary'][:300]}")
                    lines.append("")

            # Dawn / Profit (rss + scrape)
            elif "rss" in data:
                for a in data["rss"].get("articles", []):
                    lines.append(f"[{a.get('rank', '')}] {a.get('title', '')}")
                    lines.append(f"    Date: {a.get('date', '')}")
                    if a.get("summary"):
                        lines.append(f"    {a['summary'][:300]}")
                    lines.append("")
                lines.append("Scraped Headlines:")
                for h in data.get("direct_scrape", {}).get("headlines", []):
                    lines.append(f"  • {h}")
                lines.append("")

            # NCCPL Insider Transactions
            elif "buy_signals" in data:
                buy_sigs  = data.get("buy_signals", [])
                sell_sigs = data.get("sell_signals", [])
                if data.get("error"):
                    lines.append(f"[UNAVAILABLE] {data['error']}")
                else:
                    lines.append(f"Total transactions: {data.get('total_found', 0)}")
                    if buy_sigs:
                        lines.append("INSIDER BUY SIGNALS (bullish):")
                        for s in buy_sigs:
                            lines.append(
                                f"  BUY  [{s['signal_strength']:9s}] {s['symbol']:8s} — {s['summary']}"
                            )
                    if sell_sigs:
                        lines.append("INSIDER SELL SIGNALS (bearish):")
                        for s in sell_sigs:
                            lines.append(
                                f"  SELL [{s['signal_strength']:9s}] {s['symbol']:8s} — {s['summary']}"
                            )
                lines.append("")

            # NCCPL FIPI/LIPI
            elif "foreign_buying" in data:
                if data.get("error"):
                    lines.append(f"[UNAVAILABLE] {data['error']}")
                else:
                    lines.append(f"Total stocks tracked: {data.get('total_found', 0)}")
                    fb = data.get("foreign_buying", [])
                    fs = data.get("foreign_selling", [])
                    if fb:
                        lines.append("TOP FOREIGN BUYING (institutional accumulation — bullish):")
                        for s in fb[:10]:
                            lines.append(
                                f"  {s['symbol']:8s} [{s['signal_strength']:9s}] — {s['summary']}"
                            )
                    if fs:
                        lines.append("TOP FOREIGN SELLING (institutional distribution — bearish):")
                        for s in fs[:10]:
                            lines.append(
                                f"  {s['symbol']:8s} [{s['signal_strength']:9s}] — {s['summary']}"
                            )
                lines.append("")

            # PSX Data Portal
            elif "indices" in data:
                lines.append("INDICES:")
                for rec in data.get("indices", []):
                    if isinstance(rec, dict):
                        lines.append("  " + " | ".join(f"{k}: {v}" for k, v in rec.items()))
                lines.append("")
                lines.append("ALL STOCKS (top 100 by volume):")
                stocks = data.get("all_stocks", [])
                for rec in stocks[:100]:
                    if isinstance(rec, dict):
                        lines.append("  " + " | ".join(f"{k}: {v}" for k, v in rec.items()))
                lines.append("")
                kse100 = data.get("by_index", {}).get("KSE100", [])
                if kse100:
                    lines.append(f"KSE-100 STOCKS ({len(kse100)} stocks):")
                    for rec in kse100[:50]:
                        if isinstance(rec, dict):
                            lines.append("  " + " | ".join(f"{k}: {v}" for k, v in rec.items()))
                    lines.append("")

    lines += [
        "",
        "=" * 80,
        "END OF DATA",
        "=" * 80
    ]

    out = "\n".join(lines)
    path = os.path.join(OUTPUT_DIR, "COMBINED_for_LLM.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(out)
    size = os.path.getsize(path)
    print(f"  [OK] Saved -> {path}  ({size:,} bytes)")


# ── MAIN ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("PSX DATA FETCHER — Saving output from each source as JSON")
    print(f"Time: {TIMESTAMP}")
    print(f"Output folder: ./{OUTPUT_DIR}/")
    print("=" * 60)

    all_data = {}
    all_data["Google News"]              = fetch_google_news()
    all_data["Dawn Business"]            = fetch_dawn()
    all_data["Profit Pakistan"]          = fetch_profit_pk()
    all_data["General News"]             = fetch_general_news()
    all_data["PSX Data Portal"]          = fetch_psx_portal()
    all_data["NCCPL Insider Transactions"] = fetch_nccpl_insider()
    all_data["NCCPL FIPI/LIPI"]          = fetch_nccpl_fipi()

    print("\n[+] Updating rolling price history...")
    ph.append_today(all_data["PSX Data Portal"])

    build_llm_input(all_data)

    print("\n" + "=" * 60)
    print("DONE. Check your ./backend/data/ folder:")
    print("=" * 60)
    for f in sorted(os.listdir(OUTPUT_DIR)):
        path = os.path.join(OUTPUT_DIR, f)
        size = os.path.getsize(path)
        print(f"   {f:45s}  {size:,} bytes")
    print()
