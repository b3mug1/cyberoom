"""Add walk-in bookings and actual sessions."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_booking_management"
down_revision = "0002_staff_assignments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE TYPE booking_source AS ENUM ('ONLINE', 'WALK_IN')")
    op.add_column("bookings", sa.Column("source", postgresql.ENUM(name="booking_source", create_type=False), server_default="ONLINE", nullable=False))
    op.add_column("bookings", sa.Column("guest_name", sa.String(120), nullable=True))
    op.alter_column("bookings", "user_id", existing_type=postgresql.UUID(as_uuid=True), nullable=True)
    op.create_check_constraint(
        "booking_customer_matches_source", "bookings",
        "(source = 'ONLINE' AND user_id IS NOT NULL AND guest_name IS NULL) OR "
        "(source = 'WALK_IN' AND user_id IS NULL AND guest_name IS NOT NULL)",
    )
    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("ended_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_sessions_booking_id", "sessions", ["booking_id"], unique=True)
    # Preserve sessions already checked in before this migration.
    op.execute("""
        INSERT INTO sessions (id, booking_id, started_at)
        SELECT id, id, start_time FROM bookings WHERE status = 'ACTIVE'
    """)


def downgrade() -> None:
    op.drop_table("sessions")
    op.drop_constraint("booking_customer_matches_source", "bookings", type_="check")
    op.execute("DELETE FROM bookings WHERE source = 'WALK_IN'")
    op.alter_column("bookings", "user_id", existing_type=postgresql.UUID(as_uuid=True), nullable=False)
    op.drop_column("bookings", "guest_name")
    op.drop_column("bookings", "source")
    op.execute("DROP TYPE booking_source")
