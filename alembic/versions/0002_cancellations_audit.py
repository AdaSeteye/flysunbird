"""cancellations and audit logs

Revision ID: 0002_cancellations_audit
Revises: 0001_initial
Create Date: 2026-02-07
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_cancellations_audit"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "cancellations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("booking_id", sa.String(length=36), nullable=False),
        sa.Column("booking_ref", sa.String(length=20), nullable=False),
        sa.Column("requested_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="requested"),
        sa.Column("refund_amount_usd", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("decided_by_user_id", sa.String(length=36), nullable=False, server_default=""),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_cancellations_booking_id", "cancellations", ["booking_id"])
    op.create_index("ix_cancellations_booking_ref", "cancellations", ["booking_ref"])
    op.create_index("ix_cancellations_requested_by_user_id", "cancellations", ["requested_by_user_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("actor_user_id", sa.String(length=36), nullable=False),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("entity_type", sa.String(length=40), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("details_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_logs_actor_user_id", "audit_logs", ["actor_user_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_entity_type", "audit_logs", ["entity_type"])
    op.create_index("ix_audit_logs_entity_id", "audit_logs", ["entity_id"])

def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("cancellations")
