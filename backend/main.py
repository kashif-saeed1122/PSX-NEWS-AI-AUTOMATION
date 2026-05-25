"""
PSX Automation Dashboard — FastAPI Backend
"""
import os, sys, json, asyncio
from datetime import datetime, timedelta, timezone
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))                  # backend/ dir

from fastapi import FastAPI, Depends, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from jose import JWTError, jwt
from dotenv import load_dotenv

_BACKEND  = os.path.dirname(os.path.abspath(__file__))
_ROOT     = os.path.dirname(_BACKEND)
load_dotenv(os.path.join(_ROOT, ".env"))

app = FastAPI(title="PSX Dashboard API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SECRET_KEY    = os.getenv("JWT_SECRET_KEY", "psx-dashboard-secret-2025")
ALGORITHM     = "HS256"
TOKEN_HOURS   = 8
ADMIN_USER    = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASS    = os.getenv("ADMIN_PASSWORD", "admin123")
DATA_DIR      = os.path.join(_BACKEND, "data")
POSTS_DIR     = os.path.join(_ROOT, "posts")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
_pipeline_lock = False


# ── AUTH ──────────────────────────────────────────────────────────

def make_token(username: str) -> str:
    exp = datetime.utcnow() + timedelta(hours=TOKEN_HOURS)
    return jwt.encode({"sub": username, "exp": exp}, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token: str) -> str:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user = payload.get("sub")
        if not user:
            raise HTTPException(401, "Invalid token")
        return user
    except JWTError:
        raise HTTPException(401, "Invalid token")

def auth(token: str = Depends(oauth2_scheme)):
    return verify_token(token)

@app.post("/auth/login")
def login(form: OAuth2PasswordRequestForm = Depends()):
    if form.username != ADMIN_USER or form.password != ADMIN_PASS:
        raise HTTPException(400, "Incorrect username or password")
    return {"access_token": make_token(form.username), "token_type": "bearer", "username": form.username}

@app.get("/auth/me")
def me(user: str = Depends(auth)):
    return {"username": user}


# ── DATA STATUS ───────────────────────────────────────────────────

def _file_meta(path: str) -> dict:
    if not os.path.exists(path):
        return {"exists": False}
    mtime  = os.path.getmtime(path)
    age_h  = (datetime.now().timestamp() - mtime) / 3600
    return {
        "exists":        True,
        "last_modified": datetime.fromtimestamp(mtime).isoformat(),
        "size_kb":       round(os.path.getsize(path) / 1024, 1),
        "age_hours":     round(age_h, 1),
        "stale":         age_h > 6,
    }

@app.get("/data/status")
def data_status(_: str = Depends(auth)):
    files = {
        "google_news":     os.path.join(DATA_DIR, "01_google_news.json"),
        "dawn_business":   os.path.join(DATA_DIR, "02_dawn_business.json"),
        "profit_pakistan": os.path.join(DATA_DIR, "03_profit_pakistan.json"),
        "psx_data":        os.path.join(DATA_DIR, "04_psx_data_portal.json"),
        "general_news":    os.path.join(DATA_DIR, "05_general_news.json"),
    }
    out = {k: _file_meta(p) for k, p in files.items()}
    rdir = os.path.join(DATA_DIR, "reports")
    rf   = sorted([f for f in os.listdir(rdir) if f.endswith(".json")], reverse=True) \
           if os.path.exists(rdir) else []
    out["latest_report"]    = rf[0] if rf else None
    out["pipeline_running"] = _pipeline_lock
    return out


# ── NEWS ──────────────────────────────────────────────────────────

@app.get("/data/news")
def get_news(_: str = Depends(auth)):
    sources = {
        "google_news":     "01_google_news.json",
        "dawn_business":   "02_dawn_business.json",
        "profit_pakistan": "03_profit_pakistan.json",
        "general_news":    "05_general_news.json",
    }
    out: dict = {}
    for key, fname in sources.items():
        p = os.path.join(DATA_DIR, fname)
        out[key] = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None
    return out


# ── PSX DATA ──────────────────────────────────────────────────────

@app.get("/data/psx")
def get_psx(_: str = Depends(auth)):
    p = os.path.join(DATA_DIR, "04_psx_data_portal.json")
    if not os.path.exists(p):
        raise HTTPException(404, "PSX data not found — run the pipeline first")
    return json.load(open(p, encoding="utf-8"))

@app.post("/data/psx/refresh")
async def refresh_psx(_: str = Depends(auth)):
    """Fetch live PSX portal data only — no AI involved."""
    try:
        import importlib, fetch_and_save as fas
        importlib.reload(fas)
        fas.TIMESTAMP = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, fas.fetch_psx_portal)
        stocks = result.get("all_stocks", [])
        return {
            "success":      True,
            "stocks_count": len(stocks),
            "fetched_at":   fas.TIMESTAMP,
            "message":      f"PSX data refreshed — {len(stocks)} stocks loaded",
        }
    except Exception as e:
        raise HTTPException(500, f"PSX refresh failed: {e}")


# ── REPORTS ───────────────────────────────────────────────────────

@app.get("/data/report")
def get_report(_: str = Depends(auth)):
    rdir  = os.path.join(DATA_DIR, "reports")
    if not os.path.exists(rdir):
        raise HTTPException(404, "No reports found — run the pipeline first")
    files = sorted([f for f in os.listdir(rdir) if f.endswith(".json")], reverse=True)
    if not files:
        raise HTTPException(404, "No reports found — run the pipeline first")
    return json.load(open(os.path.join(rdir, files[0]), encoding="utf-8"))

