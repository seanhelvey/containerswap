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
    category: Mapped[str] = mapped_column(String(40), default="other", index=True)
    image_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Jittered before storage — see app.geo.fuzz. The exact location is never persisted.
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )

    owner: Mapped[User] = relationship(back_populates="listings")

    @property
    def is_active(self) -> bool:
        return self.status == "active"


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


Index("ix_listings_status_created", Listing.status, Listing.created_at)
