import { useEffect, useMemo } from 'react'
import { GeoJSON, MapContainer, TileLayer, useMap } from 'react-leaflet'
import L from 'leaflet'
import { TILE_ATTRIBUTION, TILE_URL } from '../lib/tiles'
import type { FeatureCollection } from 'geojson'
import type { RegistryItem } from '../lib/types'
import { registryFeatures } from '../lib/registryMap'

function FitAll({ data }: { data: FeatureCollection }) {
  const map = useMap()
  useEffect(() => {
    const bounds = L.geoJSON(data).getBounds()
    if (bounds.isValid()) map.fitBounds(bounds, { padding: [24, 24], maxZoom: 12 })
  }, [data, map])
  return null
}

export function RegistryMap({ items, observedBlock }: { items: RegistryItem[]; observedBlock: number | null }) {
  const data = useMemo(() => registryFeatures(items), [items])
  return <section className="card">
    <h2>Registered boundaries known to this API</h2>
    <p>Snapshot block: {observedBlock ?? 'No chain configured'}</p>
    <p>{data.features.length} registered claims. Green: high integrity score; amber: medium; red: low. Each label includes its data category.</p>
    <div className="map-frame">
      <MapContainer center={[15, 0]} zoom={2} scrollWheelZoom className="leaflet-map">
        <TileLayer attribution={TILE_ATTRIBUTION} url={TILE_URL} />
        <GeoJSON data={data} style={feature => ({ color: String(feature?.properties?.color), weight: 2, fillOpacity: 0.25 })} onEachFeature={(feature, layer) => {
          const text = document.createElement('span')
          text.textContent = String(feature.properties?.label)
          layer.bindTooltip(text, { sticky: true })  // on hover: 30 permanent labels overlap into an unreadable pile
        }} />
        <FitAll data={data} />
      </MapContainer>
    </div>
    <p className="fine-print">Boundaries and labels are submitted off-chain data. Shared cell uniqueness applies only to participating registries; use the verifier to check each claim hash.</p>
  </section>
}
