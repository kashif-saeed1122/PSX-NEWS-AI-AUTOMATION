import { useState, useEffect, useMemo } from 'react'
import {
  Newspaper, RefreshCw, ExternalLink, Calendar, Loader2, AlertCircle,
  CheckSquare, Square, Wand2, X, ChevronDown, ChevronUp, Info
} from 'lucide-react'
import { api } from '../api'
import PostsViewer from '../components/PostsViewer'

const SOURCES = [
  { key: 'google_news',     label: 'Google News',   color: 'text-blue-400',    dot: 'bg-blue-400',    active: 'border-blue-500' },
  { key: 'dawn_business',   label: 'Dawn Business', color: 'text-amber-400',   dot: 'bg-amber-400',   active: 'border-amber-500' },
  { key: 'profit_pakistan', label: 'Profit.pk',     color: 'text-emerald-400', dot: 'bg-emerald-400', active: 'border-emerald-500' },
]

function extractArticles(data, key) {
  if (!data) return []
  const rssArticles = (key === 'google_news' ? data.articles : data?.rss?.articles) || []
  const headlines   = (data?.direct_scrape?.headlines || []).filter(Boolean).map(h => ({
    title: h, summary: '', date: '', link: '', source: data.source || key,
  }))
  return [
    ...rssArticles.map(a => ({
      title:   a.title   || '',
      summary: a.summary || '',
      date:    a.published || a.date || '',
      link:    a.link    || '',
      source:  data.source || key,
    })),
    ...headlines,
  ]
}

function parseDate(raw) {
  if (!raw) return null
  try {
    // RFC 2822 format (RSS)
    const d = new Date(raw)
    return isNaN(d.getTime()) ? null : d
  } catch { return null }
}

