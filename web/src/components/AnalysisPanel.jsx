function pct(value) {
  return `${(Number(value || 0) * 100).toFixed(1)}%`
}

function AnalysisPanel({ analysis }) {
  const edges = analysis?.single_edges || []

  return (
    <section className="panel p-4">
      <h3 className="font-display text-base font-semibold text-ink">Tabela de edges</h3>
      <div className="mt-3 overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-xs uppercase text-slate-500">
              <th className="py-2 pr-2">Mercado</th>
              <th className="py-2 pr-2">Seleção</th>
              <th className="py-2 pr-2">Casa</th>
              <th className="py-2 pr-2">Odd</th>
              <th className="py-2 pr-2">Prob. implícita</th>
              <th className="py-2 pr-2">Prob. modelo</th>
              <th className="py-2 pr-2">Edge</th>
              <th className="py-2 pr-2">Recomendação</th>
              <th className="py-2 pr-2">Valor sug.</th>
            </tr>
          </thead>
          <tbody>
            {edges.map((edge, idx) => (
              <tr key={`${edge.market}-${edge.selection}-${idx}`} className="border-b border-slate-100">
                <td className="py-2 pr-2">{edge.market}{edge.map_number ? ` M${edge.map_number}` : ''}</td>
                <td className="py-2 pr-2">{edge.selection}</td>
                <td className="py-2 pr-2">{edge.bookmaker}</td>
                <td className="py-2 pr-2">{Number(edge.odds).toFixed(2)}</td>
                <td className="py-2 pr-2">{pct(edge.p_impl)}</td>
                <td className="py-2 pr-2">{pct(edge.p_model)}</td>
                <td className={`py-2 pr-2 font-semibold ${edge.edge > 0 ? 'text-emerald-700' : 'text-slate-500'}`}>{pct(edge.edge)}</td>
                <td className="py-2 pr-2">{edge.recommendation}</td>
                <td className="py-2 pr-2">R${Number(edge.suggested_stake || 0).toFixed(2)}</td>
              </tr>
            ))}
            {!edges.length ? (
              <tr>
                <td className="py-3 text-slate-500" colSpan={9}>Sem odds suficientes para calcular edges.</td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  )
}

export default AnalysisPanel