@app.get("/data/reports/history")
def reports_history(_: str = Depends(auth)):
    rdir = os.path.join(DATA_DIR, "reports")
    if not os.path.exists(rdir):
        return []
    out = []
    for fname in sorted(os.listdir(rdir), reverse=True)[:30]:
        if not fname.endswith(".json"):
            continue
        path = os.path.join(rdir, fname)
        try:
            data    = json.load(open(path, encoding="utf-8"))
            report  = data.get("trading_report", data)
            briefing = data.get("news_briefing", {})
            out.append({
                "filename":  fname,
                "date":      report.get("report_date", fname[:8]),
                "bias":      report.get("market_overview", {}).get("session_bias"),
                "sentiment": briefing.get("overall_sentiment"),
                "kse100":    report.get("market_overview", {}).get("kse100_level"),
                "buy_count": len(report.get("conventional_portfolio", {}).get("buy_picks", [])),
                "size_kb":   round(os.path.getsize(path) / 1024, 1),
            })
        except Exception:
            pass
    return out


# ── POSTS ─────────────────────────────────────────────────────────

def _load_posts():
    if not os.path.exists(POSTS_DIR):
        return {}
    fb = fw = pw = comp = None
    for fname in sorted(os.listdir(POSTS_DIR), reverse=True):
        if not fname.endswith(".txt"):
            continue
        content = open(os.path.join(POSTS_DIR, fname), encoding="utf-8").read()
        if "facebook"     in fname and fb   is None: fb   = {"filename": fname, "content": content}
        elif "free_wa"    in fname and fw   is None: fw   = {"filename": fname, "content": content}
        elif "paid_wa"    in fname and pw   is None: pw   = {"filename": fname, "content": content}
        elif "comprehensive" in fname and comp is None: comp = {"filename": fname, "content": content}
        if fb and fw and pw and comp:
            break
    return {"facebook": fb, "free_whatsapp": fw, "paid_whatsapp": pw, "comprehensive": comp}

@app.get("/data/posts")
def get_posts(_: str = Depends(auth)):
    posts = _load_posts()
    if not any(posts.values()):
        raise HTTPException(404, "No posts found — run the pipeline first")
    return posts


# ── CUSTOM ANALYSIS ───────────────────────────────────────────────

class ArticleIn(BaseModel):
    source:  str
    title:   str
    summary: Optional[str] = ""
    date:    Optional[str] = ""
    link:    Optional[str] = ""

class CustomAnalysisRequest(BaseModel):
    articles:         List[ArticleIn]
    analysis_date:    str                  # YYYY-MM-DD
    selected_symbols: Optional[List[str]] = None

@app.post("/analysis/custom")
async def custom_analysis(req: CustomAnalysisRequest, _: str = Depends(auth)):
    """
    Run AI analysis on user-selected articles and optionally focus on specific stocks.
    Returns news_briefing + trading_report + all 4 post formats.
    """
    loop = asyncio.get_event_loop()

    # ── Build article list with date-window weighting ─────────────
    articles = []
    try:
        analysis_dt = datetime.fromisoformat(req.analysis_date)
    except ValueError:
        analysis_dt = datetime.now()

    primary_cutoff   = analysis_dt - timedelta(days=2)   # last 2 days = PRIMARY
    secondary_cutoff = analysis_dt - timedelta(days=5)   # up to 5 days = SECONDARY

    for a in req.articles:
        weight = "SECONDARY"
        try:
            from email.utils import parsedate_to_datetime
            try:
                pub = parsedate_to_datetime(a.date)
            except Exception:
                pub = datetime.fromisoformat(a.date.replace("Z", "+00:00")) if a.date else None

            if pub:
                pub_naive = pub.replace(tzinfo=None) if pub.tzinfo else pub
                if pub_naive >= primary_cutoff:
                    weight = "PRIMARY"
                elif pub_naive < secondary_cutoff:
                    weight = "IGNORE"
        except Exception:
            weight = "SECONDARY"

        if weight != "IGNORE":
            articles.append({
                "source":  f"[{weight}] {a.source}",
                "title":   a.title,
                "summary": a.summary or "",
                "date":    a.date or "",
                "link":    a.link or "",
            })

    if not articles:
        raise HTTPException(400, "No articles passed the date filter. Try relaxing the date range.")

    # ── Run News Agent on custom articles ─────────────────────────
    from openai import OpenAI
    from news_agent import SYSTEM_PROMPT as NEWS_SYS_PROMPT

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    today_str = req.analysis_date

    news_prompt_lines = [
        f"Analysis date: {today_str}",
        f"Total selected articles: {len(articles)}",
        f"NOTE: Articles marked [PRIMARY] are from the last 2 days — weight these HEAVILY.",
        f"Articles marked [SECONDARY] are older — use only as background context.",
        "=" * 60,
    ]
    for i, a in enumerate(articles, 1):
        news_prompt_lines.append(f"\n--- Article {i} ---")
        news_prompt_lines.append(f"Source : {a['source']}")
        if a["date"]: news_prompt_lines.append(f"Date   : {a['date']}")
        news_prompt_lines.append(f"Title  : {a['title']}")
        if a["summary"]: news_prompt_lines.append(f"Detail : {a['summary']}")
    news_prompt_lines.append("\n" + "=" * 60)
    news_prompt_lines.append("Now produce the full structured JSON briefing.")

    news_prompt = "\n".join(news_prompt_lines)

    def _call_news_agent():
        resp = client.chat.completions.create(
            model="gpt-4.1-mini",
            temperature=0.2,
            max_tokens=3500,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": NEWS_SYS_PROMPT},
                {"role": "user",   "content": news_prompt},
            ],
        )
        briefing = json.loads(resp.choices[0].message.content)
        briefing["_meta"] = {
            "articles_analyzed": len(articles),
            "tokens_used":       resp.usage.total_tokens,
            "generated_at":      datetime.now().isoformat(),
            "analysis_date":     today_str,
            "custom":            True,
        }
        return briefing

    news_briefing = await loop.run_in_executor(None, _call_news_agent)

    # ── Run Trading Agent with optional symbol focus ───────────────
    from trading_agent import run_trading_analysis, SYSTEM_PROMPT as TRADE_SYS_PROMPT

    focus_note = ""
    if req.selected_symbols:
        syms = ", ".join(req.selected_symbols)
        focus_note = (
            f"\n\nUSER FOCUS: The user specifically wants analysis on these symbols: {syms}. "
            f"Prioritize these in your picks where fundamentals support it. "
            f"If a symbol doesn't have sufficient data or news support, say so honestly."
        )

    def _call_trading_agent():
        return run_trading_analysis(
            news_briefing,
            save_history=False,
            extra_system_note=focus_note,
        )

    try:
        report = await loop.run_in_executor(None, _call_trading_agent)
    except TypeError:
        report = await loop.run_in_executor(None, lambda: run_trading_analysis(news_briefing, save_history=False))

    # ── Save as custom report ─────────────────────────────────────
    ts        = datetime.now().strftime("%Y%m%d_%H%M")
    rpath     = os.path.join(DATA_DIR, "reports", f"custom_{ts}.json")
    os.makedirs(os.path.dirname(rpath), exist_ok=True)
    with open(rpath, "w", encoding="utf-8") as f:
        json.dump({"news_briefing": news_briefing, "trading_report": report}, f, ensure_ascii=False, indent=2)

    # ── Format all 4 tiers ────────────────────────────────────────
    from content_formatter import (
        format_facebook_post, format_free_whatsapp_post,
        format_paid_whatsapp_post, format_comprehensive_report,
    )
    fb_post   = format_facebook_post(report, news_briefing, os.getenv("FREE_WA_GROUP_LINK", ""))
    fw_post   = format_free_whatsapp_post(report, news_briefing, os.getenv("PAID_CHANNEL_LINK", ""))
    pw_post   = format_paid_whatsapp_post(report, news_briefing)
    comp_post = format_comprehensive_report(report, news_briefing)

    os.makedirs(POSTS_DIR, exist_ok=True)
    open(os.path.join(POSTS_DIR, f"{ts}_facebook.txt"),      "w", encoding="utf-8").write(fb_post)
    open(os.path.join(POSTS_DIR, f"{ts}_free_wa.txt"),       "w", encoding="utf-8").write(fw_post)
    open(os.path.join(POSTS_DIR, f"{ts}_paid_wa.txt"),       "w", encoding="utf-8").write(pw_post)
    open(os.path.join(POSTS_DIR, f"{ts}_comprehensive.txt"), "w", encoding="utf-8").write(comp_post)

    return {
        "news_briefing":  news_briefing,
        "trading_report": report,
        "posts": {
            "facebook":      {"filename": f"{ts}_facebook.txt",      "content": fb_post},
            "free_whatsapp": {"filename": f"{ts}_free_wa.txt",       "content": fw_post},
            "paid_whatsapp": {"filename": f"{ts}_paid_wa.txt",       "content": pw_post},
            "comprehensive": {"filename": f"{ts}_comprehensive.txt", "content": comp_post},
        },
        "report_file": f"custom_{ts}.json",
        "articles_used": len(articles),
        "primary_count": sum(1 for a in articles if "[PRIMARY]" in a["source"]),
    }


