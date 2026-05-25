import { useState, useEffect } from 'react'
import {
  FileText, RefreshCw, TrendingUp, TrendingDown, Minus,
  Loader2, AlertCircle, Target, ShieldAlert, Star
} from 'lucide-react'
import { api } from '../api'

function sentimentBadge(bias) {
  const map = {
    BULLISH:  'badge-bull',
    BEARISH:  'badge-bear',
    NEUTRAL:  'badge-neutral',
    CAUTIOUS: 'badge-caution',
    MIXED:    'badge-caution',
  }
  return map[bias] || 'badge-neutral'
}

function confidenceDot(c) {
  return {
    HIGH:   'bg-emerald-400',
    MEDIUM: 'bg-amber-400',
    LOW:    'bg-red-400',
  }[c] || 'bg-slate-500'
}

function PickRow({ pick, action }) {
  const isBuy   = action === 'BUY'
  const isAvoid = action === 'AVOID'

  return (
    <tr className="border-b border-slate-800 hover:bg-slate-700/20 transition-colors align-top">
      <td className="px-3 py-3">
        <div className="flex items-center gap-2">
          <span className="font-mono font-bold text-white text-sm">{pick.symbol}</span>
          {pick.shariah_compliant && <span className="text-amber-400 text-xs" title="Shariah compliant">☪</span>}
          {pick.kmi_index && <span className="text-xs text-amber-500">{pick.kmi_index}</span>}
        </div>
        <p className="text-xs text-slate-500 mt-0.5">{pick.company_name || pick.sector}</p>
      </td>
      <td className="px-3 py-3 text-right">
        <p className="font-mono text-slate-200 text-sm">Rs {pick.current_price}</p>
      </td>
      {isBuy && (
        <>
          <td className="px-3 py-3 text-right">
            <p className="font-mono text-slate-300 text-sm">{pick.entry_range || '—'}</p>
          </td>
          <td className="px-3 py-3 text-right">
            <p className="font-mono text-emerald-400 text-sm font-semibold">{pick.target_price || '—'}</p>
          </td>
          <td className="px-3 py-3 text-right">
            <p className="font-mono text-red-400 text-sm">{pick.stop_loss || '—'}</p>
          </td>
        </>
      )}
      <td className="px-3 py-3">
        <div className="flex items-center gap-1.5">
          <span className={`w-2 h-2 rounded-full flex-shrink-0 ${confidenceDot(pick.confidence)}`} />
          <span className="text-xs text-slate-400">{pick.confidence}</span>
        </div>
      </td>
      <td className="px-3 py-3 max-w-xs">
        <p className="text-xs text-slate-400 leading-relaxed line-clamp-3">{pick.reasoning || pick.reason}</p>
        {pick.risk && (
          <p className="text-xs text-amber-600 mt-1">⚠ {pick.risk}</p>
        )}
      </td>
    </tr>
  )
}

