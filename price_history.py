"""
price_history.py
----------------
Rolling 90-day OHLCV store for every PSX stock.
Stores data in backend/data/price_history.json.

Two public entry points:
  append_today(psx_data)  — called once per day after fetch_and_save.py runs
  get_all_signals()       — returns {symbol: signals_dict} consumed by agents
"""

import os
import json
from datetime import datetime

_ROOT        = os.path.dirname(os.path.abspath(__file__))
DATA_DIR     = os.path.join(_ROOT, "backend", "data")
HISTORY_FILE = os.path.join(DATA_DIR, "price_history.json")
MAX_DAYS     = 90


# ── HELPERS ──────────────────────────────────────────────────────────────────

def _pf(v) -> float:
    try:
        return float(str(v or "0").replace(",", "").strip())
    except (ValueError, TypeError):
        return 0.0


def _load() -> dict:
    if not os.path.exists(HISTORY_FILE):
        return {"last_updated": "", "stocks": {}}
    try:
        with open(HISTORY_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"last_updated": "", "stocks": {}}


def _save(data: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))


# ── DATA INGESTION ────────────────────────────────────────────────────────────

def append_today(psx_data: dict) -> dict:
    """
    Append today's closing snapshot from psx_data into price_history.json.
    Safe to call multiple times — duplicate dates are overwritten, not appended.
    """
    today   = datetime.now().strftime("%Y-%m-%d")
    history = _load()

    if history.get("last_updated") == today:
        print(f"  [price_history] Already updated for {today} — skipping.")
        return history

    added = 0
    for s in psx_data.get("all_stocks", []):
        sym = s.get("SYMBOL", "").strip()
        if not sym:
            continue

        close = _pf(s.get("CURRENT") or s.get("LDCP"))
        if close <= 0:
            continue

        ldcp  = _pf(s.get("LDCP"))
        high  = _pf(s.get("HIGH"))
        low   = _pf(s.get("LOW"))
        vol   = int(_pf(s.get("VOLUME") or 0))

        candle = {
            "date":   today,
            "open":   round(ldcp or close, 2),   # PSX portal has no intraday open
            "high":   round(high or close, 2),
            "low":    round(low  or close, 2),
            "close":  round(close, 2),
            "volume": vol,
        }

        stock_hist = history["stocks"].setdefault(sym, [])

        if stock_hist and stock_hist[-1]["date"] == today:
            stock_hist[-1] = candle          # overwrite same-day entry
        else:
            stock_hist.append(candle)

        if len(stock_hist) > MAX_DAYS:
            history["stocks"][sym] = stock_hist[-MAX_DAYS:]

        added += 1

    history["last_updated"] = today
    _save(history)
    print(f"  [price_history] {today}: stored {added} stocks -> {HISTORY_FILE}")
    return history


# ── SIGNAL COMPUTERS ─────────────────────────────────────────────────────────

def _sma(closes: list, n: int):
    if len(closes) < n:
        return None
    return round(sum(closes[-n:]) / n, 2)


def _rsi(closes: list, period: int = 14):
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(-period, 0):
        d = closes[i] - closes[i - 1]
        (gains if d >= 0 else losses).append(abs(d))
    avg_gain = sum(gains) / period if gains else 0.0
    avg_loss = sum(losses) / period if losses else 0.0
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - 100 / (1 + rs), 1)


def compute_signals(candles: list) -> dict:
    """
    Given a list of candle dicts (oldest→newest), return pre-labelled signals.
    All heavy arithmetic is done here so the LLM receives plain labels, not numbers.
    """
    if not candles:
        return {}

    closes  = [c["close"]  for c in candles]
    volumes = [c["volume"] for c in candles]
    today_vol = volumes[-1] if volumes else 0
    current   = closes[-1]

    # ── SMAs ──
    sma5  = _sma(closes, 5)
    sma20 = _sma(closes, 20)
    rsi   = _rsi(closes, 14)

    # ── SMA cross label ──
    sma_signal = "N/A"
    if sma5 is not None and sma20 is not None:
        prev5  = _sma(closes[:-1], 5)
        prev20 = _sma(closes[:-1], 20)
        if current > sma20:
            if prev5 is not None and prev20 is not None and prev5 <= prev20:
                sma_signal = "GOLDEN_CROSS"   # 5 just crossed above 20
            else:
                sma_signal = "ABOVE_SMA20"
        else:
            if prev5 is not None and prev20 is not None and prev5 >= prev20:
                sma_signal = "DEATH_CROSS"    # 5 just crossed below 20
            else:
                sma_signal = "BELOW_SMA20"

    # ── Volume spike: today vs 10-day average (excluding today) ──
    vol_ratio = None
    prior_vols = [v for v in volumes[-11:-1] if v > 0]
    if prior_vols:
        avg_vol   = sum(prior_vols) / len(prior_vols)
        vol_ratio = round(today_vol / avg_vol, 1) if avg_vol > 0 else None

    # ── Volume spike label ──
    vol_label = "NORMAL"
    if vol_ratio is not None:
        if vol_ratio >= 3.0:
            vol_label = "VERY_HIGH_SPIKE"
        elif vol_ratio >= 2.0:
            vol_label = "HIGH_SPIKE"
        elif vol_ratio >= 1.5:
            vol_label = "ELEVATED"
        elif vol_ratio < 0.5:
            vol_label = "DRY_UP"

    # ── 52-week proximity ──
    year_closes  = closes[-252:] if len(closes) >= 252 else closes
    w52_high     = max(year_closes)
    w52_low      = min(year_closes)
    below_52h    = round((w52_high - current) / w52_high * 100, 1) if w52_high > 0 else None
    above_52l    = round((current  - w52_low)  / w52_low  * 100, 1) if w52_low  > 0 else None

    # ── Trend: price consistently above/below SMA20 ──
    trend = "NEUTRAL"
    if sma20 and len(closes) >= 5:
        if all(c > sma20 for c in closes[-5:]):
            trend = "UPTREND"
        elif all(c < sma20 for c in closes[-5:]):
            trend = "DOWNTREND"

    # ── RSI label ──
    rsi_label = "N/A"
    if rsi is not None:
        if rsi >= 70:
            rsi_label = "OVERBOUGHT"
        elif rsi >= 55:
            rsi_label = "STRONG"
        elif rsi >= 45:
            rsi_label = "NEUTRAL"
        elif rsi >= 30:
            rsi_label = "WEAK"
        else:
            rsi_label = "OVERSOLD"

    return {
        "sma5":        sma5,
        "sma20":       sma20,
        "sma_signal":  sma_signal,
        "rsi14":       rsi,
        "rsi_label":   rsi_label,
        "vol_ratio":   vol_ratio,
        "vol_label":   vol_label,
        "trend":       trend,
        "w52_high_pct": below_52h,   # % BELOW 52w high  (0 = AT the high)
        "w52_low_pct":  above_52l,   # % ABOVE 52w low
        "days_of_data": len(candles),
    }


# ── PUBLIC API ────────────────────────────────────────────────────────────────

def get_all_signals(price_history: dict = None) -> dict:
    """Return {symbol: signals_dict} for every stock with history."""
    if price_history is None:
        price_history = _load()
    return {
        sym: compute_signals(candles)
        for sym, candles in price_history.get("stocks", {}).items()
    }
