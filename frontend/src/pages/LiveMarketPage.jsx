import { useState, useEffect, useRef, useCallback } from 'react'
import { createChart, CrosshairMode } from 'lightweight-charts'
import {
  TrendingUp, TrendingDown, Minus, RefreshCw, Copy, Check,
  Brain, Newspaper, Zap, BarChart3, ChevronDown, ChevronUp,
  AlertCircle, Activity, Target, ShieldAlert, Clock,
} from 'lucide-react'
import { api } from '../api'

// ── Constants ──────────────────────────────────────────────────────────────

const WATCHLIST = [
  'OGDC','PPL','ENGRO','HBL','MCB','UBL','LUCK',
  'PSO','MARI','POL','EFERT','FFC','MLCF','DGKC',
  'HUBC','KAPCO','NBP','BAHL','MEBL','NESPL',
]

// All chips shown — same as WATCHLIST but user can also type any symbol
const ALL_CHIPS = WATCHLIST

const TIMEFRAMES = ['1D','1W','1M','3M','1Y']

const TONES = ['Bullish','Bearish','Neutral','Breaking','Weekly']

const CHART_THEME = {
  background:  { type: 'solid', color: '#0f172a' },
  textColor:   '#64748b',
  borderColor: '#1e293b',
  grid:        { vertLines: { color: '#1e293b' }, horzLines: { color: '#1e293b' } },
}

// ── Tag detector for news ─────────────────────────────────────────────────

function detectTag(title) {
  const t = title.toLowerCase()
  if (/result|earning|profit|revenue|dividend|quarter/.test(t))  return { label: 'EARNINGS',  cls: 'bg-emerald-900/60 text-emerald-300 border-emerald-700/40' }
  if (/sbp|policy.rate|interest.rate|discount.rate/.test(t))      return { label: 'SBP',       cls: 'bg-blue-900/60 text-blue-300 border-blue-700/40' }
  if (/imf|programme|bailout|tranche/.test(t))                    return { label: 'IMF',       cls: 'bg-purple-900/60 text-purple-300 border-purple-700/40' }
  if (/pkr|rupee|dollar|currency|exchange.rate/.test(t))          return { label: 'PKR/USD',   cls: 'bg-amber-900/60 text-amber-300 border-amber-700/40' }
  if (/inflation|cpi|wpi|prices/.test(t))                         return { label: 'MACRO',     cls: 'bg-orange-900/60 text-orange-300 border-orange-700/40' }
  if (/ipo|listing|offer/.test(t))                                 return { label: 'IPO',       cls: 'bg-cyan-900/60 text-cyan-300 border-cyan-700/40' }
  if (/halt|suspend|inquiry|secp|default/.test(t))                 return { label: 'ALERT',     cls: 'bg-red-900/60 text-red-300 border-red-700/40' }
  if (/oil|crude|opec|petroleum|gas/.test(t))                      return { label: 'OIL',       cls: 'bg-yellow-900/60 text-yellow-300 border-yellow-700/40' }
  if (/war|army|military|india|china|sanction|geopolit/.test(t))  return { label: 'GEO',       cls: 'bg-rose-900/60 text-rose-300 border-rose-700/40' }
  if (/budget|fiscal|tax|finance.minister/.test(t))               return { label: 'BUDGET',    cls: 'bg-indigo-900/60 text-indigo-300 border-indigo-700/40' }
  return { label: 'NEWS', cls: 'bg-slate-700/60 text-slate-300 border-slate-600/40' }
}

// ── Ticker Strip ───────────────────────────────────────────────────────────

