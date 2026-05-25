"""
nccpl_scraper.py  —  NCCPL / PSX Insider Data Fetcher
-------------------------------------------------------
Fetches datasets relevant to insider and institutional activity:

  1. INSIDER TRANSACTIONS  — director/executive shareholding disclosures
     Source: PSX Company Announcements (publicly accessible via Playwright)
     OCR:    GIF disclosure forms read via OpenAI GPT-4o Vision

  2. FIPI / LIPI           — Foreign & Local Investor Portfolio flows (daily)
     Source: NCCPL website — currently blocked by Cloudflare
     Status: Placeholder with informative error; will work if Cloudflare lifts

  3. PSX DOWNLOADS         — Short Sell, OMTS Block Trades, Futures OI
     Source: dps.psx.com.pk/download/ (plain HTTP, no auth required)

Notes:
  - NCCPL.com.pk is protected by Cloudflare Managed Challenge (blocks all bots)
  - PSX Company Announcements ARE accessible and provide insider disclosure symbols
  - Insider disclosure forms are scanned GIFs — parsed via GPT-4o Vision
"""

import json
import os
import re
import io
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

PSX_DPS    = "https://dps.psx.com.pk"
NCCPL_BASE = "https://www.nccpl.com.pk"


# ── HELPERS ──────────────────────────────────────────────────────────────────

def _playwright_html(url: str, wait_sel: str = "tr", timeout_ms: int = 20000) -> str | None:
    """Load URL in headless Chromium (JS-rendered pages) and return full HTML."""
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
            ctx  = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 900},
            )
            page = ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            try:
                page.wait_for_selector(wait_sel, timeout=8000)
            except PWTimeout:
                pass
            page.wait_for_timeout(2000)
            html = page.content()
            browser.close()
            return html
    except Exception as e:
        print(f"  [WARN] Playwright failed ({url}): {e}")
        return None


def _signal_strength(qty: float, value: float) -> str:
    if value >= 10_000_000 or qty >= 1_000_000:
        return "VERY_HIGH"
    if value >= 2_000_000 or qty >= 200_000:
        return "HIGH"
    if value >= 500_000 or qty >= 50_000:
        return "MEDIUM"
    return "LOW"


def _infer_action(title: str) -> str:
    """Infer BUY/SELL/UNKNOWN from announcement title keywords."""
    t = title.lower()
    if any(w in t for w in ("acqui", "purchas", "buy", "bought", "subscrib")):
        return "BUY"
    if any(w in t for w in ("dispos", "sale", "sold", "transfer out", "reduc")):
        return "SELL"
    return "UNKNOWN"


# ── VISION OCR ───────────────────────────────────────────────────────────────

def _extract_disclosure_from_image(doc_id: str, symbol: str) -> dict | None:
    """
    Send GIF disclosure form to GPT-4o Vision and extract structured data.
    Downloads the GIF locally first (PSX server blocks OpenAI's IP for direct fetch).
    Returns None if OCR fails or OPENAI_API_KEY not set.
    Cost: ~$0.01 per image.
    """
    import base64
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    gif_url = f"{PSX_DPS}/download/image/{doc_id}-1.gif"

    # Download image locally — PSX blocks direct access from OpenAI servers
    try:
        img_resp = requests.get(gif_url, headers=HEADERS, timeout=15)
        if img_resp.status_code != 200 or len(img_resp.content) < 200:
            print(f"  [WARN] Vision OCR: GIF not accessible for doc_id={doc_id} (HTTP {img_resp.status_code})")
            return None
        img_data_url = f"data:image/gif;base64,{base64.b64encode(img_resp.content).decode()}"
    except Exception as e:
        print(f"  [WARN] Vision OCR: GIF download failed for doc_id={doc_id}: {e}")
        return None

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)

        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            max_tokens=400,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": img_data_url, "detail": "high"},
                    },
                    {
                        "type": "text",
                        "text": (
                            f"This is a PSX insider shareholding disclosure form for stock symbol {symbol}. "
                            "Extract these fields and return ONLY valid JSON:\n"
                            '{"person": "full name or empty string", '
                            '"designation": "role/title or empty string", '
                            '"action": "PURCHASE or DISPOSAL or UNKNOWN", '
                            '"shares": integer_or_0, '
                            '"price_per_share": float_or_0, '
                            '"total_value": float_or_0, '
                            '"transaction_date": "DD-Mon-YYYY or empty string", '
                            '"market": "READY or FUTURES"}'
                        ),
                    },
                ],
            }],
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content
        extracted = json.loads(raw)

        action_raw = extracted.get("action", "UNKNOWN").upper()
        if "PURCHASE" in action_raw or "BUY" in action_raw:
            action = "BUY"
        elif "DISPOSAL" in action_raw or "SELL" in action_raw:
            action = "SELL"
        else:
            action = "UNKNOWN"

        return {
            "person":           extracted.get("person", ""),
            "role":             extracted.get("designation", ""),
            "action":           action,
            "quantity":         int(extracted.get("shares", 0) or 0),
            "price":            float(extracted.get("price_per_share", 0) or 0),
            "value":            float(extracted.get("total_value", 0) or 0),
            "transaction_date": extracted.get("transaction_date", ""),
            "market":           extracted.get("market", "READY"),
            "gif_url":          gif_url,
            "ocr_source":       "gpt-4o-vision",
        }

    except Exception as e:
        print(f"  [WARN] Vision OCR failed for doc_id={doc_id}: {e}")
        return None


