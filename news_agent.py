"""
news_agent.py  —  Agent 1: Deep News Analyst
----------------------------------------------
Reads all raw news articles and does step-by-step reasoning
on each story — not just labelling, but thinking through:

  What happened?  →  Why does it matter to PSX traders?
  →  Which sectors/companies are affected?
  →  What is the second-order effect?
  →  What should a trader do because of this?

Output is a structured briefing passed to the Trading Agent.
"""

import os
import json
import logging
from datetime import datetime, timedelta, timezone
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend", "data")
client   = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ── SYSTEM PROMPT ────────────────────────────────────────────────

SYSTEM_PROMPT = """
You are a senior financial analyst specializing in the Pakistan economy and
PSX (Pakistan Stock Exchange). You have deep knowledge of:
  - How macro events (IMF, SBP rate, PKR/USD, CPEC, oil prices) move sectors
  - Which PSX sectors are Shariah-compliant vs conventional
  - How news flows from macro → sector → individual stocks

Your analysis process (follow this order for EVERY story):
  STEP 1 — WHAT: Summarize the core fact in one sentence
  STEP 2 — WHY IT MATTERS: Explain the direct market implication
  STEP 3 — SECOND ORDER: What is the knock-on effect beyond the obvious?
  STEP 4 — SHARIAH LENS: Does this affect Islamic finance / KMI stocks differently?
  STEP 5 — TRADER ACTION: What should a PSX trader specifically do or watch?

Shariah-compliant sectors on PSX (KMI index stocks):
  Cement, Fertilizer, Power/Energy (IPPs), Technology, Pharma,
  Food & Beverages (halal), Textile, Auto parts, Chemical (non-alcohol),
  Engineering, Modarabas, Islamic Banks (Meezan/MEBL, BankIslami/BISL)

NOT Shariah-compliant (excluded from KMI):
  Conventional Banks (HBL, UBL, MCB, ABL, BAFL, BOP etc.),
  Tobacco (PTC, PAKT), Insurance (conventional),
  Leasing companies (interest-based)

Rules:
- Reason carefully — do not just re-state the headline
- Only include news relevant to stock markets and Pakistani economy
- Be specific: name companies, sectors, PKR amounts, percentages
- Do NOT invent facts — only reason from what is in the articles
- Respond ONLY with valid JSON — no markdown, no extra text

JSON schema:
{
  "briefing_date": "YYYY-MM-DD",
  "overall_sentiment": "BULLISH | BEARISH | NEUTRAL | MIXED",
  "sentiment_reasoning": "2-3 sentence summary of why you reached this view",

  "top_stories": [
    {
      "headline": "your concise headline",
      "source": "source name",
      "impact": "POSITIVE | NEGATIVE | NEUTRAL",
      "impact_score": 1-10,
      "what": "core fact in one sentence",
      "why_it_matters": "direct market implication",
      "second_order_effect": "knock-on effect beyond the obvious",
      "shariah_lens": "how this affects Islamic/KMI stocks specifically, or N/A",
      "trader_action": "specific thing a trader should do or watch because of this",
      "sectors_affected": ["Banking", "Oil & Gas", ...],
      "companies_mentioned": ["OGDC", "HBL", ...]
    }
  ],

  "macro_factors": {
    "pkr_usd": "rate or trend with implication",
    "sbp_policy_rate": "rate or SBP news with implication",
    "imf_status": "IMF news with implication",
    "inflation": "CPI/inflation news with implication",
    "oil_prices": "oil/commodity news with implication",
    "other": ["any other important macro point"]
  },

  "sector_outlook": [
    {
      "sector": "sector name",
      "outlook": "POSITIVE | NEGATIVE | NEUTRAL",
      "shariah_compliant": true or false,
      "reasoning": "2-sentence reasoned explanation, not just a label"
    }
  ],

  "shariah_market_note": "Overall note on how today's news affects the KMI / Islamic portfolio specifically",

  "key_risks": ["specific risk 1 with reasoning", "specific risk 2 with reasoning"],
  "key_opportunities": ["specific opportunity 1 with reasoning", "specific opportunity 2 with reasoning"]
}
"""

