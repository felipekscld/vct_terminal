import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../api/client'
import LivePanel from '../components/LivePanel'
import HedgeCalculator from '../components/HedgeCalculator'

function LivePage() {
  const { id } = useParams()
  const matchId = Number(id)

  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  async function loadLive() {
    setLoading(true)
    setError('')
    try {
      const response = await api.getLiveSeriesProb(matchId)
      setData(response)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadLive()
  }, [matchId])

  if (loading) return <p className="text-sm text-slate-600">Carregando painel live...</p>
  if (error) return <p className="text-sm text-red-600">{error}</p>

  return (
    <div className="space-y-4">
      <section className="panel p-4">
        <h2 className="page-title text-xl font-bold text-ink">Análise ao vivo</h2>
        <p className="text-sm text-slate-600">Betano ao vivo x Bet365 pre-match.</p>
      </section>

      <LivePanel matchId={matchId} liveState={data} onUpdated={setData} />

      <section className="panel p-4">
        <h3 className="font-display text-base font-semibold">Live State JSON</h3>
        <pre className="mt-3 overflow-auto rounded-lg bg-slate-950 p-3 text-xs text-slate-100">{JSON.stringify(data, null, 2)}</pre>
      </section>

      <HedgeCalculator />
    </div>
  )
}

export default LivePage