# ── INSIDER TRANSACTIONS via PSX COMPANY ANNOUNCEMENTS ───────────────────────
# PSX Company Announcements page:
#   dps.psx.com.pk/announcements/companies
#   Table columns: DATE | TIME | SYMBOL | COMPANY NAME | TITLE | link
#
# Insider-related titles include:
#   "Disclosure of Interest by a Director, CEO, or Executive..."
#   "Disclosure of interest by Relevant Persons Holding..."
#   "Change in Shareholding of Substantial Shareholder..."
#   "Acquisition of Shares by ..."
#   "Disposal of Shares by ..."
#
# Excluded (false positives):
#   "Results of Board of Directors Meeting" — NOT a shareholding disclosure
#   Any title with "director" that isn't specifically about insider holdings

INSIDER_TITLE_KEYWORDS = [
    "disclosure of interest",
    "substantial shareholder",
    "change in shareholding",
    "acquisition of shares",
    "disposal of shares",
    "sale of shares",
    "purchase of shares",
]

PSX_COMPANY_ANNOUNCE = f"{PSX_DPS}/announcements/companies"


def _parse_psx_announcements(html: str, days_back: int = 7, use_ocr: bool = True) -> list[dict]:
    """
    Parse PSX company announcements HTML.
    Returns rows where the title suggests insider/director shareholding activity.
    Table columns: DATE(0) | TIME(1) | SYMBOL(2) | COMPANY(3) | TITLE(4) | link(5)

    If use_ocr=True and OPENAI_API_KEY is set, sends each GIF form to GPT-4o Vision
    to extract person name, action (BUY/SELL), quantity, and price.
    """
    soup   = BeautifulSoup(html, "lxml")
    rows   = soup.find_all("tr")
    cutoff = datetime.now() - timedelta(days=days_back)

    results = []
    for row in rows:
        cells = [td.get_text(strip=True) for td in row.find_all("td")]
        if len(cells) < 5:
            continue

        date_str = cells[0]
        symbol   = cells[2].strip().upper()
        company  = cells[3].strip()
        title    = cells[4].strip()

        if not symbol or not title:
            continue

        title_lower = title.lower()
        if not any(kw in title_lower for kw in INSIDER_TITLE_KEYWORDS):
            continue

        # Try to parse date
        date_parsed = None
        for fmt in ("%b %d, %Y", "%B %d, %Y", "%d-%b-%Y", "%Y-%m-%d"):
            try:
                date_parsed = datetime.strptime(date_str, fmt)
                break
            except ValueError:
                continue

        if date_parsed and date_parsed < cutoff:
            continue

        # Extract document ID from GIF/PDF link attributes
        doc_id  = ""
        pdf_url = ""
        for a in row.find_all("a"):
            href     = a.get("href", "")
            data_img = a.get("data-images", "")
            if href and href.startswith("/download/document/"):
                pdf_url = f"{PSX_DPS}{href}"
            if data_img:
                # data-images = "277741-1.gif" → doc_id = "277741"
                m = re.match(r"(\d+)-", data_img)
                if m:
                    doc_id = m.group(1)

        # Infer action from title (fallback if OCR fails or not used)
        action = _infer_action(title)

        tx = {
            "date":            date_str,
            "symbol":          symbol,
            "company":         company,
            "title":           title,
            "action":          action,
            "price":           0.0,
            "quantity":        0,
            "value":           0.0,
            "market":          "READY",
            "role":            "Director/CEO/Executive",
            "person":          "",
            "signal_strength": "LOW",
            "doc_id":          doc_id,
            "pdf_url":         pdf_url,
            "gif_url":         f"{PSX_DPS}/download/image/{doc_id}-1.gif" if doc_id else "",
            "source":          "PSX Company Announcements",
            "ocr_source":      None,
        }

        # Vision OCR: extract real data from the scanned GIF form
        if use_ocr and doc_id:
            ocr = _extract_disclosure_from_image(doc_id, symbol)
            if ocr:
                tx["action"]   = ocr["action"]
                tx["person"]   = ocr["person"]
                tx["role"]     = ocr["role"] or tx["role"]
                tx["quantity"] = ocr["quantity"]
                tx["price"]    = ocr["price"]
                tx["value"]    = ocr["value"]
                tx["market"]   = ocr["market"]
                tx["gif_url"]  = ocr["gif_url"]
                tx["ocr_source"] = ocr["ocr_source"]
                if not ocr["transaction_date"] and date_parsed:
                    tx["transaction_date"] = date_parsed.strftime("%d-%b-%Y")
                else:
                    tx["transaction_date"] = ocr["transaction_date"]
                tx["signal_strength"] = _signal_strength(ocr["quantity"], ocr["value"])

        results.append(tx)

    return results


