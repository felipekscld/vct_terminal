function MultiBetPanel({ items }) {
  return (
    <section className="panel p-4">
      <h3 className="font-display text-base font-semibold">Multi-Bets</h3>
      <div className="mt-3 grid gap-2">
        {(items || []).map((item, idx) => (
          <article key={`${item.strategy}-${idx}`} className="rounded-lg border border-slate-200 bg-white p-3">
            <p className="text-sm font-semibold text-slate-800">{item.strategy.toUpperCase()} · {item.description}</p>
            <p className="mt-1 text-xs text-slate-700">
              Edge: {(Number(item.edge || 0) * 100).toFixed(1)}% · EV: R${Number(item.ev || 0).toFixed(2)}
            </p>
          </article>
        ))}

        {!(items || []).length ? (
          <p className="text-sm text-slate-500">Nenhuma oportunidade multi-bet neste momento.</p>
        ) : null}
      </div>
    </section>
  )
}

export default MultiBetPanel
