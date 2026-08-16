// Map view. Leaflet + OpenStreetMap tiles, no API key, no third-party JS host.

(function initMap() {
  const el = document.getElementById('map');
  if (!el || typeof L === 'undefined') return;

  el.innerHTML = '';
  const map = L.map(el).setView(
    [parseFloat(el.dataset.lat), parseFloat(el.dataset.lng)],
    parseInt(el.dataset.zoom, 10)
  );

  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 18,
    attribution: '&copy; OpenStreetMap contributors',
  }).addTo(map);

  const params = new URLSearchParams();
  if (el.dataset.q) params.set('q', el.dataset.q);
  el.dataset.tags.split(',').filter(Boolean).forEach((tag) => params.append('tags', tag));
  if (el.dataset.nearLat) params.set('lat', el.dataset.nearLat);
  if (el.dataset.nearLng) params.set('lng', el.dataset.nearLng);

  fetch(`/api/listings.geojson?${params}`)
    .then((r) => r.json())
    .then((data) => {
      const markers = [];
      data.features.forEach((feature) => {
        const [lng, lat] = feature.geometry.coordinates;
        const p = feature.properties;
        // Demo listings get a visibly different pin — a hollow dashed circle
        // instead of the solid marker — so the map never shows planted activity
        // as indistinguishable from real activity. See listing_detail's own
        // "Demo" pill for the same distinction on a single listing.
        const marker = p.is_seed
          ? L.circleMarker([lat, lng], {
              radius: 8,
              color: '#8a9490',
              weight: 2,
              dashArray: '3,3',
              fillColor: '#8a9490',
              fillOpacity: 0.35,
            })
          : L.marker([lat, lng]);
        marker.addTo(map);
        marker.bindPopup(
          `<a href="${p.url}"><strong>${escapeHtml(p.title)}</strong></a>` +
            (p.is_seed ? ` <em>(${escapeHtml(el.dataset.demoLabel)})</em>` : '') +
            (p.price ? `<br>${escapeHtml(p.price)}` : '') +
            (p.quantity ? `<br>${escapeHtml(p.quantity)}` : '')
        );
        markers.push(marker);
      });
      // "Near me" already centred the view server-side (data-lat/data-lng, read
      // above) — fitting bounds to every pin here would immediately zoom back out
      // and undo that, so it only runs for the unfiltered/default view.
      if (markers.length && el.dataset.nearMe !== 'true') {
        map.fitBounds(L.featureGroup(markers).getBounds().pad(0.2));
      }
    })
    .catch(() => {});

  function escapeHtml(value) {
    return String(value || '').replace(/[&<>"']/g, (c) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    })[c]);
  }
})();