def _build_signals(transactions: list[dict]) -> tuple[list, list, list]:
    """Build buy/sell/unknown signal lists from transactions."""
    by_symbol: dict[str, list] = {}
    for tx in transactions:
        by_symbol.setdefault(tx["symbol"], []).append(tx)

    buy_signals, sell_signals, activity_signals = [], [], []
    strength_rank = {"VERY_HIGH": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}

    for sym, txs in by_symbol.items():
        buys     = [t for t in txs if t["action"] == "BUY"]
        sells    = [t for t in txs if t["action"] == "SELL"]
        unknowns = [t for t in txs if t["action"] == "UNKNOWN"]

        if buys:
            total_qty   = sum(t["quantity"] for t in buys)
            total_val   = sum(t["value"] for t in buys)
            strength    = _signal_strength(total_qty, total_val) if total_qty else "MEDIUM"
            first       = buys[0]
            qty_str     = f"{total_qty:,}" if total_qty else "undisclosed"
            person_str  = first["person"] or "Insider"
            buy_signals.append({
                "symbol":          sym,
                "company":         first["company"],
                "signal":          "BULLISH",
                "signal_strength": strength,
                "total_quantity":  total_qty,
                "total_value":     total_val,
                "transactions":    len(buys),
                "latest_role":     first["role"],
                "person":          person_str,
                "summary":         (
                    f"Insider BUY {qty_str} shares — {person_str} ({first['role']}) "
                    f"on {first['date']} ({first['company']})"
                ),
            })
        if sells:
            total_qty   = sum(t["quantity"] for t in sells)
            total_val   = sum(t["value"] for t in sells)
            strength    = _signal_strength(total_qty, total_val) if total_qty else "MEDIUM"
            first       = sells[0]
            qty_str     = f"{total_qty:,}" if total_qty else "undisclosed"
            person_str  = first["person"] or "Insider"
            sell_signals.append({
                "symbol":          sym,
                "company":         first["company"],
                "signal":          "BEARISH",
                "signal_strength": strength,
                "total_quantity":  total_qty,
                "total_value":     total_val,
                "transactions":    len(sells),
                "latest_role":     first["role"],
                "person":          person_str,
                "summary":         (
                    f"Insider SELL {qty_str} shares — {person_str} ({first['role']}) "
                    f"on {first['date']} ({first['company']})"
                ),
            })
        if unknowns and not buys and not sells:
            first = unknowns[0]
            activity_signals.append({
                "symbol":          sym,
                "company":         first["company"],
                "signal":          "ACTIVITY_DETECTED",
                "signal_strength": "LOW",
                "total_quantity":  0,
                "total_value":     0.0,
                "transactions":    len(unknowns),
                "latest_role":     first["role"],
                "person":          first.get("person", ""),
                "summary":         (
                    f"Insider disclosure filed on {first['date']} — "
                    "direction unknown (scanned form, OCR inconclusive)"
                ),
            })

    buy_signals.sort(key=lambda x: strength_rank.get(x["signal_strength"], 9))
    sell_signals.sort(key=lambda x: strength_rank.get(x["signal_strength"], 9))
    return buy_signals, sell_signals, activity_signals


