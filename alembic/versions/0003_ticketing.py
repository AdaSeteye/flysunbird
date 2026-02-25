"""ticket storage fields

Revision ID: 0003_ticketing
Revises: 0002_cancellations_audit
Create Date: 2026-02-08
"""

from alembic import op
import sqlalchemy as sa

revision = '0003_ticketing'
down_revision = '0002_cancellations_audit'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('bookings', sa.Column('ticket_object_key', sa.String(length=512), nullable=True))
    op.add_column('bookings', sa.Column('ticket_storage', sa.String(length=16), nullable=False, server_default='local'))
    op.add_column('bookings', sa.Column('ticket_status', sa.String(length=30), nullable=False, server_default='none'))


def downgrade():
    op.drop_column('bookings', 'ticket_status')
    op.drop_column('bookings', 'ticket_storage')
    op.drop_column('bookings', 'ticket_object_key')