function PortfolioSection({ title, portfolio, isKMI = false }) {
  if (!portfolio) return null
  const buys   = portfolio.buy_picks   || []
  const avoids = portfolio.avoid_picks || []
  const note   = portfolio.note || ''

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <h3 className="text-lg font-bold text-white">{title}</h3>
        {isKMI && <span className="badge-caution">☪ Shariah Only</span>}
        {note && <p className="text-xs text-slate-500">{note}</p>}
      </div>

      {/* BUY table */}
      {buys.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <TrendingUp className="w-4 h-4 text-emerald-400" />
            <h4 className="text-sm font-semibold text-emerald-400">BUY Picks ({buys.length})</h4>
          </div>
          <div className="card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-700 bg-slate-900/50">
                    <th className="px-3 py-2 text-left text-xs text-slate-400">Stock</th>
                    <th className="px-3 py-2 text-right text-xs text-slate-400">Price</th>
                    <th className="px-3 py-2 text-right text-xs text-slate-400">Entry</th>
                    <th className="px-3 py-2 text-right text-xs text-emerald-500">Target</th>
                    <th className="px-3 py-2 text-right text-xs text-red-500">Stop Loss</th>
                    <th className="px-3 py-2 text-left text-xs text-slate-400">Conf.</th>
                    <th className="px-3 py-2 text-left text-xs text-slate-400">Reasoning</th>
                  </tr>
                </thead>
                <tbody>
                  {buys.map((pick, i) => (
                    <PickRow key={i} pick={pick} action="BUY" />
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* AVOID table */}
      {avoids.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <ShieldAlert className="w-4 h-4 text-red-400" />
            <h4 className="text-sm font-semibold text-red-400">AVOID ({avoids.length})</h4>
          </div>
          <div className="card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-700 bg-slate-900/50">
                    <th className="px-3 py-2 text-left text-xs text-slate-400">Stock</th>
                    <th className="px-3 py-2 text-right text-xs text-slate-400">Price</th>
                    <th className="px-3 py-2 text-left text-xs text-slate-400">Conf.</th>
                    <th className="px-3 py-2 text-left text-xs text-slate-400">Reasoning</th>
                  </tr>
                </thead>
                <tbody>
                  {avoids.map((pick, i) => (
                    <PickRow key={i} pick={pick} action="AVOID" />
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default function ReportPage() {
  const [data, setData]       = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState('')
  const [tab, setTab]         = useState('conventional')

  function load() {
    setLoading(true)
    setError('')
    api.getReport()
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const report     = data?.trading_report || data
  const newsBrief  = data?.news_briefing
  const overview   = report?.market_overview || {}
  const conv       = report?.conventional_portfolio
  const shariah    = report?.shariah_portfolio
  const topStories = newsBrief?.top_stories || []
  const macro      = newsBrief?.macro_factors

  const biasIcon = {
    BULLISH: <TrendingUp className="w-4 h-4 text-emerald-400" />,
    BEARISH: <TrendingDown className="w-4 h-4 text-red-400" />,
    NEUTRAL: <Minus className="w-4 h-4 text-slate-400" />,
    CAUTIOUS: <AlertCircle className="w-4 h-4 text-amber-400" />,
  }[overview.session_bias || newsBrief?.overall_sentiment] || <Minus className="w-4 h-4 text-slate-400" />

  return (
    <div className="p-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white">Report</h1>
          <p className="text-slate-400 text-sm mt-1">Latest AI-generated trading recommendations</p>
        </div>
        <button className="btn-ghost" onClick={load} disabled={loading}>
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {loading && (
        <div className="flex items-center justify-center py-16 gap-3 text-slate-400">
          <Loader2 className="w-5 h-5 animate-spin" />
          Loading report…
        </div>
      )}
      {error && !loading && (
        <div className="flex items-center gap-2 bg-red-900/20 border border-red-700/40 text-red-400 rounded-xl px-4 py-3 text-sm mb-4">
          <AlertCircle className="w-4 h-4" />
          {error} — run the pipeline first to generate a report.
        </div>
      )}

      {!loading && report && (
        <div className="space-y-6">
          {/* Market overview */}
          <div className="card p-5">
            <div className="flex items-center gap-2 mb-4">
              {biasIcon}
              <h2 className="font-bold text-white">Market Overview</h2>
              <span className={sentimentBadge(overview.session_bias || newsBrief?.overall_sentiment)}>
                {overview.session_bias || newsBrief?.overall_sentiment || 'N/A'}
              </span>
              {report.report_date && (
                <span className="ml-auto text-xs text-slate-500">{report.report_date}</span>
              )}
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
              {[
                ['KSE-100', overview.kse100_level, overview.kse100_change_pct],
                ['KSE-100PR', overview.kse100pr_level, null],
                ['KMI-30', overview.kmi30_level, null],
                ['Breadth', overview.market_breadth?.split(',')[0], null],
              ].map(([lbl, val, chg]) => (
                <div key={lbl} className="bg-slate-900 rounded-lg px-3 py-2.5">
                  <p className="text-xs text-slate-500">{lbl}</p>
                  <p className="text-sm font-bold text-white mt-0.5">{val || '—'}</p>
                  {chg && <p className="text-xs text-emerald-400">{chg}</p>}
                </div>
              ))}
            </div>

            {overview.summary && (
              <p className="text-sm text-slate-300 leading-relaxed">{overview.summary}</p>
            )}
          </div>

          {/* News briefing summary */}
          {topStories.length > 0 && (
            <div className="card p-5">
              <h2 className="font-bold text-white mb-3 flex items-center gap-2">
                <Star className="w-4 h-4 text-amber-400" />
                Key News Drivers ({topStories.length})
              </h2>
              <div className="space-y-3">
                {topStories.slice(0, 5).map((s, i) => {
                  const impactColor = {POSITIVE:'text-emerald-400', NEGATIVE:'text-red-400', NEUTRAL:'text-slate-400'}[s.impact] || 'text-slate-400'
                  return (
                    <div key={i} className="border-l-2 border-slate-700 pl-3 py-1">
                      <div className="flex items-center gap-2">
                        <span className={`text-xs font-medium ${impactColor}`}>{s.impact}</span>
                        {s.impact_score && <span className="text-xs text-slate-500">score {s.impact_score}/10</span>}
                      </div>
                      <p className="text-sm text-white mt-0.5">{s.headline}</p>
                      {s.trader_action && (
                        <p className="text-xs text-amber-400 mt-1">→ {s.trader_action}</p>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Portfolio tabs */}
          {(conv || shariah) && (
            <div>
              <div className="flex gap-1 mb-4 border-b border-slate-800">
                <button
                  onClick={() => setTab('conventional')}
                  className={`px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-all ${
                    tab === 'conventional'
                      ? 'text-emerald-400 border-emerald-400'
                      : 'text-slate-400 border-transparent hover:text-slate-200'
                  }`}
                >
                  Conventional Portfolio
                  {conv?.buy_picks && (
                    <span className="ml-2 px-1.5 py-0.5 rounded bg-slate-700 text-xs text-slate-300">
                      {conv.buy_picks.length} BUY
                    </span>
                  )}
                </button>
                <button
                  onClick={() => setTab('shariah')}
                  className={`px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-all ${
                    tab === 'shariah'
                      ? 'text-amber-400 border-amber-400'
                      : 'text-slate-400 border-transparent hover:text-slate-200'
                  }`}
                >
                  ☪ Shariah Portfolio
                  {shariah?.buy_picks && (
                    <span className="ml-2 px-1.5 py-0.5 rounded bg-slate-700 text-xs text-slate-300">
                      {shariah.buy_picks.length} BUY
                    </span>
                  )}
                </button>
              </div>

              {tab === 'conventional' && (
                <PortfolioSection title="Conventional Portfolio" portfolio={conv} />
              )}
              {tab === 'shariah' && (
                <PortfolioSection title="Shariah Portfolio (KMI)" portfolio={shariah} isKMI />
              )}
            </div>
          )}

          {/* Macro note */}
          {macro && (
            <div className="card p-5">
              <h2 className="font-bold text-white mb-3">Macro Factors</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
                {[
                  ['PKR/USD',       macro.pkr_usd],
                  ['SBP Policy',    macro.sbp_policy_rate],
                  ['IMF Status',    macro.imf_status],
                  ['Inflation',     macro.inflation],
                  ['Oil Prices',    macro.oil_prices],
                ].filter(([, v]) => v).map(([lbl, val]) => (
                  <div key={lbl} className="bg-slate-900 rounded-lg px-3 py-2">
                    <p className="text-xs text-slate-500">{lbl}</p>
                    <p className="text-slate-300 mt-0.5">{val}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Disclaimer */}
          <p className="text-xs text-slate-600 text-center">
            {report.disclaimer || 'For educational purposes only. Not financial advice. Always do your own research.'}
          </p>
        </div>
      )}

      {!loading && !error && !report && (
        <div className="text-center py-16">
          <FileText className="w-12 h-12 text-slate-600 mx-auto mb-3" />
          <p className="text-slate-400">No report found.</p>
          <p className="text-slate-500 text-sm mt-1">Run the pipeline to generate a trading report.</p>
        </div>
      )}
    </div>
  )
}