# ── PIPELINE SSE ──────────────────────────────────────────────────

def _evt(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"

def _save_posts(report, news_briefing, ts):
    from content_formatter import (
        format_facebook_post, format_free_whatsapp_post,
        format_paid_whatsapp_post, format_comprehensive_report,
    )
    fb_post   = format_facebook_post(report, news_briefing, os.getenv("FREE_WA_GROUP_LINK", ""))
    fw_post   = format_free_whatsapp_post(report, news_briefing, os.getenv("PAID_CHANNEL_LINK", ""))
    pw_post   = format_paid_whatsapp_post(report, news_briefing)
    comp_post = format_comprehensive_report(report, news_briefing)
    os.makedirs(POSTS_DIR, exist_ok=True)
    open(os.path.join(POSTS_DIR, f"{ts}_facebook.txt"),      "w", encoding="utf-8").write(fb_post)
    open(os.path.join(POSTS_DIR, f"{ts}_free_wa.txt"),       "w", encoding="utf-8").write(fw_post)
    open(os.path.join(POSTS_DIR, f"{ts}_paid_wa.txt"),       "w", encoding="utf-8").write(pw_post)
    open(os.path.join(POSTS_DIR, f"{ts}_comprehensive.txt"), "w", encoding="utf-8").write(comp_post)
    return fb_post, fw_post, pw_post, comp_post


async def _pipeline_stream(mode: str = "full"):
    global _pipeline_lock
    _pipeline_lock = True
    loop  = asyncio.get_event_loop()
    ts    = datetime.now().strftime("%Y%m%d_%H%M")

    # Determine which steps to run
    run_fetch   = mode in ("full", "data")
    run_analyze = mode in ("full", "analyze")

    total = 6 if mode == "full" else (1 if mode == "data" else 5)
    step  = 0

    def next_step(label):
        nonlocal step
        step += 1
        return step

    try:
        news_briefing = None
        report        = None

        # ── STEP: Fetch ───────────────────────────────────────────
        if run_fetch:
            s = next_step("fetch")
            yield _evt({"type": "step_start", "step": s, "total": total,
                        "label": "Fetching fresh data (Google News, Dawn, Profit.pk, PSX Portal)"})
            try:
                import importlib, fetch_and_save as fas
                importlib.reload(fas)
                fas.TIMESTAMP = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                await loop.run_in_executor(None, fas.fetch_google_news)
                yield _evt({"type": "step_log", "step": s, "message": "âœ“ Google News"})
                await loop.run_in_executor(None, fas.fetch_dawn)
                yield _evt({"type": "step_log", "step": s, "message": "âœ“ Dawn Business"})
                await loop.run_in_executor(None, fas.fetch_profit_pk)
                yield _evt({"type": "step_log", "step": s, "message": "âœ“ Profit.pk"})
                await loop.run_in_executor(None, fas.fetch_general_news)
                yield _evt({"type": "step_log", "step": s, "message": "âœ“ General/Macro News"})
                psx_result = await loop.run_in_executor(None, fas.fetch_psx_portal)
                yield _evt({“type”: “step_log”, “step”: s, “message”: “âœ” PSX Portal”})
                import price_history as _ph
                await loop.run_in_executor(None, lambda: _ph.append_today(psx_result))
                yield _evt({“type”: “step_log”, “step”: s, “message”: “âœ” Price history updated”})
                yield _evt({“type”: “step_done”, “step”: s, “label”: “All data saved to ./backend/data/”})
            except Exception as e:
                yield _evt({"type": "step_warn", "step": s, "label": f"Partial fetch — using cached data: {e}"})

        if mode == "data":
            yield _evt({"type": "done", "message": "Data refresh complete — re-open PSX Table and News to see updated data."})
            return

        # ── STEP: News Agent ──────────────────────────────────────
        s = next_step("news")
        yield _evt({"type": "step_start", "step": s, "total": total,
                    "label": "News Analyst Agent — deep story-by-story reasoning"})
        from news_agent import run_news_analysis
        news_briefing = await loop.run_in_executor(None, lambda: run_news_analysis(days_back=2))
        yield _evt({"type": "step_done", "step": s, "label": "News briefing ready", "extra": {
            "sentiment": news_briefing.get("overall_sentiment"),
            "stories":   len(news_briefing.get("top_stories", [])),
            "tokens":    news_briefing.get("_meta", {}).get("tokens_used"),
        }})

        await asyncio.sleep(0.05)

        # ── STEP: Trading Agent ───────────────────────────────────
        s = next_step("trade")
        yield _evt({"type": "step_start", "step": s, "total": total,
                    "label": "Trading Analyst — 10 BUY + 10 AVOID (Conventional & Shariah)"})
        from trading_agent import run_trading_analysis
        report = await loop.run_in_executor(
            None, lambda: run_trading_analysis(news_briefing, save_history=True)
        )
        rpath = os.path.join(DATA_DIR, "reports", f"report_{ts}.json")
        os.makedirs(os.path.dirname(rpath), exist_ok=True)
        with open(rpath, "w", encoding="utf-8") as f:
            json.dump({"news_briefing": news_briefing, "trading_report": report}, f, ensure_ascii=False, indent=2)
        ov = report.get("market_overview", {})
        yield _evt({"type": "step_done", "step": s, "label": f"Report saved: report_{ts}.json", "extra": {
            "bias":   ov.get("session_bias"),
            "kse100": ov.get("kse100_level"),
            "kmi30":  ov.get("kmi30_level"),
        }})

        await asyncio.sleep(0.05)

        # ── STEP: Format posts ────────────────────────────────────
        s = next_step("format")
        yield _evt({"type": "step_start", "step": s, "total": total,
                    "label": "Formatting 4 content tiers (Facebook, Free WA, Paid WA, Comprehensive)"})
        _save_posts(report, news_briefing, ts)
        yield _evt({"type": "step_done", "step": s, "label": "All 4 posts saved to ./posts/"})

        await asyncio.sleep(0.05)

        if mode == "analyze":
            yield _evt({"type": "done", "message": "Analysis complete! Check Report and Posts tabs."})
            return

        # ── STEP: Facebook ────────────────────────────────────────
        s = next_step("fb")
        yield _evt({"type": "step_start", "step": s, "total": total, "label": "Publishing to Facebook Page"})
        if os.getenv("AUTO_POST", "false").lower() != "true":
            yield _evt({"type": "step_skip", "step": s, "label": "Skipped — set AUTO_POST=true in .env to enable"})
        else:
            from content_formatter import format_facebook_post
            fb_post = format_facebook_post(report, news_briefing, os.getenv("FREE_WA_GROUP_LINK", ""))
            from fb_poster import post_to_facebook
            res = await loop.run_in_executor(None, lambda: post_to_facebook(fb_post))
            if res["success"]:
                yield _evt({"type": "step_done", "step": s, "label": f"Published! ID: {res['post_id']}"})
            else:
                yield _evt({"type": "step_warn", "step": s, "label": f"FB error: {res['error']}"})

        await asyncio.sleep(0.05)

        # ── STEP: WhatsApp ────────────────────────────────────────
        s = next_step("wa")
        yield _evt({"type": "step_start", "step": s, "total": total, "label": "Sending WhatsApp messages"})
        twilio_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
        free_to    = os.getenv("FREE_WHATSAPP_TO", "")
        if not twilio_sid or not free_to:
            yield _evt({"type": "step_skip", "step": s, "label": "Skipped — configure TWILIO_ vars in .env to enable"})
        else:
            try:
                from content_formatter import format_free_whatsapp_post
                fw_post = format_free_whatsapp_post(report, news_briefing, os.getenv("PAID_CHANNEL_LINK", ""))
                from whatsapp_sender import send_analysis_to_whatsapp
                ok = await loop.run_in_executor(None, lambda: send_analysis_to_whatsapp(fw_post, to=free_to))
                if ok:
                    yield _evt({"type": "step_done", "step": s, "label": f"Sent to {free_to}"})
                else:
                    yield _evt({"type": "step_warn", "step": s, "label": "WhatsApp send failed"})
            except Exception as e:
                yield _evt({"type": "step_warn", "step": s, "label": f"WhatsApp error: {e}"})

        yield _evt({"type": "done", "message": "Pipeline complete! All steps finished."})

    except Exception as e:
        yield _evt({"type": "error", "message": str(e)})
    finally:
        _pipeline_lock = False


@app.get("/pipeline/run")
async def pipeline_run(token: str = Query(...), mode: str = Query("full")):
    """
    mode=full     — fetch + analyze + format + publish  (default)
    mode=data     — fetch only (no AI)
    mode=analyze  — analyze + format only (no fetch, no publish)
    """
    verify_token(token)
    if mode not in ("full", "data", "analyze"):
        raise HTTPException(400, "mode must be full | data | analyze")
    global _pipeline_lock
    if _pipeline_lock:
        raise HTTPException(409, "Pipeline already running")
    return StreamingResponse(
        _pipeline_stream(mode),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

@app.get("/pipeline/status")
def pipeline_status(_: str = Depends(auth)):
    return {"running": _pipeline_lock}


# ── LIVE MARKET ───────────────────────────────────────────────────

@app.get("/stocks/live")
def stocks_live(_: str = Depends(auth)):
    """
    Current price + change for the default watchlist.
    First reads the cached PSX portal JSON (fast).
    Falls back to yfinance fast_info per symbol.
    """
    # Try to serve from the already-scraped PSX JSON (zero extra network calls)
    psx_path = os.path.join(DATA_DIR, "04_psx_data_portal.json")
    if os.path.exists(psx_path):
        try:
            psx = json.load(open(psx_path, encoding="utf-8"))
            stocks = psx.get("all_stocks", [])
            from stock_data import WATCHLIST
            sym_set = set(WATCHLIST)
            def _pf(*keys):
                for k in keys:
                    v = s.get(k)
                    if v is not None:
                        try:
                            return float(str(v).replace(",", ""))
                        except (ValueError, TypeError):
                            pass
                return 0.0

            out = []
            for s in stocks:
                # PSX portal uses uppercase keys (SYMBOL, LDCP, CURRENT, …)
                sym = (s.get("SYMBOL") or s.get("Symbol") or s.get("symbol") or "").strip()
                if sym in sym_set:
                    try:
                        ldcp    = _pf("LDCP",    "Ldcp",    "ldcp",    "prev_close")
                        current = _pf("CURRENT", "Current", "current", "CLOSE", "Close", "close") or ldcp
                        chg     = round(current - ldcp, 2)
                        chgp    = round(chg / ldcp * 100, 2) if ldcp else 0
                        out.append({
                            "symbol":     sym,
                            "price":      round(current, 2),
                            "change":     chg,
                            "change_pct": chgp,
                            "volume":     int(_pf("VOLUME", "Volume", "volume", "VOL")),
                            "open":       _pf("OPEN",   "Open",   "open"),
                            "high":       _pf("HIGH",   "High",   "high"),
                            "low":        _pf("LOW",    "Low",    "low"),
                            "updated":    psx.get("fetched_at", ""),
                        })
                    except Exception:
                        pass
            if out:
                return {"stocks": out, "source": "psx_portal"}
        except Exception:
            pass

    # Fallback: yfinance fast_info
    try:
        from stock_data import get_live_prices, WATCHLIST
        prices = get_live_prices(WATCHLIST)
        return {"stocks": prices, "source": "yfinance"}
    except Exception as exc:
        raise HTTPException(500, f"Live data unavailable: {exc}")


@app.get("/stocks/historical/{symbol}")
def stocks_historical(symbol: str, timeframe: str = "1M", _: str = Depends(auth)):
    """
    OHLCV + TA indicators for a symbol.
    timeframe: 1D | 1W | 1M | 3M | 1Y
    """
    symbol = symbol.upper()
    try:
        from stock_data import get_historical
        data = get_historical(symbol, timeframe)
        if "error" in data:
            raise HTTPException(404, data["error"])
        return data
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc))


