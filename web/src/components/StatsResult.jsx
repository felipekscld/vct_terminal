const LABELS = {
  games_played: 'Jogos disputados',
  wins: 'Vitórias',
  losses: 'Derrotas',
  winrate: 'Taxa de vitória',
  ot_count: 'Overtimes',
  ot_rate: 'Taxa de overtime',
  pistols_won: 'Round pistols ganhos',
  pistols_played: 'Round pistols jogados',
  pistol_rate: '% de round pistols ganhos',
  pistol_atk_won: 'Round pistols no ataque (ganhos)',
  pistol_atk_played: 'Round pistols no ataque (jogados)',
  pistol_def_won: 'Round pistols na defesa (ganhos)',
  pistol_def_played: 'Round pistols na defesa (jogados)',
  atk_rate: 'Lado ataque',
  def_rate: 'Lado defesa',
  atk_round_rate: 'Lado ataque',
  def_round_rate: 'Lado defesa',
  close_maps: 'Mapas apertados',
  close_rate: 'Taxa de mapas apertados',
  total_maps: 'Total de mapas',
  a_wins: 'Vitórias time A',
  b_wins: 'Vitórias time B',
  map_name: 'Mapa',
  date: 'Data',
  score: 'Placar',
  matchup: 'Confronto',
  is_ot: 'Overtime',
  team: 'Time',
  compositions: 'Composições',
  likely_compositions: 'Composições prováveis',
  used: 'Usos',
  winrate_comp: 'Taxa de vitória'
}

const STAT_KEYS_ORDER = [
  'games_played', 'wins', 'losses', 'winrate', 'ot_count', 'ot_rate',
  'pistols_won', 'pistols_played', 'pistol_rate',
  'pistol_atk_won', 'pistol_atk_played', 'pistol_def_won', 'pistol_def_played',
  'atk_rate', 'def_rate',
  'atk_round_rate', 'def_round_rate', 'close_maps', 'close_rate'
]

function label(key) {
  return LABELS[key] ?? key
}

function formatValue(val, key) {
  if (val == null) return '–'
  if (typeof val === 'boolean') return val ? 'Sim' : 'Não'
  if (typeof val === 'number') {
    if (key === 'pistol_rate' || key === 'pistol_atk_rate' || key === 'pistol_def_rate') return `${Math.round(val * 100)}%`
    if (val <= 1 && val >= 0 && String(val).includes('.')) return `${Math.round(val * 100)}%`
    return Number.isInteger(val) ? String(val) : val.toFixed(2)
  }
  if (typeof val === 'object') return null
  return String(val)
}

function formatStatLine(key, value) {
  const l = label(key)
  const v = formatValue(value, key)
  if (v == null) return ''
  return `- **${l}:** ${v}`
}

function queryResultToMd(data) {
  const r = data?.result
  if (!r) return ''

  if (r.error) return `**Erro:** ${r.error}\n`

  if (typeof r.total_maps === 'number') {
    const lines = [
      '## Head-to-head',
      formatStatLine('total_maps', r.total_maps),
      formatStatLine('a_wins', r.a_wins),
      formatStatLine('b_wins', r.b_wins),
      formatStatLine('ot_count', r.ot_count),
      formatStatLine('ot_rate', r.ot_rate)
    ]
    return lines.filter(Boolean).join('\n')
  }

  if (Array.isArray(r.items) && r.items.length > 0 && r.items[0].score !== undefined) {
    const lines = ['## Placares recentes']
    r.items.forEach((it) => {
      lines.push(`- ${it.date ?? '?'} · ${it.map_name ?? '?'} · **${it.score}** · ${it.matchup ?? '?'}${it.is_ot ? ' (OT)' : ''}`)
    })
    return lines.join('\n')
  }

  if (Array.isArray(r.items) && r.items.some((it) => it.compositions != null)) {
    const lines = ['## Composições']
    r.items.forEach((it) => {
      const name = it.team?.tag ?? it.team?.name ?? it.team ?? '?'
      lines.push(`### ${name}`)
      const comps = it.compositions ?? []
      comps.forEach((c) => {
        const agentsStr = Array.isArray(c.agents) ? c.agents.join(', ') : [c.agent1, c.agent2, c.agent3, c.agent4, c.agent5].filter(Boolean).join(', ')
        const used = c.used ?? c.usage_count
        const wr = c.winrate != null ? ` · ${formatValue(c.winrate)}` : ''
        lines.push(`- ${agentsStr || c.comp_hash || '?'} (${label('used')}: ${used}${wr})`)
      })
      if (comps.length === 0) lines.push('- Nenhuma composição encontrada.')
    })
    return lines.join('\n')
  }

  if (Array.isArray(r.items)) {
    const lines = []
    r.items.forEach((it) => {
      const name = it.team?.tag ?? it.team?.name ?? it.team ?? '?'
      lines.push(`### ${name}`)
      STAT_KEYS_ORDER.forEach((key) => {
        if (it[key] !== undefined && it[key] !== null) {
          lines.push(formatStatLine(key, it[key]))
        }
      })
    })
    return lines.filter(Boolean).join('\n')
  }

  return ''
}

