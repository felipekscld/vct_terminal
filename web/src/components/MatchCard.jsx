import { Link } from 'react-router-dom'
import { resolveBoType } from '../utils/formatBo'

function statusBadge(status) {
  if (status === 'ongoing') return <span className="badge badge-live">LIVE</span>
  if (status === 'upcoming') return <span className="badge badge-upcoming">UPCOMING</span>
  return <span className="badge badge-done">DONE</span>
}

function MatchCard({ match }) {
  const boLabel = resolveBoType(match.bo_type, match.score1, match.score2)
  return (
    <article className="panel p-4 transition hover:-translate-y-0.5">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="font-display text-lg font-semibold text-ink">{match.team1_tag || match.team1_name || '?'} vs {match.team2_tag || match.team2_name || '?'}</p>
          <p className="text-sm text-slate-600">
            {match.event_name || 'Evento'} · {match.stage_name || 'Stage'}
            {boLabel !== 'Bo?' && <span className="ml-1.5 inline-flex items-center rounded bg-slate-200 px-2 py-1 text-sm font-semibold tracking-wide text-slate-800">{boLabel}</span>}
            {boLabel === 'Bo?' && ` · ${boLabel}`}
          </p>
        </div>
        {statusBadge(match.status)}
      </div>

      <div className="mt-3 flex items-center justify-between text-sm text-slate-600">
        <span>{match.date || '--'} {match.time || ''}</span>
        <span>{match.score1 != null && match.score2 != null ? `${match.score1}-${match.score2}` : 'sem placar'}</span>
      </div>

      <div className="mt-4 flex gap-2">
        <Link
          className="rounded-lg bg-signal px-3 py-1.5 text-xs font-semibold text-white"
          to={`/match/${match.id}`}
        >
          Análise
        </Link>
        <Link
          className="rounded-lg bg-ocean px-3 py-1.5 text-xs font-semibold text-white"
          to={`/live/${match.id}`}
        >
          Live
        </Link>
      </div>
    </article>
  )
}

export default MatchCard
