"""Add booking reviews."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006_booking_reviews"
down_revision = "0005_club_price_menu"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("club_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("computer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("club_rating", sa.Integer(), nullable=False),
        sa.Column("computer_rating", sa.Integer(), nullable=False),
        sa.Column("comment", sa.String(length=2000), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("club_rating BETWEEN 1 AND 5", name="review_club_rating_range"),
        sa.CheckConstraint("computer_rating BETWEEN 1 AND 5", name="review_computer_rating_range"),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["club_id"], ["clubs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["computer_id"], ["computers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("booking_id", name="uq_review_booking"),
    )
    op.create_index("ix_reviews_booking_id", "reviews", ["booking_id"])
    op.create_index("ix_reviews_user_id", "reviews", ["user_id"])
    op.create_index("ix_reviews_club_id", "reviews", ["club_id"])
    op.create_index("ix_reviews_computer_id", "reviews", ["computer_id"])


def downgrade() -> None:
    op.drop_index("ix_reviews_computer_id", table_name="reviews")
    op.drop_index("ix_reviews_club_id", table_name="reviews")
    op.drop_index("ix_reviews_user_id", table_name="reviews")
    op.drop_index("ix_reviews_booking_id", table_name="reviews")
    op.drop_table("reviews")
