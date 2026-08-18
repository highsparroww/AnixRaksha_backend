"""health conversations and refresh sessions

Revision ID: 9b6c1d2e4f30
Revises: 5e5ac4505031
Create Date: 2026-08-18
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "9b6c1d2e4f30"
down_revision = "5e5ac4505031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "health_intakes",
        sa.Column("id", sa.UUID(as_uuid=False), primary_key=True),
        sa.Column("patient_id", sa.UUID(as_uuid=False), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("structured_data", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_health_intakes_patient_id", "health_intakes", ["patient_id"])
    op.create_table(
        "health_conversations",
        sa.Column("id", sa.UUID(as_uuid=False), primary_key=True),
        sa.Column("patient_id", sa.UUID(as_uuid=False), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("health_intake_id", sa.UUID(as_uuid=False), sa.ForeignKey("health_intakes.id"), nullable=False, unique=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_health_conversations_patient_id", "health_conversations", ["patient_id"])
    op.create_index("ix_health_conversations_status", "health_conversations", ["status"])
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", sa.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("refresh_token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
    op.create_index("ix_user_sessions_expires_at", "user_sessions", ["expires_at"])
    op.add_column("appointments", sa.Column("health_intake_id", sa.UUID(as_uuid=False), nullable=True))
    op.add_column("appointments", sa.Column("health_summary_snapshot", postgresql.JSONB(), nullable=True))
    op.create_foreign_key("fk_appointments_health_intake", "appointments", "health_intakes", ["health_intake_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_appointments_health_intake", "appointments", type_="foreignkey")
    op.drop_column("appointments", "health_summary_snapshot")
    op.drop_column("appointments", "health_intake_id")
    op.drop_index("ix_user_sessions_expires_at", table_name="user_sessions")
    op.drop_index("ix_user_sessions_user_id", table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_index("ix_health_conversations_status", table_name="health_conversations")
    op.drop_index("ix_health_conversations_patient_id", table_name="health_conversations")
    op.drop_table("health_conversations")
    op.drop_index("ix_health_intakes_patient_id", table_name="health_intakes")
    op.drop_table("health_intakes")
