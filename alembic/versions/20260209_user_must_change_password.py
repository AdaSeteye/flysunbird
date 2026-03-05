"""add user must_change_password for first-login flow

Revision ID: 20260209_must_change
Revises: 20260209_referral
Create Date: 2026-02-09

"""
from alembic import op
import sqlalchemy as sa

revision = "20260209_must_change"
down_revision = "20260209_referral"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column("users", "must_change_password")
