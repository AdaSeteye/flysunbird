"""add locations table

Revision ID: 20260209_add_locations_table
Revises: 20260209_add_booking_aligned_fields
Create Date: 2026-02-09
"""

from alembic import op
import sqlalchemy as sa

revision = "20260209_add_locations_table"
down_revision = "20260209_add_booking_aligned_fields"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "locations",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("region", sa.String(length=80), nullable=True, server_default="Tanzania"),
        sa.Column("code", sa.String(length=10), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("subs_csv", sa.String(length=600), nullable=True, server_default=""),
        sa.Column("active", sa.Boolean(), nullable=True, server_default=sa.true()),
    )

def downgrade():
    op.drop_table("locations")
