import { formatNumber } from '../lib/format'

export function MetricChart({
  values,
  highlightYear,
  unit,
  color = 'var(--accent)',
  title,
}: {
  values: Record<string, number>
  highlightYear?: number
  unit: string
  color?: string
  title: string
}) {
  const entries = Object.entries(values).sort(([a], [b]) => Number(a) - Number(b))
  if (entries.length === 0) return <p className="muted">No yearly values available.</p>
  const width = Math.max(540, entries.length * 29)
  const height = 190
  const left = 44
  const bottom = 34
  const top = 12
  const plotHeight = height - bottom - top
  const max = Math.max(...entries.map(([, value]) => value), 0.0001)
  const barWidth = Math.max(5, (width - left - 8) / entries.length - 4)

  return (
    <div className="chart-wrap">
      <svg className="metric-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={title}>
        <title>{title}</title>
        <line x1={left} y1={top + plotHeight} x2={width - 2} y2={top + plotHeight} className="chart-axis" />
        <text x="2" y={top + 8} className="chart-label">{formatNumber(max, 3)}</text>
        <text x="2" y={top + plotHeight} className="chart-label">0 {unit}</text>
        {entries.map(([year, value], index) => {
          const barHeight = (value / max) * plotHeight
          const x = left + index * ((width - left) / entries.length) + 2
          const highlighted = Number(year) === highlightYear
          return (
            <g key={year}>
              <rect
                x={x}
                y={top + plotHeight - barHeight}
                width={barWidth}
                height={barHeight}
                rx="2"
                fill={highlighted ? 'var(--warning)' : color}
                opacity={highlighted ? 1 : 0.76}
              >
                <title>{year}: {formatNumber(value, 3)} {unit}</title>
              </rect>
              {(highlighted || index % Math.ceil(entries.length / 8) === 0) && (
                <text x={x + barWidth / 2} y={height - 12} textAnchor="middle" className={highlighted ? 'chart-year chart-year-highlight' : 'chart-year'}>{year}</text>
              )}
            </g>
          )
        })}
      </svg>
    </div>
  )
}
