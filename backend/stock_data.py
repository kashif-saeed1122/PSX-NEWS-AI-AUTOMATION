"""
Stock data engine: yfinance historical OHLCV + pandas-ta technical indicators.
PSX stocks use .KA suffix on Yahoo Finance (e.g. OGDC.KA, HBL.KA).

yfinance has a 1-day lag for PSX stocks. We patch this by reading today's OHLCV
from the already-scraped PSX portal JSON and appending it as the latest candle.
"""
import os, json, time
from datetime import datetime, date
import pandas as pd

try:
    import yfinance as yf
    YF_OK = True
except ImportError:
    YF_OK = False

try:
    import pandas_ta as ta
    TA_OK = True
except ImportError:
    TA_OK = False

PSX_SUFFIX = ".KA"

# 15-minute cache per (symbol, timeframe)
_cache: dict = {}
CACHE_TTL = 900

# Default watchlist shown in ticker strip
WATCHLIST = [
    "OGDC", "PPL", "ENGRO", "HBL", "MCB", "UBL", "LUCK",
    "PSO", "MARI", "POL", "EFERT", "FFC", "MLCF", "DGKC",
    "HUBC", "KAPCO", "NBP", "BAHL", "MEBL", "NESPL",
]

# Shariah KMI-30 stocks (hardcoded list)
KMI30_STOCKS = [
    "OGDC", "PPL", "MARI", "POL", "ENGRO", "EFERT", "FFC",
    "LUCK", "MLCF", "DGKC", "CHCC", "HUBC", "KAPCO", "NCPL",
    "PSO", "APL", "HASCOL", "SHEL", "SEARL", "GLAXO",
    "NESPL", "COLG", "UNILEVER", "ICI", "LOTCHEM", "FFBL",
    "FCCL", "KOHC", "POWER", "ATRL",
]

_PERIOD_MAP = {
    "1D":  {"period": "5d",  "interval": "15m", "daily": False},
    "1W":  {"period": "1mo", "interval": "60m", "daily": False},
    "1M":  {"period": "3mo", "interval": "1d",  "daily": True},
    "3M":  {"period": "6mo", "interval": "1d",  "daily": True},
    "1Y":  {"period": "2y",  "interval": "1d",  "daily": True},
}


def _cached(key: str):
    e = _cache.get(key)
    return e["data"] if e and time.time() - e["ts"] < CACHE_TTL else None


def _store(key: str, data: dict):
    _cache[key] = {"data": data, "ts": time.time()}


# ── PSX portal today-candle injection ─────────────────────────────────────────

_PSX_JSON = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "data", "04_psx_data_portal.json",
)

def _psx_today_candle(symbol: str) -> dict | None:
    """
    Read the PSX portal JSON (already on disk) and return today's OHLCV candle
    for `symbol`, or None if not found / market not open yet.

    PSX portal field names vary — we handle common variants.
    """
    try:
        if not os.path.exists(_PSX_JSON):
            return None
        with open(_PSX_JSON, encoding="utf-8") as f:
            psx = json.load(f)

        stocks = psx.get("all_stocks", [])
        sym_upper = symbol.upper()

        for s in stocks:
            # Symbol field can be "SYMBOL", "symbol", or unnamed col_0
            raw_sym = (
                s.get("SYMBOL") or s.get("Symbol") or s.get("symbol") or
                s.get("col_0") or ""
            ).strip().upper()

            if raw_sym != sym_upper:
                continue

            def _f(*keys):
                for k in keys:
                    v = s.get(k)
                    if v is not None:
                        try:
                            return float(str(v).replace(",", ""))
                        except (ValueError, TypeError):
                            pass
                return None

            open_  = _f("OPEN",    "Open",    "open")
            high   = _f("HIGH",    "High",    "high")
            low    = _f("LOW",     "Low",     "low")
            close  = _f("CURRENT", "Current", "current", "CLOSE", "Close", "close",
                        "LDCP",   "Ldcp",    "ldcp")   # LDCP = last day closing price
            volume = _f("VOLUME",  "Volume",  "volume", "VOL")

            if not close:
                return None

            # Use LDCP as previous-close reference; if OPEN is missing use close
            if not open_:
                open_ = close
            if not high or high < close:
                high = close
            if not low or low > close:
                low = close

            today_str = date.today().strftime("%Y-%m-%d")
            return {
                "time":   today_str,
                "open":   round(open_, 2),
                "high":   round(high,  2),
                "low":    round(low,   2),
                "close":  round(close, 2),
                "volume": int(volume or 0),
            }
    except Exception:
        pass
    return None


