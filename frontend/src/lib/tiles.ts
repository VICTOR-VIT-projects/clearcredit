// Dark basemap built from OpenStreetMap data, served by CARTO for map apps (attribution required).
// Natively dark, so no CSS colour inversion is needed. Keep in sync with img-src in deploy/web/nginx.conf.
export const TILE_URL = 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png'
export const TILE_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