function pushPistolAtkDefLines(lines, block) {
  const atkWon = block.pistol_atk_won
  const atkPlayed = block.pistol_atk_played
  const defWon = block.pistol_def_won
  const defPlayed = block.pistol_def_played
  if (atkPlayed != null && atkPlayed > 0) {
    const pct = atkWon != null ? Math.round((atkWon / atkPlayed) * 100) : 0
    lines.push(`- **Round pistols no ataque:** ${atkWon ?? 0} ganhos (${atkPlayed} jogados, ${pct}%)`)
  }
  if (defPlayed != null && defPlayed > 0) {
    const pct = defWon != null ? Math.round((defWon / defPlayed) * 100) : 0
    lines.push(`- **Round pistols na defesa:** ${defWon ?? 0} ganhos (${defPlayed} jogados, ${pct}%)`)
  }
}

function teamStatsToMd(data) {
  if (!data?.team) return ''

  const teamName = data.team.tag ?? data.team.name ?? `Time ${data.team.id}`
  const lines = [`## ${teamName}`, '']

  if (data.overall && typeof data.overall.games_played === 'number') {
    lines.push('### Estatísticas gerais')
    STAT_KEYS_ORDER.forEach((key) => {
      if (data.overall[key] !== undefined && data.overall[key] !== null) {
        lines.push(formatStatLine(key, data.overall[key]))
      }
    })
    pushPistolAtkDefLines(lines, data.overall)
    lines.push('')
  }

  const mapStats = data.map_stats ?? []
  mapStats.forEach((m) => {
    lines.push(`### ${m.map_name ?? 'Mapa'}`)
    STAT_KEYS_ORDER.forEach((key) => {
      if (m[key] !== undefined && m[key] !== null) {
        lines.push(formatStatLine(key, m[key]))
      }
    })
    pushPistolAtkDefLines(lines, m)
    const comps = m.likely_compositions ?? []
    if (comps.length > 0) {
      lines.push('**Composições prováveis:**')
      comps.forEach((c) => {
        const agentsStr = Array.isArray(c.agents) ? c.agents.join(', ') : [c.agent1, c.agent2, c.agent3, c.agent4, c.agent5].filter(Boolean).join(', ')
        const used = c.used ?? c.usage_count
        const wr = c.winrate != null ? ` · ${formatValue(c.winrate)}` : ''
        lines.push(`- ${agentsStr || c.comp_hash || '?'} (${label('used')}: ${used}${wr})`)
      })
    }
    lines.push('')
  })

  return lines.join('\n').trim()
}

function h2hToMd(data) {
  if (data == null || typeof data.total_maps !== 'number') return ''

  const lines = [
    '## Head-to-head',
    formatStatLine('total_maps', data.total_maps),
    formatStatLine('a_wins', data.a_wins),
    formatStatLine('b_wins', data.b_wins),
    formatStatLine('ot_count', data.ot_count),
    formatStatLine('ot_rate', data.ot_rate)
  ]
  return lines.filter(Boolean).join('\n')
}

function resultToMarkdown(data) {
  if (data == null) return ''

  if (data.intent !== undefined && data.result !== undefined) {
    return queryResultToMd(data)
  }

  if (data.team != null && data.map_stats) {
    return teamStatsToMd(data)
  }

  if (typeof data.total_maps === 'number') {
    return h2hToMd(data)
  }

  return ''
}

function renderMarkdownLines(md) {
  const lines = md.split('\n')
  return lines.map((line, i) => {
    if (line.startsWith('### ')) {
      return <h3 key={i} className="mt-3 text-sm font-semibold text-ink">{line.slice(4)}</h3>
    }
    if (line.startsWith('## ')) {
      return <h2 key={i} className="mt-4 text-base font-semibold text-ink first:mt-0">{line.slice(3)}</h2>
    }
    if (line.startsWith('- ')) {
      const rest = line.slice(2)
      const parts = []
      let remaining = rest
      while (remaining.includes('**')) {
        const i1 = remaining.indexOf('**')
        const i2 = remaining.indexOf('**', i1 + 2)
        if (i2 === -1) break
        parts.push(remaining.slice(0, i1))
        parts.push(<strong key={parts.length}>{remaining.slice(i1 + 2, i2)}</strong>)
        remaining = remaining.slice(i2 + 2)
      }
      parts.push(remaining)
      return <p key={i} className="ml-2 text-sm text-slate-700">{parts}</p>
    }
    if (line.trim() === '') return <br key={i} />
    return <p key={i} className="text-sm text-slate-700">{line}</p>
  })
}

function StatsResult({ data }) {
  const md = resultToMarkdown(data)

  if (!data) {
    return null
  }

  if (!md) {
    return (
      <section className="panel p-4">
        <h3 className="font-display text-base font-semibold text-ink">Resultado da consulta</h3>
        <p className="mt-2 text-sm text-slate-500">Nenhum resultado para exibir em formato legível.</p>
        <details className="mt-2">
          <summary className="cursor-pointer text-xs text-slate-500">Ver JSON</summary>
          <pre className="mt-1 overflow-auto rounded bg-slate-100 p-2 text-xs">{JSON.stringify(data, null, 2)}</pre>
        </details>
      </section>
    )
  }

  return (
    <section className="panel p-4">
      <h3 className="font-display text-base font-semibold text-ink">Resultado da consulta</h3>
      <div className="mt-3 prose prose-sm max-w-none text-slate-700">
        {renderMarkdownLines(md)}
      </div>
      <details className="mt-3">
        <summary className="cursor-pointer text-xs text-slate-500">Ver JSON</summary>
        <pre className="mt-1 overflow-auto rounded bg-slate-100 p-2 text-xs">{JSON.stringify(data, null, 2)}</pre>
      </details>
    </section>
  )
}

export default StatsResult