class AnalyzeStockRequest(BaseModel):
    symbol: str
    timeframe: Optional[str] = "3M"

TRADER_SYSTEM_PROMPT = """You are a seasoned PSX (Pakistan Stock Exchange) equity trader with 15+ years experience.
You think and analyze through a structured framework:

1. TREND   — Primary trend direction (weekly + daily). Price vs SMA20/50/200.
2. MOMENTUM — RSI position (overbought/oversold/neutral). MACD crossover.
3. STRUCTURE — Where is price relative to support/resistance? Distance from 52W high/low.
4. VOLUME  — Is the move backed by above-average volume conviction?
5. CATALYST — News or macro driver. SBP rate, IMF tranche, PKR, oil price, sector news.
6. RISK    — What exactly invalidates this trade? Where is the stop?
7. TIMING  — Is this a high-probability entry NOW or should we wait?

Your risk management rules:
- Always define stop-loss before entry.
- Minimum 1:2 risk-reward ratio required to enter.
- ATR(14) guides stop-loss placement.
- Prefer entries on pullbacks to SMA or support rather than chasing breakouts.

Pakistan market context (always factor in):
- KSE-100 index correlation: individual stocks often move with index.
- PKR/USD rate: importers hurt by depreciation; exporters + remittances benefit.
- SBP policy rate: high rates hurt banks' margins, benefit fixed-income but compress P/E multiples.
- IMF programme status: positive = market-wide catalyst.
- Oil price: directly impacts OGDC, PPL, PSO, HUBC, KAPCO.
- Textile/exporter stocks benefit from weak PKR.

Output ONLY valid JSON matching this exact schema (no markdown, no explanation outside JSON):
{
  "signal": "STRONG_BUY | BUY | HOLD | SELL | STRONG_SELL",
  "confidence": 0-100,
  "entry_low": number,
  "entry_high": number,
  "target1": number,
  "target2": number,
  "stop_loss": number,
  "time_horizon": "1-3 days | 1-2 weeks | 2-4 weeks | 1-3 months",
  "trend_assessment": "string — what the chart is saying",
  "momentum_assessment": "string — RSI, MACD reading",
  "key_catalyst": "string — main driver for this call",
  "risk_factors": ["string", "string"],
  "reasoning": "string — full trade rationale in 3-5 sentences"
}"""