def _inject_today(ohlcv: list, symbol: str, daily: bool) -> list:
    """
    Append today's PSX candle to `ohlcv` if it is newer than the last candle.
    Works only for daily timeframes (1M / 3M / 1Y) where time is a date string.
    """
    if not daily or not ohlcv:
        return ohlcv

    today = _psx_today_candle(symbol)
    if not today:
        return ohlcv

    last_date = ohlcv[-1]["time"]          # "YYYY-MM-DD"
    today_date = today["time"]             # "YYYY-MM-DD"

    if today_date > last_date:
        return ohlcv + [today]
    if today_date == last_date:
        # Update last candle's close/high/low with live data (intraday update)
        merged = dict(ohlcv[-1])
        merged["close"]  = today["close"]
        merged["high"]   = max(merged["high"],  today["high"])
        merged["low"]    = min(merged["low"],   today["low"])
        merged["volume"] = max(merged["volume"], today["volume"])
        return ohlcv[:-1] + [merged]

    return ohlcv


# ── Public API ────────────────────────────────────────────────────────────────

def get_historical(symbol: str, timeframe: str = "1M") -> dict:
    """
    Fetch OHLCV from Yahoo Finance + compute TA indicators.
    Returns JSON-ready dict with ohlcv list and ta sub-dict.
    """
    if not YF_OK:
        return {"error": "yfinance not installed", "symbol": symbol}

    key = f"{symbol}_{timeframe}"
    cached = _cached(key)
    if cached:
        return cached

    params = _PERIOD_MAP.get(timeframe, _PERIOD_MAP["1M"])
    yfkey = f"{symbol}{PSX_SUFFIX}"

    try:
        ticker = yf.Ticker(yfkey)
        df = ticker.history(
            period=params["period"],
            interval=params["interval"],
            auto_adjust=True,
            actions=False,
        )

        if df is None or df.empty:
            # fallback: try without .KA suffix
            ticker2 = yf.Ticker(symbol)
            df = ticker2.history(period=params["period"], interval=params["interval"],
                                 auto_adjust=True, actions=False)

        if df is None or df.empty:
            return {"error": f"No data for {symbol}", "symbol": symbol}

        # Normalise multi-level columns (some yfinance versions)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)

        df.index = pd.to_datetime(df.index, utc=True)
        df = df.dropna(subset=["Open", "High", "Low", "Close"])

        # Build OHLCV array
        daily = params["daily"]
        ohlcv = []
        for idx, row in df.iterrows():
            t = idx.strftime("%Y-%m-%d") if daily else int(idx.timestamp())
            ohlcv.append({
                "time":   t,
                "open":   round(float(row["Open"]),  2),
                "high":   round(float(row["High"]),  2),
                "low":    round(float(row["Low"]),   2),
                "close":  round(float(row["Close"]), 2),
                "volume": int(row.get("Volume", 0) or 0),
            })

        # ── Stitch today's PSX portal candle onto the end ─────────────────
        # yfinance has a 1-day lag; PSX portal already has today's OHLCV.
        ohlcv = _inject_today(ohlcv, symbol, daily)

        # Rebuild df from the (possibly extended) ohlcv for TA computation
        if daily and TA_OK:
            df_merged = pd.DataFrame(ohlcv)
            df_merged.index = pd.to_datetime(df_merged["time"], utc=True)
            df_merged = df_merged.rename(columns={
                "open": "Open", "high": "High", "low": "Low",
                "close": "Close", "volume": "Volume",
            })
            ta_data = _compute_ta(df_merged, symbol)
        else:
            # TA (only for daily data — intraday TA can be noisy)
            ta_data = _compute_ta(df, symbol) if TA_OK else {}

        # Fundamentals
        info = _get_fundamentals(ticker)

        result = {
            "symbol":     symbol,
            "timeframe":  timeframe,
            "daily":      daily,
            "ohlcv":      ohlcv,
            "ta":         ta_data,
            "info":       info,
            "fetched_at": datetime.now().isoformat(),
        }
        _store(key, result)
        return result

    except Exception as exc:
        return {"error": str(exc), "symbol": symbol}


