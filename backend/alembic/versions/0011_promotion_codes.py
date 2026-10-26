"""Add club promo codes and booking discount snapshots."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0011_promotion_codes"
down_revision = "0010_staff_shifts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "promo_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("club_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("discount_type", sa.String(length=16), nullable=False),
        sa.Column("discount_value", sa.Numeric(10, 2), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("usage_limit", sa.Integer(), nullable=True),
        sa.Column("used_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("per_user_limit", sa.Integer(), server_default="1", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("discount_type IN ('PERCENT', 'FIXED')", name="promo_discount_type_valid"),
        sa.CheckConstraint("discount_value > 0", name="promo_discount_value_positive"),
        sa.CheckConstraint("discount_type != 'PERCENT' OR discount_value <= 100", name="promo_percent_max"),
        sa.CheckConstraint("used_count >= 0", name="promo_used_count_nonnegative"),
        sa.CheckConstraint("usage_limit IS NULL OR usage_limit >= 1", name="promo_usage_limit_positive"),
        sa.CheckConstraint("per_user_limit >= 1", name="promo_user_limit_positive"),
        sa.CheckConstraint("starts_at < ends_at", name="promo_valid_interval"),
        sa.ForeignKeyConstraint(["club_id"], ["clubs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("club_id", "code", name="uq_promo_code_club_code"),
    )
    op.create_index("ix_promo_codes_club_id", "promo_codes", ["club_id"])
    op.create_index("ix_promo_codes_code", "promo_codes", ["code"])
    op.create_index("ix_promo_codes_is_active", "promo_codes", ["is_active"])

    op.add_column("bookings", sa.Column("subtotal_price", sa.Numeric(10, 2), server_default="0", nullable=False))
    op.add_column("bookings", sa.Column("discount_amount", sa.Numeric(10, 2), server_default="0", nullable=False))
    op.add_column("bookings", sa.Column("promo_code_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_bookings_promo_code_id_promo_codes", "bookings", "promo_codes", ["promo_code_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_bookings_promo_code_id", "bookings", ["promo_code_id"])
    op.execute("UPDATE bookings SET subtotal_price = total_price")


def downgrade() -> None:
    op.drop_index("ix_bookings_promo_code_id", table_name="bookings")
    op.drop_constraint("fk_bookings_promo_code_id_promo_codes", "bookings", type_="foreignkey")
    op.drop_column("bookings", "promo_code_id")
    op.drop_column("bookings", "discount_amount")
    op.drop_column("bookings", "subtotal_price")
    op.drop_index("ix_promo_codes_is_active", table_name="promo_codes")
    op.drop_index("ix_promo_codes_code", table_name="promo_codes")
    op.drop_index("ix_promo_codes_club_id", table_name="promo_codes")
    op.drop_table("promo_codes")
