"""Add payment records, membership hour packs, and refund policy."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0012_payments_memberships"
down_revision = "0011_promotion_codes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("clubs", sa.Column("refund_cutoff_hours", sa.Integer(), server_default="24", nullable=False))

    op.create_table(
        "membership_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("club_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=500), server_default="", nullable=False),
        sa.Column("hours", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("validity_days", sa.Integer(), server_default="30", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("hours > 0", name="membership_plan_hours_positive"),
        sa.CheckConstraint("price > 0", name="membership_plan_price_positive"),
        sa.CheckConstraint("validity_days >= 1", name="membership_plan_validity_positive"),
        sa.ForeignKeyConstraint(["club_id"], ["clubs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_membership_plans_club_id", "membership_plans", ["club_id"])
    op.create_index("ix_membership_plans_is_active", "membership_plans", ["is_active"])

    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("membership_plan_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="KZT", nullable=False),
        sa.Column("status", sa.String(length=24), server_default="PENDING", nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("provider_reference", sa.String(length=160), nullable=True),
        sa.Column("checkout_url", sa.String(length=2000), nullable=True),
        sa.Column("refund_amount", sa.Numeric(10, 2), server_default="0", nullable=False),
        sa.Column("refund_reference", sa.String(length=160), nullable=True),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("(booking_id IS NOT NULL) <> (membership_plan_id IS NOT NULL)", name="payment_exactly_one_target"),
        sa.CheckConstraint("amount >= 0", name="payment_amount_nonnegative"),
        sa.CheckConstraint("status IN ('PENDING', 'CHECKOUT_CREATED', 'PAID', 'FAILED', 'REFUND_PENDING', 'REFUNDED')", name="payment_status_valid"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["membership_plan_id"], ["membership_plans.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("booking_id", name="uq_payment_booking"),
        sa.UniqueConstraint("idempotency_key", name="uq_payments_idempotency_key"),
    )
    op.create_index("ix_payments_user_id", "payments", ["user_id"])
    op.create_index("ix_payments_booking_id", "payments", ["booking_id"])
    op.create_index("ix_payments_membership_plan_id", "payments", ["membership_plan_id"])
    op.create_index("ix_payments_status", "payments", ["status"])
    op.create_index("ix_payments_provider_reference", "payments", ["provider_reference"])

    op.create_table(
        "memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("club_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("total_minutes", sa.Integer(), nullable=False),
        sa.Column("remaining_minutes", sa.Integer(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("total_minutes > 0", name="membership_total_minutes_positive"),
        sa.CheckConstraint("remaining_minutes >= 0 AND remaining_minutes <= total_minutes", name="membership_remaining_minutes_valid"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["club_id"], ["clubs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_id"], ["membership_plans.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payment_id", name="uq_membership_payment"),
    )
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"])
    op.create_index("ix_memberships_club_id", "memberships", ["club_id"])
    op.create_index("ix_memberships_plan_id", "memberships", ["plan_id"])
    op.create_index("ix_memberships_payment_id", "memberships", ["payment_id"])
    op.create_index("ix_memberships_expires_at", "memberships", ["expires_at"])

    op.add_column("bookings", sa.Column("membership_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("bookings", sa.Column("membership_minutes", sa.Integer(), server_default="0", nullable=False))
    op.add_column("bookings", sa.Column("membership_credit_amount", sa.Numeric(10, 2), server_default="0", nullable=False))
    op.add_column("bookings", sa.Column("refund_cutoff_hours", sa.Integer(), server_default="24", nullable=False))
    op.create_foreign_key("fk_bookings_membership_id_memberships", "bookings", "memberships", ["membership_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_bookings_membership_id", "bookings", ["membership_id"])


def downgrade() -> None:
    op.drop_index("ix_bookings_membership_id", table_name="bookings")
    op.drop_constraint("fk_bookings_membership_id_memberships", "bookings", type_="foreignkey")
    op.drop_column("bookings", "membership_credit_amount")
    op.drop_column("bookings", "membership_minutes")
    op.drop_column("bookings", "membership_id")
    op.drop_column("bookings", "refund_cutoff_hours")
    for index in ("ix_memberships_expires_at", "ix_memberships_payment_id", "ix_memberships_plan_id", "ix_memberships_club_id", "ix_memberships_user_id"):
        op.drop_index(index, table_name="memberships")
    op.drop_table("memberships")
    for index in ("ix_payments_provider_reference", "ix_payments_status", "ix_payments_membership_plan_id", "ix_payments_booking_id", "ix_payments_user_id"):
        op.drop_index(index, table_name="payments")
    op.drop_table("payments")
    op.drop_index("ix_membership_plans_is_active", table_name="membership_plans")
    op.drop_index("ix_membership_plans_club_id", table_name="membership_plans")
    op.drop_table("membership_plans")
    op.drop_column("clubs", "refund_cutoff_hours")
