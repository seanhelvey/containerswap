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

if (locateBtn && navigator.geolocation) {
  locateBtn.addEventListener('click', () => {
    locateBtn.disabled = true;
    navigator.geolocation.getCurrentPosition(
      (position) => {
        // Sent at full precision, then jittered server-side before storage.
        latField.value = position.coords.latitude.toFixed(5);
        lngField.value = position.coords.longitude.toFixed(5);
        status.textContent = locateBtn.dataset.okLabel || '✓';
        locateBtn.disabled = false;
      },
      () => {
        status.textContent = '—';
        locateBtn.disabled = false;
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 600000 }
    );
  });
} else if (locateBtn) {
  locateBtn.hidden = true;
}
