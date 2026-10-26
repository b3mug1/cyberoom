"""Add staff shift scheduling."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010_staff_shifts"
down_revision = "0009_audit_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "staff_shifts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("club_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("staff_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("start_time < end_time", name="staff_shift_valid_interval"),
        sa.ForeignKeyConstraint(["club_id"], ["clubs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["staff_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_staff_shifts_club_id", "staff_shifts", ["club_id"])
    op.create_index("ix_staff_shifts_staff_user_id", "staff_shifts", ["staff_user_id"])
    op.create_index("ix_staff_shifts_start_time", "staff_shifts", ["start_time"])
    op.execute(
        "ALTER TABLE staff_shifts ADD CONSTRAINT staff_shift_no_overlap "
        "EXCLUDE USING gist (staff_user_id WITH =, tstzrange(start_time, end_time, '[)') WITH &&)"
    )


def downgrade() -> None:
    op.drop_index("ix_staff_shifts_start_time", table_name="staff_shifts")
    op.drop_index("ix_staff_shifts_staff_user_id", table_name="staff_shifts")
    op.drop_index("ix_staff_shifts_club_id", table_name="staff_shifts")
    op.drop_table("staff_shifts")
