const BASE = ''  // proxied via Vite to http://localhost:8000

export function getToken() {
  return localStorage.getItem('psx_token')
}

async function request(path, options = {}) {
  const token = getToken()
  const res = await fetch(BASE + path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    },
  })
  if (res.status === 401) {
    localStorage.removeItem('psx_token')
    window.location.href = '/'
    throw new Error('Unauthorized')
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Request failed')
  }
  return res.json()
}

export const api = {
  // ── Auth ──────────────────────────────────────────────────────
  login(username, password) {
    const body = new URLSearchParams({ username, password })
    return fetch(BASE + '/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body,
    }).then(async res => {
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || 'Login failed')
      }
      return res.json()
    })
  },

  // ── Data ──────────────────────────────────────────────────────
  getStatus()          { return request('/data/status') },
  getNews()            { return request('/data/news') },
  getPSX()             { return request('/data/psx') },
  refreshPSX()         { return request('/data/psx/refresh', { method: 'POST' }) },
  getReport()          { return request('/data/report') },
  getReportsHistory()  { return request('/data/reports/history') },
  getPosts()           { return request('/data/posts') },

  // ── Pipeline ──────────────────────────────────────────────────
  getPipelineStatus()  { return request('/pipeline/status') },

  /** Returns an EventSource — caller must close it. mode = 'full' | 'data' | 'analyze' */
  openPipelineSSE(mode = 'full') {
    const token = getToken()
    return new EventSource(
      `/pipeline/run?token=${encodeURIComponent(token)}&mode=${mode}`
    )
  },

  // ── Custom analysis ───────────────────────────────────────────
  runCustomAnalysis(articles, analysisDate, selectedSymbols = null) {
    return request('/analysis/custom', {
      method: 'POST',
      body: JSON.stringify({
        articles,
        analysis_date:    analysisDate,
        selected_symbols: selectedSymbols?.length ? selectedSymbols : null,
      }),
    })
  },

  // ── Live Market ───────────────────────────────────────────────
  /** Ticker strip: current prices for all watchlist stocks. */
  getLiveStocks()                   { return request('/stocks/live') },

  /** OHLCV + TA for a symbol. timeframe: 1D|1W|1M|3M|1Y */
  getHistorical(symbol, timeframe)  { return request(`/stocks/historical/${symbol}?timeframe=${timeframe}`) },

  /** GPT trader-mindset analysis for a stock. */
  analyzeStock(symbol)              {
    return request('/stocks/analyze', {
      method: 'POST',
      body: JSON.stringify({ symbol }),
    })
  },

  /** GPT trader-mindset analysis for multiple stocks in parallel. */
  analyzeStockBatch(symbols) {
    return request('/stocks/analyze/batch', {
      method: 'POST',
      body: JSON.stringify({ symbols }),
    })
  },

  /** Generate a social post via GPT. */
  generatePost(symbol, tone, platform) {
    return request('/posts/generate', {
      method: 'POST',
      body: JSON.stringify({ symbol, tone, platform }),
    })
  },

  // ── NCCPL Intelligence ────────────────────────────────────────
  getNccplInsiders()             { return request('/data/nccpl/insiders') },
  refreshNccplInsiders()         { return request('/data/nccpl/refresh', { method: 'POST' }) },
  getNccplShortSell(date = null) { return request(`/data/nccpl/short-sell${date ? `?date=${date}` : ''}`) },
  getNccplBlockTrades(date = null){ return request(`/data/nccpl/block-trades${date ? `?date=${date}` : ''}`) },
  getNccplFuturesOI(date = null) { return request(`/data/nccpl/futures-oi${date ? `?date=${date}` : ''}`) },
}
