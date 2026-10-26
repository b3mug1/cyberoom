"""Add in-app notifications and reservation waitlists."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008_notifications_waitlist"
down_revision = "0007_tariff_weekdays"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("kind", sa.String(length=48), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("message", sa.String(length=500), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_booking_id", "notifications", ["booking_id"])
    op.create_index("ix_notifications_kind", "notifications", ["kind"])
    op.create_index("ix_notifications_scheduled_at", "notifications", ["scheduled_at"])

    op.create_table(
        "waitlist_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("club_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("computer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="WAITING", nullable=False),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("start_time < end_time", name="waitlist_valid_interval"),
        sa.CheckConstraint("status IN ('WAITING', 'NOTIFIED', 'CANCELLED')", name="waitlist_valid_status"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["club_id"], ["clubs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["computer_id"], ["computers.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "club_id", "computer_id", "start_time", "end_time", name="uq_waitlist_request"),
    )
    op.create_index("ix_waitlist_entries_user_id", "waitlist_entries", ["user_id"])
    op.create_index("ix_waitlist_entries_club_id", "waitlist_entries", ["club_id"])
    op.create_index("ix_waitlist_entries_computer_id", "waitlist_entries", ["computer_id"])
    op.create_index("ix_waitlist_entries_status", "waitlist_entries", ["status"])
    op.create_index(
        "uq_waitlist_all_computers_request",
        "waitlist_entries",
        ["user_id", "club_id", "start_time", "end_time"],
        unique=True,
        postgresql_where=sa.text("computer_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_waitlist_all_computers_request", table_name="waitlist_entries")
    op.drop_index("ix_waitlist_entries_status", table_name="waitlist_entries")
    op.drop_index("ix_waitlist_entries_computer_id", table_name="waitlist_entries")
    op.drop_index("ix_waitlist_entries_club_id", table_name="waitlist_entries")
    op.drop_index("ix_waitlist_entries_user_id", table_name="waitlist_entries")
    op.drop_table("waitlist_entries")
    op.drop_index("ix_notifications_scheduled_at", table_name="notifications")
    op.drop_index("ix_notifications_kind", table_name="notifications")
    op.drop_index("ix_notifications_booking_id", table_name="notifications")
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_table("notifications")
