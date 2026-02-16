import { useState } from 'react'

function pct(value) {
  if (value == null || Number.isNaN(value)) return '—'
  return `${(Number(value) * 100).toFixed(1)}%`
}

function StatRow({ label, valueA, valueB, betterA }) {
  const classA = betterA === true ? 'font-medium text-ocean' : 'text-slate-600'
  const classB = betterA === false ? 'font-medium text-ocean' : 'text-slate-600'
  return (
    <tr className="border-b border-slate-200 last:border-0">
      <td className="py-2 pr-2 text-xs font-medium text-slate-500">{label}</td>
      <td className={`py-2 text-right text-sm ${classA}`}>{valueA}</td>
      <td className="py-2 text-center text-xs text-slate-400">vs</td>
      <td className={`py-2 text-left text-sm ${classB}`}>{valueB}</td>
    </tr>
  )
}

export default function ComparisonPanel({ analysis }) {
  const [open, setOpen] = useState(true)
  const comp = analysis?.comparison
  const teams = analysis?.teams
  const series = analysis?.series
  const maps = analysis?.maps

  if (!comp) return null

  const overall = comp.overall || {}
  const byMap = comp.by_map || []
  const tagA = teams?.team_a?.tag || teams?.team_a?.name || 'Time A'
  const tagB = teams?.team_b?.tag || teams?.team_b?.name || 'Time B'

  const pASeries = series?.p_a_series != null ? Number(series.p_a_series) : null
  const pBSeries = series?.p_b_series != null ? Number(series.p_b_series) : null
  const dataPeriod = analysis?.data_period
  const dateFrom = dataPeriod?.date_from
  const otDisplayA = overall.team_a?.games_played != null
    ? `${overall.team_a.ot_count ?? 0}/${overall.team_a.games_played} (${pct(overall.team_a.ot_rate)})`
    : '—'
  const otDisplayB = overall.team_b?.games_played != null
    ? `${overall.team_b.ot_count ?? 0}/${overall.team_b.games_played} (${pct(overall.team_b.ot_rate)})`
    : '—'

  return (
    <section className="panel p-4">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between text-left"
      >
        <h3 className="font-display text-base font-semibold text-ink">Análise comparativa</h3>
        <span className="text-slate-500">{open ? '▼' : '▶'}</span>
      </button>
      {open && (
        <>
          {dateFrom && (
            <p className="mt-1 rounded-lg bg-amber-50 border border-amber-200 px-2 py-1.5 text-xs font-medium text-amber-800">
              Probabilidades, edges e resultados anteriores usam apenas dados a partir de <strong>{dateFrom}</strong> (ano atual). Dados antigos não entram nos cálculos.
            </p>
          )}

          <div className="mt-3 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <div className="rounded-xl border border-slate-100 bg-white p-4 shadow-sm">
              <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Geral (todos os mapas)</h4>
              <table className="mt-3 w-full text-sm">
                <tbody>
                  <StatRow
                    label="Overtime"
                    valueA={otDisplayA}
                    valueB={otDisplayB}
                    betterA={overall.team_a?.ot_rate != null && overall.team_b?.ot_rate != null ? overall.team_a.ot_rate > overall.team_b.ot_rate : undefined}
                  />
                  <StatRow
                    label="Pistolas"
                    valueA={overall.team_a?.pistols_played ? `${overall.team_a.pistols_won}/${overall.team_a.pistols_played} (${pct(overall.team_a.pistol_rate)})` : '—'}
                    valueB={overall.team_b?.pistols_played ? `${overall.team_b.pistols_won}/${overall.team_b.pistols_played} (${pct(overall.team_b.pistol_rate)})` : '—'}
                    betterA={overall.team_a?.pistol_rate != null && overall.team_b?.pistol_rate != null ? overall.team_a.pistol_rate > overall.team_b.pistol_rate : undefined}
                  />
                  <StatRow
                    label="Pistol ATK%"
                    valueA={pct(overall.team_a?.pistol_atk_pct)}
                    valueB={pct(overall.team_b?.pistol_atk_pct)}
                    betterA={overall.team_a?.pistol_atk_pct != null && overall.team_b?.pistol_atk_pct != null ? overall.team_a.pistol_atk_pct > overall.team_b.pistol_atk_pct : undefined}
                  />
                  <StatRow
                    label="Pistol DEF%"
                    valueA={pct(overall.team_a?.pistol_def_pct)}
                    valueB={pct(overall.team_b?.pistol_def_pct)}
                    betterA={overall.team_a?.pistol_def_pct != null && overall.team_b?.pistol_def_pct != null ? overall.team_a.pistol_def_pct > overall.team_b.pistol_def_pct : undefined}
                  />
                  <StatRow
                    label="Winrate"
                    valueA={pct(overall.team_a?.winrate)}
                    valueB={pct(overall.team_b?.winrate)}
                    betterA={overall.team_a?.winrate != null && overall.team_b?.winrate != null ? overall.team_a.winrate > overall.team_b.winrate : undefined}
                  />
                  <StatRow label="Jogos" valueA={overall.team_a?.games_played ?? '—'} valueB={overall.team_b?.games_played ?? '—'} />
                </tbody>
              </table>
            </div>

            <div className="rounded-xl border border-ocean/20 bg-ocean/5 px-4 py-2.5 lg:col-span-2 self-start">
              <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-600">Estimativa do modelo (série)</h4>
              <div className="mt-1 flex flex-wrap items-baseline gap-4">
                <span className="text-lg font-bold text-ocean">{tagA} {pct(pASeries)}</span>
                <span className="text-slate-400">×</span>
                <span className="text-lg font-bold text-ocean">{tagB} {pct(pBSeries)}</span>
              </div>
            </div>
          </div>

          {byMap.length > 0 && (
            <div className="mt-4 rounded-xl border border-slate-100 bg-white p-4 shadow-sm">
              <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Mapas da série (veto)</h4>
              <div className="mt-3 overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 text-xs font-medium text-slate-500">
                      <th className="py-2.5 pr-2 text-left">Mapa</th>
                      <th className="py-2.5 pr-2 text-right">{tagA}</th>
                      <th className="py-2.5 w-8" />
                      <th className="py-2.5 pl-2 text-left">{tagB}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {byMap.map((row, idx) => {
                      const mapAnalysis = maps?.[idx]
                      const pA = mapAnalysis?.p_team_a_win != null ? Number(mapAnalysis.p_team_a_win) : null
                      const pB = pA != null ? 1 - pA : null
                      const pAClass = pA != null ? (pA >= 0.55 ? 'font-semibold text-emerald-700' : pA <= 0.45 ? 'font-semibold text-red-700' : 'font-medium text-amber-700') : ''
                      const pBClass = pB != null ? (pB >= 0.55 ? 'font-semibold text-emerald-700' : pB <= 0.45 ? 'font-semibold text-red-700' : 'font-medium text-amber-700') : ''
                      const otA = row.team_a?.games_played != null ? `${row.team_a.ot_count ?? 0}/${row.team_a.games_played} (${pct(row.team_a.ot_rate)})` : '—'
                      const otB = row.team_b?.games_played != null ? `${row.team_b.ot_count ?? 0}/${row.team_b.games_played} (${pct(row.team_b.ot_rate)})` : '—'
                      const pistolA = row.team_a?.pistols_played ? `${row.team_a.pistols_won}/${row.team_a.pistols_played} (${pct(row.team_a.pistol_rate)})` : '—'
                      const pistolB = row.team_b?.pistols_played ? `${row.team_b.pistols_won}/${row.team_b.pistols_played} (${pct(row.team_b.pistol_rate)})` : '—'
                      return (
                        <tr key={row.map_name} className="border-b border-slate-200 last:border-0 hover:bg-slate-50/50">
                          <td className="py-2 pr-2 font-medium text-slate-600">{row.map_name}</td>
                          <td className="py-2 pr-2 text-right text-slate-600 text-xs">
                            <span className={`mr-1.5 ${pAClass}`}>P(ganha) {pct(pA)}</span>
                            {pct(row.team_a?.winrate)} · OT {otA} · Pistol {pistolA} · Pistol ATK {pct(row.team_a?.pistol_atk_pct)} DEF {pct(row.team_a?.pistol_def_pct)}
                            {row.team_a?.games_played != null && <span className="ml-1 text-slate-400">({row.team_a.games_played} j)</span>}
                          </td>
                          <td className="py-2 text-center text-slate-400">vs</td>
                          <td className="py-2 pl-2 text-left text-slate-600 text-xs">
                            <span className={`mr-1.5 ${pBClass}`}>P(ganha) {pct(pB)}</span>
                            {pct(row.team_b?.winrate)} · OT {otB} · Pistol {pistolB} · Pistol ATK {pct(row.team_b?.pistol_atk_pct)} DEF {pct(row.team_b?.pistol_def_pct)}
                            {row.team_b?.games_played != null && <span className="ml-1 text-slate-400">({row.team_b.games_played} j)</span>}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {(comp.all_maps?.length ?? 0) > 0 && (
            <div className="mt-4 rounded-xl border border-slate-100 bg-white p-4 shadow-sm">
              <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Todos os mapas da pool</h4>
              <div className="mt-3 overflow-x-auto">
                <table className="min-w-full border-collapse text-sm">
                  <thead>
                    <tr className="border-t border-b border-slate-400">
                      <th className="sticky left-0 z-10 min-w-[72px] border-l border-slate-400 bg-white py-2 pl-2 pr-2 text-left" scope="col">Mapa</th>
                      <th className="py-2 text-center text-base font-semibold text-slate-700" colSpan={9} scope="col">{tagA}</th>
                      <th className="w-2" scope="col" />
                      <th className="py-2 text-center text-base font-semibold text-slate-700 border-r border-slate-400" colSpan={9} scope="col">{tagB}</th>
                    </tr>
                    <tr className="border-b border-slate-300 text-[10px] font-medium text-slate-400">
                      <th className="sticky left-0 z-10 border-l border-slate-400 bg-white py-1 pl-2 pr-2" />
                      <th className="py-1 px-1 text-right">P(ganha)</th>
                      <th className="border-l border-slate-400 py-1 px-1 text-right">Win%</th>
                      <th className="border-l border-slate-400 py-1 px-1 text-right">OT</th>
                      <th className="border-l border-slate-400 py-1 px-1 text-right">Pistol</th>
                      <th className="border-l border-slate-400 py-1 px-1 text-right">P.ATK%</th>
                      <th className="border-l border-slate-400 py-1 px-1 text-right">P.DEF%</th>
                      <th className="border-l border-slate-400 py-1 px-1 text-right">ATK%</th>
                      <th className="border-l border-slate-400 py-1 px-1 text-right">DEF%</th>
                      <th className="border-l border-slate-400 py-1 px-1 text-right">J</th>
                      <th className="w-2" />
                      <th className="border-l-2 border-slate-500 py-1 px-1 text-left">P(ganha)</th>
                      <th className="border-l border-slate-400 py-1 px-1 text-left">Win%</th>
                      <th className="border-l border-slate-400 py-1 px-1 text-left">OT</th>
                      <th className="border-l border-slate-400 py-1 px-1 text-left">Pistol</th>
                      <th className="border-l border-slate-400 py-1 px-1 text-left">P.ATK%</th>
                      <th className="border-l border-slate-400 py-1 px-1 text-left">P.DEF%</th>
                      <th className="border-l border-slate-400 py-1 px-1 text-left">ATK%</th>
                      <th className="border-l border-slate-400 py-1 px-1 text-left">DEF%</th>
                      <th className="border-l border-slate-400 py-1 px-1 text-left border-r border-slate-400">J</th>
                    </tr>
                  </thead>
                  <tbody>
                    {comp.all_maps.map((row, idx) => {
                      const a = row.team_a
                      const b = row.team_b
                      const otA = a?.games_played != null ? `${a.ot_count ?? 0}/${a.games_played}` : '—'
                      const otB = b?.games_played != null ? `${b.ot_count ?? 0}/${b.games_played}` : '—'
                      const pistolA = a?.pistols_played ? `${a.pistols_won}/${a.pistols_played}` : '—'
                      const pistolB = b?.pistols_played ? `${b.pistols_won}/${b.pistols_played}` : '—'
                      const pA = row.p_team_a_win != null ? Number(row.p_team_a_win) : null
                      const pB = pA != null ? 1 - pA : null
                      const pAClass = pA != null ? (pA >= 0.55 ? 'font-semibold text-emerald-700 bg-emerald-50' : pA <= 0.45 ? 'font-semibold text-red-700 bg-red-50' : 'font-medium text-amber-700 bg-amber-50/50') : ''
                      const pBClass = pB != null ? (pB >= 0.55 ? 'font-semibold text-emerald-700 bg-emerald-50' : pB <= 0.45 ? 'font-semibold text-red-700 bg-red-50' : 'font-medium text-amber-700 bg-amber-50/50') : ''
                      const winAWinner = (a?.winrate ?? 0) > (b?.winrate ?? 0)
                      const winBWinner = (b?.winrate ?? 0) > (a?.winrate ?? 0)
                      const pistolAWinner = (a?.pistol_rate ?? 0) > (b?.pistol_rate ?? 0) && (a?.pistols_played ?? 0) >= 1
                      const pistolBWinner = (b?.pistol_rate ?? 0) > (a?.pistol_rate ?? 0) && (b?.pistols_played ?? 0) >= 1
                      const isLast = idx === comp.all_maps.length - 1
                      const v = 'border-l border-slate-400'
                      return (
                        <tr key={row.map_name} className={`hover:bg-slate-50/50 ${isLast ? 'border-b border-slate-400' : ''}`}>
                          <td className="sticky left-0 z-10 bg-white py-2 pl-2 pr-2 font-medium text-slate-600 border-l border-r border-slate-400">{row.map_name}</td>
                          <td className={`${v} py-2 px-1 text-right tabular-nums ${pAClass}`}>{pct(pA)}</td>
                          <td className={`${v} py-2 px-1 text-right tabular-nums ${winAWinner ? 'text-ocean font-medium' : 'text-slate-600'}`}>{pct(a?.winrate)}</td>
                          <td className={`${v} py-2 px-1 text-right text-slate-600 text-xs tabular-nums`}>{otA}</td>
                          <td className={`${v} py-2 px-1 text-right text-xs tabular-nums ${pistolAWinner ? 'text-ocean font-medium' : 'text-slate-600'}`}>{pistolA}</td>
                          <td className={`${v} py-2 px-1 text-right text-slate-600 tabular-nums`}>{pct(a?.pistol_atk_pct)}</td>
                          <td className={`${v} py-2 px-1 text-right text-slate-600 tabular-nums`}>{pct(a?.pistol_def_pct)}</td>
                          <td className={`${v} py-2 px-1 text-right text-slate-600 tabular-nums`}>{pct(a?.atk_win_pct)}</td>
                          <td className={`${v} py-2 px-1 text-right text-slate-600 tabular-nums`}>{pct(a?.def_win_pct)}</td>
                          <td className={`${v} py-2 px-1 text-right text-slate-500`}>{a?.games_played ?? '—'}</td>
                          <td className="w-2" />
                          <td className={`border-l-2 border-slate-500 py-2 px-1 text-left tabular-nums ${pBClass}`}>{pct(pB)}</td>
                          <td className={`${v} py-2 px-1 text-left tabular-nums ${winBWinner ? 'text-ocean font-medium' : 'text-slate-600'}`}>{pct(b?.winrate)}</td>
                          <td className={`${v} py-2 px-1 text-left text-slate-600 text-xs tabular-nums`}>{otB}</td>
                          <td className={`${v} py-2 px-1 text-left text-xs tabular-nums ${pistolBWinner ? 'text-ocean font-medium' : 'text-slate-600'}`}>{pistolB}</td>
                          <td className={`${v} py-2 px-1 text-left text-slate-600 tabular-nums`}>{pct(b?.pistol_atk_pct)}</td>
                          <td className={`${v} py-2 px-1 text-left text-slate-600 tabular-nums`}>{pct(b?.pistol_def_pct)}</td>
                          <td className={`${v} py-2 px-1 text-left text-slate-600 tabular-nums`}>{pct(b?.atk_win_pct)}</td>
                          <td className={`${v} py-2 px-1 text-left text-slate-600 tabular-nums`}>{pct(b?.def_win_pct)}</td>
                          <td className={`${v} py-2 px-1 text-left text-slate-500 border-r border-slate-400`}>{b?.games_played ?? '—'}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </section>
  )
}