function TickerStrip({ stocks, onSelect, selected }) {
  const trackRef = useRef()

  useEffect(() => {
    if (!trackRef.current || !stocks.length) return
    const el  = trackRef.current
    let start = null
    let id

    function step(ts) {
      if (!start) start = ts
      const elapsed = ts - start
      // scroll 40px/s, reset when fully scrolled past half
      el.scrollLeft = (elapsed * 0.04) % (el.scrollWidth / 2)
      id = requestAnimationFrame(step)
    }
    id = requestAnimationFrame(step)
    return () => cancelAnimationFrame(id)
  }, [stocks])

  // Duplicate list for seamless loop
  const doubled = [...stocks, ...stocks]

  return (
    <div className="bg-slate-950 border-b border-slate-800 overflow-hidden h-10 flex items-center">
      <div className="flex-shrink-0 px-3 border-r border-slate-800 h-full flex items-center gap-1.5 text-emerald-400 text-xs font-bold tracking-widest">
        <Activity className="w-3 h-3 animate-pulse" />
        LIVE
      </div>
      <div
        ref={trackRef}
        className="flex items-center gap-0 overflow-hidden whitespace-nowrap flex-1"
        style={{ scrollBehavior: 'auto' }}
      >
        {doubled.map((s, i) => {
          const up = s.change_pct >= 0
          return (
            <button
              key={i}
              onClick={() => onSelect(s.symbol)}
              className={`
                inline-flex items-center gap-2 px-4 h-10 text-xs border-r border-slate-800 transition-colors flex-shrink-0
                ${selected === s.symbol ? 'bg-emerald-900/30 text-emerald-300' : 'hover:bg-slate-800 text-slate-300'}
              `}
            >
              <span className="font-bold">{s.symbol}</span>
              <span>{s.price?.toFixed(2) ?? '—'}</span>
              <span className={up ? 'text-emerald-400' : 'text-red-400'}>
                {up ? '▲' : '▼'} {Math.abs(s.change_pct ?? 0).toFixed(2)}%
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}

// ── Price Chart (candlestick + SMAs + BB) ─────────────────────────────────

function PriceChart({ ohlcv, ta, timeframe }) {
  const containerRef = useRef()
  const chartRef     = useRef()

  useEffect(() => {
    if (!containerRef.current || !ohlcv?.length) return

    const chart = createChart(containerRef.current, {
      layout:      CHART_THEME,
      grid:        CHART_THEME.grid,
      crosshair:   { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: CHART_THEME.borderColor },
      timeScale:   {
        borderColor:     CHART_THEME.borderColor,
        timeVisible:     true,
        secondsVisible:  false,
      },
      width:  containerRef.current.clientWidth,
      height: 320,
    })

    const candle = chart.addCandlestickSeries({
      upColor:         '#10b981',
      downColor:       '#ef4444',
      borderUpColor:   '#10b981',
      borderDownColor: '#ef4444',
      wickUpColor:     '#10b981',
      wickDownColor:   '#ef4444',
    })
    candle.setData(ohlcv.map(d => ({ time: d.time, open: d.open, high: d.high, low: d.low, close: d.close })))

    // SMAs
    const smaColors = { sma20: '#f59e0b', sma50: '#3b82f6', sma200: '#ec4899' }
    for (const [key, color] of Object.entries(smaColors)) {
      if (ta?.[key]?.length) {
        const s = chart.addLineSeries({ color, lineWidth: 1, priceLineVisible: false, lastValueVisible: false })
        s.setData(ta[key])
      }
    }

    // Bollinger Bands
    if (ta?.bb_upper?.length && ta?.bb_lower?.length) {
      const bbOpts = { lineWidth: 1, priceLineVisible: false, lastValueVisible: false, lineStyle: 2 }
      chart.addLineSeries({ ...bbOpts, color: '#334155' }).setData(ta.bb_upper)
      chart.addLineSeries({ ...bbOpts, color: '#334155' }).setData(ta.bb_lower)
    }

    chart.timeScale().fitContent()
    chartRef.current = chart

    const resize = () => {
      if (containerRef.current)
        chart.applyOptions({ width: containerRef.current.clientWidth })
    }
    window.addEventListener('resize', resize)
    return () => { window.removeEventListener('resize', resize); chart.remove() }
  }, [ohlcv, ta])

  return <div ref={containerRef} className="w-full" />
}

// ── RSI Chart ─────────────────────────────────────────────────────────────

function RSIChart({ rsiData }) {
  const ref = useRef()

  useEffect(() => {
    if (!ref.current || !rsiData?.length) return

    const chart = createChart(ref.current, {
      layout:   CHART_THEME,
      grid:     CHART_THEME.grid,
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: {
        borderColor: CHART_THEME.borderColor,
        scaleMargins: { top: 0.1, bottom: 0.1 },
        autoScale: false,
      },
      timeScale: { borderColor: CHART_THEME.borderColor, timeVisible: true, secondsVisible: false },
      width:  ref.current.clientWidth,
      height: 110,
    })

    const line = chart.addLineSeries({ color: '#a78bfa', lineWidth: 2, priceLineVisible: false })
    line.setData(rsiData)
    line.applyOptions({ priceScaleId: 'right' })
    chart.priceScale('right').applyOptions({ autoScale: false, minimum: 0, maximum: 100 })

    // Overbought / oversold bands
    const ob = chart.addLineSeries({ color: '#ef4444', lineWidth: 1, lineStyle: 2, priceLineVisible: false, lastValueVisible: false })
    const os = chart.addLineSeries({ color: '#10b981', lineWidth: 1, lineStyle: 2, priceLineVisible: false, lastValueVisible: false })
    const times = rsiData.map(d => d.time)
    ob.setData(times.map(t => ({ time: t, value: 70 })))
    os.setData(times.map(t => ({ time: t, value: 30 })))

    chart.timeScale().fitContent()

    const resize = () => { if (ref.current) chart.applyOptions({ width: ref.current.clientWidth }) }
    window.addEventListener('resize', resize)
    return () => { window.removeEventListener('resize', resize); chart.remove() }
  }, [rsiData])

  return <div ref={ref} className="w-full" />
}

// ── Volume Chart ──────────────────────────────────────────────────────────

function VolumeChart({ ohlcv, volSma20 }) {
  const ref = useRef()

  useEffect(() => {
    if (!ref.current || !ohlcv?.length) return

    const chart = createChart(ref.current, {
      layout:   CHART_THEME,
      grid:     CHART_THEME.grid,
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: CHART_THEME.borderColor },
      timeScale: { borderColor: CHART_THEME.borderColor, timeVisible: true, secondsVisible: false },
      width:  ref.current.clientWidth,
      height: 90,
    })

    const hist = chart.addHistogramSeries({
      priceFormat:     { type: 'volume' },
      priceScaleId:    'vol',
      scaleMargins:    { top: 0.1, bottom: 0 },
    })
    hist.setData(ohlcv.map(d => ({
      time:  d.time,
      value: d.volume,
      color: d.close >= d.open ? '#10b98160' : '#ef444460',
    })))

    if (volSma20?.length) {
      const vline = chart.addLineSeries({ color: '#f59e0b', lineWidth: 1, priceLineVisible: false, lastValueVisible: false })
      vline.setData(volSma20)
    }

    chart.timeScale().fitContent()

    const resize = () => { if (ref.current) chart.applyOptions({ width: ref.current.clientWidth }) }
    window.addEventListener('resize', resize)
    return () => { window.removeEventListener('resize', resize); chart.remove() }
  }, [ohlcv, volSma20])

  return <div ref={ref} className="w-full" />
}

// ── OHLC Stats Bar ────────────────────────────────────────────────────────

function StatsBar({ ohlcv, info, ta }) {
  if (!ohlcv?.length) return null
  const last = ohlcv[ohlcv.length - 1]
  const prev = ohlcv.length > 1 ? ohlcv[ohlcv.length - 2] : last
  const chg  = last.close - prev.close
  const chgp = prev.close ? (chg / prev.close * 100) : 0
  const up   = chg >= 0

  const sum = ta?.summary || {}

  return (
    <div className="flex flex-wrap gap-x-5 gap-y-1 px-1 py-2 text-xs">
      <div>
        <span className="text-slate-500">O </span>
        <span className="text-slate-300">{last.open.toFixed(2)}</span>
      </div>
      <div>
        <span className="text-slate-500">H </span>
        <span className="text-emerald-400">{last.high.toFixed(2)}</span>
      </div>
      <div>
        <span className="text-slate-500">L </span>
        <span className="text-red-400">{last.low.toFixed(2)}</span>
      </div>
      <div>
        <span className="text-slate-500">C </span>
        <span className={up ? 'text-emerald-400' : 'text-red-400'}>{last.close.toFixed(2)}</span>
      </div>
      <div className={`font-semibold ${up ? 'text-emerald-400' : 'text-red-400'}`}>
        {up ? '▲' : '▼'} {Math.abs(chgp).toFixed(2)}%
      </div>
      <div className="ml-auto flex gap-4">
        {info?.['52w_high'] && (
          <div>
            <span className="text-slate-500">52W H </span>
            <span className="text-slate-300">{Number(info['52w_high']).toFixed(2)}</span>
          </div>
        )}
        {info?.['52w_low'] && (
          <div>
            <span className="text-slate-500">52W L </span>
            <span className="text-slate-300">{Number(info['52w_low']).toFixed(2)}</span>
          </div>
        )}
        {sum.rsi && (
          <div>
            <span className="text-slate-500">RSI </span>
            <span className={
              sum.rsi > 70 ? 'text-red-400' :
              sum.rsi < 30 ? 'text-emerald-400' : 'text-slate-300'
            }>{sum.rsi.toFixed(1)}</span>
          </div>
        )}
        {sum.trend && (
          <div>
            <span className="text-slate-500">Trend </span>
            <span className={
              sum.trend.includes('STRONG_UP') ? 'text-emerald-400' :
              sum.trend.includes('UP')        ? 'text-emerald-300' :
              sum.trend.includes('STRONG_DOWN') ? 'text-red-400' : 'text-red-300'
            }>{sum.trend.replace(/_/g, ' ')}</span>
          </div>
        )}
      </div>
    </div>
  )
}

// ── AI Predictions Panel ──────────────────────────────────────────────────

function AIPredictions({ symbol }) {
  const [state,    setState]    = useState('idle') // idle | loading | done | error
  const [result,   setResult]   = useState(null)
  const [errorMsg, setErrorMsg] = useState('')

  useEffect(() => {
    setState('idle')
    setResult(null)
    setErrorMsg('')
  }, [symbol])

  const run = useCallback(async () => {
    setState('loading')
    setResult(null)
    try {
      const data = await api.analyzeStock(symbol)
      setResult(data)
      setState('done')
    } catch (e) {
      setErrorMsg(e.message)
      setState('error')
    }
  }, [symbol])

  const p = result?.prediction

  const signalMeta = {
    STRONG_BUY:  { color: 'text-emerald-400', bg: 'bg-emerald-900/30 border-emerald-700/40', icon: '🚀' },
    BUY:         { color: 'text-emerald-300', bg: 'bg-emerald-900/20 border-emerald-800/40', icon: '📈' },
    HOLD:        { color: 'text-amber-300',   bg: 'bg-amber-900/20 border-amber-800/40',     icon: '⏸️' },
    SELL:        { color: 'text-red-300',     bg: 'bg-red-900/20 border-red-800/40',         icon: '📉' },
    STRONG_SELL: { color: 'text-red-400',     bg: 'bg-red-900/30 border-red-700/40',         icon: '🔻' },
  }
  const meta = signalMeta[p?.signal] || signalMeta.HOLD

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800">
        <div className="flex items-center gap-2 text-sm font-semibold text-white">
          <Brain className="w-4 h-4 text-violet-400" />
          AI Trader Analysis
        </div>
        <button
          onClick={run}
          disabled={state === 'loading'}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-violet-600 hover:bg-violet-500 text-white text-xs font-medium disabled:opacity-50 transition-colors"
        >
          {state === 'loading'
            ? <><RefreshCw className="w-3 h-3 animate-spin" /> Analyzing…</>
            : <><Zap className="w-3 h-3" /> Analyze {symbol}</>}
        </button>
      </div>

      <div className="p-4 space-y-3">
        {state === 'idle' && (
          <p className="text-slate-500 text-sm text-center py-4">
            Click "Analyze" to run the GPT trader-mindset analysis on {symbol}.
          </p>
        )}

        {state === 'error' && (
          <div className="flex items-start gap-2 text-red-400 text-sm">
            <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
            {errorMsg}
          </div>
        )}

        {state === 'loading' && (
          <div className="space-y-2 animate-pulse">
            {[80, 60, 70, 50].map((w, i) => (
              <div key={i} className="h-3 bg-slate-800 rounded" style={{ width: `${w}%` }} />
            ))}
          </div>
        )}

        {state === 'done' && p && (
          <>
            {/* Signal badge */}
            <div className={`rounded-lg border px-4 py-3 ${meta.bg}`}>
              <div className="flex items-center justify-between">
                <div className={`text-2xl font-bold ${meta.color}`}>
                  {meta.icon} {p.signal?.replace('_', ' ')}
                </div>
                <div className="text-right">
                  <div className="text-xs text-slate-400">Confidence</div>
                  <div className={`text-xl font-bold ${meta.color}`}>{p.confidence}%</div>
                </div>
              </div>
              {/* Confidence bar */}
              <div className="mt-2 h-1.5 bg-slate-800 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${
                    p.confidence >= 70 ? 'bg-emerald-500' :
                    p.confidence >= 50 ? 'bg-amber-500' : 'bg-red-500'
                  }`}
                  style={{ width: `${p.confidence}%` }}
                />
              </div>
            </div>

            {/* Entry / Targets / SL */}
            <div className="grid grid-cols-2 gap-2 text-xs">
              {[
                { label: 'Entry Zone',  value: `${p.entry_low} – ${p.entry_high}`,  icon: Target,     color: 'text-blue-300' },
                { label: 'Target 1',    value: p.target1,                            icon: TrendingUp,  color: 'text-emerald-300' },
                { label: 'Target 2',    value: p.target2,                            icon: TrendingUp,  color: 'text-emerald-400' },
                { label: 'Stop Loss',   value: p.stop_loss,                          icon: ShieldAlert, color: 'text-red-400' },
              ].map(({ label, value, icon: Icon, color }) => (
                <div key={label} className="rounded-lg border border-slate-800 bg-slate-950 px-3 py-2">
                  <div className="flex items-center gap-1 text-slate-500 mb-0.5">
                    <Icon className="w-3 h-3" />
                    {label}
                  </div>
                  <div className={`font-semibold ${color}`}>{value ?? '—'}</div>
                </div>
              ))}
            </div>

            {/* Horizon */}
            {p.time_horizon && (
              <div className="flex items-center gap-2 text-xs text-slate-400">
                <Clock className="w-3 h-3" />
                Time horizon: <span className="text-slate-200">{p.time_horizon}</span>
              </div>
            )}

            {/* Reasoning */}
            {p.reasoning && (
              <div className="rounded-lg border border-slate-800 bg-slate-950 p-3 text-xs text-slate-300 leading-relaxed">
                {p.reasoning}
              </div>
            )}

            {/* Trend + Momentum short */}
            <div className="grid grid-cols-2 gap-2 text-xs">
              {p.trend_assessment && (
                <div>
                  <div className="text-slate-500 mb-0.5">Trend</div>
                  <div className="text-slate-300">{p.trend_assessment}</div>
                </div>
              )}
              {p.momentum_assessment && (
                <div>
                  <div className="text-slate-500 mb-0.5">Momentum</div>
                  <div className="text-slate-300">{p.momentum_assessment}</div>
                </div>
              )}
            </div>

            {/* Risk factors */}
            {p.risk_factors?.length > 0 && (
              <div>
                <div className="text-xs text-slate-500 mb-1">Risk Factors</div>
                <ul className="space-y-1">
                  {p.risk_factors.map((r, i) => (
                    <li key={i} className="flex items-start gap-1.5 text-xs text-red-300">
                      <AlertCircle className="w-3 h-3 flex-shrink-0 mt-0.5" />
                      {r}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className="text-xs text-slate-600 text-center">
              Not financial advice. DYOR.
            </div>
          </>
        )}
      </div>
    </div>
  )
}

// ── News Feed ─────────────────────────────────────────────────────────────

function NewsFeed() {
  const [articles, setArticles] = useState([])
  const [loading,  setLoading]  = useState(true)

  useEffect(() => {
    api.getNews().then(data => {
      const all = []
      // Collect from all sources
      const addArticles = (source, arr) =>
        arr?.forEach(a => { if (a.title) all.push({ ...a, _source: source }) })

      addArticles('Google News',   data?.google_news?.articles)
      addArticles('Dawn Business', data?.dawn_business?.rss?.articles)
      addArticles('Profit.pk',     data?.profit_pakistan?.rss?.articles)
      addArticles('General News',  data?.general_news?.articles)

      // Sort by date (newest first), remove duplicates by title prefix
      const seen = new Set()
      const deduped = all.filter(a => {
        const key = a.title.slice(0, 40)
        if (seen.has(key)) return false
        seen.add(key)
        return true
      })

      setArticles(deduped.slice(0, 40))
    }).catch(() => {}).finally(() => setLoading(false))
  }, [])

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-slate-800 text-sm font-semibold text-white">
        <Newspaper className="w-4 h-4 text-blue-400" />
        Market News Feed
      </div>
      <div className="max-h-72 overflow-y-auto divide-y divide-slate-800/50">
        {loading && (
          <div className="p-4 text-center text-slate-500 text-sm">Loading news…</div>
        )}
        {!loading && articles.length === 0 && (
          <div className="p-4 text-center text-slate-500 text-sm">
            No news yet — run the pipeline to fetch.
          </div>
        )}
        {articles.map((a, i) => {
          const tag = detectTag(a.title)
          return (
            <a
              key={i}
              href={a.link}
              target="_blank"
              rel="noopener noreferrer"
              className="block px-4 py-2.5 hover:bg-slate-800/50 transition-colors group"
            >
              <div className="flex items-start gap-2">
                <span className={`flex-shrink-0 text-[10px] font-bold px-1.5 py-0.5 rounded border ${tag.cls}`}>
                  {tag.label}
                </span>
                <div className="min-w-0">
                  <p className="text-xs text-slate-300 group-hover:text-white leading-snug line-clamp-2">
                    {a.title}
                  </p>
                  <p className="text-[10px] text-slate-600 mt-0.5">{a._source}</p>
                </div>
              </div>
            </a>
          )
        })}
      </div>
    </div>
  )
}

// ── Post Generator ────────────────────────────────────────────────────────

function PostGenerator({ symbol }) {
  const [tone,     setTone]     = useState('Bullish')
  const [platform, setPlatform] = useState('facebook')
  const [post,     setPost]     = useState('')
  const [loading,  setLoading]  = useState(false)
  const [copied,   setCopied]   = useState(false)
  const [error,    setError]    = useState('')

  const generate = async () => {
    setLoading(true)
    setPost('')
    setError('')
    try {
      const res = await api.generatePost(symbol, tone, platform)
      setPost(res.post)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const copy = () => {
    if (!post) return
    navigator.clipboard.writeText(post)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-slate-800 text-sm font-semibold text-white">
        <BarChart3 className="w-4 h-4 text-pink-400" />
        AI Post Generator
      </div>

      <div className="p-4 space-y-3">
        {/* Platform toggle */}
        <div className="flex rounded-lg border border-slate-700 overflow-hidden text-xs">
          {['facebook', 'whatsapp'].map(p => (
            <button
              key={p}
              onClick={() => setPlatform(p)}
              className={`flex-1 py-1.5 capitalize font-medium transition-colors ${
                platform === p ? 'bg-emerald-700 text-white' : 'text-slate-400 hover:text-white hover:bg-slate-800'
              }`}
            >
              {p}
            </button>
          ))}
        </div>

        {/* Tone selector */}
        <div className="flex flex-wrap gap-1.5">
          {TONES.map(t => (
            <button
              key={t}
              onClick={() => setTone(t)}
              className={`px-2.5 py-1 rounded-full text-xs font-medium border transition-colors ${
                tone === t
                  ? 'bg-pink-700 border-pink-600 text-white'
                  : 'border-slate-700 text-slate-400 hover:border-slate-600 hover:text-white'
              }`}
            >
              {t}
            </button>
          ))}
        </div>

        {/* Stock + Generate */}
        <div className="flex gap-2">
          <div className="flex-1 px-3 py-2 rounded-lg bg-slate-950 border border-slate-700 text-xs text-slate-300">
            {symbol}
          </div>
          <button
            onClick={generate}
            disabled={loading}
            className="px-4 py-2 rounded-lg bg-pink-700 hover:bg-pink-600 text-white text-xs font-medium disabled:opacity-50 transition-colors"
          >
            {loading ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : 'Generate'}
          </button>
        </div>

        {error && <p className="text-xs text-red-400">{error}</p>}

        {/* Output */}
        {post && (
          <div className="relative">
            <pre className="whitespace-pre-wrap text-xs text-slate-300 bg-slate-950 border border-slate-800 rounded-lg p-3 max-h-44 overflow-y-auto leading-relaxed">
              {post}
            </pre>
            <button
              onClick={copy}
              className="absolute top-2 right-2 p-1.5 rounded-md bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white transition-colors"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Stock Selector Chips ───────────────────────────────────────────────────

function StockChips({ selected, onSelect, liveStocks }) {
  const [customSym, setCustomSym] = useState('')
  const priceMap = Object.fromEntries((liveStocks || []).map(s => [s.symbol, s]))

  const submitCustom = (e) => {
    e.preventDefault()
    const sym = customSym.trim().toUpperCase()
    if (sym) { onSelect(sym); setCustomSym('') }
  }

  return (
    <div className="space-y-2 flex-1">
      {/* All watchlist chips */}
      <div className="flex flex-wrap gap-1.5">
        {ALL_CHIPS.map(sym => {
          const live = priceMap[sym]
          const up   = live ? live.change_pct >= 0 : true
          return (
            <button
              key={sym}
              onClick={() => onSelect(sym)}
              className={`
                flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-xs font-medium transition-all
                ${selected === sym
                  ? 'bg-emerald-700/30 border-emerald-600/50 text-emerald-300'
                  : 'bg-slate-900 border-slate-700 text-slate-300 hover:border-slate-500 hover:text-white'}
              `}
            >
              {sym}
              {live && (
                <span className={`${up ? 'text-emerald-400' : 'text-red-400'}`}>
                  {up ? '▲' : '▼'}{Math.abs(live.change_pct).toFixed(1)}%
                </span>
              )}
            </button>
          )
        })}
      </div>

      {/* Custom symbol input */}
      <form onSubmit={submitCustom} className="flex gap-2">
        <input
          value={customSym}
          onChange={e => setCustomSym(e.target.value.toUpperCase())}
          placeholder="Any symbol… e.g. UNITY, SNGP, MARI"
          className="flex-1 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-700 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-emerald-600"
        />
        <button
          type="submit"
          className="px-3 py-1.5 rounded-lg bg-emerald-700 hover:bg-emerald-600 text-white text-xs font-medium transition-colors"
        >
          Load
        </button>
      </form>
    </div>
  )
}

// ── Legend ────────────────────────────────────────────────────────────────

function ChartLegend() {
  return (
    <div className="flex flex-wrap gap-3 text-xs text-slate-500 px-1 pb-1">
      {[
        { color: 'bg-amber-400', label: 'SMA 20' },
        { color: 'bg-blue-400',  label: 'SMA 50' },
        { color: 'bg-pink-400',  label: 'SMA 200' },
        { color: 'bg-slate-600', label: 'BB Bands', dashed: true },
      ].map(({ color, label, dashed }) => (
        <div key={label} className="flex items-center gap-1">
          <div className={`w-4 h-0.5 ${color} ${dashed ? 'border-dashed' : ''}`} />
          {label}
        </div>
      ))}
    </div>
  )
}

// ── Stock Screener ────────────────────────────────────────────────────────

const SIGNAL_META = {
  STRONG_BUY:  { color: 'text-emerald-400', bar: 'bg-emerald-500', icon: '🚀' },
  BUY:         { color: 'text-emerald-300', bar: 'bg-emerald-400', icon: '📈' },
  HOLD:        { color: 'text-amber-300',   bar: 'bg-amber-500',   icon: '⏸️' },
  SELL:        { color: 'text-red-300',     bar: 'bg-red-400',     icon: '📉' },
  STRONG_SELL: { color: 'text-red-400',     bar: 'bg-red-500',     icon: '🔻' },
}

function StockScreener({ liveStocks, onSelectSymbol }) {
  const [selected,  setSelected]  = useState(new Set())
  const [customSym, setCustomSym] = useState('')
  const [status,    setStatus]    = useState('idle') // idle | loading | done | error
  const [results,   setResults]   = useState([])
  const [errors,    setErrors]    = useState([])

  const priceMap = Object.fromEntries((liveStocks || []).map(s => [s.symbol, s]))

  const toggle = sym => setSelected(prev => {
    const n = new Set(prev)
    n.has(sym) ? n.delete(sym) : n.add(sym)
    return n
  })

  const addCustom = e => {
    e.preventDefault()
    const sym = customSym.trim().toUpperCase()
    if (sym) { toggle(sym); setCustomSym('') }
  }

  const run = async () => {
    if (!selected.size) return
    setStatus('loading')
    setResults([])
    setErrors([])
    try {
      const data = await api.analyzeStockBatch([...selected])
      setResults(data.results || [])
      setErrors(data.errors  || [])
      setStatus('done')
    } catch {
      setStatus('error')
    }
  }

  return (
    <div className="rounded-xl border border-violet-800/40 bg-slate-900 p-4 space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <BarChart3 className="w-4 h-4 text-violet-400" />
          <span className="text-sm font-semibold text-white">Stock Screener</span>
          {selected.size > 0 && (
            <span className="px-2 py-0.5 rounded-full bg-violet-900/50 text-violet-300 text-xs font-medium">
              {selected.size} selected
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <button onClick={() => setSelected(new Set(WATCHLIST))} className="text-xs text-slate-500 hover:text-slate-300 transition-colors">All</button>
          <button onClick={() => setSelected(new Set())}          className="text-xs text-slate-500 hover:text-slate-300 transition-colors">Clear</button>
          <button
            onClick={run}
            disabled={!selected.size || status === 'loading'}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white text-xs font-medium transition-colors"
          >
            {status === 'loading'
              ? <><RefreshCw className="w-3 h-3 animate-spin" /> Screening…</>
              : <><Zap className="w-3 h-3" /> {selected.size ? `Screen (${selected.size})` : 'Screen'}</>
            }
          </button>
        </div>
      </div>

      {/* Multi-select chips */}
      <div className="flex flex-wrap gap-1.5">
        {WATCHLIST.map(sym => {
          const on   = selected.has(sym)
          const live = priceMap[sym]
          const up   = live ? live.change_pct >= 0 : true
          return (
            <button
              key={sym}
              onClick={() => toggle(sym)}
              className={`flex items-center gap-1 px-2.5 py-1 rounded-lg border text-xs font-medium transition-all ${
                on
                  ? 'bg-violet-700/40 border-violet-500/60 text-violet-200'
                  : 'bg-slate-950 border-slate-700 text-slate-400 hover:border-slate-500 hover:text-white'
              }`}
            >
              {on && <Check className="w-2.5 h-2.5 flex-shrink-0" />}
              {sym}
              {live && (
                <span className={`${up ? 'text-emerald-400' : 'text-red-400'} opacity-70`}>
                  {up ? '+' : ''}{live.change_pct?.toFixed(1)}%
                </span>
              )}
            </button>
          )
        })}
      </div>

      {/* Custom symbol add */}
      <form onSubmit={addCustom} className="flex gap-2">
        <input
          value={customSym}
          onChange={e => setCustomSym(e.target.value.toUpperCase())}
          placeholder="Add any symbol… e.g. UNITY, SNGP, MARI"
          className="flex-1 px-3 py-1.5 rounded-lg bg-slate-950 border border-slate-700 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-violet-600"
        />
        <button type="submit" className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-white text-xs font-medium transition-colors">
          Add
        </button>
      </form>

      {/* Loading skeleton */}
      {status === 'loading' && (
        <div className="space-y-1.5 animate-pulse pt-1">
          {Array.from({ length: Math.min(selected.size, 6) }, (_, i) => (
            <div key={i} className="h-9 bg-slate-800/60 rounded-lg" />
          ))}
          <p className="text-xs text-slate-500 text-center pt-1">
            Analyzing {selected.size} stocks in parallel…
          </p>
        </div>
      )}

      {/* Results table */}
      {status === 'done' && results.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-slate-800">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-slate-800/50 text-slate-400 text-left">
                <th className="px-3 py-2">Symbol</th>
                <th className="px-3 py-2">Signal</th>
                <th className="px-3 py-2 text-right">Conf</th>
                <th className="px-3 py-2 text-right">Entry Zone</th>
                <th className="px-3 py-2 text-right">T1</th>
                <th className="px-3 py-2 text-right">SL</th>
                <th className="px-3 py-2 text-right">Horizon</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/50">
              {results.map(r => {
                const p   = r.prediction
                const sig = SIGNAL_META[p.signal] || SIGNAL_META.HOLD
                return (
                  <tr
                    key={r.symbol}
                    onClick={() => onSelectSymbol(r.symbol)}
                    className="hover:bg-slate-800/40 cursor-pointer transition-colors"
                    title="Click to load chart"
                  >
                    <td className="px-3 py-2.5 font-bold text-white">{r.symbol}</td>
                    <td className={`px-3 py-2.5 font-semibold whitespace-nowrap ${sig.color}`}>
                      {sig.icon} {p.signal?.replace('_', ' ')}
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        <div className="w-10 h-1.5 bg-slate-700 rounded-full overflow-hidden">
                          <div className={`h-full rounded-full ${sig.bar}`} style={{ width: `${p.confidence}%` }} />
                        </div>
                        <span className={`font-bold tabular-nums ${sig.color}`}>{p.confidence}%</span>
                      </div>
                    </td>
                    <td className="px-3 py-2.5 text-right text-slate-300 tabular-nums">{p.entry_low}–{p.entry_high}</td>
                    <td className="px-3 py-2.5 text-right text-emerald-400 tabular-nums font-medium">{p.target1}</td>
                    <td className="px-3 py-2.5 text-right text-red-400   tabular-nums font-medium">{p.stop_loss}</td>
                    <td className="px-3 py-2.5 text-right text-slate-400 whitespace-nowrap">{p.time_horizon}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Failed symbols */}
      {status === 'done' && errors.length > 0 && (
        <p className="text-xs text-slate-600">
          No data for: {errors.map(e => e.symbol).join(', ')}
        </p>
      )}

      {status === 'error' && (
        <div className="flex items-center gap-2 text-red-400 text-xs">
          <AlertCircle className="w-3.5 h-3.5" />
          Screening failed — check API key and server connection.
        </div>
      )}
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────

export default function LiveMarketPage() {
  const [symbol,       setSymbol]       = useState('OGDC')
  const [timeframe,    setTimeframe]    = useState('1M')
  const [chartData,    setChartData]    = useState(null)
  const [chartLoading, setChartLoading] = useState(false)
  const [chartError,   setChartError]   = useState('')
  const [liveStocks,   setLiveStocks]   = useState([])
  const [screenerOpen, setScreenerOpen] = useState(false)

  // Load live ticker data on mount + every 30s
  useEffect(() => {
    const load = () => {
      api.getLiveStocks()
         .then(res => setLiveStocks(res.stocks || []))
         .catch(() => {})
    }
    load()
    const iv = setInterval(load, 30_000)
    return () => clearInterval(iv)
  }, [])

  // Load chart data when symbol or timeframe changes
  useEffect(() => {
    setChartLoading(true)
    setChartError('')
    api.getHistorical(symbol, timeframe)
       .then(data => {
         if (data.error) { setChartError(data.error); setChartData(null) }
         else setChartData(data)
       })
       .catch(e => setChartError(e.message))
       .finally(() => setChartLoading(false))
  }, [symbol, timeframe])

  const ohlcv = chartData?.ohlcv || []
  const ta    = chartData?.ta    || {}
  const info  = chartData?.info  || {}

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Ticker Strip */}
      <TickerStrip stocks={liveStocks} onSelect={setSymbol} selected={symbol} />

      {/* Body */}
      <div className="flex-1 overflow-auto p-4">
        <div className="flex gap-4 max-w-[1600px] mx-auto">

          {/* ── Left: Charts ─────────────────────────────────── */}
          <div className="flex-1 min-w-0 space-y-3">

            {/* Stock selector + timeframes */}
            <div className="flex flex-col gap-2">
              <div className="flex items-start gap-3">
                <StockChips selected={symbol} onSelect={setSymbol} liveStocks={liveStocks} />
                <div className="flex-shrink-0 flex items-center gap-2">
                  <button
                    onClick={() => setScreenerOpen(o => !o)}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium transition-colors ${
                      screenerOpen
                        ? 'bg-violet-700/40 border-violet-600/50 text-violet-300'
                        : 'bg-slate-900 border-slate-700 text-slate-400 hover:border-slate-500 hover:text-white'
                    }`}
                  >
                    <BarChart3 className="w-3.5 h-3.5" />
                    Screener
                  </button>
                  <div className="flex rounded-lg border border-slate-800 overflow-hidden text-xs">
                    {TIMEFRAMES.map(tf => (
                      <button
                        key={tf}
                        onClick={() => setTimeframe(tf)}
                        className={`px-3 py-1.5 font-medium transition-colors ${
                          timeframe === tf
                            ? 'bg-slate-700 text-white'
                            : 'text-slate-400 hover:bg-slate-800 hover:text-white'
                        }`}
                      >
                        {tf}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
              {screenerOpen && (
                <StockScreener liveStocks={liveStocks} onSelectSymbol={sym => { setSymbol(sym); setScreenerOpen(false) }} />
              )}
            </div>

            {/* Chart card */}
            <div className="rounded-xl border border-slate-800 bg-slate-900 overflow-hidden">
              {/* Header */}
              <div className="flex items-center justify-between px-4 py-2.5 border-b border-slate-800">
                <div>
                  <span className="text-base font-bold text-white">{symbol}</span>
                  {info.name && <span className="ml-2 text-xs text-slate-400">{info.name}</span>}
                  {info.sector && <span className="ml-2 text-xs text-slate-600">{info.sector}</span>}
                </div>
                {chartLoading && <RefreshCw className="w-4 h-4 animate-spin text-slate-500" />}
              </div>

              {/* OHLC stats */}
              {ohlcv.length > 0 && (
                <div className="border-b border-slate-800 px-3">
                  <StatsBar ohlcv={ohlcv} info={info} ta={ta} />
                </div>
              )}

              {/* Error state */}
              {chartError && (
                <div className="p-6 text-center text-slate-500 text-sm">
                  <AlertCircle className="w-5 h-5 mx-auto mb-2 text-red-400" />
                  {chartError}
                  <p className="text-xs mt-1">Check that yfinance is installed and the symbol is valid on Yahoo Finance (.KA).</p>
                </div>
              )}

              {/* Loading skeleton */}
              {chartLoading && !chartError && (
                <div className="h-80 flex items-center justify-center">
                  <div className="text-slate-500 text-sm animate-pulse">Loading chart data…</div>
                </div>
              )}

              {/* Charts */}
              {!chartLoading && ohlcv.length > 0 && (
                <div className="px-2 pt-2">
                  <PriceChart ohlcv={ohlcv} ta={ta} timeframe={timeframe} />
                  <ChartLegend />
                </div>
              )}

              {/* RSI */}
              {!chartLoading && ta?.rsi?.length > 0 && (
                <div className="border-t border-slate-800 px-2 pt-1">
                  <div className="text-[10px] text-slate-600 px-1 py-0.5">RSI (14)</div>
                  <RSIChart rsiData={ta.rsi} />
                </div>
              )}

              {/* Volume */}
              {!chartLoading && ohlcv.length > 0 && (
                <div className="border-t border-slate-800 px-2 pt-1">
                  <div className="text-[10px] text-slate-600 px-1 py-0.5">Volume</div>
                  <VolumeChart ohlcv={ohlcv} volSma20={ta?.vol_sma20} />
                </div>
              )}
            </div>

            {/* Fundamentals row */}
            {info.pe_ratio && (
              <div className="flex flex-wrap gap-2">
                {[
                  { label: 'P/E',          value: Number(info.pe_ratio).toFixed(1)  },
                  { label: 'P/B',          value: Number(info.pb_ratio).toFixed(2)  },
                  { label: 'Div Yield',    value: info.div_yield ? `${(info.div_yield * 100).toFixed(2)}%` : '—' },
                  { label: 'Avg Volume',   value: info.avg_volume ? `${(info.avg_volume / 1e6).toFixed(1)}M` : '—' },
                  { label: 'Market Cap',   value: info.market_cap ? `PKR ${(info.market_cap / 1e9).toFixed(1)}B` : '—' },
                ].map(({ label, value }) => (
                  <div key={label} className="rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-xs">
                    <div className="text-slate-500">{label}</div>
                    <div className="text-slate-200 font-medium">{value}</div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* ── Right: AI + News + Post Generator ────────────── */}
          <div className="w-80 flex-shrink-0 space-y-3">
            <AIPredictions symbol={symbol} />
            <NewsFeed />
            <PostGenerator symbol={symbol} />
          </div>
        </div>
      </div>
    </div>
  )
}
