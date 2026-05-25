import { useState, useRef, useCallback, useEffect } from 'react'
import {
  Play, Database, Brain, CheckCircle2, XCircle, AlertTriangle,
  Clock, Loader2, SkipForward, ChevronDown, ChevronRight,
  RefreshCw, Activity, AlertCircle, Zap
} from 'lucide-react'
import { api } from '../api'

const STEP_LABELS = {
  full:    ['Fetch Data', 'News Agent', 'Trading Agent', 'Format Posts', 'Facebook', 'WhatsApp'],
  data:    ['Fetch All Data'],
  analyze: ['News Agent', 'Trading Agent', 'Format Posts'],
}

const STATUS_STYLE = {
  waiting: { icon: Clock,         cls: 'text-slate-500',  bg: 'bg-slate-800/60',        border: 'border-slate-700' },
  running: { icon: Loader2,       cls: 'text-blue-400',   bg: 'bg-blue-900/20',         border: 'border-blue-600/40' },
  done:    { icon: CheckCircle2,  cls: 'text-emerald-400', bg: 'bg-emerald-900/20',      border: 'border-emerald-600/40' },
  warn:    { icon: AlertTriangle, cls: 'text-amber-400',   bg: 'bg-amber-900/20',        border: 'border-amber-600/40' },
  skip:    { icon: SkipForward,   cls: 'text-slate-400',   bg: 'bg-slate-800/60',        border: 'border-slate-700' },
  error:   { icon: XCircle,       cls: 'text-red-400',     bg: 'bg-red-900/20',          border: 'border-red-600/40' },
}

function initSteps(mode) {
  return (STEP_LABELS[mode] || STEP_LABELS.full).map((label, i) => ({
    id: i + 1, label, status: 'waiting', message: '', logs: [], extra: null,
  }))
}

function FreshnessBar({ status }) {
  if (!status) return null
  const files = [
    { key: 'google_news',     label: 'Google News' },
    { key: 'dawn_business',   label: 'Dawn Business' },
    { key: 'profit_pakistan', label: 'Profit.pk' },
    { key: 'psx_data',        label: 'PSX Data' },
  ]
  return (
    <div className="card p-4 mb-5">
      <div className="flex items-center gap-2 mb-3 text-sm font-medium text-slate-300">
        <Activity className="w-4 h-4 text-slate-400" />
        Data Freshness
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        {files.map(({ key, label }) => {
          const s = status[key]
          if (!s) return null
          const stale = s.stale || !s.exists
          return (
            <div key={key} className={`rounded-lg px-3 py-2 border text-xs ${
              !s.exists       ? 'bg-red-900/20 border-red-700/40' :
              s.stale         ? 'bg-amber-900/20 border-amber-700/40' :
                                'bg-emerald-900/20 border-emerald-700/40'
            }`}>
              <p className="font-medium text-white">{label}</p>
              {!s.exists
                ? <p className="text-red-400 mt-0.5">No data — run pipeline</p>
                : <p className={stale ? 'text-amber-400' : 'text-emerald-400'}>
                    {s.age_hours}h ago {stale ? '⚠ stale' : '✓ fresh'}
                  </p>
              }
            </div>
          )
        })}
      </div>
    </div>
  )
}

