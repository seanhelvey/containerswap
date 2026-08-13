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

// PWA: offline access to listings already visited.
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {
      /* offline support is a bonus, never a requirement */
    });
  });
}
