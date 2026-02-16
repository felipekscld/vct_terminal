import { useState } from 'react'
import { api } from '../api/client'

function VetoInput({ matchId, onSaved }) {
  const [vetoText, setVetoText] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleSave() {
    setError('')
    if (!vetoText.trim()) {
      setError('Cole o veto antes de salvar.')
      return
    }

    setLoading(true)
    try {
      const res = await api.saveVeto(matchId, { veto_text: vetoText })
      setVetoText('')
      onSaved?.(res)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="panel p-4">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="font-display text-base font-semibold">Veto da Partida</h3>
        <button
          type="button"
          onClick={handleSave}
          disabled={loading}
          className="rounded-lg bg-ocean px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-60"
        >
          {loading ? 'Salvando...' : 'Salvar Veto'}
        </button>
      </div>

      <textarea
        value={vetoText}
        onChange={(e) => setVetoText(e.target.value)}
        className="h-24 w-full rounded-lg border border-slate-300 bg-slate-900 p-2 text-sm text-slate-100 outline-none focus:ring-2 focus:ring-blue-500/50"
        placeholder="Ex: MIBR ban Pearl; NRG ban Breeze; MIBR pick Bind; NRG pick Corrode; Haven remains"
      />

      {error ? <p className="mt-2 text-xs text-red-600">{error}</p> : null}
    </section>
  )
}

export default VetoInput
