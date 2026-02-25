"""add booking-aligned route/time_entry/booking fields

Revision ID: 20260209_add_booking_aligned_fields
Revises: 
Create Date: 2026-02-09
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260209_add_booking_aligned_fields"
down_revision = "0004_ops_admin_routes_price"
branch_labels = None
depends_on = None

def upgrade():
    # routes
    with op.batch_alter_table("routes") as b:
        b.add_column(sa.Column("main_region", sa.String(length=20), server_default="MAINLAND", nullable=True))
        b.add_column(sa.Column("sub_region", sa.String(length=80), nullable=True))
    # time_entries
    with op.batch_alter_table("time_entries") as b:
        b.add_column(sa.Column("visibility", sa.String(length=12), server_default="PUBLIC", nullable=True))
        b.add_column(sa.Column("status", sa.String(length=12), server_default="PUBLISHED", nullable=True))
        b.add_column(sa.Column("currency", sa.String(length=3), server_default="USD", nullable=True))
        b.add_column(sa.Column("exchange_rate", sa.Integer(), nullable=True))
        b.add_column(sa.Column("base_price_usd", sa.Integer(), server_default="0", nullable=True))
        b.add_column(sa.Column("base_price_tzs", sa.Integer(), nullable=True))
        b.add_column(sa.Column("override_price_usd", sa.Integer(), nullable=True))
        b.add_column(sa.Column("override_price_tzs", sa.Integer(), nullable=True))
    # bookings
    with op.batch_alter_table("bookings") as b:
        b.add_column(sa.Column("created_by_role", sa.String(length=12), server_default="USER", nullable=True))
        b.add_column(sa.Column("currency", sa.String(length=3), server_default="USD", nullable=True))
        b.add_column(sa.Column("exchange_rate_used", sa.Integer(), nullable=True))

def downgrade():
    with op.batch_alter_table("bookings") as b:
        b.drop_column("exchange_rate_used")
        b.drop_column("currency")
        b.drop_column("created_by_role")
    with op.batch_alter_table("time_entries") as b:
        b.drop_column("override_price_tzs")
        b.drop_column("override_price_usd")
        b.drop_column("base_price_tzs")
        b.drop_column("base_price_usd")
        b.drop_column("exchange_rate")
        b.drop_column("currency")
        b.drop_column("status")
        b.drop_column("visibility")
    with op.batch_alter_table("routes") as b:
        b.drop_column("sub_region")
        b.drop_column("main_region")