def fetch_insider_transactions(days_back: int = 7, use_ocr: bool = True) -> dict:
    """
    Scrape insider transaction disclosures from PSX Company Announcements.
    If use_ocr=True and OPENAI_API_KEY is available, reads actual quantities/prices
    from the GIF disclosure forms via GPT-4o Vision.
    Returns structured buy/sell/activity signals per stock symbol.
    """
    ocr_available = bool(os.getenv("OPENAI_API_KEY")) and use_ocr
    print(f"\n[NCCPL 1/2] Insider Transactions (last {days_back} days) — OCR: {'ON' if ocr_available else 'OFF'}...")

    result = {
        "source":            "PSX Company Announcements (insider disclosures)",
        "fetched_at":        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "days_back":         days_back,
        "ocr_enabled":       ocr_available,
        "total_found":       0,
        "transactions":      [],
        "by_symbol":         {},
        "buy_signals":       [],
        "sell_signals":      [],
        "activity_signals":  [],
        "working_url":       PSX_COMPANY_ANNOUNCE,
        "error":             None,
        "note": (
            "Direction (BUY/SELL) extracted via GPT-4o Vision OCR from scanned GIF forms. "
            "ACTIVITY_DETECTED = disclosure filed but direction could not be read from form."
        ) if ocr_available else (
            "OCR disabled — set OPENAI_API_KEY to extract quantities/prices from disclosure forms. "
            "Direction inferred from title keywords where possible."
        ),
    }

    html = _playwright_html(PSX_COMPANY_ANNOUNCE, wait_sel="tr", timeout_ms=20000)
    if not html:
        result["error"] = "Could not load PSX company announcements page via Playwright"
        print("  [WARN] Could not load PSX announcements")
        return result

    transactions = _parse_psx_announcements(html, days_back=days_back, use_ocr=ocr_available)

    if not transactions:
        result["error"] = "No insider-related announcements found in the last 7 days"
        print("  [INFO] No insider announcements this week")
        return result

    by_symbol: dict[str, list] = {}
    for tx in transactions:
        by_symbol.setdefault(tx["symbol"], []).append(tx)

    buy_signals, sell_signals, activity_signals = _build_signals(transactions)

    result.update({
        "transactions":     transactions,
        "total_found":      len(transactions),
        "by_symbol":        by_symbol,
        "buy_signals":      buy_signals,
        "sell_signals":     sell_signals,
        "activity_signals": activity_signals,
    })

    print(
        f"  -> {len(transactions)} disclosures | "
        f"{len(buy_signals)} BUY | {len(sell_signals)} SELL | "
        f"{len(activity_signals)} activity (direction unknown)"
    )
    return result


# ── FIPI / LIPI (PLACEHOLDER — BLOCKED BY CLOUDFLARE) ────────────────────────

