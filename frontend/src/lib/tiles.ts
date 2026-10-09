// OpenStreetMap standard tiles, darkened in CSS (.leaflet-tile-pane) to sit on the black UI.
// OSM's tile policy requires a Referer naming the site: requests without one get an "Access blocked"
// tile, so the server must not send `Referrer-Policy: no-referrer` (deploy/web/nginx.conf uses
// strict-origin-when-cross-origin). Keep the host in sync with img-src in that file's CSP.
export const TILE_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
export const TILE_ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