function StepCard({ step, expanded, onToggle }) {
  const { icon: Icon, cls, bg, border } = STATUS_STYLE[step.status] || STATUS_STYLE.waiting
  return (
    <div className={`rounded-xl border transition-colors ${bg} ${border}`}>
      <button className="w-full flex items-center gap-3 px-4 py-3 text-left" onClick={onToggle}>
        <div className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center border ${border} ${bg}`}>
          <Icon className={`w-4 h-4 ${cls} ${step.status === 'running' ? 'animate-spin' : ''}`} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-500">Step {step.id}</span>
            <span className={`text-xs font-semibold uppercase tracking-wide ${cls}`}>{step.status}</span>
          </div>
          <p className="text-sm font-medium text-white truncate">{step.message || step.label}</p>
        </div>
        {(step.logs.length > 0 || step.extra) && (
          <span className="text-slate-500 flex-shrink-0">
            {expanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
          </span>
        )}
      </button>
      {expanded && (step.logs.length > 0 || step.extra) && (
        <div className="px-4 pb-3 pt-2 border-t border-slate-700/50 space-y-1.5">
          {step.logs.map((log, i) => (
            <p key={i} className="text-xs text-slate-400 font-mono">» {log}</p>
          ))}
          {step.extra && (
            <div className="flex flex-wrap gap-2 mt-1">
              {Object.entries(step.extra).filter(([,v]) => v != null).map(([k, v]) => (
                <span key={k} className="badge-neutral">{k}: {v}</span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function PipelinePage({ status, onStatusRefresh }) {
  const [mode, setMode]           = useState('full')
  const [steps, setSteps]         = useState(() => initSteps('full'))
  const [running, setRunning]     = useState(false)
  const [done, setDone]           = useState(false)
  const [pipelineErr, setPipeErr] = useState('')
  const [expanded, setExpanded]   = useState({})
  const esRef                     = useRef(null)

  useEffect(() => {
    if (!running) setSteps(initSteps(mode))
  }, [mode])

  const updateStep = useCallback((id, patch) => {
    setSteps(prev => prev.map(s => s.id === id ? { ...s, ...patch } : s))
  }, [])

  function reset() {
    esRef.current?.close()
    esRef.current = null
    setSteps(initSteps(mode))
    setRunning(false)
    setDone(false)
    setPipeErr('')
    setExpanded({})
  }

  function run() {
    reset()
    setRunning(true)
    const es = api.openPipelineSSE(mode)
    esRef.current = es

    es.onmessage = e => {
      let msg; try { msg = JSON.parse(e.data) } catch { return }

      if (msg.type === 'step_start') {
        updateStep(msg.step, { status: 'running', message: msg.label })
        setExpanded(p => ({ ...p, [msg.step]: true }))
      } else if (msg.type === 'step_done') {
        updateStep(msg.step, { status: 'done', message: msg.label, extra: msg.extra || null })
      } else if (msg.type === 'step_warn') {
        updateStep(msg.step, { status: 'warn', message: msg.label })
      } else if (msg.type === 'step_skip') {
        updateStep(msg.step, { status: 'skip', message: msg.label })
      } else if (msg.type === 'step_log') {
        setSteps(prev => prev.map(s =>
          s.id === msg.step ? { ...s, logs: [...s.logs, msg.message] } : s
        ))
      } else if (msg.type === 'done') {
        setDone(true); setRunning(false); es.close(); onStatusRefresh()
      } else if (msg.type === 'error') {
        setPipeErr(msg.message); setRunning(false); es.close(); onStatusRefresh()
      }
    }
    es.onerror = () => {
      setPipeErr('Connection lost — is the backend server running?')
      setRunning(false); es.close()
    }
  }

  const completed = steps.filter(s => ['done','skip','warn'].includes(s.status)).length
  const total     = steps.length

  const MODES = [
    { id: 'full',    label: 'Full Run',      icon: Zap,      desc: 'Fetch + Analyze + Format + Publish',  color: 'text-emerald-400' },
    { id: 'data',    label: 'Refresh Data',  icon: Database, desc: 'Fetch news & PSX only (no AI)',        color: 'text-blue-400' },
    { id: 'analyze', label: 'Re-Analyze',    icon: Brain,    desc: 'AI analysis on existing data (fast)', color: 'text-purple-400' },
  ]

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white">Pipeline</h1>
        <p className="text-slate-400 text-sm mt-1">Choose a run mode and trigger the analysis</p>
      </div>

      <FreshnessBar status={status} />

      {/* Mode selector */}
      <div className="grid grid-cols-3 gap-3 mb-5">
        {MODES.map(m => (
          <button
            key={m.id}
            onClick={() => !running && setMode(m.id)}
            disabled={running}
            className={`card p-3 text-left transition-all disabled:opacity-50 ${
              mode === m.id ? `border-2 border-current ${m.color}` : 'hover:border-slate-600'
            }`}
          >
            <div className="flex items-center gap-1.5 mb-1">
              <m.icon className={`w-4 h-4 ${mode === m.id ? m.color : 'text-slate-400'}`} />
              <span className={`text-sm font-semibold ${mode === m.id ? m.color : 'text-slate-200'}`}>
                {m.label}
              </span>
            </div>
            <p className="text-xs text-slate-500 leading-tight">{m.desc}</p>
          </button>
        ))}
      </div>

      {/* Action row */}
      <div className="flex items-center gap-3 mb-5">
        <button className="btn-primary" onClick={run} disabled={running}>
          {running
            ? <><Loader2 className="w-4 h-4 animate-spin" /> Running…</>
            : <><Play className="w-4 h-4" /> {MODES.find(m => m.id === mode)?.label}</>
          }
        </button>
        {(done || pipelineErr) && (
          <button className="btn-ghost" onClick={reset}>
            <RefreshCw className="w-4 h-4" /> Reset
          </button>
        )}
        {running && (
          <span className="text-sm text-slate-400">Step {completed + 1} / {total}</span>
        )}
      </div>

      {/* Progress bar */}
      {(running || done) && (
        <div className="mb-5">
          <div className="flex justify-between text-xs text-slate-400 mb-1.5">
            <span>{completed} of {total} steps</span>
            <span>{Math.round((completed / total) * 100)}%</span>
          </div>
          <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
            <div
              className="h-full bg-emerald-500 rounded-full transition-all duration-500"
              style={{ width: `${(completed / total) * 100}%` }}
            />
          </div>
        </div>
      )}

      {/* Error/success banners */}
      {pipelineErr && (
        <div className="flex items-start gap-2 bg-red-900/30 border border-red-700/50 text-red-400 rounded-lg px-4 py-3 mb-5 text-sm">
          <XCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
          <span><strong>Error:</strong> {pipelineErr}</span>
        </div>
      )}
      {done && !pipelineErr && (
        <div className="flex items-center gap-2 bg-emerald-900/30 border border-emerald-700/50 text-emerald-400 rounded-lg px-4 py-3 mb-5 text-sm">
          <CheckCircle2 className="w-4 h-4" />
          Done! Switch to News, PSX Table, Report, or Posts to see results.
        </div>
      )}

      {/* Steps */}
      <div className="space-y-2">
        {steps.map(step => (
          <StepCard
            key={step.id}
            step={step}
            expanded={!!expanded[step.id]}
            onToggle={() => setExpanded(p => ({ ...p, [step.id]: !p[step.id] }))}
          />
        ))}
      </div>

      {status?.latest_report && !running && (
        <p className="text-xs text-slate-500 text-center mt-5">
          Latest report on disk: {status.latest_report}
        </p>
      )}
    </div>
  )
}