def get_live_prices(symbols: list) -> list:
    """
    Return current price snapshot for each symbol.
    Uses yfinance fast_info (lightweight, no full history).
    Falls back gracefully if a symbol fails.
    """
    if not YF_OK:
        return []

    result = []
    for sym in symbols:
        key = f"{sym}_LIVE"
        cached = _cached(key)
        if cached:
            result.append(cached)
            continue
        try:
            fi = yf.Ticker(f"{sym}{PSX_SUFFIX}").fast_info
            last  = float(fi.last_price or 0)
            prev  = float(fi.previous_close or last)
            chg   = round(last - prev, 2)
            chgp  = round((chg / prev * 100) if prev else 0, 2)
            entry = {
                "symbol":     sym,
                "price":      round(last, 2),
                "change":     chg,
                "change_pct": chgp,
                "volume":     int(fi.last_volume or 0),
                "updated":    datetime.now().isoformat(),
            }
            _store(key, entry)
            result.append(entry)
        except Exception:
            result.append({"symbol": sym, "price": 0, "change": 0, "change_pct": 0, "volume": 0})

    return result


def get_analysis_context(symbol: str) -> dict:
    """Return compact context (TA summary + fundamentals) for the AI prediction prompt."""
    data = get_historical(symbol, "3M")
    if "error" in data:
        return data
    ta   = data.get("ta", {})
    info = data.get("info", {})
    tail = data.get("ohlcv", [])[-20:]  # last 20 candles for price context
    return {
        "symbol":     symbol,
        "ta_summary": ta.get("summary", {}),
        "info":       info,
        "recent_ohlcv": tail,
    }


# ── TA computation ────────────────────────────────────────────────────────────

def _compute_ta(df: pd.DataFrame, symbol: str) -> dict:
    out: dict = {}
    try:
        close  = df["Close"]
        high   = df["High"]
        low    = df["Low"]
        volume = df.get("Volume", pd.Series(dtype=float))

        def _series(s, precision=2):
            """Convert a pandas Series to [{time, value}, ...] for lightweight-charts."""
            if s is None or s.empty:
                return []
            return [
                {"time": idx.strftime("%Y-%m-%d"), "value": round(float(v), precision)}
                for idx, v in zip(df.index, s)
                if not pd.isna(v)
            ]

        def _vol_series(s):
            return [
                {"time": idx.strftime("%Y-%m-%d"), "value": int(float(v) if not pd.isna(v) else 0)}
                for idx, v in zip(df.index, s)
            ]

        # RSI
        rsi = ta.rsi(close, length=14)
        out["rsi"] = _series(rsi)

        # MACD
        macd_df = ta.macd(close, fast=12, slow=26, signal=9)
        if macd_df is not None and not macd_df.empty:
            mcol = next((c for c in macd_df.columns if "MACD_" in c and "MACDs" not in c and "MACDh" not in c), None)
            scol = next((c for c in macd_df.columns if "MACDs" in c), None)
            hcol = next((c for c in macd_df.columns if "MACDh" in c), None)
            if mcol:  out["macd_line"]   = _series(macd_df[mcol], 4)
            if scol:  out["macd_signal"] = _series(macd_df[scol], 4)
            if hcol:
                out["macd_hist"] = [
                    {
                        "time":  idx.strftime("%Y-%m-%d"),
                        "value": round(float(v), 4),
                        "color": "#10b981" if (v or 0) >= 0 else "#ef4444",
                    }
                    for idx, v in zip(df.index, macd_df[hcol])
                    if not pd.isna(v)
                ]

        # Bollinger Bands
        bb = ta.bbands(close, length=20, std=2)
        if bb is not None and not bb.empty:
            ucol = next((c for c in bb.columns if "BBU" in c), None)
            mcol = next((c for c in bb.columns if "BBM" in c), None)
            lcol = next((c for c in bb.columns if "BBL" in c), None)
            if ucol: out["bb_upper"] = _series(bb[ucol])
            if mcol: out["bb_mid"]   = _series(bb[mcol])
            if lcol: out["bb_lower"] = _series(bb[lcol])

        # Moving averages
        for p in [20, 50, 200]:
            s = ta.sma(close, length=p)
            if s is not None:
                out[f"sma{p}"] = _series(s)
        for p in [9, 21]:
            e = ta.ema(close, length=p)
            if e is not None:
                out[f"ema{p}"] = _series(e)

        # Volume SMA
        if not volume.empty:
            vs = ta.sma(volume, length=20)
            if vs is not None:
                out["vol_sma20"] = _vol_series(vs)

        # ATR
        atr = ta.atr(high, low, close, length=14)
        if atr is not None and not atr.dropna().empty:
            out["atr"] = round(float(atr.dropna().iloc[-1]), 2)

        out["summary"] = _build_summary(df, out)

    except Exception as exc:
        out["_error"] = str(exc)

    return out


