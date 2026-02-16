import { useEffect, useState } from 'react'
import { api } from '../api/client'

function SettingsPage({ config: parentConfig, onConfigUpdate }) {
  const [config, setConfig] = useState(parentConfig)
  const [marketOptions, setMarketOptions] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  useEffect(() => {
    if (parentConfig) setConfig(parentConfig)
  }, [parentConfig])

  async function refresh() {
    try {
      const data = await api.getConfig()
      setConfig(data)
      onConfigUpdate?.(data)
    } catch (err) {
      setError(err.message)
    }
  }

  useEffect(() => {
    if (!config) refresh()
  }, [])

  useEffect(() => {
    api.getMarkets()
      .then((res) => setMarketOptions(res.items || []))
      .catch(() => setMarketOptions([]))
  }, [])

  function setField(path, value) {
    setConfig((prev) => {
      const next = structuredClone(prev || {})
      const keys = path.split('.')
      let cursor = next
      keys.slice(0, -1).forEach((key) => {
        cursor[key] = cursor[key] || {}
        cursor = cursor[key]
      })
      cursor[keys[keys.length - 1]] = value
      return next
    })
  }

  async function save() {
    setLoading(true)
    setError('')
    setSuccess('')

    try {
      const payload = {
        data_filter: {
          event_ids: config?.data_filter?.event_ids || [],
          stage_names: config?.data_filter?.stage_names || [],
          date_from: config?.data_filter?.date_from || null,
          date_to: config?.data_filter?.date_to || null
        },
        bankroll: {
          total: Number(config?.bankroll?.total || 0),
          max_stake_pct: Number(config?.bankroll?.max_stake_pct || 0),
          daily_limit: Number(config?.bankroll?.daily_limit || 0),
          event_limit: Number(config?.bankroll?.event_limit || 0),
          kelly_fraction: Number(config?.bankroll?.kelly_fraction || 0)
        },
        edge: {
          min_edge: Number(config?.edge?.min_edge || 0),
          strong_edge: Number(config?.edge?.strong_edge || 0),
          min_confidence: config?.edge?.min_confidence || 'medium',
          min_sample_map: Number(config?.edge?.min_sample_map || 0),
          min_sample_general: Number(config?.edge?.min_sample_general || 0)
        },
        markets: {
          enabled_markets: config?.markets?.enabled_markets || []
        },
        live: {
          betano_live: Boolean(config?.live?.betano_live),
          bet365_live: Boolean(config?.live?.bet365_live),
          show_live_opportunities: Boolean(config?.live?.show_live_opportunities),
          auto_recalc_on_map_result: Boolean(config?.live?.auto_recalc_on_map_result)
        }
      }

      const updated = await api.updateConfig(payload)
      setConfig(updated)
      onConfigUpdate?.(updated)
      setSuccess('Configurações salvas com sucesso.')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-4">
      <section className="panel p-4">
        <h2 className="page-title text-xl font-bold">Configurações</h2>
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <article className="panel p-4">
          <h3 className="font-display text-base font-semibold text-ink">Seu dinheiro e limites</h3>
          <div className="mt-3 space-y-4">
            <div>
              <label className="block text-sm font-medium text-slate-700">Caixa total (R$)</label>
              <input type="number" step="any" min="0" className="mt-1 w-full rounded border border-slate-300 p-2 text-sm" value={config?.bankroll?.total ?? ''} onChange={(e) => setField('bankroll.total', e.target.value)} placeholder="Ex: 1300" />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700">Máximo por aposta (% do caixa)</label>
              <input type="number" step="0.01" min="0" max="1" className="mt-1 w-full rounded border border-slate-300 p-2 text-sm" value={config?.bankroll?.max_stake_pct ?? ''} onChange={(e) => setField('bankroll.max_stake_pct', e.target.value)} placeholder="Ex: 0.03 (3%)" />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700">Limite por dia (R$)</label>
              <input type="number" step="any" min="0" className="mt-1 w-full rounded border border-slate-300 p-2 text-sm" value={config?.bankroll?.daily_limit ?? ''} onChange={(e) => setField('bankroll.daily_limit', e.target.value)} placeholder="Ex: 300" />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700">Limite por evento (R$)</label>
              <input type="number" step="any" min="0" className="mt-1 w-full rounded border border-slate-300 p-2 text-sm" value={config?.bankroll?.event_limit ?? ''} onChange={(e) => setField('bankroll.event_limit', e.target.value)} placeholder="Ex: 500" />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700">Conservadorismo do valor (Kelly)</label>
              <p className="text-xs text-slate-500">0,25 = mais seguro (recomendado). 1 = mais agressivo. Controla o tamanho da aposta sugerida.</p>
              <input type="number" step="0.05" min="0" max="1" className="mt-1 w-full rounded border border-slate-300 p-2 text-sm" value={config?.bankroll?.kelly_fraction ?? ''} onChange={(e) => setField('bankroll.kelly_fraction', e.target.value)} placeholder="Ex: 0.25" />
            </div>
          </div>
        </article>

        <article className="panel p-4">
          <h3 className="font-display text-base font-semibold text-ink">Quando recomendar apostas</h3>
          <div className="mt-3 space-y-4">
            <div>
              <label className="block text-sm font-medium text-slate-700">Edge mínimo para &quot;Observar&quot; (%)</label>
              <input type="number" step="0.01" min="0" max="1" className="mt-1 w-full rounded border border-slate-300 p-2 text-sm" value={config?.edge?.min_edge ?? ''} onChange={(e) => setField('edge.min_edge', e.target.value)} placeholder="Ex: 0.03 (3%)" />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700">Edge para &quot;Edge forte&quot; (%)</label>
              <input type="number" step="0.01" min="0" max="1" className="mt-1 w-full rounded border border-slate-300 p-2 text-sm" value={config?.edge?.strong_edge ?? ''} onChange={(e) => setField('edge.strong_edge', e.target.value)} placeholder="Ex: 0.08 (8%)" />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700">Confiança mínima</label>
              <p className="text-xs text-slate-500">low = exige menos dados, high = só recomenda com bastante histórico.</p>
              <select className="mt-1 w-full rounded border border-slate-300 p-2 text-sm" value={config?.edge?.min_confidence ?? 'medium'} onChange={(e) => setField('edge.min_confidence', e.target.value)}>
                <option value="low">Baixa (low)</option>
                <option value="medium">Média (medium)</option>
                <option value="high">Alta (high)</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700">Mín. jogos no mapa</label>
              <p className="text-xs text-slate-500">Só usa estatística do mapa se o time tiver pelo menos esse número de jogos naquele mapa.</p>
              <input type="number" min="0" className="mt-1 w-full rounded border border-slate-300 p-2 text-sm" value={config?.edge?.min_sample_map ?? ''} onChange={(e) => setField('edge.min_sample_map', e.target.value)} placeholder="Ex: 3" />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700">Mín. jogos em geral</label>
              <p className="text-xs text-slate-500">Mínimo de jogos totais para confiar na estatística geral do time.</p>
              <input type="number" min="0" className="mt-1 w-full rounded border border-slate-300 p-2 text-sm" value={config?.edge?.min_sample_general ?? ''} onChange={(e) => setField('edge.min_sample_general', e.target.value)} placeholder="Ex: 5" />
            </div>
          </div>
        </article>
      </section>

      <section className="panel p-4">
        <h3 className="font-display text-base font-semibold text-ink">Mercados que você usa</h3>
        <div className="mt-2 flex flex-wrap gap-x-6 gap-y-2">
          {marketOptions.map((m) => {
            const enabled = (config?.markets?.enabled_markets || []).includes(m.id)
            return (
              <label key={m.id} className="flex cursor-pointer items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={enabled}
                  onChange={(e) => {
                    const list = [...(config?.markets?.enabled_markets || [])]
                    if (e.target.checked) {
                      setField('markets.enabled_markets', [...list, m.id])
                    } else {
                      setField('markets.enabled_markets', list.filter((id) => id !== m.id))
                    }
                  }}
                />
                <span>{m.label}</span>
              </label>
            )
          })}
        </div>
        {marketOptions.length === 0 ? <p className="mt-2 text-xs text-slate-500">Carregando opções…</p> : null}
      </section>

      <section className="panel p-4">
        <h3 className="font-display text-base font-semibold text-ink">Apostas ao vivo</h3>
        <div className="mt-2 space-y-2">
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={Boolean(config?.live?.betano_live)} onChange={(e) => setField('live.betano_live', e.target.checked)} /> Considerar odds ao vivo da Betano</label>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={Boolean(config?.live?.bet365_live)} onChange={(e) => setField('live.bet365_live', e.target.checked)} /> Considerar odds ao vivo da Bet365</label>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={Boolean(config?.live?.show_live_opportunities)} onChange={(e) => setField('live.show_live_opportunities', e.target.checked)} /> Mostrar oportunidades de live no painel</label>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={Boolean(config?.live?.auto_recalc_on_map_result)} onChange={(e) => setField('live.auto_recalc_on_map_result', e.target.checked)} /> Recalcular probabilidades ao registrar resultado de mapa</label>
        </div>
      </section>

      <div className="flex items-center gap-2">
        <button type="button" onClick={save} disabled={loading} className="rounded-lg bg-signal px-4 py-2 text-sm font-semibold text-white">{loading ? 'Salvando...' : 'Salvar configurações'}</button>
        <button type="button" onClick={refresh} className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white">Recarregar</button>
      </div>

      {error ? <p className="text-sm text-red-600">{error}</p> : null}
      {success ? <p className="text-sm text-emerald-700">{success}</p> : null}
    </div>
  )
}

export default SettingsPage