@app.post("/stocks/analyze")
async def analyze_stock(req: AnalyzeStockRequest, _: str = Depends(auth)):
    """
    Run GPT trader-mindset analysis on a stock.
    Combines TA summary + fundamentals + recent news for the AI context.
    """
    symbol = req.symbol.upper()
    loop   = asyncio.get_event_loop()

    # Get TA context
    try:
        from stock_data import get_analysis_context
        ctx = await loop.run_in_executor(None, lambda: get_analysis_context(symbol))
    except Exception as exc:
        raise HTTPException(500, f"Could not fetch stock context: {exc}")

    if "error" in ctx:
        raise HTTPException(404, ctx["error"])

    # Get relevant news headlines (from cached files)
    news_lines = []
    for fname in ["01_google_news.json", "02_dawn_business.json", "03_profit_pakistan.json"]:
        p = os.path.join(DATA_DIR, fname)
        if not os.path.exists(p):
            continue
        try:
            data = json.load(open(p, encoding="utf-8"))
            articles = data if isinstance(data, list) else data.get("articles", [])
            for a in articles[:5]:
                title = a.get("title", "")
                if title:
                    news_lines.append(f"- {title}")
        except Exception:
            pass

    ta_s = ctx.get("ta_summary", {})
    info = ctx.get("info", {})
    tail = ctx.get("recent_ohlcv", [])

    user_prompt = f"""
Stock: {symbol}
Company: {info.get('name', symbol)}
Sector: {info.get('sector', 'Unknown')}

=== TECHNICAL ANALYSIS (3-Month Daily Data) ===
Current Price : {ta_s.get('current_price', 'N/A')}
Change Today  : {ta_s.get('change_pct', 'N/A')}%
Trend         : {ta_s.get('trend', 'N/A')}
RSI(14)       : {ta_s.get('rsi', 'N/A')} — {ta_s.get('rsi_signal', '')}
SMA20         : {ta_s.get('sma20', 'N/A')} ({"above" if ta_s.get('above_sma20') else "below"})
SMA50         : {ta_s.get('sma50', 'N/A')} ({"above" if ta_s.get('above_sma50') else "below"})
SMA200        : {ta_s.get('sma200', 'N/A')} ({"above" if ta_s.get('above_sma200') else "below"})
ATR(14)       : {ta_s.get('atr', 'N/A')}
Period High   : {ta_s.get('period_high', 'N/A')} ({ta_s.get('pct_from_high', 'N/A')}% from current)
Period Low    : {ta_s.get('period_low', 'N/A')}  ({ta_s.get('pct_from_low', 'N/A')}% from current)

=== FUNDAMENTALS ===
P/E Ratio     : {info.get('pe_ratio', 'N/A')}
P/B Ratio     : {info.get('pb_ratio', 'N/A')}
Div Yield     : {info.get('div_yield', 'N/A')}
52W High      : {info.get('52w_high', 'N/A')}
52W Low       : {info.get('52w_low', 'N/A')}
Market Cap    : {info.get('market_cap', 'N/A')}

=== LAST 5 CANDLES ===
{chr(10).join(f"  {c['time']} O:{c['open']} H:{c['high']} L:{c['low']} C:{c['close']} V:{c['volume']}" for c in tail[-5:])}

=== RECENT MARKET NEWS (PSX context) ===
{chr(10).join(news_lines[:10]) if news_lines else "No recent news available."}

Based on all of the above, apply your full trading framework and produce the JSON prediction.
"""

    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def _call():
        resp = client.chat.completions.create(
            model="gpt-4.1-mini",
            temperature=0.15,
            max_tokens=1000,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": TRADER_SYSTEM_PROMPT},
                {"role": "user",   "content": user_prompt},
            ],
        )
        return json.loads(resp.choices[0].message.content)

    try:
        prediction = await loop.run_in_executor(None, _call)
    except Exception as exc:
        raise HTTPException(500, f"AI analysis failed: {exc}")

    return {
        "symbol":     symbol,
        "prediction": prediction,
        "context":    {"ta_summary": ta_s, "info": info},
        "analyzed_at": datetime.now().isoformat(),
    }


