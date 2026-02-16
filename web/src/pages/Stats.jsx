import { useEffect, useState } from 'react'
import { api } from '../api/client'
import StatsResult from '../components/StatsResult'

const REGION_OPTIONS = [
  { value: '', label: 'Todas' },
  { value: 'Americas', label: 'Americas' },
  { value: 'EMEA', label: 'EMEA' },
  { value: 'Pacific', label: 'Pacific' },
  { value: 'China', label: 'China' }
]

const EXEMPLOS_CONSULTA = [
  { label: 'OT de um time', query: 'OT MIBR' },
  { label: 'Round pistols de um time', query: 'pistols TL' },
  { label: 'Winrate / taxa de vitória', query: 'winrate FNC' },
  { label: 'Placares recentes', query: 'placar MIBR' },
  { label: 'Mapas apertados', query: 'close NRG' },
  { label: 'Lado ataque/defesa', query: 'rounds FNC Bind' },
  { label: 'Composições de um time', query: 'composições SEN' },
  { label: 'Head-to-head entre dois times', query: 'H2H MIBR NRG' },
  { label: 'Estatísticas gerais do time', query: 'estatísticas C9' }
]

function StatsPage() {
  const [query, setQuery] = useState('')
  const [teamId, setTeamId] = useState('')
  const [teamMap, setTeamMap] = useState('')
  const [h2hA, setH2hA] = useState('')
  const [h2hB, setH2hB] = useState('')
  const [h2hMap, setH2hMap] = useState('')
  const [regionFilter, setRegionFilter] = useState('')
  const [teams, setTeams] = useState([])
  const [maps, setMaps] = useState([])
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.getTeams(regionFilter || undefined)
      .then((res) => setTeams(res.items || []))
      .catch(() => setTeams([]))
  }, [regionFilter])

  useEffect(() => {
    api.getMaps()
      .then((res) => setMaps(res.items || []))
      .catch(() => {})
  }, [])

  function runNaturalQuery() {
    setError('')
    if (!query.trim()) {
      setError('Digite uma consulta ou escolha um exemplo abaixo.')
      return
    }
    setResult(null)
    api.statsQuery(query.trim())
      .then(setResult)
      .catch((err) => setError(err.message))
  }

  function loadTeamStats() {
    setError('')
    const id = Number(teamId)
    if (!id) {
      setError('Selecione um time.')
      return
    }
    setResult(null)
    api.getTeamStats(id, teamMap || undefined)
      .then(setResult)
      .catch((err) => setError(err.message))
  }

  function loadH2h() {
    setError('')
    const a = Number(h2hA)
    const b = Number(h2hB)
    if (!a || !b) {
      setError('Selecione os dois times.')
      return
    }
    if (a === b) {
      setError('Escolha times diferentes.')
      return
    }
    setResult(null)
    api.statsH2h(a, b, h2hMap || undefined)
      .then(setResult)
      .catch((err) => setError(err.message))
  }

  return (
    <div className="space-y-4">
      <section className="panel p-4">
        <h2 className="page-title text-xl font-bold text-ink">Consulta de estatísticas</h2>
        <p className="text-sm text-slate-600">
          Use uma consulta em linguagem natural (escolha um exemplo ou digite) ou busque por time e mapa.
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <label className="text-sm font-medium text-slate-700">Região</label>
          <select
            className="rounded border border-slate-300 p-2 text-sm"
            value={regionFilter}
            onChange={(e) => setRegionFilter(e.target.value)}
          >
            {REGION_OPTIONS.map((opt) => (
              <option key={opt.value || 'all'} value={opt.value}>{opt.label}</option>
            ))}
          </select>
          <span className="text-xs text-slate-500">(reduz a lista de times nos selects abaixo)</span>
        </div>
      </section>

      <section className="panel p-4">
        <h3 className="font-display text-base font-semibold text-ink">Siglas dos times (use na consulta)</h3>
        <p className="mt-1 text-xs text-slate-500">Use a sigla na caixa de consulta (ex: OT C9, winrate SEN). Lista filtrada pela região acima.</p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {teams.length === 0 ? (
            <span className="text-sm text-slate-500">Nenhum time (sincronize eventos ou mude a região).</span>
          ) : (
            teams.map((t) => {
              const sigla = t.tag || t.name || `Time ${t.id}`
              const label = t.tag && t.name && t.tag !== t.name ? `${t.tag} (${t.name})` : sigla
              return (
                <span key={t.id} className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-700" title={t.name}>{label}</span>
              )
            })
          )}
        </div>
      </section>

      <section className="grid gap-4 lg:grid-cols-3">
        <article className="panel p-4">
          <h3 className="font-display text-base font-semibold text-ink">Consulta em linguagem natural</h3>
          <p className="mt-1 text-xs text-slate-500">Digite ou clique em um exemplo para preencher.</p>
          <textarea
            className="mt-2 h-20 w-full rounded border border-slate-300 p-2 text-sm"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Ex: OT MIBR, winrate C9, H2H SEN NRG"
          />
          <div className="mt-2 flex flex-wrap gap-1.5">
            {EXEMPLOS_CONSULTA.map((ex) => (
              <button
                key={ex.query}
                type="button"
                onClick={() => setQuery(ex.query)}
                className="rounded bg-slate-100 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-200"
                title={ex.label}
              >
                {ex.label}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={runNaturalQuery}
            className="mt-3 rounded bg-signal px-3 py-1.5 text-xs font-semibold text-white hover:opacity-90"
          >
            Rodar consulta
          </button>
        </article>

        <article className="panel p-4">
          <h3 className="font-display text-base font-semibold text-ink">Estatísticas por time</h3>
          <p className="mt-1 text-xs text-slate-500">Selecione o time e, se quiser, o mapa.</p>
          <div className="mt-3 space-y-2">
            <label className="block text-sm font-medium text-slate-700">Time</label>
            <select
              className="w-full rounded border border-slate-300 p-2 text-sm"
              value={teamId}
              onChange={(e) => setTeamId(e.target.value)}
            >
              <option value="">Selecione um time</option>
              {teams.map((t) => (
                <option key={t.id} value={t.id}>{t.tag || t.name || `Time ${t.id}`}</option>
              ))}
            </select>
            <label className="block text-sm font-medium text-slate-700">Mapa (opcional)</label>
            <select
              className="w-full rounded border border-slate-300 p-2 text-sm"
              value={teamMap}
              onChange={(e) => setTeamMap(e.target.value)}
            >
              <option value="">Todos os mapas</option>
              {maps.map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
            <button
              type="button"
              onClick={loadTeamStats}
              className="mt-2 rounded bg-ocean px-3 py-1.5 text-xs font-semibold text-white hover:opacity-90"
            >
              Buscar estatísticas do time
            </button>
          </div>
        </article>

        <article className="panel p-4">
          <h3 className="font-display text-base font-semibold text-ink">Head-to-head (H2H)</h3>
          <p className="mt-1 text-xs text-slate-500">Selecione os dois times para ver o histórico entre eles.</p>
          <div className="mt-3 space-y-2">
            <label className="block text-sm font-medium text-slate-700">Time A</label>
            <select
              className="w-full rounded border border-slate-300 p-2 text-sm"
              value={h2hA}
              onChange={(e) => setH2hA(e.target.value)}
            >
              <option value="">Selecione</option>
              {teams.map((t) => (
                <option key={t.id} value={t.id}>{t.tag || t.name || `Time ${t.id}`}</option>
              ))}
            </select>
            <label className="block text-sm font-medium text-slate-700">Time B</label>
            <select
              className="w-full rounded border border-slate-300 p-2 text-sm"
              value={h2hB}
              onChange={(e) => setH2hB(e.target.value)}
            >
              <option value="">Selecione</option>
              {teams.map((t) => (
                <option key={t.id} value={t.id}>{t.tag || t.name || `Time ${t.id}`}</option>
              ))}
            </select>
            <label className="block text-sm font-medium text-slate-700">Mapa (opcional)</label>
            <select
              className="w-full rounded border border-slate-300 p-2 text-sm"
              value={h2hMap}
              onChange={(e) => setH2hMap(e.target.value)}
            >
              <option value="">Todos</option>
              {maps.map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
            <button
              type="button"
              onClick={loadH2h}
              className="mt-2 rounded bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white hover:opacity-90"
            >
              Buscar H2H
            </button>
          </div>
        </article>
      </section>

      {error ? <p className="text-sm text-red-600">{error}</p> : null}
      <StatsResult data={result} />
    </div>
  )
}

export default StatsPage
