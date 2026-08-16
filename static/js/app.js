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
