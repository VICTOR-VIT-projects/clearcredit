import { expect, it } from 'vitest'
import { bandColors, registryFeatures } from './registryMap'
import type { RegistryItem } from './types'

it('keeps project labels and score colors on registered boundary features', () => {
  const item: RegistryItem = { projectId: 'DEMO', claimHash: `0x${'11'.repeat(32)}`, dataLabel: 'synthetic',
    projectType: 'avoided_deforestation', vintageYear: 2023, claimedCredits: 100, areaHa: 2, sourceRegistry: null,
    score: 50, band: 'medium', status: 'registered',
    boundary: { type: 'Polygon', coordinates: [[[0, 0], [1, 0], [1, 1], [0, 0]]] } }
  const data = registryFeatures([item, { ...item, status: 'pending' }])
  expect(data.features).toHaveLength(1)
  expect(data.features[0].properties).toMatchObject({ dataLabel: 'synthetic', color: bandColors.medium, label: 'DEMO · SYNTHETIC · 50/100' })
})