class BatchAnalyzeRequest(BaseModel):
    symbols: List[str]


def _parse_article_date(date_str: str):
    """Parse RSS or ISO date string → aware datetime, or None."""
    if not date_str:
        return None
    try:
        from email.utils import parsedate_to_datetime
        try:
            dt = parsedate_to_datetime(date_str)
        except Exception:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _load_recent_news(data_dir: str, days: int = 1) -> list[dict]:
    """
    Load all 5 news files, return articles from the last `days` days only.
    Each article: {title, source, date}
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    def _flat(data: dict) -> list:
        """Extract article list from any of our JSON shapes."""
        if isinstance(data, list):
            return data
        arts = []
        # Shape 1: {"articles": [...]}
        arts += data.get("articles", [])
        # Shape 2: {"rss": {"articles": [...]}, "scraped": [...]}
        arts += data.get("rss", {}).get("articles", [])
        arts += data.get("scraped", [])
        # Shape 3: {"sources": {"name": {"articles": [...]}}}
        for src_val in data.get("sources", {}).values():
            if isinstance(src_val, list):
                arts += src_val
            elif isinstance(src_val, dict):
                arts += src_val.get("articles", [])
        # Shape 4: flat dict of lists (05_general_news uses source keys)
        for v in data.values():
            if isinstance(v, list) and v and isinstance(v[0], dict) and "title" in v[0]:
                arts += v
        return arts

    sources = [
        ("01_google_news.json",     "Google News"),
        ("02_dawn_business.json",   "Dawn Business"),
        ("03_profit_pakistan.json",  "Profit.pk"),
        ("05_general_news.json",    "General/Macro"),
    ]
    recent = []
    seen   = set()
    for fname, label in sources:
        p = os.path.join(data_dir, fname)
        if not os.path.exists(p):
            continue
        try:
            data = json.load(open(p, encoding="utf-8"))
            for a in _flat(data):
                title = (a.get("title") or "").strip()
                if not title or title in seen:
                    continue
                date_str = a.get("published") or a.get("date") or a.get("pub_date") or ""
                dt = _parse_article_date(date_str)
                # Include if recent enough, or if date is missing (can't tell — include cautiously)
                if dt is None or dt >= cutoff:
                    seen.add(title)
                    recent.append({"title": title, "source": label, "date": date_str})
        except Exception:
            pass
    return recent


def _split_news(articles: list[dict], symbol: str, company: str) -> tuple[list[str], list[str]]:
    """
    Split articles into:
      stock_lines  — headlines mentioning this stock or company
      market_lines — macro/general market headlines
    """
    sym_lower  = symbol.lower()
    co_lower   = company.lower().split("(")[0].strip()   # strip parenthetical e.g. "(Pvt)"
    co_words   = [w for w in co_lower.split() if len(w) > 3]  # meaningful words only

    macro_kw = [
        "sbp", "policy rate", "interest rate", "discount rate",
        "imf", "tranche", "bailout", "programme",
        "pkr", "rupee", "dollar", "exchange rate",
        "inflation", "cpi", "gdp", "fiscal",
        "oil", "crude", "opec", "petroleum",
        "kse", "psx", "market", "index", "equity",
        "budget", "tax", "ministry of finance",
        "war", "india", "china", "sanction", "geopolit",
        "cpec", "investment", "fdi", "current account",
    ]

    stock_lines  = []
    market_lines = []

    for a in articles:
        t = a["title"].lower()
        is_stock = sym_lower in t or any(w in t for w in co_words if w)
        is_macro  = any(kw in t for kw in macro_kw)

        line = f"- [{a['source']}] {a['title']}"
        if is_stock:
            stock_lines.append(line)
        elif is_macro:
            market_lines.append(line)

    return stock_lines, market_lines


@app.post("/stocks/analyze/batch")
async def analyze_stock_batch(req: BatchAnalyzeRequest, _: str = Depends(auth)):
    """Run GPT trader analysis on multiple stocks in parallel. Capped at 15."""
    symbols = list(dict.fromkeys(s.upper() for s in req.symbols))[:15]
    loop    = asyncio.get_event_loop()

    # Load today/yesterday news once — split per stock inside _analyze_one
    all_recent_news = _load_recent_news(DATA_DIR, days=1)

    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    async def _analyze_one(symbol: str) -> dict:
        try:
            from stock_data import get_analysis_context
            ctx = await loop.run_in_executor(None, lambda: get_analysis_context(symbol))
            if "error" in ctx:
                return {"symbol": symbol, "error": ctx["error"]}

            ta_s = ctx.get("ta_summary", {})
            info = ctx.get("info", {})
            tail = ctx.get("recent_ohlcv", [])

            company = info.get("name", symbol)
            stock_news, market_news = _split_news(all_recent_news, symbol, company)

            def _ab(flag_key): return "above" if ta_s.get(flag_key) else "below"
            def _val(k):       return ta_s.get(k, "N/A")

            rsi_trend_line = ""
            if ta_s.get("rsi_last5"):
                rsi_trend_line = f"RSI 5-day     : {' → '.join(str(v) for v in ta_s['rsi_last5'])} ({_val('rsi_direction')})"

            vol_line = ""
            if ta_s.get("volume_ratio"):
                vol_line = f"Volume vs Avg : {ta_s['volume_ratio']}x — {ta_s.get('volume_signal', '')}"

            fund_lines = []
            if info.get("pe_ratio"):  fund_lines.append(f"P/E Ratio     : {info['pe_ratio']}")
            if info.get("pb_ratio"):  fund_lines.append(f"P/B Ratio     : {info['pb_ratio']}")
            if info.get("div_yield"): fund_lines.append(f"Div Yield     : {round(info['div_yield']*100,2)}%")
            if info.get("market_cap"):fund_lines.append(f"Market Cap    : PKR {round(info['market_cap']/1e9,1)}B")
            fund_section = "\n".join(fund_lines) if fund_lines else "Not available (PSX/yfinance gap)"

            candles = tail[-15:]
            candle_lines = "\n".join(
                f"  {c['time']} O:{c['open']} H:{c['high']} L:{c['low']} C:{c['close']} V:{c['volume']}"
                for c in candles
            )

            stock_section  = "\n".join(stock_news[:8])  if stock_news  else "None found for this symbol today."
            market_section = "\n".join(market_news[:12]) if market_news else "No macro news today."

            user_prompt = f"""Stock: {symbol}
