# Security Policy

## Reporting a vulnerability

Please **do not open a public issue** for a security problem.

Use GitHub's private reporting: **Security → Report a vulnerability** on this
repository. That opens a private thread visible only to maintainers.

Include what you did, what happened, and what you expected. A proof of concept helps
but is not required. We aim to acknowledge within 72 hours.

We will not pursue legal action against anyone acting in good faith who reports a
problem privately and does not access, modify, or retain other people's data while
investigating.

## What this project promises its users

These are the guarantees a vulnerability report should measure us against:

1. **No contact details are stored or published.** There is no email, phone, or
   address column anywhere in the schema. Any code path that would collect one is a
   bug, not a feature request.
2. **Exact locations are never persisted.** Coordinates are jittered before being
   written (`app/geo.py`). A report showing precise coordinates recoverable from the
   database, the API, or the logs is a high-severity issue.
3. **Uploads carry no metadata.** Images are re-encoded from raw pixels to strip EXIF
   GPS (`app/images.py`). A path that stores an original file unaltered is a
   high-severity issue.
4. **Messages are private to their recipient.** `/inbox` only ever returns rows where
   `recipient_id` is the session user. Any read path that widens this is critical.

## Deployment checklist

An instance is not safe to invite users to until all of these are true:

- [ ] `CS_SECRET_KEY` is set to a random 48-byte value. The default is a known string;
      leaving it means anyone can forge a session cookie for any account.
- [ ] `CS_DEBUG=false` — this is what makes session cookies `Secure` and hides
      tracebacks and the OpenAPI schema.
- [ ] The site is served over HTTPS only (FastAPI Cloud does this by default).
- [ ] `CS_DATA_DIR` is on a persistent volume that is backed up.
- [ ] Reports at `/listings/{id}/report` are actually being read by a human.

## Current known limitations

Stated plainly rather than left for someone to discover:

- **Rate limiting is per-process and in memory** (`app/ratelimit.py`). It blunts
  casual abuse from a single IP; it does not survive a restart and does not
  coordinate across replicas. Scaling past one worker needs shared storage.
- **There is no moderation queue.** Reports are written to a table that a maintainer
  has to query by hand.
- **There is no account recovery.** No email means no password reset — a forgotten
  password is a lost account. This is the deliberate cost of collecting nothing.
- **Comments and messages are not filtered** for abuse beyond length caps.
