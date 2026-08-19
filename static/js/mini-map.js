// Small non-interactive map on a listing page. The circle communicates that the
// location is approximate — the pin is deliberately not the real address.

(function initMiniMap() {
  const el = document.getElementById('mini-map');
  if (!el || typeof L === 'undefined') return;

  const lat = parseFloat(el.dataset.lat);
  const lng = parseFloat(el.dataset.lng);
  if (Number.isNaN(lat) || Number.isNaN(lng)) return;

  const map = L.map(el, {
    zoomControl: false,
    dragging: false,
    scrollWheelZoom: false,
    doubleClickZoom: false,
    touchZoom: false,
    keyboard: false,
  }).setView([lat, lng], 13);

  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 16,
    attribution: '&copy; OpenStreetMap contributors',
    // Without this OSM blocks the tiles — see map.js.
    referrerPolicy: 'strict-origin-when-cross-origin',
  }).addTo(map);

  L.circle([lat, lng], {
    radius: 500,
    color: '#1b5e3f',
    fillColor: '#1b5e3f',
    fillOpacity: 0.18,
    weight: 2,
  }).addTo(map);
})();