Company: {company}
Sector: {info.get('sector', 'Unknown')}

=== TECHNICAL ANALYSIS (6-month daily data) ===
Current Price : {_val('current_price')}
Today's Change: {_val('change_pct')}%
Trend         : {_val('trend')}
RSI(14)       : {_val('rsi')} — {_val('rsi_signal')}
{rsi_trend_line}
MACD          : {_val('macd')}
SMA 20        : {_val('sma20')} ({_ab('above_sma20')})
SMA 50        : {_val('sma50')} ({_ab('above_sma50')})
SMA 200       : {_val('sma200')} ({_ab('above_sma200')})
ATR(14)       : {_val('atr')}
{vol_line}
6M High       : {_val('period_high')} ({_val('pct_from_high')}% from current)
6M Low        : {_val('period_low')}  ({_val('pct_from_low')}% from current)

=== FUNDAMENTALS ===
{fund_section}

=== LAST {len(candles)} CANDLES ===
{candle_lines}

=== STOCK-SPECIFIC NEWS (Today / Yesterday) ===
{stock_section}

=== GENERAL MARKET NEWS (Today / Yesterday) ===
{market_section}

Produce the JSON prediction."""

            def _call():
                resp = client.chat.completions.create(
                    model="gpt-4.1-mini",
                    temperature=0.15,
                    max_tokens=800,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": TRADER_SYSTEM_PROMPT},
                        {"role": "user",   "content": user_prompt},
                    ],
                )
                return json.loads(resp.choices[0].message.content)

            prediction = await loop.run_in_executor(None, _call)
            return {"symbol": symbol, "prediction": prediction, "context": {"ta_summary": ta_s, "info": info}}
        except Exception as e:
            return {"symbol": symbol, "error": str(e)}

    results = await asyncio.gather(*[_analyze_one(sym) for sym in symbols])
    ok      = sorted([r for r in results if "prediction" in r],
                     key=lambda x: x["prediction"].get("confidence", 0), reverse=True)
    errors  = [r for r in results if "error" in r]

    return {
        "results":     ok,
        "errors":      errors,
        "total":       len(symbols),
        "analyzed_at": datetime.now().isoformat(),
    }


class GeneratePostRequest(BaseModel):
    symbol:   str
    tone:     str   # Bullish | Bearish | Neutral | Breaking | Weekly
    platform: str   # facebook | whatsapp

POST_GEN_PROMPT = """You are an expert financial content writer for Pakistan stock market audiences.
You write engaging, credible social media posts about PSX stocks.

