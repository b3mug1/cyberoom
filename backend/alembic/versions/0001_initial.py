"""Initial Cyberoom schema."""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute("CREATE TYPE user_role AS ENUM ('USER', 'STAFF', 'OWNER', 'ADMIN')")
    op.execute("CREATE TYPE computer_status AS ENUM ('AVAILABLE', 'OCCUPIED', 'MAINTENANCE', 'DISABLED')")
    op.execute("CREATE TYPE booking_status AS ENUM ('PENDING', 'CONFIRMED', 'ACTIVE', 'COMPLETED', 'CANCELLED', 'EXPIRED')")

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("username", sa.String(40), nullable=False),
        sa.Column("full_name", sa.String(120), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", postgresql.ENUM(name="user_role", create_type=False), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.create_table(
        "clubs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("address", sa.String(240), nullable=False),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("phone", sa.String(32), nullable=False),
        sa.Column("opening_time", sa.Time(), nullable=False),
        sa.Column("closing_time", sa.Time(), nullable=False),
        sa.Column("rating", sa.Numeric(3, 2), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_clubs_owner_id", "clubs", ["owner_id"])
    op.create_index("ix_clubs_name", "clubs", ["name"])
    op.create_index("ix_clubs_city", "clubs", ["city"])
    op.create_index("ix_clubs_is_active", "clubs", ["is_active"])

    op.create_table(
        "computers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("club_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("cpu", sa.String(120), nullable=False),
        sa.Column("gpu", sa.String(120), nullable=False),
        sa.Column("ram_gb", sa.Integer(), nullable=False),
        sa.Column("storage", sa.String(80), nullable=False),
        sa.Column("monitor", sa.String(120), nullable=False),
        sa.Column("refresh_rate", sa.Integer(), nullable=False),
        sa.Column("status", postgresql.ENUM(name="computer_status", create_type=False), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_computers_club_id", "computers", ["club_id"])
    op.create_index("ix_computers_gpu", "computers", ["gpu"])
    op.create_index("ix_computers_is_active", "computers", ["is_active"])

    op.create_table(
        "tariffs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("club_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("description", sa.String(240), nullable=False),
        sa.Column("price_per_hour", sa.Numeric(10, 2), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_tariffs_club_id", "tariffs", ["club_id"])

    op.create_table(
        "bookings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("computer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("computers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", postgresql.ENUM(name="booking_status", create_type=False), nullable=False),
        sa.Column("total_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("qr_token", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_bookings_user_id", "bookings", ["user_id"])
    op.create_index("ix_bookings_computer_id", "bookings", ["computer_id"])
    op.create_index("ix_bookings_start_time", "bookings", ["start_time"])
    op.create_index("ix_bookings_status", "bookings", ["status"])
    op.create_index("ix_bookings_qr_token", "bookings", ["qr_token"], unique=True)
    op.execute(
        "ALTER TABLE bookings ADD CONSTRAINT booking_no_overlapping_active_ranges "
        "EXCLUDE USING gist (computer_id WITH =, tstzrange(start_time, end_time, '[)') WITH &&) "
        "WHERE (status IN ('PENDING', 'CONFIRMED', 'ACTIVE'))"
    )

    op.create_table(
        "refresh_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_refresh_sessions_user_id", "refresh_sessions", ["user_id"])
    op.create_index("ix_refresh_sessions_token_hash", "refresh_sessions", ["token_hash"], unique=True)


def downgrade() -> None:
    op.drop_table("refresh_sessions")
    op.drop_table("bookings")
    op.drop_table("tariffs")
    op.drop_table("computers")
    op.drop_table("clubs")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS booking_status")
    op.execute("DROP TYPE IF EXISTS computer_status")
    op.execute("DROP TYPE IF EXISTS user_role")