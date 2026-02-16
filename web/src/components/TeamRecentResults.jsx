import { useState } from 'react'
import { Link } from 'react-router-dom'

function TeamRecentResults({ teamLabel, matches }) {
  const [open, setOpen] = useState(false)
  const list = matches ?? []

  return (
    <div className="rounded-xl border border-slate-100 bg-white shadow-sm">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between px-3 py-2.5 text-left text-sm font-medium text-slate-700 hover:bg-slate-50 rounded-xl transition-colors"
      >
        <span>{teamLabel} – últimos jogos</span>
        <span className="text-slate-400">{open ? '▼' : '▶'} {list.length} partidas</span>
      </button>
      {open && (
        <div className="border-t border-slate-100 px-3 py-2">
          {list.length === 0 ? (
            <p className="text-xs text-slate-500">Nenhuma partida concluída no período do filtro.</p>
          ) : (
            <ul className="space-y-1.5 text-sm">
              {list.map((m) => (
                <li key={m.match_id}>
                  <Link
                    to={`/match/${m.match_id}`}
                    className="flex items-center justify-between gap-2 text-slate-600 hover:bg-slate-50 hover:text-slate-800 rounded-lg px-2 py-1 -mx-1 transition-colors"
                  >
                    <span className="truncate">{m.date || '—'} · vs {m.opponent_tag || m.opponent_name}</span>
                    <span className="shrink-0 font-medium">
                      {m.team_score}-{m.opponent_score}
                      {m.won ? <span className="ml-1 text-emerald-600">W</span> : <span className="ml-1 text-red-600">L</span>}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
          {list.length > 0 && (
            <p className="mt-2 text-xs text-slate-500">Mesmo filtro de eventos/datas da análise.</p>
          )}
        </div>
      )}
    </div>
  )
}

export default function ResultadosAnteriores({ analysis }) {
  const teamA = analysis?.teams?.team_a
  const teamB = analysis?.teams?.team_b
  const recentA = analysis?.recent_matches_team_a ?? []
  const recentB = analysis?.recent_matches_team_b ?? []
  const labelA = teamA?.tag || teamA?.name || 'Time A'
  const labelB = teamB?.tag || teamB?.name || 'Time B'
  const dateFrom = analysis?.data_period?.date_from

  return (
    <section className="panel p-4">
      <h3 className="font-display text-base font-semibold text-ink">Resultados anteriores</h3>
      <p className="mt-0.5 text-xs text-slate-500">
        {dateFrom ? (
          <>Apenas partidas do ano atual (a partir de <strong>{dateFrom}</strong>).</>
        ) : (
          'Últimas partidas de cada time.'
        )}
      </p>
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <TeamRecentResults teamLabel={labelA} matches={recentA} />
        <TeamRecentResults teamLabel={labelB} matches={recentB} />
      </div>
    </section>
  )
}
