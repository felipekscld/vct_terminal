import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { formatBoType, inferSeriesFormatFromScoreProbs, seriesChartData } from '../utils/formatBo'

function SeriesProbs({ scoreProbs, boType }) {
  const format = boType != null && boType !== '' ? formatBoType(boType) : inferSeriesFormatFromScoreProbs(scoreProbs)
  const data = seriesChartData(scoreProbs, format)
  const formatLabel = format === 'Bo5' ? 'Bo5' : 'Bo3'

  return (
    <section className="panel p-4">
      <h3 className="font-display text-base font-semibold text-ink">Probabilidades da série</h3>
      <p className="mt-0.5 text-xs text-slate-500">Formato: {formatLabel} — placar (time A – time B). Baseado em estatísticas passadas dos dois times (e confronto direto quando houver).</p>
      <div className="mt-3 h-56 w-full">
        {data.length ? (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data}>
              <CartesianGrid strokeDasharray="3 3" stroke="#d8e1ea" />
              <XAxis dataKey="score" />
              <YAxis unit="%" />
              <Tooltip formatter={(value) => `${value}%`} />
              <Bar dataKey="probability" fill="#0f6adf" radius={[8, 8, 2, 2]} />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-slate-500">Sem distribuição de placar para exibir.</div>
        )}
      </div>
    </section>
  )
}

export default SeriesProbs
