import { useState, useEffect, useMemo } from 'react'
import {
  BarChart2, RefreshCw, Search, TrendingUp, TrendingDown, Loader2,
  AlertCircle, ArrowUpDown, CheckSquare, Square, Wand2, X, Zap
} from 'lucide-react'
import { api } from '../api'

function pct(val) {
  if (!val) return 0
  return parseFloat(String(val).replace('%','').replace(',','')) || 0
}
function vol(val) {
  if (!val) return 0
  return parseInt(String(val).replace(/,/g,''), 10) || 0
}

const COLS = [
  { key: 'SYMBOL',    label: 'Symbol',   sort: a => a.SYMBOL || '' },
  { key: 'SECTOR',    label: 'Sector',   sort: a => a.SECTOR || '' },
  { key: 'LISTED IN', label: 'Index',    sort: a => a['LISTED IN'] || '' },
  { key: 'LDCP',      label: 'Prev',     sort: a => parseFloat(String(a.LDCP).replace(/,/g,''))||0 },
  { key: 'OPEN',      label: 'Open',     sort: a => parseFloat(String(a.OPEN).replace(/,/g,''))||0 },
  { key: 'HIGH',      label: 'High',     sort: a => parseFloat(String(a.HIGH).replace(/,/g,''))||0 },
  { key: 'LOW',       label: 'Low',      sort: a => parseFloat(String(a.LOW).replace(/,/g,''))||0 },
  { key: 'CURRENT',   label: 'Current',  sort: a => parseFloat(String(a.CURRENT).replace(/,/g,''))||0 },
  { key: 'CHANGE (%)', label: 'Chg %',  sort: a => pct(a['CHANGE (%)']) },
  { key: 'VOLUME',    label: 'Volume',   sort: a => vol(a.VOLUME) },
]

const SIGNAL_META = {
  STRONG_BUY:  { color: 'text-emerald-400', bar: 'bg-emerald-500', icon: '🚀' },
  BUY:         { color: 'text-emerald-300', bar: 'bg-emerald-400', icon: '📈' },
  HOLD:        { color: 'text-amber-300',   bar: 'bg-amber-500',   icon: '⏸️' },
  SELL:        { color: 'text-red-300',     bar: 'bg-red-400',     icon: '📉' },
  STRONG_SELL: { color: 'text-red-400',     bar: 'bg-red-500',     icon: '🔻' },
}

