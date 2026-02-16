import { useState } from 'react'
import { api } from '../api/client'

function LivePanel({ matchId, liveState, onUpdated }) {
  const [mapNumber, setMapNumber] = useState(String((liveState?.map_results?.length || 0) + 1))
  const [winnerSide, setWinnerSide] = useState('a')
  const [scoreA, setScoreA] = useState('13')
  const [scoreB, setScoreB] = useState('10')
  const [error, setError] = useState('')

  async function submitResult() {
    setError('')
    try {
      await api.saveLiveMapResult(matchId, {
        map_number: Number(mapNumber),
        winner_side: winnerSide,
        score_a: Number(scoreA),
        score_b: Number(scoreB)
      })
      const updated = await api.getLiveSeriesProb(matchId)
      onUpdated?.(updated)
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <section className="panel p-4">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="font-display text-base font-semibold">Painel Live</h3>
        <span className="rounded-full bg-mint-soft px-2 py-1 text-xs font-semibold text-emerald-800">Betano live · Bet365 nao</span>
      </div>

      <div className="grid gap-2 md:grid-cols-5">
        <input className="rounded border border-slate-300 p-2 text-sm text-slate-800 placeholder:text-slate-500" value={mapNumber} onChange={(e) => setMapNumber(e.target.value)} placeholder="Map #" />
        <select className="rounded border border-slate-300 p-2 text-sm text-slate-800" value={winnerSide} onChange={(e) => setWinnerSide(e.target.value)}>
          <option value="a">Time A venceu</option>
          <option value="b">Time B venceu</option>
        </select>
        <input className="rounded border border-slate-300 p-2 text-sm text-slate-800 placeholder:text-slate-500" value={scoreA} onChange={(e) => setScoreA(e.target.value)} placeholder="Score A" />
        <input className="rounded border border-slate-300 p-2 text-sm text-slate-800 placeholder:text-slate-500" value={scoreB} onChange={(e) => setScoreB(e.target.value)} placeholder="Score B" />
        <button type="button" onClick={submitResult} className="rounded-lg bg-ocean px-3 py-2 text-xs font-semibold text-white">Registrar mapa</button>
      </div>

      {liveState?.series_prob ? (
        <div className="mt-3 rounded-lg border border-slate-200 bg-white p-3 text-sm text-slate-800">
          <p>Placar: {liveState.a_score} x {liveState.b_score}</p>
          <p>P(Time A serie): {(Number(liveState.series_prob.p_a_series || 0) * 100).toFixed(1)}%</p>
          <p>P(Time B serie): {(Number(liveState.series_prob.p_b_series || 0) * 100).toFixed(1)}%</p>
        </div>
      ) : null}

      {error ? <p className="mt-2 text-xs text-red-600">{error}</p> : null}
    </section>
  )
}

export default LivePanel
