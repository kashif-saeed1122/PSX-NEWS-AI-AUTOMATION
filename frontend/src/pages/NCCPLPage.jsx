import { useState, useEffect, useCallback } from 'react'
import {
  RefreshCw, Loader2, AlertCircle, Eye, X,
  TrendingUp, TrendingDown, Activity, BarChart2,
  Building2, FileText, Layers
} from 'lucide-react'
import { api } from '../api'

// ── Helpers ────────────────────────────────────────────────────────────────

function fmt(n, decimals = 0) {
  if (!n) return '—'
  return Number(n).toLocaleString('en-US', { maximumFractionDigits: decimals })
}

function fmtVal(v) {
  if (!v) return '—'
  if (v >= 1_000_000) return `Rs ${(v / 1_000_000).toFixed(1)}M`
  if (v >= 1_000) return `Rs ${(v / 1_000).toFixed(0)}K`
  return `Rs ${v}`
}

const ACTION_STYLE = {
  BUY:              'bg-emerald-900/50 text-emerald-300 border border-emerald-700/50',
  SELL:             'bg-red-900/50 text-red-300 border border-red-700/50',
  UNKNOWN:          'bg-slate-700/50 text-slate-400 border border-slate-600/50',
  ACTIVITY_DETECTED:'bg-amber-900/30 text-amber-400 border border-amber-700/40',
}

const STRENGTH_STYLE = {
  VERY_HIGH: 'text-emerald-300 font-bold',
  HIGH:      'text-emerald-400',
  MEDIUM:    'text-amber-400',
  LOW:       'text-slate-500',
}

const OI_SIGNAL = {
  BULLISH: 'text-emerald-400',
  BEARISH: 'text-red-400',
  NEUTRAL: 'text-slate-400',
}

// ── GIF Modal ──────────────────────────────────────────────────────────────

function GifModal({ gifUrl, title, onClose }) {
  if (!gifUrl) return null
  return (
    <div
      className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="relative bg-slate-900 border border-slate-700 rounded-xl shadow-2xl max-w-3xl w-full"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700">
          <div>
            <p className="text-white font-semibold text-sm">PSX Insider Disclosure Form</p>
            <p className="text-slate-400 text-xs mt-0.5 truncate max-w-md">{title}</p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white transition-colors ml-4">
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="p-4 flex items-center justify-center min-h-[300px] bg-white/5 rounded-b-xl">
          <img
            src={gifUrl}
            alt="Disclosure form"
            className="max-w-full max-h-[70vh] object-contain rounded"
            onError={e => { e.target.style.display = 'none'; e.target.nextSibling.style.display = 'flex' }}
          />
          <div className="hidden items-center gap-2 text-slate-400">
            <AlertCircle className="w-5 h-5" />
            <span className="text-sm">Could not load disclosure image</span>
          </div>
        </div>
        <div className="px-4 py-2 border-t border-slate-800 text-center">
          <a
            href={gifUrl}
            target="_blank"
            rel="noreferrer"
            className="text-xs text-emerald-400 hover:text-emerald-300"
          >
            Open full image in browser
          </a>
        </div>
      </div>
    </div>
  )
}

// ── Tab: Insider Transactions ───────────────────────────────────────────────

