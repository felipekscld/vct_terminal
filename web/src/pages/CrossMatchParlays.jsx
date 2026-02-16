import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'

function formatDate(d) {
  if (!d) return '–'
  try {
    const [y, m, day] = String(d).split('-')
    return `${day}/${m}` || d
  } catch {
    return d
  }
}

function CrossMatchParlaysPage() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [maxLegs, setMaxLegs] = useState(4)

  function load() {
    setLoading(true)
    setError('')
    const params = {}
    if (dateFrom) params.dateFrom = dateFrom
    if (dateTo) params.dateTo = dateTo
    params.maxLegs = maxLegs
    api.getCrossMatchParlays(params)
      .then(setData)
      .catch((err) => setError(err?.message || 'Erro ao carregar'))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
  }, [])

  return (
    <div className="space-y-4">
      <section className="panel p-4">
        <h2 className="page-title text-xl font-bold text-ink">Parlays entre jogos</h2>
        <p className="mt-1 text-sm text-slate-600">
          Uma perna por partida. O sistema sugere combinações com boa expectativa a partir das odds coletadas (agente/clawdbot) para partidas futuras.
        </p>
        <div className="mt-4 flex flex-wrap items-end gap-3">
          <div>
            <label className="block text-xs font-semibold uppercase text-slate-500">Data início</label>
            <input
              type="date"
              className="mt-1 rounded border border-slate-300 p-2 text-sm"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-xs font-semibold uppercase text-slate-500">Data fim</label>
            <input
              type="date"
              className="mt-1 rounded border border-slate-300 p-2 text-sm"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-xs font-semibold uppercase text-slate-500">Máx. pernas</label>
            <select
              className="mt-1 rounded border border-slate-300 p-2 text-sm"
              value={maxLegs}
              onChange={(e) => setMaxLegs(Number(e.target.value))}
            >
              <option value={2}>2</option>
              <option value={3}>3</option>
              <option value={4}>4</option>
              <option value={5}>5</option>
            </select>
          </div>
          <button
            type="button"
            onClick={load}
            className="rounded-lg bg-ocean px-4 py-2 text-sm font-semibold text-white hover:opacity-90"
          >
            Atualizar
          </button>
        </div>
      </section>

      {error && (
        <p className="text-sm text-red-600">{error}</p>
      )}

      {loading && (
        <p className="text-sm text-slate-500">Carregando partidas e odds…</p>
      )}

      {!loading && data && (
        <>
          <section className="panel p-4">
            <h3 className="font-display text-base font-semibold text-ink">Partidas no período (com odds)</h3>
            <p className="mt-1 text-xs text-slate-500">
              {data.date_from} a {data.date_to} · {data.upcoming_matches?.length ?? 0} partidas · {data.matches_with_edges ?? 0} com edges positivos
            </p>
            <ul className="mt-3 space-y-2">
              {(data.upcoming_matches || []).map((m) => (
                <li key={m.id} className="flex items-center justify-between rounded border border-slate-200 bg-white px-3 py-2 text-sm">
                  <span className="font-medium text-slate-800">
                    {m.team1_display} vs {m.team2_display}
                  </span>
                  <span className="text-slate-800">{formatDate(m.date)} {m.time || ''}</span>
                  <Link
                    to={`/match/${m.id}`}
                    className="rounded bg-slate-300 px-2 py-1 text-xs font-semibold text-slate-900 hover:bg-slate-400"
                  >
                    Análise
                  </Link>
                </li>
              ))}
            </ul>
            {(!data.upcoming_matches || data.upcoming_matches.length === 0) && (
              <p className="mt-2 text-sm text-slate-500">Nenhuma partida upcoming com odds no período. Colete odds (Análise da partida → Buscar odds) para os jogos que deseja incluir.</p>
            )}
          </section>

          <section className="panel p-4">
            <h3 className="font-display text-base font-semibold text-ink">Sugestões de parlay (uma perna por jogo)</h3>
            <div className="mt-3 grid gap-3">
              {(data.cross_match_parlays || []).map((p, idx) => (
                <article key={idx} className="rounded-lg border border-slate-200 bg-white p-4">
                  <p className="text-sm font-semibold text-slate-800">{p.description}</p>
                  <p className="mt-2 text-xs text-slate-600">
                    Odds combinadas: <strong>{p.combined_odds}</strong>
                    {' · '}
                    Edge: <strong>{(Number(p.edge || 0) * 100).toFixed(1)}%</strong>
                    {' · '}
                    P(modelo): {(Number(p.p_model || 0) * 100).toFixed(1)}%
                  </p>
                  {p.details?.legs && (
                    <ul className="mt-2 list-inside list-disc text-xs text-slate-600">
                      {p.details.legs.map((leg, i) => (
                        <li key={i}>{leg.match_label}: {leg.selection} @ {leg.odds}</li>
                      ))}
                    </ul>
                  )}
                </article>
              ))}
            </div>
            {(!data.cross_match_parlays || data.cross_match_parlays.length === 0) && (
              <p className="mt-2 text-sm text-slate-500">Nenhuma combinação com edge mínimo no momento. Adicione odds em mais partidas ou amplie o período.</p>
            )}
          </section>
        </>
      )}
    </div>
  )
}

export default CrossMatchParlaysPage
