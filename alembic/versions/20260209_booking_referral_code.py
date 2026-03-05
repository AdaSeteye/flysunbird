"""add booking referral_code for partner verification

Revision ID: 20260209_referral
Revises: 20260209_attach_ticket
Create Date: 2026-02-09

"""
from alembic import op
import sqlalchemy as sa

revision = "20260209_referral"
down_revision = "20260209_attach_ticket"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("bookings", sa.Column("referral_code", sa.String(length=100), nullable=True))
    op.create_index(op.f("ix_bookings_referral_code"), "bookings", ["referral_code"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_bookings_referral_code"), table_name="bookings")
    op.drop_column("bookings", "referral_code")