function formatDate(raw) {
  const d = parseDate(raw)
  if (!d) return ''
  return d.toLocaleString('en-PK', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function getWindow(analysisDate, articleDate) {
  if (!articleDate) return 'secondary'
  const ad  = new Date(analysisDate)
  const art = parseDate(articleDate)
  if (!art) return 'secondary'
  const diffDays = (ad - art) / (1000 * 60 * 60 * 24)
  if (diffDays <= 2)  return 'primary'
  if (diffDays <= 5)  return 'secondary'
  return 'ignore'
}

const WINDOW_STYLE = {
  primary:   { label: 'PRIMARY',   cls: 'bg-emerald-900/40 border-emerald-700/60 text-emerald-300', badge: 'bg-emerald-700 text-emerald-100' },
  secondary: { label: 'SECONDARY', cls: 'bg-slate-800 border-slate-700',                            badge: 'bg-slate-600 text-slate-300' },
  ignore:    { label: 'OLD',       cls: 'bg-slate-900 border-slate-800 opacity-50',                 badge: 'bg-slate-700 text-slate-500' },
}

function ArticleCard({ article, idx, analysisDate, selected, onToggle, showWindow }) {
  const win    = showWindow ? getWindow(analysisDate, article.date) : 'secondary'
  const style  = WINDOW_STYLE[win]
  const isIgn  = win === 'ignore'

  return (
    <div
      className={`rounded-xl border px-4 py-3 transition-all cursor-pointer ${style.cls} ${
        selected ? 'ring-2 ring-emerald-500' : 'hover:border-slate-600'
      } ${isIgn ? 'pointer-events-none' : ''}`}
      onClick={() => !isIgn && onToggle(article)}
    >
      <div className="flex items-start gap-3">
        {/* Checkbox */}
        <div className="flex-shrink-0 mt-0.5">
          {selected
            ? <CheckSquare className="w-4 h-4 text-emerald-400" />
            : <Square className="w-4 h-4 text-slate-500" />
          }
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <div className="flex items-center gap-2 flex-wrap mb-1">
              <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${style.badge}`}>{style.label}</span>
              <span className="text-xs text-slate-500">#{idx + 1}</span>
            </div>
            {article.link && !isIgn && (
              <a href={article.link} target="_blank" rel="noopener noreferrer"
                onClick={e => e.stopPropagation()}
                className="flex-shrink-0 text-slate-500 hover:text-emerald-400 transition-colors">
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            )}
          </div>
          <p className="text-sm font-medium text-white leading-snug">{article.title}</p>
          {article.summary && (
            <p className="text-xs text-slate-400 mt-1 line-clamp-2">{article.summary}</p>
          )}
          {article.date && (
            <div className="flex items-center gap-1 mt-1.5 text-xs text-slate-500">
              <Calendar className="w-3 h-3" />
              {formatDate(article.date)}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function CustomAnalysisPanel({ result, onClose }) {
  const [tab, setTab] = useState('report')
  if (!result) return null

  const { news_briefing, trading_report, posts } = result
  const ov = trading_report?.market_overview || {}

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-start justify-end p-4 overflow-auto">
      <div className="w-full max-w-2xl bg-slate-900 border border-slate-700 rounded-2xl shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-700">
          <div>
            <h2 className="font-bold text-white">Custom Analysis Result</h2>
            <p className="text-xs text-slate-400 mt-0.5">
              {result.articles_used} articles ({result.primary_count} primary) · {result.report_file}
            </p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Quick stats */}
        <div className="grid grid-cols-3 gap-2 px-5 py-3 border-b border-slate-700 text-xs">
          <div className="bg-slate-800 rounded-lg px-3 py-2">
            <p className="text-slate-400">News Sentiment</p>
            <p className="font-bold text-white mt-0.5">{news_briefing?.overall_sentiment || '—'}</p>
          </div>
          <div className="bg-slate-800 rounded-lg px-3 py-2">
            <p className="text-slate-400">Session Bias</p>
            <p className="font-bold text-white mt-0.5">{ov.session_bias || '—'}</p>
          </div>
          <div className="bg-slate-800 rounded-lg px-3 py-2">
            <p className="text-slate-400">KSE-100</p>
            <p className="font-bold text-white mt-0.5">{ov.kse100_level || '—'}</p>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 px-5 pt-3 border-b border-slate-800">
          {['report', 'facebook', 'free_wa', 'paid_wa', 'comprehensive'].map(t => (
            <button key={t}
              onClick={() => setTab(t)}
              className={`px-3 py-2 text-xs font-medium border-b-2 -mb-px transition-all ${
                tab === t ? 'text-emerald-400 border-emerald-400' : 'text-slate-400 border-transparent hover:text-slate-200'
              }`}>
              {t === 'report' ? 'Report' : t === 'facebook' ? 'Facebook' :
               t === 'free_wa' ? 'Free WA' : t === 'paid_wa' ? 'Paid WA' : 'Full Report'}
            </button>
          ))}
        </div>

        <div className="p-5 max-h-[65vh] overflow-y-auto">
          {tab === 'report' && (
            <div className="space-y-3 text-sm">
              <p className="text-slate-300">{ov.summary}</p>
              {(trading_report?.conventional_portfolio?.buy_picks || []).slice(0, 5).map((p, i) => (
                <div key={i} className="flex items-center gap-3 bg-slate-800 rounded-lg px-3 py-2">
                  <span className="font-mono font-bold text-emerald-400">{p.symbol}</span>
                  <span className="text-slate-300 text-xs flex-1">{p.reasoning?.slice(0, 80)}…</span>
                  <span className="text-xs text-slate-400">→ Rs{p.target_price}</span>
                </div>
              ))}
            </div>
          )}
          {tab !== 'report' && posts && (
            <PostsViewer singlePost={
              tab === 'facebook'      ? posts.facebook :
              tab === 'free_wa'       ? posts.free_whatsapp :
              tab === 'paid_wa'       ? posts.paid_whatsapp :
                                        posts.comprehensive
            } />
          )}
        </div>
      </div>
    </div>
  )
}

export default function NewsPage() {
  const [activeTab, setActiveTab]   = useState('google_news')
  const [data, setData]             = useState(null)
  const [loading, setLoading]       = useState(true)
  const [error, setError]           = useState('')
  const [analysisDate, setDate]     = useState(() => new Date().toISOString().split('T')[0])
  const [selected, setSelected]     = useState([])         // array of article objects
  const [showIgnored, setShowIgnored] = useState(false)
  const [analyzing, setAnalyzing]   = useState(false)
  const [analyzeErr, setAnalyzeErr] = useState('')
  const [result, setResult]         = useState(null)

  function load() {
    setLoading(true); setError('')
    api.getNews()
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }
  useEffect(() => { load() }, [])

  // All articles sorted newest first
  const allArticles = useMemo(() => {
    if (!data) return []
    return SOURCES.flatMap(src => extractArticles(data[src.key], src.key))
      .sort((a, b) => {
        const da = parseDate(a.date)?.getTime() || 0
        const db = parseDate(b.date)?.getTime() || 0
        return db - da
      })
  }, [data])

  // Per-tab articles sorted newest first
  const tabArticles = useMemo(() => {
    if (!data) return []
    return extractArticles(data[activeTab], activeTab)
      .sort((a, b) => {
        const da = parseDate(a.date)?.getTime() || 0
        const db = parseDate(b.date)?.getTime() || 0
        return db - da
      })
  }, [data, activeTab])

  const visibleArticles = showIgnored
    ? tabArticles
    : tabArticles.filter(a => getWindow(analysisDate, a.date) !== 'ignore')

  const primaryCount   = tabArticles.filter(a => getWindow(analysisDate, a.date) === 'primary').length
  const secondaryCount = tabArticles.filter(a => getWindow(analysisDate, a.date) === 'secondary').length
  const ignoredCount   = tabArticles.filter(a => getWindow(analysisDate, a.date) === 'ignore').length

  function toggleArticle(article) {
    setSelected(prev => {
      const key = article.title + article.date
      const exists = prev.some(a => a.title + a.date === key)
      return exists ? prev.filter(a => a.title + a.date !== key) : [...prev, article]
    })
  }

  function isSelected(article) {
    const key = article.title + article.date
    return selected.some(a => a.title + a.date === key)
  }

  function selectAllPrimary() {
    const primaries = tabArticles.filter(a => getWindow(analysisDate, a.date) === 'primary')
    setSelected(prev => {
      const existingKeys = new Set(prev.map(a => a.title + a.date))
      const toAdd = primaries.filter(a => !existingKeys.has(a.title + a.date))
      return [...prev, ...toAdd]
    })
  }

  async function runCustomAnalysis() {
    if (selected.length === 0) return
    setAnalyzing(true); setAnalyzeErr('')
    try {
      const res = await api.runCustomAnalysis(selected, analysisDate)
      setResult(res)
    } catch (e) {
      setAnalyzeErr(e.message)
    } finally {
      setAnalyzing(false)
    }
  }

  return (
    <div className="p-6">
      {result && <CustomAnalysisPanel result={result} onClose={() => setResult(null)} />}

      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold text-white">News</h1>
          <p className="text-slate-400 text-sm mt-1">
            {allArticles.length} articles across all sources
          </p>
        </div>
        <button className="btn-ghost" onClick={load} disabled={loading}>
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Analysis date + selection controls */}
      <div className="card p-4 mb-4">
        <div className="flex flex-wrap items-center gap-4">
          <div>
            <label className="block text-xs text-slate-400 mb-1">Analysis Date</label>
            <input
              type="date"
              value={analysisDate}
              onChange={e => setDate(e.target.value)}
              className="bg-slate-900 border border-slate-600 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:border-emerald-500"
            />
          </div>
          <div className="flex items-center gap-3 text-xs text-slate-400">
            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-emerald-400" /> {primaryCount} Primary (last 2d)</span>
            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-slate-500" /> {secondaryCount} Secondary</span>
            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-slate-700" /> {ignoredCount} Too old</span>
          </div>

          <div className="ml-auto flex items-center gap-2">
            {selected.length > 0 && (
              <span className="text-xs text-emerald-400 font-medium">{selected.length} selected</span>
            )}
            <button className="btn-ghost text-xs" onClick={selectAllPrimary}>
              Select all primary
            </button>
            {selected.length > 0 && (
              <button className="btn-ghost text-xs text-red-400 hover:text-red-300" onClick={() => setSelected([])}>
                Clear
              </button>
            )}
          </div>
        </div>

        {/* Custom analysis button + info */}
        {selected.length > 0 && (
          <div className="mt-3 pt-3 border-t border-slate-700 flex items-center gap-3 flex-wrap">
            <button
              className="btn-primary text-sm"
              onClick={runCustomAnalysis}
              disabled={analyzing}
            >
              {analyzing
                ? <><Loader2 className="w-4 h-4 animate-spin" /> Analyzing…</>
                : <><Wand2 className="w-4 h-4" /> Run Custom Analysis</>
              }
            </button>
            <p className="text-xs text-slate-400">
              {selected.filter(a => getWindow(analysisDate, a.date) === 'primary').length} primary
              + {selected.filter(a => getWindow(analysisDate, a.date) !== 'primary').length} secondary
              articles will be sent to the AI
            </p>
            {analyzeErr && (
              <span className="text-xs text-red-400 flex items-center gap-1">
                <AlertCircle className="w-3.5 h-3.5" /> {analyzeErr}
              </span>
            )}
          </div>
        )}
      </div>

      {/* Date-window info banner */}
      <div className="flex items-start gap-2 bg-blue-900/20 border border-blue-700/30 rounded-lg px-3 py-2 mb-4 text-xs text-blue-300">
        <Info className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
        <span>
          <strong>PRIMARY</strong> = articles from within 2 days of your analysis date — AI weights these 3× heavier.
          <strong className="ml-1">SECONDARY</strong> = older context. <strong className="ml-1">OLD</strong> = excluded automatically.
        </span>
      </div>

      {/* Source tabs */}
      <div className="flex gap-1 border-b border-slate-800 mb-4">
        {SOURCES.map(src => {
          const count = data ? extractArticles(data[src.key], src.key).length : 0
          return (
            <button key={src.key} onClick={() => setActiveTab(src.key)}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-all -mb-px ${
                activeTab === src.key ? `${src.color} border-current` : 'text-slate-400 border-transparent hover:text-slate-200'
              }`}>
              <span className={`w-2 h-2 rounded-full ${src.dot}`} />
              {src.label}
              {data && <span className="ml-1 px-1.5 py-0.5 rounded bg-slate-700 text-slate-300 text-xs">{count}</span>}
            </button>
          )
        })}
      </div>

      {loading && (
        <div className="flex items-center justify-center py-16 gap-3 text-slate-400">
          <Loader2 className="w-5 h-5 animate-spin" /> Loading news…
        </div>
      )}
      {error && !loading && (
        <div className="flex items-center gap-2 bg-red-900/20 border border-red-700/40 text-red-400 rounded-xl px-4 py-3 text-sm">
          <AlertCircle className="w-4 h-4" /> {error} — run the pipeline first.
        </div>
      )}

      {!loading && !error && (
        <>
          <div className="space-y-2">
            {visibleArticles.map((a, i) => (
              <ArticleCard
                key={i} article={a} idx={i}
                analysisDate={analysisDate}
                selected={isSelected(a)}
                onToggle={toggleArticle}
                showWindow
              />
            ))}
          </div>

          {ignoredCount > 0 && (
            <button
              className="btn-ghost w-full mt-3 text-xs text-slate-500 justify-center"
              onClick={() => setShowIgnored(v => !v)}
            >
              {showIgnored ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
              {showIgnored ? 'Hide' : 'Show'} {ignoredCount} old articles
            </button>
          )}

          {visibleArticles.length === 0 && !loading && (
            <div className="text-center py-16">
              <Newspaper className="w-12 h-12 text-slate-600 mx-auto mb-3" />
              <p className="text-slate-400">No articles found.</p>
              <p className="text-slate-500 text-sm mt-1">Run the pipeline to fetch fresh news.</p>
            </div>
          )}
        </>
      )}
    </div>
  )
}
