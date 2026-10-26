"""Allow tariffs to apply on selected weekdays."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007_tariff_weekdays"
down_revision = "0006_booking_reviews"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tariffs",
        sa.Column(
            "days_of_week",
            postgresql.ARRAY(sa.Integer()),
            server_default=sa.text("ARRAY[0,1,2,3,4,5,6]"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("tariffs", "days_of_week")
