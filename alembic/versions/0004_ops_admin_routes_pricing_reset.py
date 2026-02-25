"""ops/admin routes + pricing + settings

Revision ID: 0004_ops_admin_routes_price
Revises: 0003_ticketing
Create Date: 2026-02-08

"""

from alembic import op
import sqlalchemy as sa

revision = "0004_ops_admin_routes_price"
down_revision = "0003_ticketing"
branch_labels = None
depends_on = None

def upgrade() -> None:
    # routes
    op.add_column("routes", sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")))

    # time_entries
    op.add_column("time_entries", sa.Column("price_tzs", sa.Integer(), nullable=True))

    # slot_rules
    op.add_column("slot_rules", sa.Column("price_tzs", sa.Integer(), nullable=True))

    # bookings totals
    op.add_column("bookings", sa.Column("unit_price_usd", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("bookings", sa.Column("unit_price_tzs", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("bookings", sa.Column("total_usd", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("bookings", sa.Column("total_tzs", sa.Integer(), nullable=False, server_default="0"))

    # payments
    op.add_column("payments", sa.Column("amount_tzs", sa.Integer(), nullable=False, server_default="0"))

    # settings table
    op.create_table(
        "settings",
        sa.Column("key", sa.String(length=80), primary_key=True),
        sa.Column("int_value", sa.Integer(), nullable=True),
        sa.Column("str_value", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

def downgrade() -> None:
    op.drop_table("settings")
    op.drop_column("payments", "amount_tzs")
    op.drop_column("bookings", "total_tzs")
    op.drop_column("bookings", "total_usd")
    op.drop_column("bookings", "unit_price_tzs")
    op.drop_column("bookings", "unit_price_usd")
    op.drop_column("slot_rules", "price_tzs")
    op.drop_column("time_entries", "price_tzs")
    op.drop_column("routes", "active")