def fetch_fipi_lipi() -> dict:
    """
    FIPI/LIPI daily data from NCCPL.
    STATUS: NCCPL.com.pk is blocked by Cloudflare Managed Challenge.
    Returns placeholder with clear error. Trading agent handles missing data gracefully.
    """
    print(f"\n[NCCPL 2/2] FIPI/LIPI Data (today)...")

    result = {
        "source":          "NCCPL FIPI/LIPI",
        "fetched_at":      datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_found":     0,
        "records":         [],
        "foreign_buying":  [],
        "foreign_selling": [],
        "by_symbol":       {},
        "working_url":     None,
        "error": (
            "NCCPL website (nccpl.com.pk) is protected by Cloudflare Managed Challenge. "
            "Automated access is blocked. FIPI/LIPI data is not available this run. "
            "Insider transaction data from PSX announcements is still active."
        ),
        "status": "BLOCKED_CLOUDFLARE",
    }

    print("  [SKIP] NCCPL blocked by Cloudflare — FIPI data unavailable this run")
    return result


# ── PSX DOWNLOADS — SHORT SELL, OMTS, FUTURES OI ────────────────────────────
# These files are directly downloadable from dps.psx.com.pk/download/
# No auth, no Cloudflare. URL pattern: /download/{type}/{YYYY-MM-DD}.{ext}
# Files are published after market close (usually by 18:00 PKT).

