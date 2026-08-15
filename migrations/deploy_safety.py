"""Whether pre-push should let a push land ahead of a migration.

Normally the schema must already be at the repo's migration head before a push,
because migrations are additive: old instances keep serving through a zero-downtime
rollover, and an additive change doesn't break them. A destructive migration is the
opposite — it must apply *after* the code that stops touching what it removes is
live, or it breaks whichever old instances are still serving. A migration marks
itself `post_deploy = True` to say it's one of those.

This is only safe to push ahead of if EVERY migration production is missing is
marked that way. If even one ordinary migration is mixed in, production still
needs it before the new code can boot against the schema — so this must still fail.
"""

import sys

from alembic.config import Config
from alembic.script import ScriptDirectory


def pending_are_all_post_deploy(prod_rev: str | None) -> bool:
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    head = script.get_current_head()
    if prod_rev == head:
        return True
    pending = list(script.iterate_revisions(head, prod_rev))
    return bool(pending) and all(
        getattr(script.get_revision(rev.revision).module, "post_deploy", False) for rev in pending
    )


if __name__ == "__main__":
    prod_rev = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else None
    sys.exit(0 if pending_are_all_post_deploy(prod_rev) else 1)
