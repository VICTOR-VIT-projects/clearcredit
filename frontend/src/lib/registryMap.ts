import type { FeatureCollection } from 'geojson'
import type { RegistryItem } from './types'

export const bandColors = { high: '#166534', medium: '#966000', low: '#b91c1c' }

export function registryFeatures(items: RegistryItem[]): FeatureCollection {
  return { type: 'FeatureCollection', features: items.filter(item => item.status === 'registered' && item.boundary).map(item => ({
    type: 'Feature', geometry: item.boundary!, properties: {
      projectId: item.projectId, dataLabel: item.dataLabel, score: item.score,
      color: bandColors[item.band], label: `${item.projectId} · ${item.dataLabel.toUpperCase()} · ${item.score}/100`,
    },
  })) }
}
