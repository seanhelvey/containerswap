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

  const resultsEl = document.getElementById('map-results');
  let allFeatures = [];

  // The list mirrors whatever's actually framed on screen, not the full result
  // set — pan or zoom and it updates, same as the pins you can see moving into
  // and out of view. All client-side: the data's already loaded, and at this
  // project's scale (a few hundred listings, capped well below that) filtering
  // in the browser is plenty — no separate "search this area" round trip needed.
  function updateResultsList() {
    if (!resultsEl) return;
    const bounds = map.getBounds();
    const inView = allFeatures.filter((feature) => {
      const [lng, lat] = feature.geometry.coordinates;
      return bounds.contains([lat, lng]);
    });
    renderResultsList(inView);
  }

  fetch(`/api/listings.geojson?${params}`)
    .then((r) => r.json())
    .then((data) => {
      allFeatures = data.features;
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
      updateResultsList();
    })
    .catch(() => {});

  map.on('moveend', updateResultsList);

  function escapeHtml(value) {
    return String(value || '').replace(/[&<>"']/g, (c) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    })[c]);
  }

  // The same cards the home grid uses, so the map doesn't feel disconnected from
  // its own data — every pin above is also a card here, and vice versa.
  function renderResultsList(features) {
    resultsEl.innerHTML = features
      .map((feature) => {
        const p = feature.properties;
        const media = p.image
          ? `<img src="${p.image}" alt="${escapeHtml(p.title)}" loading="lazy" decoding="async" width="400" height="300">`
          : `<div class="card-media-empty" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M7 2h10l1 3v15a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V5zm1 5v13h8V7z"/></svg></div>`;
        const badge = p.is_seed
          ? `<span class="badge badge-seed">${escapeHtml(el.dataset.demoLabel)}</span>`
          : '';
        const price = p.price ? `<span class="pill pill-price">${escapeHtml(p.price)}</span>` : '';
        const quantity = p.quantity ? `<span class="pill">${escapeHtml(p.quantity)}</span>` : '';
        return (
          `<a class="card" href="${p.url}">` +
            `<div class="card-media">${media}${badge}</div>` +
            `<div class="card-body">` +
              `<h2 class="card-title">${escapeHtml(p.title)}</h2>` +
              `<p class="card-meta">${price}${quantity}</p>` +
            `</div>` +
          `</a>`
        );
      })
      .join('');
  }
})();
