// New-listing form: photo preview + one-tap geolocation.

const fileInput = document.getElementById('image');
const preview = document.getElementById('photo-preview');
const prompt = document.querySelector('.photo-picker-prompt');

if (fileInput) {
  fileInput.addEventListener('change', () => {
    const file = fileInput.files && fileInput.files[0];
    if (!file) return;
    preview.src = URL.createObjectURL(file);
    preview.hidden = false;
    if (prompt) prompt.hidden = true;
  });
}

const locateBtn = document.getElementById('locate-btn');
const status = document.getElementById('locate-status');
const latField = document.getElementById('lat');
const lngField = document.getElementById('lng');

// The map picker. Coordinates are never typed by hand — people do not know their
// latitude — so this is the fallback whenever geolocation is unavailable or refused.
const pickEl = document.getElementById('pick-map');
let marker = null;
let pickMap = null;

function setPoint(lat, lng, recentre) {
  // Full precision goes over the wire; app/geo.fuzz jitters it before storage, so
  // there is nothing gained by rounding here and accuracy to lose.
  latField.value = lat.toFixed(5);
  lngField.value = lng.toFixed(5);
  if (!pickMap) return;
  if (marker) {
    marker.setLatLng([lat, lng]);
  } else {
    marker = L.marker([lat, lng], { draggable: true }).addTo(pickMap);
    marker.on('dragend', () => {
      const p = marker.getLatLng();
      setPoint(p.lat, p.lng, false);
    });
  }
  if (recentre) pickMap.setView([lat, lng], Math.max(pickMap.getZoom(), 13));
}

if (pickEl && typeof L !== 'undefined') {
  const startLat = parseFloat(pickEl.dataset.lat);
  const startLng = parseFloat(pickEl.dataset.lng);
  const hasPoint = !Number.isNaN(startLat) && !Number.isNaN(startLng);

  pickMap = L.map(pickEl).setView(
    hasPoint
      ? [startLat, startLng]
      : [parseFloat(pickEl.dataset.defaultLat), parseFloat(pickEl.dataset.defaultLng)],
    hasPoint ? 13 : parseInt(pickEl.dataset.defaultZoom, 10)
  );

  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 16,
    attribution: '&copy; OpenStreetMap contributors',
    // Without this OSM blocks the tiles — see map.js.
    referrerPolicy: 'strict-origin-when-cross-origin',
  }).addTo(pickMap);

  if (hasPoint) setPoint(startLat, startLng, false);
  pickMap.on('click', (e) => setPoint(e.latlng.lat, e.latlng.lng, false));
}

if (locateBtn && navigator.geolocation) {
  locateBtn.addEventListener('click', () => {
    locateBtn.disabled = true;
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setPoint(position.coords.latitude, position.coords.longitude, true);
        status.textContent = locateBtn.dataset.okLabel || '✓';
        locateBtn.disabled = false;
      },
      () => {
        // Refused or unavailable: the map below is already the way out, so say so
        // rather than leaving a bare dash.
        status.textContent = locateBtn.dataset.failLabel || '';
        locateBtn.disabled = false;
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 600000 }
    );
  });
} else if (locateBtn) {
  locateBtn.hidden = true;
}