function BatchResultsPanel({ result, onClose }) {
  if (!result) return null
  const { results = [], errors = [], analyzed_at } = result

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-start justify-center p-4 overflow-auto">
      <div className="w-full max-w-3xl bg-slate-900 border border-slate-700 rounded-2xl shadow-2xl mt-8">
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-700">
          <div>
            <h2 className="font-bold text-white">Screener Results</h2>
            <p className="text-xs text-slate-400 mt-0.5">
              {results.length} stocks · ranked by confidence
              {analyzed_at && ` · ${new Date(analyzed_at).toLocaleTimeString()}`}
            </p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white"><X className="w-5 h-5" /></button>
        </div>

        <div className="p-5 space-y-4 max-h-[80vh] overflow-y-auto">
          {/* Ranked table */}
          <div className="overflow-x-auto rounded-lg border border-slate-800">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-slate-800/60 text-slate-400 text-xs text-left">
                  <th className="px-4 py-2.5">Symbol</th>
                  <th className="px-4 py-2.5">Signal</th>
                  <th className="px-4 py-2.5 text-right">Confidence</th>
                  <th className="px-4 py-2.5 text-right">Entry Zone</th>
                  <th className="px-4 py-2.5 text-right">T1</th>
                  <th className="px-4 py-2.5 text-right">T2</th>
                  <th className="px-4 py-2.5 text-right">Stop Loss</th>
                  <th className="px-4 py-2.5 text-right">Horizon</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {results.map(r => {
                  const p   = r.prediction
                  const sig = SIGNAL_META[p.signal] || SIGNAL_META.HOLD
                  return (
                    <tr key={r.symbol} className="hover:bg-slate-800/40 transition-colors">
                      <td className="px-4 py-3 font-mono font-bold text-white">{r.symbol}</td>
                      <td className={`px-4 py-3 font-semibold whitespace-nowrap ${sig.color}`}>
                        {sig.icon} {p.signal?.replace('_', ' ')}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <div className="flex items-center justify-end gap-2">
                          <div className="w-16 h-1.5 bg-slate-700 rounded-full overflow-hidden">
                            <div className={`h-full rounded-full ${sig.bar}`} style={{ width: `${p.confidence}%` }} />
                          </div>
                          <span className={`font-bold tabular-nums ${sig.color}`}>{p.confidence}%</span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-right text-slate-300 tabular-nums">{p.entry_low}–{p.entry_high}</td>
                      <td className="px-4 py-3 text-right text-emerald-400 tabular-nums font-semibold">{p.target1}</td>
                      <td className="px-4 py-3 text-right text-emerald-300 tabular-nums">{p.target2}</td>
                      <td className="px-4 py-3 text-right text-red-400 tabular-nums font-semibold">{p.stop_loss}</td>
                      <td className="px-4 py-3 text-right text-slate-400 text-xs whitespace-nowrap">{p.time_horizon}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          {/* Per-stock reasoning */}
          <div className="space-y-2">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Trade Reasoning</p>
            {results.map(r => {
              const p   = r.prediction
              const sig = SIGNAL_META[p.signal] || SIGNAL_META.HOLD
              return (
                <div key={r.symbol} className="bg-slate-800/60 rounded-xl px-4 py-3 space-y-1.5">
                  <div className="flex items-center gap-2">
                    <span className="font-mono font-bold text-white">{r.symbol}</span>
                    {r.context?.info?.name && <span className="text-xs text-slate-500">{r.context.info.name}</span>}
                    <span className={`ml-auto text-xs font-semibold ${sig.color}`}>{sig.icon} {p.signal?.replace('_', ' ')}</span>
                  </div>
                  <p className="text-xs text-slate-300 leading-relaxed">{p.reasoning}</p>
                  {p.key_catalyst && (
                    <p className="text-xs text-amber-400">⚡ {p.key_catalyst}</p>
                  )}
                  {p.risk_factors?.length > 0 && (
                    <div className="flex flex-wrap gap-1 pt-0.5">
                      {p.risk_factors.map((rf, i) => (
                        <span key={i} className="text-[10px] text-red-400 bg-red-900/20 px-2 py-0.5 rounded-full">{rf}</span>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
          </div>

          {errors.length > 0 && (
            <p className="text-xs text-slate-500">No data for: {errors.map(e => e.symbol).join(', ')}</p>
          )}
        </div>
      </div>
    </div>
  )
}

export default function PSXPage() {
  const [data, setData]           = useState(null)
  const [loading, setLoading]     = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError]         = useState('')
  const [search, setSearch]       = useState('')
  const [sortKey, setSortKey]     = useState('VOLUME')
  const [sortDir, setSortDir]     = useState('desc')
  const [sectorFilter, setSector] = useState('')
  const [page, setPage]           = useState(0)
  const [selected, setSelected]   = useState([])        // symbol strings
  const [analyzing, setAnalyzing] = useState(false)
  const [analyzeErr, setAnalyzeErr] = useState('')
  const [result, setResult]       = useState(null)
  const [refreshMsg, setRefreshMsg] = useState('')
  const PAGE_SIZE = 50

  function loadFromFile() {
    setLoading(true); setError('')
    api.getPSX().then(setData).catch(e => setError(e.message)).finally(() => setLoading(false))
  }
  useEffect(() => { loadFromFile() }, [])

  async function liveRefresh() {
    setRefreshing(true); setRefreshMsg(''); setError('')
    try {
      const res = await api.refreshPSX()
      setRefreshMsg(res.message)
      // reload the file after refresh
      const fresh = await api.getPSX()
      setData(fresh)
    } catch (e) {
      setError(`Live refresh failed: ${e.message}`)
    } finally {
      setRefreshing(false)
    }
  }

  const stocks  = useMemo(() => data?.all_stocks || [], [data])
  const sectors = useMemo(() => [...new Set(stocks.map(s=>s.SECTOR).filter(Boolean))].sort(), [stocks])

  const filtered = useMemo(() => {
    let list = stocks
    if (search) {
      const q = search.toLowerCase()
      list = list.filter(s => (s.SYMBOL||'').toLowerCase().includes(q) || (s.SECTOR||'').toLowerCase().includes(q))
    }
    if (sectorFilter) list = list.filter(s => s.SECTOR === sectorFilter)
    const col = COLS.find(c => c.key === sortKey)
    if (col) list = [...list].sort((a,b) => {
      const va = col.sort(a), vb = col.sort(b)
      return va < vb ? (sortDir==='asc'?-1:1) : va > vb ? (sortDir==='asc'?1:-1) : 0
    })
    return list
  }, [stocks, search, sectorFilter, sortKey, sortDir])

  const paged      = filtered.slice(page*PAGE_SIZE, (page+1)*PAGE_SIZE)
  const totalPages = Math.ceil(filtered.length / PAGE_SIZE)

  function toggleSort(key) {
    if (sortKey===key) setSortDir(d=>d==='asc'?'desc':'asc')
    else { setSortKey(key); setSortDir('desc') }
    setPage(0)
  }

  function toggleStock(sym) {
    setSelected(prev => prev.includes(sym) ? prev.filter(s=>s!==sym) : [...prev, sym])
  }

  async function analyzeSelected() {
    if (!selected.length) return
    setAnalyzing(true); setAnalyzeErr(''); setResult(null)
    try {
      const data = await api.analyzeStockBatch(selected)
      setResult(data)
    } catch (e) {
      setAnalyzeErr(e.message)
    } finally {
      setAnalyzing(false)
    }
  }

  // Use computed index stats (derived from stock data — always reliable)
  const indicesComputed = data?.indices_computed || {}
  const INDEX_ORDER = ['KSE100', 'KSE100PR', 'KMI30', 'KMIALLSHR']

  return (
    <div className="p-6">
      {result && <BatchResultsPanel result={result} onClose={() => setResult(null)} />}

      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-2xl font-bold text-white">PSX Table</h1>
          <p className="text-slate-400 text-sm mt-1">
            {stocks.length > 0 ? `${stocks.length} stocks` : 'Live market data'}
            {data?.fetched_at && <span className="ml-2 text-slate-500">· fetched {data.fetched_at}</span>}
          </p>
        </div>
        <div className="flex gap-2">
          <button className="btn-ghost" onClick={loadFromFile} disabled={loading||refreshing}>
            <RefreshCw className={`w-4 h-4 ${loading?'animate-spin':''}`} />
            Reload
          </button>
          <button className="btn-primary" onClick={liveRefresh} disabled={loading||refreshing}>
            {refreshing
              ? <><Loader2 className="w-4 h-4 animate-spin" /> Fetching…</>
              : <><Zap className="w-4 h-4" /> Fetch Live PSX</>
            }
          </button>
        </div>
      </div>

      {refreshMsg && (
        <div className="flex items-center gap-2 bg-emerald-900/30 border border-emerald-700/40 text-emerald-400 rounded-lg px-3 py-2 mb-4 text-xs">
          ✓ {refreshMsg}
        </div>
      )}

      {/* Index cards — computed from stock data (reliable) */}
      {Object.keys(indicesComputed).length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
          {INDEX_ORDER.filter(k => indicesComputed[k]).map(key => {
            const idx      = indicesComputed[key]
            const chgN     = idx.change_pct ?? idx.avg_chg ?? 0  // prefer official index change_pct
            const up       = chgN >= 0
            const hasLevel = idx.level != null
            return (
              <div key={key} className="card px-4 py-3">
                {/* Index name + stock count */}
                <div className="flex items-center justify-between mb-1">
                  <p className="text-xs font-bold text-slate-300">{idx.name}</p>
                  <p className="text-[10px] text-slate-500">{idx.stocks != null ? `${idx.stocks} stocks` : ''}</p>
                </div>

                {/* Actual index level or avg change */}
                {hasLevel ? (
                  <p className="text-lg font-bold text-white">
                    {Number(idx.level).toLocaleString('en-PK', { maximumFractionDigits: 0 })}
                  </p>
                ) : (
                  <p className={`text-lg font-bold ${up ? 'text-emerald-400' : 'text-red-400'}`}>
                    {up ? '+' : ''}{Number(chgN).toFixed(2)}%
                  </p>
                )}

                {/* Change % row */}
                <p className={`text-xs flex items-center gap-0.5 mt-0.5 ${up ? 'text-emerald-400' : 'text-red-400'}`}>
                  {up ? <TrendingUp className="w-3 h-3"/> : <TrendingDown className="w-3 h-3"/>}
                  {up ? '+' : ''}{Number(chgN).toFixed(2)}%
                  {idx.change_pct != null && idx.avg_chg != null && (
                    <span className="text-slate-500 ml-1">(avg {idx.avg_chg >= 0 ? '+' : ''}{Number(idx.avg_chg).toFixed(2)}%)</span>
                  )}
                </p>

                {/* Breadth: advancing / declining */}
                {(idx.advancing != null) && (
                  <div className="flex gap-2 mt-1.5 text-[10px]">
                    <span className="text-emerald-500">▲ {idx.advancing}</span>
                    <span className="text-red-500">▼ {idx.declining}</span>
                    {idx.unchanged > 0 && <span className="text-slate-500">= {idx.unchanged}</span>}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Selected stocks action bar */}
      {selected.length > 0 && (
        <div className="card p-3 mb-4 flex flex-col gap-2 border-emerald-700/40 bg-emerald-900/10">
          <div className="flex items-center gap-3 flex-wrap">
            <span className="text-sm font-medium text-emerald-400">{selected.length} stocks selected:</span>
            <div className="flex flex-wrap gap-1">
              {selected.map(sym => (
                <span key={sym} className="flex items-center gap-1 px-2 py-0.5 bg-slate-700 rounded text-xs font-mono text-white">
                  {sym}
                  <button onClick={() => toggleStock(sym)} className="text-slate-400 hover:text-red-400">×</button>
                </span>
              ))}
            </div>
            <div className="ml-auto flex items-center gap-2">
              {analyzeErr && <span className="text-xs text-red-400">{analyzeErr}</span>}
              <button className="btn-ghost text-xs text-red-400 hover:text-red-300" onClick={() => setSelected([])}>Clear</button>
              <button className="btn-primary text-sm" onClick={analyzeSelected} disabled={analyzing}>
                {analyzing
                  ? <><Loader2 className="w-4 h-4 animate-spin"/>Analyzing {selected.length} stocks…</>
                  : <><Wand2 className="w-4 h-4"/>Analyze Selected ({selected.length})</>
                }
              </button>
            </div>
          </div>
          {analyzing && (
            <div className="text-xs text-slate-400 border-t border-slate-700/50 pt-2 space-y-1">
              <p className="text-slate-500">Running parallel TA + AI analysis on:</p>
              <div className="flex flex-wrap gap-1.5">
                {selected.map(sym => (
                  <span key={sym} className="flex items-center gap-1 px-2 py-0.5 bg-violet-900/30 border border-violet-700/40 rounded text-violet-300 text-xs font-mono">
                    <Loader2 className="w-2.5 h-2.5 animate-spin" />{sym}
                  </span>
                ))}
              </div>
              <p className="text-slate-600 text-[10px]">Each stock: yfinance historical → TA indicators → GPT analysis · all parallel</p>
            </div>
          )}
        </div>
      )}

      {/* Loading / error */}
      {loading && (
        <div className="flex items-center justify-center py-16 gap-3 text-slate-400">
          <Loader2 className="w-5 h-5 animate-spin"/> Loading PSX data…
        </div>
      )}
      {error && !loading && (
        <div className="flex items-center gap-2 bg-red-900/20 border border-red-700/40 text-red-400 rounded-xl px-4 py-3 text-sm mb-4">
          <AlertCircle className="w-4 h-4"/> {error}
        </div>
      )}

      {!loading && stocks.length > 0 && (
        <>
          {/* Filters */}
          <div className="flex flex-wrap gap-3 mb-4">
            <div className="relative flex-1 min-w-48">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400"/>
              <input type="text" value={search} onChange={e=>{setSearch(e.target.value);setPage(0)}}
                placeholder="Search symbol or sector…"
                className="w-full bg-slate-900 border border-slate-700 rounded-lg pl-9 pr-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500"/>
            </div>
            <select value={sectorFilter} onChange={e=>{setSector(e.target.value);setPage(0)}}
              className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500">
              <option value="">All sectors</option>
              {sectors.map(s=><option key={s} value={s}>{s}</option>)}
            </select>
            <span className="self-center text-sm text-slate-400">{filtered.length} results</span>
          </div>

          {/* Table */}
          <div className="card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-700 bg-slate-900/60">
                    <th className="px-3 py-2.5 w-10">
                      <button className="text-slate-500 hover:text-slate-300 text-xs"
                        onClick={() => {
                          const vis = paged.map(s => s.SYMBOL)
                          const allSel = vis.every(s => selected.includes(s))
                          setSelected(prev => allSel ? prev.filter(s => !vis.includes(s)) : [...new Set([...prev, ...vis])])
                        }}>
                        ☑
                      </button>
                    </th>
                    {COLS.map(col => (
                      <th key={col.key}
                        className="px-3 py-2.5 text-left text-xs font-medium text-slate-400 whitespace-nowrap cursor-pointer hover:text-slate-200 select-none"
                        onClick={() => toggleSort(col.key)}>
                        <span className="flex items-center gap-1">
                          {col.label}
                          <ArrowUpDown className={`w-3 h-3 ${sortKey===col.key?'text-emerald-400 opacity-100':'opacity-25'}`}/>
                        </span>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {paged.map((stock, i) => {
                    const chgNum = pct(stock['CHANGE (%)'])
                    const isKMI  = (stock['LISTED IN']||'').toLowerCase().includes('kmi')
                    const isSel  = selected.includes(stock.SYMBOL)
                    return (
                      <tr key={i}
                        className={`hover:bg-slate-700/30 transition-colors cursor-pointer ${isSel?'bg-emerald-900/15':''}`}
                        onClick={() => toggleStock(stock.SYMBOL)}>
                        <td className="px-3 py-2 text-center">
                          {isSel
                            ? <CheckSquare className="w-4 h-4 text-emerald-400 mx-auto"/>
                            : <Square className="w-4 h-4 text-slate-600 mx-auto"/>
                          }
                        </td>
                        <td className="px-3 py-2 font-mono font-semibold text-white whitespace-nowrap">
                          {stock.SYMBOL}
                          {isKMI && <span className="ml-1 text-amber-400 text-xs">☪</span>}
                        </td>
                        <td className="px-3 py-2 text-slate-400 text-xs max-w-32 truncate">{stock.SECTOR}</td>
                        <td className="px-3 py-2 text-slate-500 text-xs whitespace-nowrap">{stock['LISTED IN']}</td>
                        <td className="px-3 py-2 text-slate-300 text-right font-mono">{stock.LDCP}</td>
                        <td className="px-3 py-2 text-slate-300 text-right font-mono">{stock.OPEN}</td>
                        <td className="px-3 py-2 text-emerald-400 text-right font-mono">{stock.HIGH}</td>
                        <td className="px-3 py-2 text-red-400 text-right font-mono">{stock.LOW}</td>
                        <td className="px-3 py-2 text-white text-right font-mono font-semibold">{stock.CURRENT}</td>
                        <td className={`px-3 py-2 text-right font-mono font-semibold whitespace-nowrap ${chgNum>0?'text-emerald-400':chgNum<0?'text-red-400':'text-slate-400'}`}>
                          {chgNum>0?'+':''}{stock['CHANGE (%)']}
                        </td>
                        <td className="px-3 py-2 text-slate-400 text-right font-mono text-xs">{stock.VOLUME}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-between mt-4 text-sm text-slate-400">
              <span>Page {page+1} of {totalPages}</span>
              <div className="flex gap-2">
                <button className="btn-ghost" onClick={()=>setPage(p=>Math.max(0,p-1))} disabled={page===0}>Prev</button>
                <button className="btn-ghost" onClick={()=>setPage(p=>Math.min(totalPages-1,p+1))} disabled={page===totalPages-1}>Next</button>
              </div>
            </div>
          )}
        </>
      )}

      {!loading && !error && stocks.length === 0 && (
        <div className="text-center py-16">
          <BarChart2 className="w-12 h-12 text-slate-600 mx-auto mb-3"/>
          <p className="text-slate-400">No PSX data found.</p>
          <p className="text-slate-500 text-sm mt-1">Click "Fetch Live PSX" to load stock data.</p>
        </div>
      )}
    </div>
  )
}
