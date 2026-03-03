"""add email_log attach_ticket_booking_ref for retry with ticket

Revision ID: 20260209_attach_ticket
Revises: 20260209_email_log_body
Create Date: 2026-02-09

"""
from alembic import op
import sqlalchemy as sa

revision = "20260209_attach_ticket"
down_revision = "20260209_email_log_body"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("email_logs", sa.Column("attach_ticket_booking_ref", sa.String(length=20), nullable=True))


def downgrade():
    op.drop_column("email_logs", "attach_ticket_booking_ref")
