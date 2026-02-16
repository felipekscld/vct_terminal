import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../api/client'
import { formatBoType } from '../utils/formatBo'
import VetoInput from '../components/VetoInput'
import OddsForm from '../components/OddsForm'
import AnalysisPanel from '../components/AnalysisPanel'
import MultiBetPanel from '../components/MultiBetPanel'
import SeriesProbs from '../components/SeriesProbs'
import HedgeCalculator from '../components/HedgeCalculator'
import ResultadosAnteriores from '../components/TeamRecentResults'
import ComparisonPanel from '../components/ComparisonPanel'

function MatchAnalysisPage() {
  const { id } = useParams()
  const matchId = Number(id)

  const [match, setMatch] = useState(null)
  const [analysis, setAnalysis] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  async function loadAll() {
    setLoading(true)
    setError('')
    try {
      const [matchRes, analysisRes] = await Promise.all([
        api.getMatch(matchId),
        api.getMatchAnalysis(matchId)
      ])
      setMatch(matchRes)
      setAnalysis(analysisRes)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadAll()
  }, [matchId])

  if (loading) return <p className="text-sm text-slate-600">Carregando análise...</p>
  if (error) return <p className="text-sm text-red-600">{error}</p>

  return (
    <div className="space-y-4">
      <section className="panel p-4">
        <h2 className="page-title text-xl font-bold text-ink">
          {analysis?.teams?.team_a?.tag || analysis?.teams?.team_a?.name} vs {analysis?.teams?.team_b?.tag || analysis?.teams?.team_b?.name}
        </h2>
        <p className="text-sm text-slate-600">
          {analysis?.match?.event_name || 'Evento'} · {analysis?.match?.stage_name || 'Stage'} · {formatBoType(analysis?.match?.bo_type ?? analysis?.bo_type)}
        </p>
        {(match?.match?.score1 != null && match?.match?.score2 != null) && (
          <p className="mt-2 text-lg font-bold text-slate-100">
            Placar da série: {match.match.score1}–{match.match.score2}
          </p>
        )}
      </section>

      {match?.map_results?.length > 0 && (
        <section className="panel p-4">
          <h3 className="font-display text-base font-semibold text-ink">Mapas jogados</h3>
          <div className="mt-3 overflow-x-auto">
            <table className="min-w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-slate-300">
                  <th className="py-2 pr-3 text-left text-sm font-semibold text-slate-700">Mapa</th>
                  <th className="py-2 px-2 text-right text-sm font-semibold text-slate-700">{analysis?.teams?.team_a?.tag || 'Time A'}</th>
                  <th className="py-2 px-2 text-center text-sm font-semibold text-slate-500">×</th>
                  <th className="py-2 pl-2 text-left text-sm font-semibold text-slate-700">{analysis?.teams?.team_b?.tag || 'Time B'}</th>
                  <th className="py-2 pl-3 text-left text-sm font-semibold text-slate-700">Vencedor</th>
                </tr>
              </thead>
              <tbody>
                {match.map_results.map((row) => {
                  const teamAId = analysis?.teams?.team_a?.id
                  const teamBId = analysis?.teams?.team_b?.id
                  const winnerId = row.winner_team_id
                  const teamAWon = winnerId === teamAId
                  const teamBWon = winnerId === teamBId
                  const winnerTag = teamAWon
                    ? (analysis?.teams?.team_a?.tag || analysis?.teams?.team_a?.name)
                    : teamBWon
                      ? (analysis?.teams?.team_b?.tag || analysis?.teams?.team_b?.name)
                      : '—'
                  return (
                    <tr key={row.map_order} className="border-b border-slate-200 last:border-0 hover:bg-slate-50/50">
                      <td className="py-2 pr-3 font-semibold text-slate-100">{row.map_name}</td>
                      <td className={`py-2 px-2 text-right tabular-nums font-semibold ${teamAWon ? 'text-emerald-600' : teamBWon ? 'text-red-600' : 'text-slate-800'}`}>{row.team1_score ?? '—'}</td>
                      <td className="py-2 px-2 text-center font-semibold text-slate-400">×</td>
                      <td className={`py-2 pl-2 text-left tabular-nums font-semibold ${teamBWon ? 'text-emerald-600' : teamAWon ? 'text-red-600' : 'text-slate-800'}`}>{row.team2_score ?? '—'}</td>
                      <td className={`py-2 pl-3 font-semibold ${teamAWon || teamBWon ? 'text-emerald-600' : 'text-slate-700'}`}>{winnerTag}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <VetoInput matchId={matchId} onSaved={loadAll} />

      <OddsForm
        matchId={matchId}
        teams={analysis?.teams}
        maps={analysis?.maps}
        onSaved={loadAll}
      />

      <ResultadosAnteriores analysis={analysis} />

      <ComparisonPanel analysis={analysis} />

      <section className="grid gap-4 lg:grid-cols-2">
        <AnalysisPanel analysis={analysis} />
        <MultiBetPanel items={analysis?.multi_bets} />
      </section>

      <SeriesProbs scoreProbs={analysis?.series?.score_probs} boType={analysis?.bo_type ?? analysis?.match?.bo_type} />
      <HedgeCalculator />

      <section className="panel p-4">
        <h3 className="font-display text-base font-semibold">Arbitragem</h3>
        {analysis?.odds_count === 0 ? (
          <p className="mt-3 text-sm text-slate-500">
            Nenhuma odd cadastrada para este jogo. Cadastre odds (vencedor da série, mapas, etc.) na seção de odds para que o sistema possa detectar possíveis arbitragens entre bookmakers.
          </p>
        ) : (analysis?.arbitrage?.length ?? 0) === 0 ? (
          <p className="mt-3 text-sm text-slate-500">
            Nenhuma oportunidade de arbitragem encontrada para as odds atuais (surebets ou anomalias entre bookmakers).
          </p>
        ) : null}
        <pre className="mt-3 overflow-auto rounded-lg bg-slate-950 p-3 text-xs text-slate-100">
          {JSON.stringify(analysis?.arbitrage || [], null, 2)}
        </pre>
      </section>

      <section className="panel p-4">
        <h3 className="font-display text-base font-semibold">Veto salvo</h3>
        {match?.veto_markdown ? (
          <pre className="mt-3 overflow-auto rounded-lg bg-slate-950 p-3 text-xs text-slate-100 whitespace-pre-wrap font-mono">
            {match.veto_markdown}
          </pre>
        ) : (match?.veto?.length ?? 0) > 0 ? (
          <pre className="mt-3 overflow-auto rounded-lg bg-slate-950 p-3 text-xs text-slate-100">
            {JSON.stringify(match.veto, null, 2)}
          </pre>
        ) : (
          <p className="mt-3 text-sm text-slate-500">Nenhum veto salvo. Use o campo acima para colar o veto (VLR) ou preencher manualmente.</p>
        )}
      </section>
    </div>
  )
}

export default MatchAnalysisPage