def _build_summary(df: pd.DataFrame, ind: dict) -> dict:
    close   = df["Close"]
    volume  = df["Volume"] if "Volume" in df.columns else pd.Series(dtype=float)
    current = float(close.iloc[-1])
    prev    = float(close.iloc[-2]) if len(close) > 1 else current
    s: dict = {
        "current_price": round(current, 2),
        "change_pct":    round((current - prev) / prev * 100, 2) if prev else 0,
        "period_high":   round(float(df["High"].max()), 2),
        "period_low":    round(float(df["Low"].min()), 2),
    }

    # RSI + direction
    if ind.get("rsi") and len(ind["rsi"]) >= 2:
        rsi_series = ind["rsi"]
        rv = rsi_series[-1]["value"]
        s["rsi"] = rv
        s["rsi_signal"] = "OVERSOLD" if rv < 30 else "OVERBOUGHT" if rv > 70 else "NEUTRAL"
        if len(rsi_series) >= 5:
            last5 = [round(r["value"], 1) for r in rsi_series[-5:]]
            s["rsi_last5"]    = last5
            s["rsi_direction"] = "RISING" if last5[-1] > last5[-3] else "FALLING"

    # Trend via SMAs (20, 50, 200)
    trend_count = 0
    for p in [20, 50, 200]:
        key = f"sma{p}"
        if ind.get(key):
            sv = ind[key][-1]["value"]
            s[f"sma{p}"]       = sv
            s[f"above_sma{p}"] = current > sv
            if current > sv:
                trend_count += 1

    s["trend"] = (
        "STRONG_UPTREND"   if trend_count == 3 else
        "UPTREND"          if trend_count == 2 else
        "DOWNTREND"        if trend_count == 1 else
        "STRONG_DOWNTREND"
    )

    # MACD cross signal
    ml_series = ind.get("macd_line", [])
    ms_series = ind.get("macd_signal", [])
    if len(ml_series) >= 2 and len(ms_series) >= 2:
        ml, ms     = ml_series[-1]["value"],  ms_series[-1]["value"]
        ml_p, ms_p = ml_series[-2]["value"],  ms_series[-2]["value"]
        bull,  bull_p = ml > ms, ml_p > ms_p
        if   bull and not bull_p: s["macd"] = "BULLISH_CROSS"
        elif not bull and bull_p: s["macd"] = "BEARISH_CROSS"
        else:                     s["macd"] = "BULLISH" if bull else "BEARISH"

    # ATR
    if ind.get("atr"):
        s["atr"] = ind["atr"]

    # Volume vs 20-day average
    if ind.get("vol_sma20") and not volume.empty:
        avg_vol  = ind["vol_sma20"][-1]["value"]
        last_vol = float(volume.iloc[-1]) if not pd.isna(volume.iloc[-1]) else 0
        if avg_vol and avg_vol > 0:
            ratio = round(last_vol / avg_vol, 2)
            s["volume_ratio"] = ratio
            s["volume_signal"] = (
                "HIGH — strong conviction" if ratio >= 2.0 else
                "ABOVE average"            if ratio >= 1.2 else
                "NORMAL"                   if ratio >= 0.8 else
                "LOW — weak conviction"
            )

    s["pct_from_high"] = round((current - s["period_high"]) / s["period_high"] * 100, 2)
    s["pct_from_low"]  = round((current - s["period_low"])  / s["period_low"]  * 100, 2)
    return s


def _get_fundamentals(ticker) -> dict:
    try:
        raw = ticker.info
        return {
            "name":       raw.get("longName", ""),
            "sector":     raw.get("sector", ""),
            "market_cap": raw.get("marketCap"),
            "pe_ratio":   raw.get("trailingPE"),
            "pb_ratio":   raw.get("priceToBook"),
            "div_yield":  raw.get("dividendYield"),
            "52w_high":   raw.get("fiftyTwoWeekHigh"),
            "52w_low":    raw.get("fiftyTwoWeekLow"),
            "avg_volume": raw.get("averageVolume"),
            "currency":   raw.get("currency", "PKR"),
        }
    except Exception:
        return {}
