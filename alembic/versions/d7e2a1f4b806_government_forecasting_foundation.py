"""government forecasting data foundation

Revision ID: d7e2a1f4b806
Revises: c4d8f0a2b173
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import geoalchemy2

revision = "d7e2a1f4b806"
down_revision = "c4d8f0a2b173"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("surveillance_signals",
        sa.Column("id", sa.UUID(as_uuid=False), primary_key=True),
        sa.Column("signal_type", sa.String(30), nullable=False), sa.Column("disease", sa.String(50)),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("location", geoalchemy2.Geography(geometry_type="POINT", srid=4326), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False), sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False), sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.Column("collected_by_user_id", sa.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    for name, column in [("ix_surveillance_signals_signal_type", "signal_type"), ("ix_surveillance_signals_disease", "disease"), ("ix_surveillance_signals_observed_at", "observed_at")]:
        op.create_index(name, "surveillance_signals", [column])
    op.create_table("forecast_assessments",
        sa.Column("id", sa.UUID(as_uuid=False), primary_key=True), sa.Column("disease", sa.String(50), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False), sa.Column("longitude", sa.Float(), nullable=False), sa.Column("radius_km", sa.Float(), nullable=False),
        sa.Column("risk_level", sa.String(20), nullable=False), sa.Column("confidence", sa.Float(), nullable=False), sa.Column("model_version", sa.String(100), nullable=False),
        sa.Column("explanation", postgresql.JSONB(), nullable=False), sa.Column("evidence_context", postgresql.JSONB(), nullable=False),
        sa.Column("forecast_start", sa.DateTime(timezone=True), nullable=False), sa.Column("forecast_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_forecast_assessments_disease", "forecast_assessments", ["disease"])
    op.create_index("ix_forecast_assessments_status", "forecast_assessments", ["status"])


def downgrade() -> None:
    op.drop_index("ix_forecast_assessments_status", table_name="forecast_assessments")
    op.drop_index("ix_forecast_assessments_disease", table_name="forecast_assessments")
    op.drop_table("forecast_assessments")
    op.drop_index("ix_surveillance_signals_observed_at", table_name="surveillance_signals")
    op.drop_index("ix_surveillance_signals_disease", table_name="surveillance_signals")
    op.drop_index("ix_surveillance_signals_signal_type", table_name="surveillance_signals")
    op.drop_table("surveillance_signals")