def _get_psx_download(url: str, label: str) -> bytes | None:
    """Download a file from PSX data portal. Returns raw bytes or None."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code == 200 and len(r.content) > 100:
            return r.content
        print(f"  [WARN] {label}: HTTP {r.status_code} — file may not be published yet")
        return None
    except Exception as e:
        print(f"  [WARN] {label}: {e}")
        return None


def fetch_short_sell(date_str: str | None = None) -> dict:
    """
    Fetch PSX Short Sell Volume report (PDF).
    date_str: 'YYYY-MM-DD'. Defaults to today.
    Parses with pdfplumber to extract symbol-level short sell volumes.
    Returns records list with symbol, short_volume, total_volume, pct_short.
    """
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")

    url = f"{PSX_DPS}/download/short_sell_vol/{date_str}.pdf"
    print(f"\n[PSX] Short Sell Volume — {date_str}...")

    result = {
        "source":      "PSX Short Sell Volume",
        "date":        date_str,
        "url":         url,
        "fetched_at":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_found": 0,
        "records":     [],
        "high_short":  [],
        "error":       None,
    }

    raw = _get_psx_download(url, "Short Sell PDF")
    if not raw:
        result["error"] = f"File not available for {date_str} — may not be published yet"
        return result

    try:
        import pdfplumber
        records = []
        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            for page in pdf.pages:
                # Try structured table extraction first
                table = page.extract_table()
                if table:
                    # Find header row (contains "SYMBOL" or "SCRIP")
                    header_idx = None
                    for i, row in enumerate(table):
                        cells = [str(c or "").strip().upper() for c in row]
                        if any(h in cells for h in ("SYMBOL", "SCRIP", "SCRIPT")):
                            header_idx = i
                            break

                    if header_idx is not None:
                        headers = [str(c or "").strip().upper() for c in table[header_idx]]
                        def _col_idx(*names):
                            for name in names:
                                for i, h in enumerate(headers):
                                    if name in h:
                                        return i
                            return None

                        sym_i   = _col_idx("SYMBOL", "SCRIP", "SCRIPT")
                        co_i    = _col_idx("COMPANY", "NAME")
                        shrt_i  = _col_idx("SHORT")
                        total_i = _col_idx("TOTAL", "VOLUME")
                        if sym_i is None:
                            continue

                        for row in table[header_idx + 1:]:
                            if not row:
                                continue
                            cells = [str(c or "").strip() for c in row]
                            sym = cells[sym_i].upper() if sym_i < len(cells) else ""
                            if not sym or len(sym) > 12 or not sym.replace("-","").isalpha():
                                continue
                            try:
                                sv = int(re.sub(r"[,\s]", "", cells[shrt_i] if shrt_i and shrt_i < len(cells) else "0") or 0)
                                tv = int(re.sub(r"[,\s]", "", cells[total_i] if total_i and total_i < len(cells) else "0") or 0)
                                pct = round(sv / tv * 100, 2) if tv > 0 else 0.0
                                records.append({
                                    "symbol":       sym,
                                    "company":      cells[co_i] if co_i and co_i < len(cells) else "",
                                    "short_volume": sv,
                                    "total_volume": tv,
                                    "pct_short":    pct,
                                })
                            except (ValueError, IndexError):
                                continue
                    else:
                        # No header found — try positional parsing (col 0=sym, 2=short, 3=total)
                        for row in table:
                            if not row or len(row) < 3:
                                continue
                            cells = [str(c or "").strip() for c in row]
                            sym = cells[0].upper()
                            if not sym or not sym.replace("-","").isalpha() or len(sym) > 12:
                                continue
                            try:
                                sv  = int(re.sub(r"[,\s]", "", cells[2] or "0") or 0)
                                tv  = int(re.sub(r"[,\s]", "", cells[3] or "0") or 0) if len(cells) > 3 else 0
                                pct = round(sv / tv * 100, 2) if tv > 0 else 0.0
                                records.append({
                                    "symbol": sym, "company": cells[1] if len(cells) > 1 else "",
                                    "short_volume": sv, "total_volume": tv, "pct_short": pct,
                                })
                            except (ValueError, IndexError):
                                continue
                else:
                    # Fallback: parse raw text lines
                    text = page.extract_text() or ""
                    for line in text.splitlines():
                        parts = line.split()
                        if len(parts) < 3:
                            continue
                        sym = parts[0].upper()
                        if not sym.replace("-","").isalpha() or len(sym) > 12 or sym in ("SYMBOL","SCRIP","SR","NO"):
                            continue
                        try:
                            nums = [int(re.sub(r"[,]", "", p)) for p in parts if re.match(r"^[\d,]+$", p)]
                            if len(nums) >= 2:
                                sv, tv = nums[0], nums[1]
                                pct = round(sv / tv * 100, 2) if tv > 0 else 0.0
                                records.append({
                                    "symbol": sym, "company": "",
                                    "short_volume": sv, "total_volume": tv, "pct_short": pct,
                                })
                        except (ValueError, IndexError):
                            continue

        records.sort(key=lambda x: x["short_volume"], reverse=True)
        high_short = [r for r in records if r["pct_short"] >= 5.0]

        result.update({
            "total_found": len(records),
            "records":     records,
            "high_short":  high_short,
        })
        print(f"  -> {len(records)} symbols, {len(high_short)} with >5% short interest")

    except Exception as e:
        result["error"] = f"PDF parse error: {e}"
        print(f"  [WARN] Short sell parse failed: {e}")

    return result


def fetch_omts(date_str: str | None = None) -> dict:
    """
    Fetch PSX Off-Market Transaction System (OMTS / Block Trades) CSV.
    date_str: 'YYYY-MM-DD'. Defaults to today.
    Returns records list with symbol, volume, rate, value, buyer/seller type.
    """
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")

    url = f"{PSX_DPS}/download/omts/{date_str}.csv"
    print(f"\n[PSX] OMTS Block Trades — {date_str}...")

    result = {
        "source":      "PSX OMTS Block Trades",
        "date":        date_str,
        "url":         url,
        "fetched_at":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_found": 0,
        "records":     [],
        "large_blocks": [],
        "error":       None,
    }

    raw = _get_psx_download(url, "OMTS CSV")
    if not raw:
        result["error"] = f"File not available for {date_str} — may not be published yet"
        return result

    try:
        import csv
        text  = raw.decode("utf-8", errors="ignore").lstrip("﻿")
        lines = text.splitlines()

        # Find the actual data header row (contains DATE and SYMBOL CODE)
        header_line_idx = None
        for i, line in enumerate(lines):
            up = line.upper()
            if "SYMBOL" in up and ("DATE" in up or "TURNOVER" in up or "RATE" in up):
                header_line_idx = i
                break

        if header_line_idx is None:
            result["error"] = "OMTS CSV: could not locate header row"
            return result

        # Re-parse from the header row downward
        reader  = csv.DictReader(io.StringIO("\n".join(lines[header_line_idx:])))
        records = []
        for row in reader:
            # Normalize keys (strip whitespace, uppercase)
            row = {
                (k or "").strip().upper().replace(" ", "_"): (v or "").strip()
                for k, v in row.items()
                if (k or "").strip()
            }
            # PSX OMTS header: Date, SETTLEMENT DATE, MEMBER CODE, SYMBOL CODE, COMPANY, TURNOVER, RATE, VALUES
            sym = (row.get("SYMBOL_CODE") or row.get("SYMBOL") or row.get("SCRIP") or "").strip().upper()
            if not sym or len(sym) > 12 or not sym.replace("-","").isalnum():
                continue
            try:
                def _n(keys):
                    for k in keys:
                        v = row.get(k, "")
                        if v:
                            return re.sub(r"[,\s]", "", v)
                    return "0"

                volume = int(float(_n(["TURNOVER", "VOLUME", "QTY", "QUANTITY", "SHARES"])))
                rate   = float(_n(["RATE", "PRICE", "SETTLEMENT_PRICE"]))
                value  = float(_n(["VALUES", "VALUE", "AMOUNT", "CONSIDERATION"]))
                if value == 0 and volume > 0 and rate > 0:
                    value = round(volume * rate, 2)
                records.append({
                    "symbol":  sym,
                    "company": row.get("COMPANY", row.get("COMPANY_NAME", "")),
                    "volume":  volume,
                    "rate":    rate,
                    "value":   value,
                    "members": row.get("MEMBER_CODE", ""),   # buyer/seller broker codes
                    "date":    row.get("DATE", date_str),
                    "settle":  row.get("SETTLEMENT_DATE", ""),
                })
            except (ValueError, KeyError, ZeroDivisionError):
                continue

        records.sort(key=lambda x: x["value"], reverse=True)
        large_blocks = [r for r in records if r["value"] >= 5_000_000]

        result.update({
            "total_found":  len(records),
            "records":      records,
            "large_blocks": large_blocks,
        })
        print(f"  -> {len(records)} block trades, {len(large_blocks)} >= Rs 5M")

    except Exception as e:
        result["error"] = f"CSV parse error: {e}"
        print(f"  [WARN] OMTS parse failed: {e}")

    return result


def fetch_futures_oi(date_str: str | None = None) -> dict:
    """
    Fetch PSX Futures Open Interest XLS report.
    date_str: 'YYYY-MM-DD'. Defaults to today.
    Returns records with symbol, contract, open_interest, change_oi.
    """
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")

    url = f"{PSX_DPS}/download/fut_opn_int/{date_str}.xls"
    print(f"\n[PSX] Futures Open Interest — {date_str}...")

    result = {
        "source":      "PSX Futures Open Interest",
        "date":        date_str,
        "url":         url,
        "fetched_at":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_found": 0,
        "records":     [],
        "rising_oi":   [],
        "falling_oi":  [],
        "error":       None,
    }

    raw = _get_psx_download(url, "Futures OI XLS")
    if not raw:
        result["error"] = f"File not available for {date_str} — may not be published yet"
        return result

    # PSX Futures OI XLS actual structure (verified):
    # Sheet index 1 contains the data (sheet 0 is a summary)
    # Rows 0-5: title + merged header
    # Data rows from row 6 onward:
    #   Col 0: Sr No  | Col 1: Name (e.g. "AGHA-JUN")  | Col 2: Category
    #   Col 3: OI Contracts | Col 4: OI Volume | Col 5: OI Value
    #   Col 6: Free Float Vol | Col 7: % Free Float

    def _parse_futures_sheet(ws_rows, data_start_row=6):
        records = []
        for r_idx, row_vals in enumerate(ws_rows):
            if r_idx < data_start_row:
                continue
            row_vals = [str(v or "").strip() for v in row_vals]
            if not any(row_vals):
                continue

            name = row_vals[1] if len(row_vals) > 1 else ""  # e.g. "AGHA-JUN"
            if not name or name.upper() in ("NAME", ""):
                continue

            # Split "AGHA-JUN" → symbol="AGHA", contract="JUN"
            parts = name.rsplit("-", 1)
            sym      = parts[0].strip().upper() if parts else name.upper()
            contract = parts[1].strip() if len(parts) > 1 else ""

            if not sym or len(sym) > 15:
                continue
            try:
                oi_contracts = int(float(row_vals[3] or 0)) if len(row_vals) > 3 else 0
                oi_volume    = int(float(row_vals[4] or 0)) if len(row_vals) > 4 else 0
                oi_value     = float(row_vals[5] or 0)      if len(row_vals) > 5 else 0.0
                pct_float    = float(row_vals[7] or 0)      if len(row_vals) > 7 else 0.0
                records.append({
                    "symbol":        sym,
                    "contract":      contract,
                    "name":          name,
                    "oi_contracts":  oi_contracts,
                    "open_interest": oi_volume,
                    "oi_value":      oi_value,
                    "pct_freefloat": round(pct_float, 2),
                    "oi_change":     0,   # no prev-day data in file
                    "signal":        "ACTIVE" if oi_contracts > 0 else "NEUTRAL",
                })
            except (ValueError, TypeError, IndexError):
                continue
        return records

    records = []
    parse_error = None

    try:
        import xlrd
        wb  = xlrd.open_workbook(file_contents=raw)
        # Sheet 1 has the per-contract data
        sheet_idx = 1 if wb.nsheets > 1 else 0
        ws  = wb.sheet_by_index(sheet_idx)
        ws_rows = ([ws.cell_value(r, c) for c in range(ws.ncols)] for r in range(ws.nrows))
        records = _parse_futures_sheet(ws_rows)
    except Exception as e1:
        parse_error = str(e1)
        try:
            import openpyxl
            wb  = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
            ws  = list(wb.worksheets)[1] if len(wb.worksheets) > 1 else wb.active
            ws_rows = ([cell.value for cell in row] for row in ws.iter_rows())
            records = _parse_futures_sheet(ws_rows)
            parse_error = None
        except Exception as e2:
            parse_error = f"xlrd: {e1} | openpyxl: {e2}"

    if parse_error and not records:
        result["error"] = f"XLS parse error: {parse_error}"
        print(f"  [WARN] Futures OI parse failed: {parse_error}")
    else:
        # Sort by OI volume descending
        records.sort(key=lambda x: x["open_interest"], reverse=True)
        # "rising_oi" = highest OI contracts (most active), "falling_oi" = lowest non-zero
        top_active  = [r for r in records if r["oi_contracts"] > 0]
        result.update({
            "total_found": len(records),
            "records":     records,
            "rising_oi":   top_active[:20],    # most active contracts
            "falling_oi":  [],                  # requires prev-day comparison
        })
        print(f"  -> {len(records)} contracts, {len(top_active)} active")

    return result


# ── CLI TEST ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("NCCPL SCRAPER — Testing all endpoints")
    print("=" * 60)

    insider = fetch_insider_transactions(days_back=7)
    print(f"\nInsider Results:")
    print(f"  Disclosures found: {insider['total_found']}")
    print(f"  OCR enabled:       {insider.get('ocr_enabled', False)}")
    print(f"  BUY  signals: {len(insider['buy_signals'])}")
    print(f"  SELL signals: {len(insider['sell_signals'])}")
    print(f"  Activity (unknown): {len(insider.get('activity_signals', []))}")
    if insider.get("error"):
        print(f"  Note: {insider['error']}")
    for s in insider["buy_signals"][:5]:
        print(f"  BUY  [{s['signal_strength']}] {s['symbol']:8s}  {s['summary']}")
    for s in insider["sell_signals"][:5]:
        print(f"  SELL [{s['signal_strength']}] {s['symbol']:8s}  {s['summary']}")
    for s in insider.get("activity_signals", [])[:5]:
        print(f"  ACT  [{s['signal_strength']}] {s['symbol']:8s}  {s['summary']}")

    print()
    fipi = fetch_fipi_lipi()
    print(f"FIPI/LIPI: {fipi['total_found']} stocks")
    if fipi.get("error"):
        print(f"  Status: {fipi.get('status', 'N/A')}")
        print(f"  Note: {fipi['error'][:120]}")

    print()
    omts = fetch_omts()
    print(f"OMTS Block Trades: {omts['total_found']} trades, {len(omts['large_blocks'])} large blocks")
    if omts.get("error"):
        print(f"  Note: {omts['error']}")

    print()
    futures = fetch_futures_oi()
    print(f"Futures OI: {futures['total_found']} contracts")
    if futures.get("error"):
        print(f"  Note: {futures['error']}")
