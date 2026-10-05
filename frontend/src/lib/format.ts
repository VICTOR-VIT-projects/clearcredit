export function formatNumber(value: number, maximumFractionDigits = 2): string {
  return new Intl.NumberFormat(undefined, { maximumFractionDigits }).format(value)
}

export function shorten(value: string, start = 8, end = 6): string {
  if (value.length <= start + end + 1) return value
  return `${value.slice(0, start)}…${value.slice(-end)}`
}

export function formatDate(value: string | number): string {
  const date = typeof value === 'number' ? new Date(value * 1000) : new Date(value)
  return Number.isNaN(date.valueOf()) ? 'Unknown time' : date.toLocaleString()
}

export function percent(value: number): string {
  return new Intl.NumberFormat(undefined, { style: 'percent', maximumFractionDigits: 1 }).format(value)
}

export async function copyText(value: string): Promise<void> {
  await navigator.clipboard.writeText(value)
}

/** "avoided_deforestation" -> "Avoided deforestation" (sentence case; CSS capitalize would mangle units). */
export function humanize(value: string): string {
  const text = value.replaceAll('_', ' ')
  return text.charAt(0).toUpperCase() + text.slice(1)
}
