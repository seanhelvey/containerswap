"""replace category with listing tags

Revision ID: 1b966eb4c94b
Revises: 609e77eef42c
Create Date: 2026-08-16 12:55:24.295597

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1b966eb4c94b"
down_revision: str | Sequence[str] | None = "609e77eef42c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "listing_tags",
        sa.Column("listing_id", sa.Integer(), nullable=False),
        sa.Column("tag", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("listing_id", "tag"),
    )
    op.create_index(op.f("ix_listing_tags_tag"), "listing_tags", ["tag"], unique=False)

    # Backfill before category is gone: "storage"/"upcycled" only existed for a few
    # hours earlier the same day this migration was written, so this is mostly a
    # 1:1 carry-over rather than real data migration. storage -> bins matches the
    # rename decided in the same pass; upcycled had no shape of its own to recover,
    # so it falls back to "other" alongside gaining the upcycled tag itself.
    op.execute(
        sa.text("""
            INSERT INTO listing_tags (listing_id, tag)
            SELECT id,
                   CASE
                       WHEN category = 'storage' THEN 'bins'
                       WHEN category = 'upcycled' THEN 'other'
                       ELSE category
                   END
            FROM listings
        """)
    )
    op.execute(
        sa.text("""
            INSERT INTO listing_tags (listing_id, tag)
            SELECT id, 'upcycled' FROM listings WHERE category = 'upcycled'
        """)
    )

    op.drop_index(op.f("ix_listings_category"), table_name="listings")
    op.drop_column("listings", "category")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        "listings",
        sa.Column("category", sa.VARCHAR(length=40), autoincrement=False, nullable=False),
    )
    op.create_index(op.f("ix_listings_category"), "listings", ["category"], unique=False)
    op.drop_index(op.f("ix_listing_tags_tag"), table_name="listing_tags")
    op.drop_table("listing_tags")
