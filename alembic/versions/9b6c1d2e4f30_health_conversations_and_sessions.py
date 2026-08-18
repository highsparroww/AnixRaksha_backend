"""health conversations and refresh sessions

Revision ID: 9b6c1d2e4f30
Revises: 5e5ac4505031
Create Date: 2026-08-18
"""

from alembic import op

revision = "9b6c1d2e4f30"
down_revision = "5e5ac4505031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL DDL is intentionally idempotent: a previous interrupted
    # deployment may have created some tables before Alembic recorded revision.
    op.execute("""
        CREATE TABLE IF NOT EXISTS health_intakes (
            id UUID PRIMARY KEY, patient_id UUID NOT NULL REFERENCES patients(id),
            structured_data JSONB NOT NULL DEFAULT '{}'::jsonb, summary TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_health_intakes_patient_id ON health_intakes (patient_id)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS health_conversations (
            id UUID PRIMARY KEY, patient_id UUID NOT NULL REFERENCES patients(id),
            health_intake_id UUID NOT NULL UNIQUE REFERENCES health_intakes(id),
            status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_health_conversations_patient_id ON health_conversations (patient_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_health_conversations_status ON health_conversations (status)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_sessions (
            id UUID PRIMARY KEY, user_id UUID NOT NULL REFERENCES users(id),
            refresh_token_hash VARCHAR(64) NOT NULL UNIQUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(), expires_at TIMESTAMPTZ NOT NULL,
            last_used_at TIMESTAMPTZ, revoked_at TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_sessions_user_id ON user_sessions (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_sessions_expires_at ON user_sessions (expires_at)")
    op.execute("ALTER TABLE appointments ADD COLUMN IF NOT EXISTS health_intake_id UUID")
    op.execute("ALTER TABLE appointments ADD COLUMN IF NOT EXISTS health_summary_snapshot JSONB")
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_appointments_health_intake') THEN
                ALTER TABLE appointments ADD CONSTRAINT fk_appointments_health_intake
                FOREIGN KEY (health_intake_id) REFERENCES health_intakes(id);
            END IF;
        END $$;
    """)


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
