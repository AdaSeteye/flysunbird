"""add email_log body for retry

Revision ID: 20260209_email_log_body
Revises: 20260209_add_locations_table
Create Date: 2026-02-09

"""
from alembic import op
import sqlalchemy as sa

revision = "20260209_email_log_body"
down_revision = "20260209_add_locations_table"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("email_logs", sa.Column("body", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("email_logs", "body")
