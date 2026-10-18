"""Store each club's IANA time zone for tariff and booking display."""

import sqlalchemy as sa
from alembic import op

revision = "0004_club_timezone"
down_revision = "0003_booking_management"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "clubs",
        sa.Column("timezone", sa.String(64), server_default="Asia/Almaty", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("clubs", "timezone")
