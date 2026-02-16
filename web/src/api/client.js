const DEFAULT_HEADERS = {
  'Content-Type': 'application/json'
}

const REQUEST_TIMEOUT_MS = 30000

async function request(path, options = {}) {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)

  try {
    const response = await fetch(path, {
      ...options,
      signal: controller.signal,
      headers: {
        ...DEFAULT_HEADERS,
        ...(options.headers || {})
      }
    })
    clearTimeout(timeoutId)

    const isJson = response.headers.get('content-type')?.includes('application/json')
    const payload = isJson ? await response.json() : null

    if (!response.ok) {
      const message = payload?.detail || payload?.error || `Request failed (${response.status})`
      const error = new Error(typeof message === 'string' ? message : JSON.stringify(message))
      error.status = response.status
      error.payload = payload
      throw error
    }

    return payload
  } catch (err) {
    clearTimeout(timeoutId)
    if (err.name === 'AbortError') {
      throw new Error('A requisição passou do tempo limite (30s). Verifique se a API está rodando na porta 8000 e se o servidor não travou.')
    }
    throw err
  }
}

export const api = {
  getEvents: (params = {}) => {
    const search = new URLSearchParams()
    if (params.fromYear != null) search.set('from_year', String(params.fromYear))
    const query = search.toString()
    return request(`/api/events${query ? `?${query}` : ''}`)
  },
  getTeams: (region) => {
    const q = region && region !== 'all' ? `?region=${encodeURIComponent(region)}` : ''
    return request(`/api/teams${q}`)
  },
  getMaps: () => request('/api/maps'),
  getMarkets: () => request('/api/markets'),
  getMatches: (params = {}) => {
    const search = new URLSearchParams()
    if (Array.isArray(params.eventIds)) params.eventIds.forEach((id) => search.append('event_id', id))
    if (params.status) search.set('status', params.status)
    if (params.dateFrom) search.set('date_from', params.dateFrom)
    if (params.dateTo) search.set('date_to', params.dateTo)
    if (params.fromYear != null) search.set('from_year', String(params.fromYear))
    if (params.limit) search.set('limit', params.limit)
    const query = search.toString()
    return request(`/api/matches${query ? `?${query}` : ''}`)
  },
  getMatch: (matchId) => request(`/api/matches/${matchId}`),
  getMatchAnalysis: (matchId) => request(`/api/matches/${matchId}/analysis`),
  getCrossMatchParlays: (params = {}) => {
    const search = new URLSearchParams()
    if (params.dateFrom) search.set('date_from', params.dateFrom)
    if (params.dateTo) search.set('date_to', params.dateTo)
    if (params.maxLegs != null) search.set('max_legs', String(params.maxLegs))
    const query = search.toString()
    return request(`/api/analysis/cross-match-parlays${query ? `?${query}` : ''}`)
  },
  saveVeto: (matchId, body) => request(`/api/matches/${matchId}/veto`, { method: 'POST', body: JSON.stringify(body) }),
  saveOdds: (matchId, body) => request(`/api/matches/${matchId}/odds`, { method: 'POST', body: JSON.stringify(body) }),
  getOdds: (matchId, latestOnly = true) => request(`/api/matches/${matchId}/odds?latest_only=${latestOnly}`),
  autoOdds: (matchId, force = false) => request(`/api/matches/${matchId}/odds/auto`, { method: 'POST', body: JSON.stringify({ force }) }),
  getTeamStats: (teamId, mapName) => request(`/api/stats/team/${teamId}${mapName ? `?map_name=${encodeURIComponent(mapName)}` : ''}`),
  statsQuery: (q) => request(`/api/stats/query?q=${encodeURIComponent(q)}`),
  statsH2h: (a, b, mapName) => {
    const search = new URLSearchParams({ a, b })
    if (mapName) search.set('map_name', mapName)
    return request(`/api/stats/h2h?${search.toString()}`)
  },
  saveLiveMapResult: (matchId, body) => request(`/api/matches/${matchId}/live/map-result`, { method: 'POST', body: JSON.stringify(body) }),
  getLiveSeriesProb: (matchId) => request(`/api/matches/${matchId}/live/series-prob`),
  getConfig: () => request('/api/config'),
  updateConfig: (body) => request('/api/config', { method: 'PUT', body: JSON.stringify(body) }),
  sync: (body) => request('/api/sync', { method: 'POST', body: JSON.stringify(body || {}) }),
  hedge: (stake, odds, hedgeOdds, lockProfit = true) => request(`/api/hedge?stake=${stake}&odds=${odds}&hedge_odds=${hedgeOdds}&lock_profit=${lockProfit}`)
}