Rules:
- Facebook posts: 200-280 words, professional + conversational, 3-4 relevant hashtags at end.
- WhatsApp posts: 150-220 words, concise bullet format with âœ…/âš ï¸/ðŸ“Š emojis, no hashtags.
- Always include: stock name, current context, key signal, brief reasoning, a CTA.
- Tone guide: Bullish=optimistic with caution, Bearish=risk-focused, Neutral=balanced analysis,
  Breaking=urgent/time-sensitive, Weekly=week-ahead outlook.
- Never give financial advice. Always add a brief disclaimer.
- Write in fluent English. No Urdu mixing.

Output ONLY the post text — no JSON, no labels, no extra explanation."""

@app.post("/posts/generate")
async def generate_post(req: GeneratePostRequest, _: str = Depends(auth)):
    """Generate a social media post for a given stock + tone + platform using GPT."""
    symbol   = req.symbol.upper()
    tone     = req.tone
    platform = req.platform.lower()
    loop     = asyncio.get_event_loop()

    # Get brief stock context
    try:
        from stock_data import get_analysis_context
        ctx = await loop.run_in_executor(None, lambda: get_analysis_context(symbol))
    except Exception:
        ctx = {}

    ta_s = ctx.get("ta_summary", {}) if "error" not in ctx else {}
    info = ctx.get("info", {}) if "error" not in ctx else {}

    user_prompt = f"""
Platform: {platform.upper()}
Stock: {symbol} — {info.get('name', symbol)}
Sector: {info.get('sector', 'PSX')}
Current Price: PKR {ta_s.get('current_price', 'N/A')}
Today's Change: {ta_s.get('change_pct', 'N/A')}%
Trend: {ta_s.get('trend', 'N/A')}
RSI: {ta_s.get('rsi', 'N/A')} ({ta_s.get('rsi_signal', '')})
Tone requested: {tone}

Write the {platform} post now.
"""

    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def _call():
        resp = client.chat.completions.create(
            model="gpt-4.1-mini",
            temperature=0.75,
            max_tokens=600,
            messages=[
                {"role": "system", "content": POST_GEN_PROMPT},
                {"role": "user",   "content": user_prompt},
            ],
        )
        return resp.choices[0].message.content.strip()

    try:
        post_text = await loop.run_in_executor(None, _call)
    except Exception as exc:
        raise HTTPException(500, f"Post generation failed: {exc}")

    return {
        "symbol":   symbol,
        "platform": platform,
        "tone":     tone,
        "post":     post_text,
        "generated_at": datetime.now().isoformat(),
    }


# ── NCCPL / INSIDER INTELLIGENCE ─────────────────────────────────

NCCPL_DATA_DIR = DATA_DIR

@app.get("/data/nccpl/insiders")
def get_nccpl_insiders(_: str = Depends(auth)):
    """Load latest insider transaction disclosures from 06_nccpl_insider.json."""
    p = os.path.join(NCCPL_DATA_DIR, "06_nccpl_insider.json")
    if not os.path.exists(p):
        raise HTTPException(404, "Insider data not found — run the pipeline or click Refresh")
    return json.load(open(p, encoding="utf-8"))


@app.post("/data/nccpl/refresh")
async def refresh_nccpl_insiders(_: str = Depends(auth)):
    """Re-run nccpl_scraper to fetch fresh insider disclosures from PSX announcements."""
    loop = asyncio.get_event_loop()
    try:
        from nccpl_scraper import fetch_insider_transactions
        result = await loop.run_in_executor(None, lambda: fetch_insider_transactions(days_back=7))
        os.makedirs(NCCPL_DATA_DIR, exist_ok=True)
        with open(os.path.join(NCCPL_DATA_DIR, "06_nccpl_insider.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        return {
            "success":          True,
            "total_found":      result.get("total_found", 0),
            "buy_signals":      len(result.get("buy_signals", [])),
            "sell_signals":     len(result.get("sell_signals", [])),
            "activity_signals": len(result.get("activity_signals", [])),
            "fetched_at":       result.get("fetched_at"),
            "ocr_enabled":      result.get("ocr_enabled", False),
        }
    except Exception as e:
        raise HTTPException(500, f"NCCPL refresh failed: {e}")


@app.get("/data/nccpl/short-sell")
async def get_short_sell(date: str = Query(None), _: str = Depends(auth)):
    """Fetch PSX Short Sell Volume PDF for date (YYYY-MM-DD). Defaults to today."""
    loop = asyncio.get_event_loop()
    try:
        from nccpl_scraper import fetch_short_sell
        result = await loop.run_in_executor(None, lambda: fetch_short_sell(date))
        return result
    except Exception as e:
        raise HTTPException(500, f"Short sell fetch failed: {e}")


@app.get("/data/nccpl/block-trades")
async def get_block_trades(date: str = Query(None), _: str = Depends(auth)):
    """Fetch PSX OMTS block trades CSV for date (YYYY-MM-DD). Defaults to today."""
    loop = asyncio.get_event_loop()
    try:
        from nccpl_scraper import fetch_omts
        result = await loop.run_in_executor(None, lambda: fetch_omts(date))
        return result
    except Exception as e:
        raise HTTPException(500, f"OMTS fetch failed: {e}")


@app.get("/data/nccpl/futures-oi")
async def get_futures_oi(date: str = Query(None), _: str = Depends(auth)):
    """Fetch PSX Futures Open Interest XLS for date (YYYY-MM-DD). Defaults to today."""
    loop = asyncio.get_event_loop()
    try:
        from nccpl_scraper import fetch_futures_oi
        result = await loop.run_in_executor(None, lambda: fetch_futures_oi(date))
        return result
    except Exception as e:
        raise HTTPException(500, f"Futures OI fetch failed: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)

