// Site-wide behaviour. Kept tiny on purpose — every page works without it.

// Dates are rendered by the browser in the visitor's own locale and timezone, so
// nothing here hardcodes a US format. The server only ever emits ISO-8601.
(function localizeDates() {
  const now = Date.now();
  document.querySelectorAll('time[datetime]').forEach((el) => {
    const stamp = new Date(el.getAttribute('datetime'));
    if (Number.isNaN(stamp.getTime())) return;

    const seconds = Math.round((stamp.getTime() - now) / 1000);
    const abs = Math.abs(seconds);

    if (typeof Intl.RelativeTimeFormat === 'function' && abs < 604800) {
      const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' });
      const [unit, size] =
        abs < 60 ? ['second', 1] : abs < 3600 ? ['minute', 60] : abs < 86400 ? ['hour', 3600] : ['day', 86400];
      el.textContent = rtf.format(Math.round(seconds / size), unit);
    } else {
      el.textContent = stamp.toLocaleDateString(undefined, {
        year: 'numeric', month: 'short', day: 'numeric',
      });
    }
    el.title = stamp.toLocaleString();
  });
})();

// Confirm before a destructive submit. Reads the prompt from a data attribute
// rather than a translated string interpolated into inline JS, so a future
// locale's apostrophe or quote can't break the script.
document.querySelectorAll('form[data-confirm]').forEach((form) => {
  form.addEventListener('submit', (event) => {
    if (!window.confirm(form.dataset.confirm)) event.preventDefault();
  });
});

// Filter chips submit themselves on change instead of needing a separate "Apply"
// button. A data attribute, not an inline onchange: the CSP's script-src 'self'
// blocks inline event handlers same as it would inline <script> content.
document.querySelectorAll('form[data-autosubmit] input').forEach((field) => {
  field.addEventListener('change', () => field.form.submit());
});

// "Near me" (search bar, shared between the home grid and the map): fills the
// form's hidden lat/lng and resubmits — a normal page load, sorted server-side,
// same as any other filter. Already active: clear instead of re-locating, so
// there is always a plain way back to newest-first.
document.querySelectorAll('[data-near-me]').forEach((btn) => {
  const form = btn.closest('form');
  const latField = form.querySelector('input[name="lat"]');
  const lngField = form.querySelector('input[name="lng"]');

  btn.addEventListener('click', () => {
    if (btn.dataset.active === 'true') {
      latField.value = '';
      lngField.value = '';
      form.submit();
      return;
    }
    if (!navigator.geolocation) return;
    btn.disabled = true;
    navigator.geolocation.getCurrentPosition(
      (position) => {
        latField.value = position.coords.latitude;
        lngField.value = position.coords.longitude;
        form.submit();
      },
      () => { btn.disabled = false; },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 600000 }
    );
  });
});
