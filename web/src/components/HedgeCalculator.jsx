import { useState } from 'react'
import { api } from '../api/client'

function HedgeCalculator() {
  const [stake, setStake] = useState('100')
  const [odds, setOdds] = useState('2.1')
  const [hedgeOdds, setHedgeOdds] = useState('1.85')
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')

  async function run() {
    setError('')
    try {
      const data = await api.hedge(Number(stake), Number(odds), Number(hedgeOdds), true)
      setResult(data)
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <section className="panel p-4">
      <h3 className="font-display text-base font-semibold">Hedge Calculator</h3>
      <p className="mt-1 text-sm text-slate-400">
        Calcula quanto apostar na odd contrária (hedge) para garantir lucro em qualquer resultado. Informe o valor já apostado, a odd da aposta original e a odd do hedge; o resultado mostra quanto apostar no hedge e o lucro garantido.
      </p>
      <div className="mt-2 grid gap-2 md:grid-cols-3">
        <input className="input-box rounded border border-slate-300 bg-slate-900/80 p-2 text-sm text-slate-200 placeholder:text-slate-500" value={stake} onChange={(e) => setStake(e.target.value)} placeholder="Stake original" />
        <input className="input-box rounded border border-slate-300 bg-slate-900/80 p-2 text-sm text-slate-200 placeholder:text-slate-500" value={odds} onChange={(e) => setOdds(e.target.value)} placeholder="Odd original" />
        <input className="input-box rounded border border-slate-300 bg-slate-900/80 p-2 text-sm text-slate-200 placeholder:text-slate-500" value={hedgeOdds} onChange={(e) => setHedgeOdds(e.target.value)} placeholder="Odd hedge" />
      </div>
      <button type="button" onClick={run} className="mt-2 rounded-lg bg-signal px-3 py-1.5 text-xs font-semibold text-white">Calcular hedge</button>

      {result ? (
        <div className="mt-3 rounded-lg border border-slate-200 bg-white p-3 text-sm text-slate-800">
          <p>Hedge sugerido: <strong className="text-slate-900">R${Number(result.hedge_stake).toFixed(2)}</strong></p>
          <p>Lucro se original ganha: R${Number(result.profit_if_original_wins).toFixed(2)}</p>
          <p>Lucro se hedge ganha: R${Number(result.profit_if_hedge_wins).toFixed(2)}</p>
          <p className="font-semibold">Lucro garantido: R${Number(result.guaranteed_profit).toFixed(2)}</p>
        </div>
      ) : null}

      {error ? <p className="mt-2 text-xs text-red-600">{error}</p> : null}
    </section>
  )
}

export default HedgeCalculator