function InsiderTab() {
  const [data, setData]         = useState(null)
  const [loading, setLoading]   = useState(true)
  const [refreshing, setRef]    = useState(false)
  const [error, setError]       = useState(null)
  const [modal, setModal]       = useState(null)  // { gifUrl, title }

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    api.getNccplInsiders()
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])

  const refresh = () => {
    setRef(true)
    setError(null)
    api.refreshNccplInsiders()
      .then(() => load())
      .catch(e => setError(e.message))
      .finally(() => setRef(false))
  }

  if (loading) return (
    <div className="flex items-center justify-center h-64 text-slate-400">
      <Loader2 className="w-6 h-6 animate-spin mr-2" /> Loading insider data…
    </div>
  )

  const transactions = data?.transactions || []
  const buys         = data?.buy_signals  || []
  const sells        = data?.sell_signals || []
  const activity     = data?.activity_signals || []

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-slate-400 text-sm">
            {transactions.length} disclosures · last {data?.days_back || 7} days
            {data?.ocr_enabled && (
              <span className="ml-2 text-xs bg-emerald-900/40 text-emerald-400 border border-emerald-700/40 rounded px-2 py-0.5">
                OCR ON
              </span>
            )}
          </p>
        </div>
        <button
          onClick={refresh}
          disabled={refreshing}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 border border-slate-700 rounded-lg text-slate-300 hover:text-white text-sm transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
          {refreshing ? 'Scraping…' : 'Refresh'}
        </button>
      </div>

      {error && (
        <div className="flex items-center gap-2 p-3 bg-red-900/20 border border-red-800/40 rounded-lg text-red-400 text-sm">
          <AlertCircle className="w-4 h-4 flex-shrink-0" /> {error}
        </div>
      )}

      {/* Signal summary badges */}
      {(buys.length > 0 || sells.length > 0) && (
        <div className="flex flex-wrap gap-2">
          {buys.map(s => (
            <div key={s.symbol} className="flex items-center gap-2 px-3 py-2 bg-emerald-900/30 border border-emerald-700/40 rounded-lg">
              <TrendingUp className="w-4 h-4 text-emerald-400 flex-shrink-0" />
              <div>
                <span className="font-mono font-bold text-emerald-300 text-sm">{s.symbol}</span>
                <span className="text-xs text-emerald-500 ml-1.5">{s.signal_strength}</span>
                {s.total_quantity > 0 && (
                  <span className="text-xs text-slate-400 ml-1">· {fmt(s.total_quantity)} shares</span>
                )}
              </div>
            </div>
          ))}
          {sells.map(s => (
            <div key={s.symbol} className="flex items-center gap-2 px-3 py-2 bg-red-900/30 border border-red-700/40 rounded-lg">
              <TrendingDown className="w-4 h-4 text-red-400 flex-shrink-0" />
              <div>
                <span className="font-mono font-bold text-red-300 text-sm">{s.symbol}</span>
                <span className="text-xs text-red-500 ml-1.5">{s.signal_strength}</span>
                {s.total_quantity > 0 && (
                  <span className="text-xs text-slate-400 ml-1">· {fmt(s.total_quantity)} shares</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Transactions table */}
      {transactions.length === 0 ? (
        <div className="text-center py-12 text-slate-500">
          <FileText className="w-10 h-10 mx-auto mb-3 opacity-30" />
          <p>No insider disclosures found in the last 7 days</p>
          <p className="text-xs mt-1">{data?.error || ''}</p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-800">
                {['Date', 'Symbol', 'Company', 'Person / Role', 'Action', 'Shares', 'Price', 'Value', 'Signal', 'Form'].map(h => (
                  <th key={h} className="px-3 py-2.5 text-left text-xs text-slate-500 font-medium whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {transactions.map((tx, i) => {
                const rowBg = tx.action === 'BUY'
                  ? 'hover:bg-emerald-950/20'
                  : tx.action === 'SELL'
                    ? 'hover:bg-red-950/20'
                    : 'hover:bg-slate-800/30'
                return (
                  <tr key={i} className={`border-b border-slate-800/50 transition-colors ${rowBg}`}>
                    <td className="px-3 py-2.5 text-slate-400 text-xs whitespace-nowrap">{tx.date}</td>
                    <td className="px-3 py-2.5 font-mono font-bold text-white">{tx.symbol}</td>
                    <td className="px-3 py-2.5 text-slate-300 text-xs max-w-[140px] truncate">{tx.company}</td>
                    <td className="px-3 py-2.5 text-xs">
                      {tx.person
                        ? <><span className="text-slate-200">{tx.person}</span><br/><span className="text-slate-500">{tx.role}</span></>
                        : <span className="text-slate-500">{tx.role}</span>
                      }
                    </td>
                    <td className="px-3 py-2.5">
                      <span className={`text-xs px-2 py-0.5 rounded font-semibold ${ACTION_STYLE[tx.action] || ACTION_STYLE.UNKNOWN}`}>
                        {tx.action}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 font-mono text-slate-300 text-xs text-right whitespace-nowrap">
                      {tx.quantity > 0 ? fmt(tx.quantity) : '—'}
                    </td>
                    <td className="px-3 py-2.5 font-mono text-slate-300 text-xs text-right whitespace-nowrap">
                      {tx.price > 0 ? `Rs ${tx.price.toFixed(2)}` : '—'}
                    </td>
                    <td className="px-3 py-2.5 font-mono text-slate-300 text-xs text-right whitespace-nowrap">
                      {tx.value > 0 ? fmtVal(tx.value) : '—'}
                    </td>
                    <td className="px-3 py-2.5">
                      <span className={`text-xs font-semibold ${STRENGTH_STYLE[tx.signal_strength] || 'text-slate-500'}`}>
                        {tx.signal_strength}
                      </span>
                    </td>
                    <td className="px-3 py-2.5">
                      {tx.gif_url ? (
                        <button
                          onClick={() => setModal({ gifUrl: tx.gif_url, title: tx.title })}
                          className="flex items-center gap-1 text-xs text-emerald-400 hover:text-emerald-300 transition-colors"
                        >
                          <Eye className="w-3.5 h-3.5" /> View
                        </button>
                      ) : '—'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Activity signals */}
      {activity.length > 0 && (
        <div className="mt-4 p-3 bg-amber-900/10 border border-amber-800/30 rounded-lg">
          <p className="text-xs text-amber-500 font-medium mb-2">
            {activity.length} disclosures filed — direction unknown (OCR inconclusive or no GIF available)
          </p>
          {activity.map(s => (
            <p key={s.symbol} className="text-xs text-slate-400">
              <span className="font-mono text-slate-300">{s.symbol}</span>
              {' — '}{s.company} · {s.transactions} filing(s)
            </p>
          ))}
        </div>
      )}

      {data?.note && (
        <p className="text-xs text-slate-600 italic">{data.note}</p>
      )}

      {modal && (
        <GifModal gifUrl={modal.gifUrl} title={modal.title} onClose={() => setModal(null)} />
      )}
    </div>
  )
}

// ── Tab: Short Selling ─────────────────────────────────────────────────────

function ShortSellTab() {
  const [data, setData]       = useState(null)
  const [loading, setLoading] = useState(false)
  const [date, setDate]       = useState(new Date().toISOString().slice(0, 10))
  const [error, setError]     = useState(null)

  const load = useCallback((d) => {
    setLoading(true)
    setError(null)
    setData(null)
    api.getNccplShortSell(d)
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load(date) }, [])

  const records = data?.records || []
  const highShort = data?.high_short || []

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5">
          <span className="text-xs text-slate-400">Date</span>
          <input
            type="date"
            value={date}
            onChange={e => setDate(e.target.value)}
            className="bg-transparent text-slate-200 text-sm outline-none"
          />
        </div>
        <button
          onClick={() => load(date)}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 border border-slate-700 rounded-lg text-slate-300 hover:text-white text-sm transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          Load
        </button>
        {data && (
          <span className="text-xs text-slate-500">
            {records.length} symbols · {highShort.length} with &gt;5% short interest
          </span>
        )}
      </div>

      {error && (
        <div className="flex items-center gap-2 p-3 bg-red-900/20 border border-red-800/40 rounded-lg text-red-400 text-sm">
          <AlertCircle className="w-4 h-4 flex-shrink-0" /> {error}
        </div>
      )}

      {data?.error && !error && (
        <div className="flex items-center gap-2 p-3 bg-amber-900/20 border border-amber-800/40 rounded-lg text-amber-400 text-sm">
          <AlertCircle className="w-4 h-4 flex-shrink-0" /> {data.error}
        </div>
      )}

      {loading && (
        <div className="flex items-center justify-center h-32 text-slate-400">
          <Loader2 className="w-5 h-5 animate-spin mr-2" /> Downloading PDF…
        </div>
      )}

      {!loading && records.length > 0 && (
        <>
          {highShort.length > 0 && (
            <div className="p-3 bg-red-900/10 border border-red-800/30 rounded-lg">
              <p className="text-xs text-red-400 font-medium mb-2">High short interest (&gt;5% of volume)</p>
              <div className="flex flex-wrap gap-2">
                {highShort.slice(0, 10).map(r => (
                  <div key={r.symbol} className="px-2 py-1 bg-red-900/30 border border-red-700/40 rounded text-xs">
                    <span className="font-mono text-red-300 font-bold">{r.symbol}</span>
                    <span className="text-red-500 ml-1">{r.pct_short}%</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-800">
                  {['Symbol', 'Company', 'Short Volume', 'Total Volume', 'Short %'].map(h => (
                    <th key={h} className="px-3 py-2.5 text-left text-xs text-slate-500 font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {records.slice(0, 100).map((r, i) => (
                  <tr key={i} className="border-b border-slate-800/50 hover:bg-slate-800/30 transition-colors">
                    <td className="px-3 py-2 font-mono font-bold text-white">{r.symbol}</td>
                    <td className="px-3 py-2 text-slate-400 text-xs max-w-[180px] truncate">{r.company || '—'}</td>
                    <td className="px-3 py-2 font-mono text-red-400 text-right">{fmt(r.short_volume)}</td>
                    <td className="px-3 py-2 font-mono text-slate-400 text-right">{fmt(r.total_volume)}</td>
                    <td className="px-3 py-2 text-right">
                      <span className={`font-semibold text-xs ${r.pct_short >= 10 ? 'text-red-300' : r.pct_short >= 5 ? 'text-amber-400' : 'text-slate-400'}`}>
                        {r.pct_short > 0 ? `${r.pct_short}%` : '—'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {!loading && !error && records.length === 0 && data && !data.error && (
        <div className="text-center py-12 text-slate-500">
          <BarChart2 className="w-10 h-10 mx-auto mb-3 opacity-30" />
          <p>No short sell data found for {date}</p>
        </div>
      )}

      <p className="text-xs text-slate-600 italic">
        High short interest = potential downward pressure, OR setup for a short squeeze rally.
        PSX files are published after market close (~18:00 PKT).
      </p>
    </div>
  )
}

// ── Tab: Block Trades (OMTS) ───────────────────────────────────────────────

function BlockTradesTab() {
  const [data, setData]       = useState(null)
  const [loading, setLoading] = useState(false)
  const [date, setDate]       = useState(new Date().toISOString().slice(0, 10))
  const [error, setError]     = useState(null)

  const load = useCallback((d) => {
    setLoading(true)
    setError(null)
    setData(null)
    api.getNccplBlockTrades(d)
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load(date) }, [])

  const records    = data?.records     || []
  const largeBlocks = data?.large_blocks || []

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5">
          <span className="text-xs text-slate-400">Date</span>
          <input
            type="date"
            value={date}
            onChange={e => setDate(e.target.value)}
            className="bg-transparent text-slate-200 text-sm outline-none"
          />
        </div>
        <button
          onClick={() => load(date)}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 border border-slate-700 rounded-lg text-slate-300 hover:text-white text-sm transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          Load
        </button>
        {data && (
          <span className="text-xs text-slate-500">
            {records.length} trades · {largeBlocks.length} large blocks ≥ Rs 5M
          </span>
        )}
      </div>

      {error && (
        <div className="flex items-center gap-2 p-3 bg-red-900/20 border border-red-800/40 rounded-lg text-red-400 text-sm">
          <AlertCircle className="w-4 h-4 flex-shrink-0" /> {error}
        </div>
      )}

      {data?.error && !error && (
        <div className="flex items-center gap-2 p-3 bg-amber-900/20 border border-amber-800/40 rounded-lg text-amber-400 text-sm">
          <AlertCircle className="w-4 h-4 flex-shrink-0" /> {data.error}
        </div>
      )}

      {loading && (
        <div className="flex items-center justify-center h-32 text-slate-400">
          <Loader2 className="w-5 h-5 animate-spin mr-2" /> Downloading CSV…
        </div>
      )}

      {!loading && records.length > 0 && (
        <>
          {largeBlocks.length > 0 && (
            <div className="p-3 bg-blue-900/10 border border-blue-800/30 rounded-lg">
              <p className="text-xs text-blue-400 font-medium mb-2">Large institutional blocks ≥ Rs 5M</p>
              <div className="flex flex-wrap gap-2">
                {largeBlocks.slice(0, 10).map((r, i) => (
                  <div key={i} className="px-2 py-1 bg-blue-900/30 border border-blue-700/40 rounded text-xs">
                    <span className="font-mono text-blue-300 font-bold">{r.symbol}</span>
                    <span className="text-blue-500 ml-1">{fmtVal(r.value)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-800">
                  {['Symbol', 'Company', 'Volume', 'Rate', 'Value', 'Members (Buy/Sell)', 'Settle Date'].map(h => (
                    <th key={h} className="px-3 py-2.5 text-left text-xs text-slate-500 font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {records.slice(0, 100).map((r, i) => (
                  <tr key={i} className="border-b border-slate-800/50 hover:bg-slate-800/30 transition-colors">
                    <td className="px-3 py-2 font-mono font-bold text-white">{r.symbol}</td>
                    <td className="px-3 py-2 text-slate-400 text-xs max-w-[160px] truncate">{r.company || '—'}</td>
                    <td className="px-3 py-2 font-mono text-slate-300 text-right">{fmt(r.volume)}</td>
                    <td className="px-3 py-2 font-mono text-slate-300 text-right">
                      {r.rate > 0 ? `Rs ${r.rate.toFixed(2)}` : '—'}
                    </td>
                    <td className="px-3 py-2 font-mono text-right">
                      <span className={r.value >= 5_000_000 ? 'text-blue-300 font-semibold' : 'text-slate-300'}>
                        {fmtVal(r.value)}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-xs text-slate-500 max-w-[160px] truncate">{r.members || '—'}</td>
                    <td className="px-3 py-2 text-xs text-slate-500">{r.settle || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {!loading && !error && records.length === 0 && data && !data.error && (
        <div className="text-center py-12 text-slate-500">
          <Building2 className="w-10 h-10 mx-auto mb-3 opacity-30" />
          <p>No block trades found for {date}</p>
        </div>
      )}

      <p className="text-xs text-slate-600 italic">
        OMTS = Off-Market Transaction System. Large block trades signal institutional accumulation/distribution.
        Published after market close by PSX.
      </p>
    </div>
  )
}

// ── Tab: Futures Open Interest ─────────────────────────────────────────────

function FuturesOITab() {
  const [data, setData]       = useState(null)
  const [loading, setLoading] = useState(false)
  const [date, setDate]       = useState(new Date().toISOString().slice(0, 10))
  const [error, setError]     = useState(null)

  const load = useCallback((d) => {
    setLoading(true)
    setError(null)
    setData(null)
    api.getNccplFuturesOI(d)
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load(date) }, [])

  const records   = data?.records    || []
  const risingOI  = data?.rising_oi  || []
  const fallingOI = data?.falling_oi || []

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5">
          <span className="text-xs text-slate-400">Date</span>
          <input
            type="date"
            value={date}
            onChange={e => setDate(e.target.value)}
            className="bg-transparent text-slate-200 text-sm outline-none"
          />
        </div>
        <button
          onClick={() => load(date)}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 border border-slate-700 rounded-lg text-slate-300 hover:text-white text-sm transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          Load
        </button>
        {data && (
          <span className="text-xs text-slate-500">
            {records.length} contracts · {risingOI.length} rising OI · {fallingOI.length} falling
          </span>
        )}
      </div>

      {error && (
        <div className="flex items-center gap-2 p-3 bg-red-900/20 border border-red-800/40 rounded-lg text-red-400 text-sm">
          <AlertCircle className="w-4 h-4 flex-shrink-0" /> {error}
        </div>
      )}

      {data?.error && !error && (
        <div className="flex items-center gap-2 p-3 bg-amber-900/20 border border-amber-800/40 rounded-lg text-amber-400 text-sm">
          <AlertCircle className="w-4 h-4 flex-shrink-0" /> {data.error}
        </div>
      )}

      {loading && (
        <div className="flex items-center justify-center h-32 text-slate-400">
          <Loader2 className="w-5 h-5 animate-spin mr-2" /> Downloading XLS…
        </div>
      )}

      {!loading && records.length > 0 && (
        <>
          {risingOI.length > 0 && (
            <div className="p-3 bg-emerald-900/10 border border-emerald-800/30 rounded-lg">
              <p className="text-xs text-emerald-400 font-medium mb-2">
                Most active contracts — top {Math.min(risingOI.length, 10)} by OI volume
              </p>
              <div className="flex flex-wrap gap-2">
                {risingOI.slice(0, 12).map((r, i) => (
                  <div key={i} className="px-2 py-1 bg-emerald-900/30 border border-emerald-700/40 rounded text-xs">
                    <span className="font-mono text-emerald-300 font-bold">{r.symbol}</span>
                    <span className="text-slate-400 ml-1">{r.contract}</span>
                    <span className="text-emerald-500 ml-1">{fmt(r.oi_contracts)} lots</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-800">
                  {['Symbol', 'Contract', 'OI Contracts', 'OI Volume', 'OI Value', '% Float'].map(h => (
                    <th key={h} className="px-3 py-2.5 text-left text-xs text-slate-500 font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {records.slice(0, 60).map((r, i) => (
                  <tr key={i} className="border-b border-slate-800/50 hover:bg-slate-800/30 transition-colors">
                    <td className="px-3 py-2 font-mono font-bold text-white">{r.symbol}</td>
                    <td className="px-3 py-2 text-slate-400 text-xs">{r.contract || '—'}</td>
                    <td className="px-3 py-2 font-mono text-slate-300 text-right">{fmt(r.oi_contracts)}</td>
                    <td className="px-3 py-2 font-mono text-slate-300 text-right">{fmt(r.open_interest)}</td>
                    <td className="px-3 py-2 font-mono text-right">
                      <span className={r.oi_value >= 100_000_000 ? 'text-emerald-300 font-semibold' : 'text-slate-300'}>
                        {fmtVal(r.oi_value)}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right">
                      <span className={r.pct_freefloat >= 5 ? 'text-amber-400 font-semibold' : 'text-slate-500'}>
                        {r.pct_freefloat > 0 ? `${r.pct_freefloat}%` : '—'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {!loading && !error && records.length === 0 && data && !data.error && (
        <div className="text-center py-12 text-slate-500">
          <Layers className="w-10 h-10 mx-auto mb-3 opacity-30" />
          <p>No futures OI data found for {date}</p>
        </div>
      )}

      <p className="text-xs text-slate-600 italic">
        OI = Open Interest (number of outstanding futures contracts). High OI = active institutional positioning.
        % Float shows what fraction of free-float shares are held in futures. Published by PSX after market close.
      </p>
    </div>
  )
}

// ── Main NCCPLPage ─────────────────────────────────────────────────────────

const TABS = [
  { id: 'insiders',    label: 'Insider Transactions', icon: Eye },
  { id: 'short_sell',  label: 'Short Selling',        icon: TrendingDown },
  { id: 'omts',        label: 'Block Trades (OMTS)',   icon: Building2 },
  { id: 'futures_oi',  label: 'Futures OI',            icon: Activity },
]

export default function NCCPLPage() {
  const [tab, setTab] = useState('insiders')

  return (
    <div className="h-full flex flex-col">
      {/* Page header */}
      <div className="px-6 py-5 border-b border-slate-800 flex-shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-blue-600/20 border border-blue-600/40 rounded-lg flex items-center justify-center">
            <BarChart2 className="w-4 h-4 text-blue-400" />
          </div>
          <div>
            <h1 className="text-white font-bold text-lg leading-tight">NCCPL Intelligence</h1>
            <p className="text-slate-400 text-xs">Insider disclosures · Short sell · Block trades · Futures positioning</p>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 mt-4">
          {TABS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
                tab === id
                  ? 'bg-blue-600/20 text-blue-300 border border-blue-700/40'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-auto p-6">
        {tab === 'insiders'   && <InsiderTab />}
        {tab === 'short_sell' && <ShortSellTab />}
        {tab === 'omts'       && <BlockTradesTab />}
        {tab === 'futures_oi' && <FuturesOITab />}
      </div>
    </div>
  )
}