# ── DATA LOADER ──────────────────────────────────────────────────

def load_raw_news(days_back: int = 1) -> list:
    """Load yesterday's news from all JSON source files."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    articles = []

    sources = [
        ("01_google_news.json",     "articles"),
        ("02_dawn_business.json",   "rss.articles"),
        ("03_profit_pakistan.json", "rss.articles"),
    ]

    for filename, path_key in sources:
        filepath = os.path.join(DATA_DIR, filename)
        if not os.path.exists(filepath):
            logger.warning(f"Missing: {filepath}")
            continue
        try:
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.warning(f"Could not read {filepath}: {e}")
            continue

        # Navigate nested key path
        obj = data
        for key in path_key.split("."):
            obj = obj.get(key, {}) if isinstance(obj, dict) else {}

        source_name = data.get("source", filename)
        raw_list    = obj if isinstance(obj, list) else []

        for a in raw_list:
            pub_raw = a.get("published") or a.get("date") or ""
            include = True
            try:
                from email.utils import parsedate_to_datetime
                include = parsedate_to_datetime(pub_raw) >= cutoff
            except Exception:
                pass  # include if date cannot be parsed

            if include and a.get("title"):
                articles.append({
                    "source":  source_name,
                    "title":   a.get("title", "").strip(),
                    "summary": a.get("summary", "")[:500].strip(),
                    "date":    pub_raw,
                })

        # Direct-scraped headlines
        for h in data.get("direct_scrape", {}).get("headlines", []):
            if h and len(h) > 15:
                articles.append({
                    "source":  source_name + " (headline)",
                    "title":   h.strip(),
                    "summary": "",
                    "date":    "",
                })

    logger.info(f"News agent loaded {len(articles)} articles (last {days_back} day)")
    return articles


def _build_prompt(articles: list) -> str:
    today     = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    lines = [
        f"Today: {today}. Analyze ALL news from: {yesterday}.",
        f"Total articles: {len(articles)}",
        "",
        "IMPORTANT: For every relevant story, follow the 5-step reasoning process",
        "(WHAT → WHY IT MATTERS → SECOND ORDER → SHARIAH LENS → TRADER ACTION)",
        "=" * 60,
    ]

    for i, a in enumerate(articles, 1):
        lines.append(f"\n--- Article {i} ---")
        lines.append(f"Source : {a['source']}")
        if a['date']:
            lines.append(f"Date   : {a['date']}")
        lines.append(f"Title  : {a['title']}")
        if a["summary"]:
            lines.append(f"Detail : {a['summary']}")

    lines.append("\n" + "=" * 60)
    lines.append("Now produce the full structured JSON briefing using deep reasoning.")
    return "\n".join(lines)


# ── MAIN ────────────────────────────────────────────────────────

def run_news_analysis(days_back: int = 1) -> dict:
    articles = load_raw_news(days_back=days_back)

    if not articles:
        logger.warning("No articles found — returning empty briefing")
        return {
            "briefing_date": datetime.now().strftime("%Y-%m-%d"),
            "overall_sentiment": "NEUTRAL",
            "sentiment_reasoning": "No news articles available for this date.",
            "top_stories": [],
            "macro_factors": {},
            "sector_outlook": [],
            "shariah_market_note": "No data.",
            "key_risks": [],
            "key_opportunities": [],
        }

    prompt = _build_prompt(articles)
    logger.info(f"News agent -> GPT-4.1-mini  ({len(articles)} articles, {len(prompt):,} chars)")

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        temperature=0.2,
        max_tokens=3500,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
    )

    briefing = json.loads(response.choices[0].message.content)
    briefing["_meta"] = {
        "articles_analyzed": len(articles),
        "tokens_used":       response.usage.total_tokens,
        "generated_at":      datetime.now().isoformat(),
    }

    logger.info(
        f"News agent done | Sentiment: {briefing.get('overall_sentiment')} | "
        f"Stories: {len(briefing.get('top_stories', []))} | "
        f"Tokens: {response.usage.total_tokens}"
    )
    return briefing


# ── CLI ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    result = run_news_analysis()
    print(json.dumps(result, indent=2, ensure_ascii=False))
