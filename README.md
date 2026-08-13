# ContainerSwap

**Jars, tubs and containers looking for a second life.**

A peer-to-peer marketplace for swapping used food containers — glass jars, deli tubs,
yogurt pots — that would otherwise go in the bin. Mobile-first, low-bandwidth,
installable, and built to work as well on a cheap phone in Nairobi as on a laptop in
Arcata.

Server-rendered FastAPI + Jinja2 + SQLite. No frontend build step, no bundler, no
node_modules. About 40 KB of hand-written CSS and JS on the wire.

---

## Design commitments

These are the decisions worth defending, not implementation trivia:

**Nobody's contact details are ever published.** There is no email column in the
database at all — signup is username and password only, so there is nothing to leak
even under a full database compromise. Buyers reach sellers through a contact form
that writes to a `messages` table, readable only by the recipient at `/inbox`.

**A pin is a neighbourhood, not a doorstep.** Coordinates are jittered by up to
400 m before they are written, and the precise value the browser reported is never
stored or logged. Listing pages draw a 500 m circle rather than a point, so the
approximation is visible rather than implied.

**Photos are stripped and shrunk.** Every upload is decoded and re-encoded from raw
pixels, which drops EXIF — including the GPS tags a phone camera embeds by default —
and caps the result at ~300 KB and 1280 px.

**Price is free text.** `$5`, `500 KSh`, `free`, `trade for basil starts` are all
valid. A structured currency field would quietly exclude barter and most of the world.

**Nothing is hardcoded English.** Every visible string goes through `t()` against
`locales/en.json`. Adding a language is one JSON file — no template changes. Dates
render in the visitor's own locale and timezone, client-side, from ISO-8601.

**Local and global are the same code.** `CS_HOME_REGION` adds regional framing to the
tagline ("in Humboldt County and beyond"); leaving it empty gives the global framing.
One deployment can be grassroots without the codebase being parochial.

---

## Run it locally

```bash
uv sync
cp .env.example .env
uv run fastapi dev
```

Open http://127.0.0.1:8000. Tests: `uv run pytest`. Lint: `uv run ruff check .`

## Deploy

```bash
uv run fastapi login    # once
uv run fastapi deploy
```

Then, in the FastAPI Cloud dashboard, set these environment variables:

| Variable | Value |
| --- | --- |
| `CS_SECRET_KEY` | `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `CS_DEBUG` | `false` |
| `CS_DATA_DIR` | a path on a persistent volume (see below) |
| `CS_HOME_REGION` | e.g. `Humboldt County`, or leave empty |

### ⚠️ Persistence

SQLite and uploaded images both live under `CS_DATA_DIR`. If that path is on an
ephemeral container filesystem, **every redeploy wipes all listings and photos.**
Point it at a persistent volume before inviting real users. Migrating later means
Postgres for the database and object storage for images; `app/db.py` and
`app/images.py` are the only two files that would change.

## Layout

```
main.py              app wiring, security headers, PWA routes
app/config.py        settings (all CS_-prefixed env vars)
app/models.py        users, listings, messages, comments, reports, event_log
app/auth.py          argon2 + signed-cookie sessions + CSRF
app/geo.py           coordinate fuzzing
app/images.py        upload validation, EXIF stripping, compression
app/i18n.py          translation lookup
app/routes/          account.py, listings.py
templates/           Jinja2, mobile-first
static/              css, js, vendored Leaflet, icons
locales/en.json      every user-facing string
```

## Analytics

The whole analytics layer is the `event_log` table: `listing_created`,
`listing_viewed`, `contact_sent`, `listing_completed`. No dashboard, no third-party
tracker, no IP or user-agent stored. Query it directly:

```sql
SELECT event_type, date(created_at) AS day, count(*)
FROM event_log GROUP BY 1, 2 ORDER BY 2 DESC;
```

## Contributing & security

Bug reports and PRs welcome. Please read [SECURITY.md](SECURITY.md) before reporting a
vulnerability — do not open a public issue for one.

MIT licensed. See [LICENSE](LICENSE).
