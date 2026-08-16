from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    """Email is the identity. `display_name` is the public label.

    Two separate jobs that a username was doing badly at once. Email logs you in,
    receives notifications, and recovers the account — and is never rendered
    anywhere. `display_name` is what strangers see next to a listing; it is
    generated at signup so nobody has to invent one, and can be changed later.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # PRIVATE. Never put this in a template, an API response, or a log line.
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    # PUBLIC. Shown on listings.
    display_name: Mapped[str] = mapped_column(String(32), index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    email_verified: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    # Bumped on password reset. A session's own copy of this must match, or it is
    # treated as signed out — see app.auth.issue_session / get_current_user.
    session_version: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    listings: Mapped[list["Listing"]] = relationship(back_populates="owner")


class Listing(Base):
    __tablename__ = "listings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(Text, default="")
    # Free text on purpose: "12 assorted", "a big box", "~30".
    quantity: Mapped[str] = mapped_column(String(60), default="")
    # Free text on purpose: "$5", "500 KSh", "free", "trade for basil starts".
    # A structured currency field would exclude barter and most of the world.
    price: Mapped[str] = mapped_column(String(60), default="")
    image_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Jittered before storage — see app.geo.fuzz. The exact location is never persisted.
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    # A planted listing that shows what an active marketplace looks like before one
    # exists. Never presented as real: the detail page swaps the contact form for a
    # disclosure, and this must stay excluded from any future impact counts.
    is_seed: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )

    owner: Mapped[User] = relationship(back_populates="listings")
    # Genuinely multi-valued and, for now, a single flat vocabulary — a bundled lot
    # can honestly be both jars and bottles, and "upcycled" lives in the same list
    # as the shape tags rather than its own column. Tags may eventually want a
    # kind/flavor split (shape vs. state) if that distinction proves worth encoding,
    # but that's undecided, so this doesn't build for it yet.
    tags: Mapped[list["ListingTag"]] = relationship(
        back_populates="listing", cascade="all, delete-orphan"
    )

    @property
    def is_active(self) -> bool:
        return self.status == "active"

    @property
    def tag_slugs(self) -> list[str]:
        return [t.tag for t in self.tags]


class ListingTag(Base):
    """One row per (listing, tag). A plain fixed vocabulary validated against
    app.templating.TAGS, not a user-defined tag system — same spirit as the single
    `category` column this replaces, just no longer mutually exclusive."""

    __tablename__ = "listing_tags"

    listing_id: Mapped[int] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE"), primary_key=True
    )
    tag: Mapped[str] = mapped_column(String(40), primary_key=True, index=True)

    listing: Mapped[Listing] = relationship(back_populates="tags")


class Message(Base):
    """A contact-form message. This table is the ONLY channel between a buyer and a
    seller, which is what keeps the seller's identity private."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"))
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    recipient_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    body: Mapped[str] = mapped_column(Text)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    listing: Mapped[Listing] = relationship()
    sender: Mapped[User] = relationship(foreign_keys=[sender_id])


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    listing_id: Mapped[int] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE"), index=True
    )
    reporter_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reason: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Feedback(Base):
    """Beta feedback, not tied to a listing. Anonymous on purpose — the moments people
    most want to flag something confusing are often before they've signed up, so this
    is reachable without a session the way signup is (honeypot + rate limit, no CSRF)."""

    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Voluntary, so we can close the loop with someone. Never rendered anywhere —
    # same treatment as User.email — only ever read by a human via email/psql.
    contact_email: Mapped[str] = mapped_column(String(255), default="")
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EventLog(Base):
    """The entire v1 analytics layer. No dashboard — just queryable rows.

    Event types: listing_created, listing_viewed, contact_sent, listing_completed.
    """

    __tablename__ = "event_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    listing_id: Mapped[int | None] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class RateLimitHit(Base):
    """Backs app.ratelimit. Postgres instead of in-memory so limits survive a
    restart and are actually shared across FastAPI Cloud's multiple instances,
    rather than each one keeping its own undercounted total."""

    __tablename__ = "rate_limit_hits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bucket: Mapped[str] = mapped_column(String(20))
    client_key: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


Index("ix_listings_status_created", Listing.status, Listing.created_at)
Index(
    "ix_rate_limit_hits_lookup",
    RateLimitHit.bucket,
    RateLimitHit.client_key,
    RateLimitHit.created_at,
)
