import type { DataLabel } from '../lib/types'

const descriptions: Record<DataLabel, string> = {
  synthetic: 'test case constructed for evaluation',
  illustrative: 'hand-built boundary, not an official registry boundary',
  real: 'boundary from a published dataset — see provenance',
}

export function LabelBadge({ label, detailed = false }: { label: DataLabel; detailed?: boolean }) {
  return (
    <span className={`label-badge label-${label}`} title={descriptions[label]}>
      <strong>{label.toUpperCase()}</strong>
      {detailed && <span>{descriptions[label]}</span>}
    </span>
  )
}
