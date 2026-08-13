# ContainerSwap — working notes

Peer-to-peer swapping of used food containers. Server-rendered FastAPI + Jinja2, no
frontend build step. Public repo, so assume anything committed is world-readable.

## Commands

```bash
uv sync                    # install
uv run fastapi dev         # local server on :8000
uv run pytest -q           # tests
uv run ruff check . --fix && uv run ruff format .   # lint + format (CI checks both)
```

Delete `data/` if the schema changed under you — SQLite dev DBs go stale.

## Deployment

**Pushing to `main` deploys to production.** FastAPI Cloud's GitHub integration builds
and ships the default branch automatically. There is no staging. CI runs tests on
push but does not gate the deploy, so a red build still ships — check tests locally
before pushing to main.

Env vars live in the FastAPI Cloud dashboard (App → Environment Variables). Secrets
must be marked Secret **at creation**; the toggle is not available afterwards.

## Platform constraints that shape the code

- **No persistent volumes.** SQLite on local disk and `data/uploads` are both wrong
  in production and will be lost on redeploy. Migrating to Neon or Supabase Postgres
  plus object storage is the top open task.
- **Zero-downtime deploys run old and new instances at once.** Nothing may assume a
  single process: the in-memory rate limiter in `app/ratelimit.py` under-counts, and
  additive-only migrations are the only safe kind (see `db._add_missing_columns`).

## Non-negotiables

These are promises made to users in `SECURITY.md`. Treat a change that breaks one as
a bug, not a tradeoff:

1. **A user's email is never rendered.** Not in a page, an API response, or a log.
   The public label is `display_name`. `tests/test_privacy.py` enforces this.
2. **Exact coordinates are never stored.** `app/geo.fuzz` jitters before write; the
   browser's precise value is dropped.
3. **Uploads are re-encoded from raw pixels** so EXIF GPS cannot survive.
4. **`/inbox` only returns rows where `recipient_id` is the session user.**

## Conventions

- Every user-facing string goes through `t()` against `locales/en.json`. No English
  in templates. v1 ships English only; that is not a reason to hardcode.
- Dates render client-side in the visitor's locale from ISO-8601. Never format a date
  server-side, and never assume USD or US date order.
- Prices are free text (`$5`, `500 KSh`, `free`, `trade for basil starts`). Do not
  add a structured currency field.
- Every state-changing POST takes `Depends(verify_csrf)` and includes the hidden
  `csrf_token` input in its form.
- Simplest working implementation wins. Do not add an abstraction for a second
  backend that does not exist yet.

## Style

Comments explain *why*, especially for the privacy and platform decisions above —
those look like over-engineering until you know the reason. Skip comments that
restate the code.
