import { useState, useEffect } from 'react'
import {
  TrendingUp, Play, Newspaper, BarChart2, FileText, Send,
  LogOut, Menu, X, ChevronRight, Activity, AlertCircle, CandlestickChart,
  Eye
} from 'lucide-react'
import { api } from '../api'
import PipelinePage    from '../pages/PipelinePage'
import NewsPage        from '../pages/NewsPage'
import PSXPage         from '../pages/PSXPage'
import ReportPage      from '../pages/ReportPage'
import PostsPage       from '../pages/PostsPage'
import LiveMarketPage  from '../pages/LiveMarketPage'
import NCCPLPage       from '../pages/NCCPLPage'

const NAV = [
  { id: 'live',     label: 'Live Market',   icon: CandlestickChart, desc: 'Charts, AI signals, news' },
  { id: 'pipeline', label: 'Run Pipeline',  icon: Play,             desc: 'Trigger full analysis' },
  { id: 'news',     label: 'News',          icon: Newspaper,        desc: 'Articles from all sources' },
  { id: 'psx',      label: 'PSX Table',     icon: BarChart2,        desc: 'Live stock data' },
  { id: 'nccpl',    label: 'NCCPL Intel',   icon: Eye,              desc: 'Insiders, blocks, futures' },
  { id: 'report',   label: 'Report',        icon: FileText,         desc: 'Trading recommendations' },
  { id: 'posts',    label: 'Posts',         icon: Send,             desc: 'Content for all channels' },
]

export default function Dashboard({ onLogout }) {
  const [page, setPage]         = useState('live')
  const [sidebarOpen, setSidebar] = useState(true)
  const [status, setStatus]     = useState(null)

  useEffect(() => {
    api.getStatus().then(setStatus).catch(() => {})
    const iv = setInterval(() => api.getStatus().then(setStatus).catch(() => {}), 15000)
    return () => clearInterval(iv)
  }, [])

  const Page = {
    live:     LiveMarketPage,
    pipeline: PipelinePage,
    news:     NewsPage,
    psx:      PSXPage,
    nccpl:    NCCPLPage,
    report:   ReportPage,
    posts:    PostsPage,
  }[page]

  return (
    <div className="flex h-screen overflow-hidden">
      {/* ── Sidebar ──────────────────────────────────────────── */}
      <aside className={`
        flex flex-col bg-slate-950 border-r border-slate-800 transition-all duration-200 flex-shrink-0
        ${sidebarOpen ? 'w-60' : 'w-16'}
      `}>
        {/* Logo */}
        <div className="flex items-center gap-3 px-4 h-16 border-b border-slate-800">
          <div className="flex-shrink-0 w-8 h-8 bg-emerald-600/20 border border-emerald-600/40 rounded-lg flex items-center justify-center">
            <TrendingUp className="w-4 h-4 text-emerald-400" />
          </div>
          {sidebarOpen && (
            <div className="min-w-0">
              <div className="font-bold text-white text-sm leading-tight">PSX Automation</div>
              <div className="text-slate-500 text-xs">Dashboard</div>
            </div>
          )}
          <button
            className="ml-auto text-slate-400 hover:text-white transition-colors flex-shrink-0"
            onClick={() => setSidebar(v => !v)}
          >
            {sidebarOpen ? <X className="w-4 h-4" /> : <Menu className="w-4 h-4" />}
          </button>
        </div>

        {/* Nav */}
        <nav className="flex-1 py-4 px-2 space-y-0.5 overflow-y-auto">
          {NAV.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setPage(id)}
              className={`
                w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all
                ${page === id
                  ? 'bg-emerald-600/20 text-emerald-400 border border-emerald-700/40'
                  : 'text-slate-400 hover:text-slate-100 hover:bg-slate-800'}
              `}
              title={!sidebarOpen ? label : undefined}
            >
              <Icon className="w-4 h-4 flex-shrink-0" />
              {sidebarOpen && <span className="truncate">{label}</span>}
              {sidebarOpen && page === id && <ChevronRight className="ml-auto w-3 h-3" />}
            </button>
          ))}
        </nav>

        {/* Status indicator */}
        {sidebarOpen && status && (
          <div className="px-3 py-2 mx-2 mb-2 rounded-lg bg-slate-900 border border-slate-800 text-xs space-y-1">
            <div className="flex items-center gap-1.5 text-slate-400 font-medium">
              <Activity className="w-3 h-3" />
              Data Status
            </div>
            {[
              ['Google News', status.google_news],
              ['Dawn Business', status.dawn_business],
              ['Profit.pk', status.profit_pakistan],
              ['PSX Data', status.psx_data],
            ].map(([label, s]) => (
              <div key={label} className="flex items-center justify-between gap-1">
                <span className="text-slate-500 truncate">{label}</span>
                <span className={s?.exists ? 'text-emerald-400' : 'text-red-400'}>
                  {s?.exists ? '●' : '○'}
                </span>
              </div>
            ))}
            {status.pipeline_running && (
              <div className="flex items-center gap-1 text-amber-400 mt-1 pt-1 border-t border-slate-700">
                <AlertCircle className="w-3 h-3 animate-pulse" />
                Pipeline running…
              </div>
            )}
          </div>
        )}

        {/* Logout */}
        <div className="p-2 border-t border-slate-800">
          <button
            onClick={onLogout}
            className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-slate-400 hover:text-red-400 hover:bg-red-900/10 text-sm transition-colors"
            title={!sidebarOpen ? 'Logout' : undefined}
          >
            <LogOut className="w-4 h-4 flex-shrink-0" />
            {sidebarOpen && 'Logout'}
          </button>
        </div>
      </aside>

      {/* ── Main content ─────────────────────────────────────── */}
      <main className="flex-1 overflow-auto">
        <Page status={status} onStatusRefresh={() => api.getStatus().then(setStatus).catch(() => {})} />
      </main>
    </div>
  )
}
