"""add time_entry aircraft_type and departure_location for ticketing

Revision ID: 20260209_aircraft
Revises: 20260209_must_change
Create Date: 2026-02-09

"""
from alembic import op
import sqlalchemy as sa

revision = "20260209_aircraft"
down_revision = "20260209_must_change"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("time_entries", sa.Column("aircraft_type", sa.String(length=80), nullable=True))
    op.add_column("time_entries", sa.Column("departure_location", sa.String(length=120), nullable=True))


def downgrade():
    op.drop_column("time_entries", "departure_location")
    op.drop_column("time_entries", "aircraft_type")
