import { useState, useEffect } from 'react'
import { Send, RefreshCw, Loader2, AlertCircle, Facebook, FileText, Users, Crown } from 'lucide-react'
import { api } from '../api'
import PostsViewer from '../components/PostsViewer'

const CHANNELS = [
  {
    key:   'facebook',
    label: 'Facebook',
    icon:  Facebook,
    color: 'text-blue-400',
    border: 'border-blue-600/40',
    bg:    'bg-blue-900/10',
    dot:   'bg-blue-400',
    tier:  'Tier 1',
    desc:  'Public teaser — market mood, sector hints, no stock names. CTA to free WhatsApp.',
  },
  {
    key:   'free_whatsapp',
    label: 'Free WhatsApp',
    icon:  Users,
    color: 'text-emerald-400',
    border: 'border-emerald-600/40',
    bg:    'bg-emerald-900/10',
    dot:   'bg-emerald-400',
    tier:  'Tier 2',
    desc:  'Top 3 picks with entry zones only — no targets or stop-losses. CTA to paid channel.',
  },
  {
    key:   'paid_whatsapp',
    label: 'Paid WhatsApp',
    icon:  Crown,
    color: 'text-amber-400',
    border: 'border-amber-600/40',
    bg:    'bg-amber-900/10',
    dot:   'bg-amber-400',
    tier:  'Tier 3',
    desc:  'Full report — all 10+10 picks, entry, targets, stop-losses, Shariah portfolio.',
  },
  {
    key:   'comprehensive',
    label: 'Comprehensive',
    icon:  FileText,
    color: 'text-purple-400',
    border: 'border-purple-600/40',
    bg:    'bg-purple-900/10',
    dot:   'bg-purple-400',
    tier:  'Tier 4',
    desc:  'Deep-dive document — macro context, story-by-story analysis, both portfolios, risks.',
  },
]

export default function PostsPage() {
  const [data, setData]       = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState('')
  const [tab, setTab]         = useState('facebook')

  function load() {
    setLoading(true); setError('')
    api.getPosts()
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }
  useEffect(() => { load() }, [])

  const activeChannel = CHANNELS.find(c => c.key === tab)
  const hasAny = data && Object.values(data).some(Boolean)

  return (
    <div className="p-6 max-w-3xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-2xl font-bold text-white">Posts</h1>
          <p className="text-slate-400 text-sm mt-1">4-tier content funnel for all distribution channels</p>
        </div>
        <button className="btn-ghost" onClick={load} disabled={loading}>
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Channel overview cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-5">
        {CHANNELS.map(ch => {
          const has = !!data?.[ch.key]
          return (
            <button key={ch.key} onClick={() => setTab(ch.key)}
              className={`card p-3 text-left transition-all ${
                tab === ch.key ? `border-2 ${ch.border} ${ch.bg}` : 'hover:border-slate-600'
              }`}>
              <div className="flex items-center gap-1.5 mb-1">
                <span className={`w-2 h-2 rounded-full ${ch.dot} ${has ? '' : 'opacity-25'}`} />
                <span className={`text-xs font-bold ${tab===ch.key ? ch.color : 'text-slate-400'}`}>{ch.tier}</span>
              </div>
              <p className={`text-sm font-semibold ${tab===ch.key ? ch.color : 'text-slate-200'}`}>{ch.label}</p>
              <p className="text-xs text-slate-500 mt-0.5 leading-tight line-clamp-2">{ch.desc}</p>
            </button>
          )
        })}
      </div>

      {/* Tabs (mobile-friendly strip) */}
      <div className="flex gap-0.5 border-b border-slate-800 mb-5 overflow-x-auto">
        {CHANNELS.map(ch => (
          <button key={ch.key} onClick={() => setTab(ch.key)}
            className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px whitespace-nowrap transition-all ${
              tab === ch.key ? `${ch.color} border-current` : 'text-slate-400 border-transparent hover:text-slate-200'
            }`}>
            <ch.icon className="w-3.5 h-3.5" />
            {ch.label}
            {data?.[ch.key] && <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 ml-0.5" />}
          </button>
        ))}
      </div>

      {/* Active channel description */}
      {activeChannel && (
        <p className="text-xs text-slate-500 mb-4 flex items-center gap-1.5">
          <activeChannel.icon className={`w-3.5 h-3.5 ${activeChannel.color}`} />
          <span className={`font-medium ${activeChannel.color}`}>{activeChannel.tier}:</span>
          {activeChannel.desc}
        </p>
      )}

      {/* Content */}
      {loading && (
        <div className="flex items-center justify-center py-16 gap-3 text-slate-400">
          <Loader2 className="w-5 h-5 animate-spin" /> Loading posts…
        </div>
      )}

      {error && !loading && (
        <div className="flex items-center gap-2 bg-red-900/20 border border-red-700/40 text-red-400 rounded-xl px-4 py-3 text-sm">
          <AlertCircle className="w-4 h-4" />
          {error} — run the pipeline first to generate posts.
        </div>
      )}

      {!loading && !error && hasAny && (
        <PostsViewer singlePost={data?.[tab]} />
      )}

      {!loading && !error && !hasAny && (
        <div className="text-center py-16">
          <Send className="w-12 h-12 text-slate-600 mx-auto mb-3" />
          <p className="text-slate-400">No posts generated yet.</p>
          <p className="text-slate-500 text-sm mt-1">Run the pipeline to create content for all 4 channels.</p>
        </div>
      )}
    </div>
  )
}
