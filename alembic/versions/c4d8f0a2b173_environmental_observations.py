"""environmental model input observations

Revision ID: c4d8f0a2b173
Revises: 9b6c1d2e4f30
Create Date: 2026-08-18
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import geoalchemy2

revision = "c4d8f0a2b173"
down_revision = "9b6c1d2e4f30"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "environmental_observations",
        sa.Column("id", sa.UUID(as_uuid=False), primary_key=True),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("location", geoalchemy2.Geography(geometry_type="POINT", srid=4326), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_data", postgresql.JSONB(), nullable=False),
        sa.Column("normalized_features", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_environmental_observations_observed_at", "environmental_observations", ["observed_at"])


def downgrade() -> None:
    op.drop_index("ix_environmental_observations_observed_at", table_name="environmental_observations")
    op.drop_table("environmental_observations")
