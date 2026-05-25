import { useState } from 'react'
import { Copy, CheckCheck } from 'lucide-react'

export default function PostsViewer({ singlePost }) {
  const [copied, setCopied] = useState(false)
  if (!singlePost) return (
    <div className="text-center py-8 text-slate-500 text-sm">No content available.</div>
  )

  function copy() {
    navigator.clipboard.writeText(singlePost.content).then(() => {
      setCopied(true); setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-2 px-1">
        <span className="text-xs text-slate-500 font-mono truncate">{singlePost.filename}</span>
        <button onClick={copy} className={`btn-ghost text-xs flex-shrink-0 ${copied?'text-emerald-400':''}`}>
          {copied ? <CheckCheck className="w-3.5 h-3.5"/> : <Copy className="w-3.5 h-3.5"/>}
          {copied ? 'Copied!' : 'Copy'}
        </button>
      </div>
      <div className="card p-4 max-h-96 overflow-y-auto">
        <pre className="text-sm text-slate-200 whitespace-pre-wrap font-sans leading-relaxed break-words">
          {singlePost.content}
        </pre>
      </div>
      <p className="text-xs text-slate-500 mt-1.5 text-right">
        {singlePost.content.length.toLocaleString()} chars
      </p>
    </div>
  )
}
