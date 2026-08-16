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

  fetch('/api/listings.geojson')
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
      if (markers.length) {
        map.fitBounds(L.featureGroup(markers).getBounds().pad(0.2));
      }
    })
    .catch(() => {});

  if (navigator.geolocation) {
    const control = L.control({ position: 'topright' });
    control.onAdd = function () {
      const div = L.DomUtil.create('div', 'leaflet-bar');
      const link = L.DomUtil.create('a', '', div);
      link.href = '#';
      link.title = el.dataset.locateLabel;
      link.textContent = '◎';
      link.style.fontSize = '20px';
      L.DomEvent.on(link, 'click', (event) => {
        L.DomEvent.stop(event);
        navigator.geolocation.getCurrentPosition((position) => {
          map.setView([position.coords.latitude, position.coords.longitude], 13);
        });
      });
      return div;
    };
    control.addTo(map);
  }

  function escapeHtml(value) {
    return String(value || '').replace(/[&<>"']/g, (c) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    })[c]);
  }
})();
