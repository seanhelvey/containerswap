from sqlalchemy.orm import Session

from app.models import EventLog

LISTING_CREATED = "listing_created"
LISTING_VIEWED = "listing_viewed"
CONTACT_SENT = "contact_sent"
LISTING_COMPLETED = "listing_completed"


def log_event(
    db: Session,
    event_type: str,
    *,
    listing_id: int | None = None,
    user_id: int | None = None,
    commit: bool = True,
) -> None:
    """Append one analytics row. Deliberately stores no IP or user agent."""
    db.add(EventLog(event_type=event_type, listing_id=listing_id, user_id=user_id))
    if commit:
        db.commit()
