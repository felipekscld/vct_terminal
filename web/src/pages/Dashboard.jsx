import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import MatchCard from '../components/MatchCard'

const MATCHES_LIMIT = 80

function DashboardPage() {
  const [matches, setMatches] = useState([])
  const [events, setEvents] = useState([])
  const [config, setConfig] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const [eventFilter, setEventFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [fromYear, setFromYear] = useState(2026)

  function loadData() {
    setLoading(true)
    setError('')
    const params = {
      ...(eventFilter ? { eventIds: [Number(eventFilter)] } : {}),
      status: statusFilter || undefined,
      dateFrom: dateFrom || undefined,
      dateTo: dateTo || undefined,
      fromYear,
      limit: MATCHES_LIMIT
    }
    Promise.all([
      api.getEvents({ fromYear }),
      api.getConfig(),
      api.getMatches(params)
    ])
      .then(([eventsRes, configRes, matchesRes]) => {
        const eventList = Array.isArray(eventsRes) ? eventsRes : (eventsRes?.items ?? [])
        const matchList = Array.isArray(matchesRes) ? matchesRes : (matchesRes?.items ?? [])
        setEvents(eventList)
        setConfig(configRes)
        setMatches(matchList)
      })
      .catch((err) => {
        setError(err?.message || 'Erro ao carregar')
        setEvents([])
        setMatches([])
      })
      .finally(() => {
        setLoading(false)
      })
  }

  useEffect(() => {
    loadData()
  }, [eventFilter, statusFilter, dateFrom, dateTo, fromYear])

  const overview = useMemo(() => {
    const live = matches.filter((m) => m.status === 'ongoing').length
    const upcoming = matches.filter((m) => m.status === 'upcoming').length
    const done = matches.filter((m) => m.status === 'completed').length
    return { live, upcoming, done }
  }, [matches])

  async function runSync() {
    setError('')
    try {
      await api.sync({ deep: false })
      await loadData()
    } catch (err) {
      setError(err.message)
    }
  }

  async function runSyncAll() {
    setError('')
    try {
      await api.sync({ deep: false, event_status: 'all' })
      await loadData()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div className="space-y-4">
      <section className="panel p-4">
        <div className="flex flex-wrap items-end gap-2">
          <div>
            <label className="text-xs font-semibold uppercase text-slate-500">Desde o ano</label>
            <select className="mt-1 block rounded border border-slate-300 p-2 text-sm" value={fromYear} onChange={(e) => setFromYear(Number(e.target.value))}>
              <option value={2026}>2026</option>
              <option value={2025}>2025</option>
              <option value={2024}>2024</option>
              <option value={2020}>2020 (todos)</option>
            </select>
          </div>
          <div>
            <label className="text-xs font-semibold uppercase text-slate-500">Evento</label>
            <select className="mt-1 block rounded border border-slate-300 p-2 text-sm" value={eventFilter} onChange={(e) => setEventFilter(e.target.value)}>
              <option value="">Todos os eventos</option>
              {events.map((event) => {
                const dates = [event.start_date, event.end_date].filter(Boolean)
                const dateLabel = dates.length ? ` (${dates.join(' – ')})` : ''
                const statusLabel = event.status ? ` [${event.status}]` : ''
                return (
                  <option key={event.id} value={event.id}>{event.name}{dateLabel}{statusLabel}</option>
                )
              })}
            </select>
          </div>

          <div>
            <label className="text-xs font-semibold uppercase text-slate-500">Status</label>
            <select className="mt-1 block rounded border border-slate-300 p-2 text-sm" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              <option value="">Todos</option>
              <option value="ongoing">Live</option>
              <option value="upcoming">Upcoming</option>
              <option value="completed">Completed</option>
            </select>
          </div>

          <div>
            <label className="text-xs font-semibold uppercase text-slate-500">Data início</label>
            <input className="mt-1 block rounded border border-slate-300 p-2 text-sm" type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          </div>

          <div>
            <label className="text-xs font-semibold uppercase text-slate-500">Data fim</label>
            <input className="mt-1 block rounded border border-slate-300 p-2 text-sm" type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </div>

          <button type="button" onClick={runSync} className="rounded-lg bg-ocean px-3 py-2 text-xs font-semibold text-white">Sincronizar eventos e partidas</button>
          <button type="button" onClick={runSyncAll} className="rounded-lg bg-slate-600 px-3 py-2 text-xs font-semibold text-white">Incluir eventos passados</button>
          <button type="button" onClick={loadData} className="rounded-lg bg-slate-900 px-3 py-2 text-xs font-semibold text-white">Atualizar lista</button>
        </div>
        <p className="mt-2 text-xs text-slate-500">A sincronização traz eventos em andamento e futuros (Kickoff, Masters, etc.) com datas do VLR.gg.</p>
      </section>

      <section className="grid gap-3 md:grid-cols-3">
        <article className="panel p-4">
          <p className="text-xs uppercase text-slate-500">Partidas Live</p>
          <p className="mt-1 text-2xl font-semibold">{overview.live}</p>
        </article>
        <article className="panel p-4">
          <p className="text-xs uppercase text-slate-500">Upcoming</p>
          <p className="mt-1 text-2xl font-semibold">{overview.upcoming}</p>
        </article>
        <article className="panel p-4">
          <p className="text-xs uppercase text-slate-500">Concluídas</p>
          <p className="mt-1 text-2xl font-semibold">{overview.done}</p>
        </article>
      </section>

      {error ? <p className="text-sm text-red-600">{error}</p> : null}

      {!loading && events.length === 0 ? (
        <section className="panel p-6 text-center">
          <p className="text-slate-300 font-medium">Nenhum evento aparecendo.</p>
          <p className="mt-2 text-sm text-slate-500">Se a API estiver rodando, clique em <strong>Atualizar lista</strong> para recarregar. Se o banco estiver vazio, use <strong>Sincronizar eventos e partidas</strong> (ou <strong>Incluir eventos passados</strong>) para buscar torneios do VLR.gg.</p>
          <button type="button" onClick={() => loadData()} className="mt-4 rounded-lg bg-ocean px-4 py-2 text-sm font-semibold text-white">Atualizar lista</button>
        </section>
      ) : null}

      <section className="grid gap-3 md:grid-cols-2">
        {loading ? (
          <p className="col-span-2 text-sm text-slate-500">Carregando partidas...</p>
        ) : matches.length === 0 ? (
          <p className="col-span-2 rounded-lg border border-slate-200 bg-slate-50 p-4 text-center text-sm text-slate-600">
            {events.length === 0
              ? 'Sincronize eventos e partidas para ver as partidas aqui.'
              : 'Nenhuma partida encontrada com os filtros atuais. Tente "Incluir eventos passados" ou mude evento/status/datas.'}
          </p>
        ) : (
          matches.map((match) => (
            <MatchCard key={match.id} match={match} />
          ))
        )}
      </section>
    </div>
  )
}

export default DashboardPage
