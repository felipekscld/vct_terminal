import { useMemo, useState } from 'react'
import { api } from '../api/client'

const BOOKMAKERS = ['betano', 'bet365']

function parseBatch(batchText) {
  const lines = batchText.replace(/\n/g, ';').split(';').map((part) => part.trim()).filter(Boolean)
  const entries = []

  for (const line of lines) {
    const tokens = line.split(/\s+/)
    if (tokens.length < 4) continue

    const bookmaker = tokens[0].toLowerCase()
    const market_type = tokens[1].toLowerCase()
    const selection = tokens.slice(2, -1).join(' ')
    const odds_value = Number(tokens[tokens.length - 1])
    if (!Number.isFinite(odds_value) || odds_value <= 1) continue

    const mapDigits = market_type.replace(/\D+/g, '')
    entries.push({
      bookmaker,
      market_type,
      selection,
      odds_value,
      map_number: mapDigits ? Number(mapDigits) : null
    })
  }

  return entries
}

function OddsForm({ matchId, teams, maps, onSaved }) {
  const [values, setValues] = useState({})
  const [batchText, setBatchText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const teamA = teams?.team_a?.tag || teams?.team_a?.name || 'Team A'
  const teamB = teams?.team_b?.tag || teams?.team_b?.name || 'Team B'

  const mapList = useMemo(() => {
    if (!maps?.length) {
      return [
        { map_order: 1, map_name: 'Map 1' },
        { map_order: 2, map_name: 'Map 2' },
        { map_order: 3, map_name: 'Map 3' }
      ]
    }
    return maps
  }, [maps])

  const setField = (key, value) => setValues((prev) => ({ ...prev, [key]: value }))

  function collectStructuredEntries() {
    const entries = []

    BOOKMAKERS.forEach((book) => {
      const mwA = Number(values[`match_winner_${book}_a`])
      const mwB = Number(values[`match_winner_${book}_b`])
      if (mwA > 1) entries.push({ bookmaker: book, market_type: 'match_winner', selection: teamA, odds_value: mwA, map_number: null })
      if (mwB > 1) entries.push({ bookmaker: book, market_type: 'match_winner', selection: teamB, odds_value: mwB, map_number: null })
    })

    mapList.forEach((map) => {
      const n = map.map_order
      BOOKMAKERS.forEach((book) => {
        const winnerA = Number(values[`map${n}_winner_${book}_a`])
        const winnerB = Number(values[`map${n}_winner_${book}_b`])
        const otYes = Number(values[`map${n}_ot_${book}`])
        const handicap = Number(values[`map${n}_handicap_${book}`])
        const total = Number(values[`map${n}_total_rounds_${book}`])
        const pistol = Number(values[`map${n}_pistol_${book}`])

        if (winnerA > 1) entries.push({ bookmaker: book, market_type: `map${n}_winner`, selection: teamA, odds_value: winnerA, map_number: n })
        if (winnerB > 1) entries.push({ bookmaker: book, market_type: `map${n}_winner`, selection: teamB, odds_value: winnerB, map_number: n })
        if (otYes > 1) entries.push({ bookmaker: book, market_type: `map${n}_ot`, selection: 'Yes', odds_value: otYes, map_number: n })
        if (handicap > 1) entries.push({ bookmaker: book, market_type: `map${n}_handicap`, selection: `${teamA} -2.5`, odds_value: handicap, map_number: n })
        if (total > 1) entries.push({ bookmaker: book, market_type: `map${n}_total_rounds`, selection: 'Over 24.5', odds_value: total, map_number: n })
        if (pistol > 1) entries.push({ bookmaker: book, market_type: `map${n}_pistol_1h`, selection: teamA, odds_value: pistol, map_number: n })
      })
    })

    return entries
  }

  async function saveStructured() {
    setError('')
    setBusy(true)
    try {
      const entries = collectStructuredEntries()
      if (!entries.length) throw new Error('Preencha pelo menos uma odd valida.')
      const res = await api.saveOdds(matchId, { entries })
      onSaved?.(res)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function saveBatch() {
    setError('')
    setBusy(true)
    try {
      const entries = parseBatch(batchText)
      if (!entries.length) throw new Error('Nenhuma odd valida no batch paste.')
      const res = await api.saveOdds(matchId, { entries })
      setBatchText('')
      onSaved?.(res)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function autoFetch() {
    setError('')
    setBusy(true)
    try {
      const res = await api.autoOdds(matchId)
      onSaved?.(res)
    } catch (err) {
      const fallbackSteps = err?.payload?.fallback_steps
      const fallbackText = Array.isArray(fallbackSteps) ? ` | Fallback: ${fallbackSteps.join(' | ')}` : ''
      setError(`${err.message}${fallbackText}`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="panel space-y-4 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-display text-base font-semibold text-ink">Formulário de odds</h3>
        <div className="flex gap-2">
          <button type="button" onClick={autoFetch} className="rounded-lg bg-mint px-3 py-1.5 text-xs font-semibold text-white" disabled={busy}>
            Buscar odds automaticamente
          </button>
          <button type="button" onClick={saveStructured} className="rounded-lg bg-signal px-3 py-1.5 text-xs font-semibold text-white" disabled={busy}>
            Salvar odds do formulário
          </button>
        </div>
      </div>

      <div className="rounded-xl border border-slate-200 p-3">
        <p className="mb-2 text-sm font-semibold text-slate-700">Vencedor da série</p>
        <div className="grid gap-2 md:grid-cols-2">
          {BOOKMAKERS.map((book) => (
            <div key={book} className="rounded-lg bg-slate-50 p-2">
              <p className="text-xs font-semibold uppercase text-slate-500">{book}</p>
              <div className="mt-2 grid gap-2">
                <input className="rounded border p-2 text-sm" placeholder={`Odd ${teamA}`} value={values[`match_winner_${book}_a`] || ''} onChange={(e) => setField(`match_winner_${book}_a`, e.target.value)} />
                <input className="rounded border p-2 text-sm" placeholder={`Odd ${teamB}`} value={values[`match_winner_${book}_b`] || ''} onChange={(e) => setField(`match_winner_${book}_b`, e.target.value)} />
              </div>
            </div>
          ))}
        </div>
      </div>

      {mapList.map((map) => (
        <div key={map.map_order} className="rounded-xl border border-slate-200 p-3">
          <p className="mb-2 text-sm font-semibold text-slate-700">Mapa {map.map_order} ({map.map_name})</p>
          <div className="grid gap-3 md:grid-cols-2">
            {BOOKMAKERS.map((book) => (
              <div key={`${map.map_order}_${book}`} className="rounded-lg bg-slate-50 p-2">
                <p className="text-xs font-semibold uppercase text-slate-500">{book}</p>
                <div className="mt-2 grid gap-2">
                  <input className="rounded border p-2 text-sm" placeholder={`Vencedor ${teamA}`} value={values[`map${map.map_order}_winner_${book}_a`] || ''} onChange={(e) => setField(`map${map.map_order}_winner_${book}_a`, e.target.value)} />
                  <input className="rounded border p-2 text-sm" placeholder={`Vencedor ${teamB}`} value={values[`map${map.map_order}_winner_${book}_b`] || ''} onChange={(e) => setField(`map${map.map_order}_winner_${book}_b`, e.target.value)} />
                  <input className="rounded border p-2 text-sm" placeholder="Overtime (Sim)" value={values[`map${map.map_order}_ot_${book}`] || ''} onChange={(e) => setField(`map${map.map_order}_ot_${book}`, e.target.value)} />
                  <input className="rounded border p-2 text-sm" placeholder="Handicap de rounds" value={values[`map${map.map_order}_handicap_${book}`] || ''} onChange={(e) => setField(`map${map.map_order}_handicap_${book}`, e.target.value)} />
                  <input className="rounded border p-2 text-sm" placeholder="Total de rounds (Over 24.5)" value={values[`map${map.map_order}_total_rounds_${book}`] || ''} onChange={(e) => setField(`map${map.map_order}_total_rounds_${book}`, e.target.value)} />
                  <input className="rounded border p-2 text-sm" placeholder="Pistol 1º half" value={values[`map${map.map_order}_pistol_${book}`] || ''} onChange={(e) => setField(`map${map.map_order}_pistol_${book}`, e.target.value)} />
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}

      <div className="rounded-xl border border-slate-200 p-3">
        <p className="mb-2 text-sm font-semibold text-slate-700">Batch Paste (alternativo)</p>
        <textarea
          className="h-24 w-full rounded border p-2 text-sm"
          placeholder="betano map1_winner MIBR 1.75; bet365 map1_ot Yes 5.00"
          value={batchText}
          onChange={(e) => setBatchText(e.target.value)}
        />
        <div className="mt-2">
          <button type="button" onClick={saveBatch} className="rounded-lg bg-ocean px-3 py-1.5 text-xs font-semibold text-white" disabled={busy}>
            Salvar batch
          </button>
        </div>
      </div>

      {error ? <p className="text-xs text-red-600">{error}</p> : null}
    </section>
  )
}

export default OddsForm
