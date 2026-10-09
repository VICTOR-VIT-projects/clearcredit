import { useEffect, useMemo } from 'react'
import { GeoJSON, MapContainer, TileLayer, useMap } from 'react-leaflet'
import type { GeoJsonObject } from 'geojson'
import L from 'leaflet'
import { TILE_ATTRIBUTION, TILE_URL } from '../lib/tiles'
import type { Boundary } from '../lib/canonical'

function FitBoundary({ boundary }: { boundary: Boundary }) {
  const map = useMap()
  useEffect(() => {
    const layer = L.geoJSON(boundary as GeoJsonObject)
    const bounds = layer.getBounds()
    if (bounds.isValid()) map.fitBounds(bounds, { padding: [28, 28], maxZoom: 13 })
  }, [boundary, map])
  return null
}

export function BoundaryMap({ boundary, compact = false }: { boundary: Boundary; compact?: boolean }) {
  const data = useMemo(() => boundary as GeoJsonObject, [boundary])
  return (
    <div className={`map-frame ${compact ? 'map-compact' : ''}`}>
      <MapContainer center={[15, 0]} zoom={2} scrollWheelZoom className="leaflet-map">
        <TileLayer attribution={TILE_ATTRIBUTION} url={TILE_URL} />
        <GeoJSON data={data} style={{ color: '#c8ff00', weight: 2, fillColor: '#c8ff00', fillOpacity: 0.12 }} />
        <FitBoundary boundary={boundary} />
      </MapContainer>
    </div>
  )
}
