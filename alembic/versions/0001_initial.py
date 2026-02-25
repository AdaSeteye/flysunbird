"""initial

Revision ID: 0001_initial
Revises:
Create Date: 2026-02-07

"""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("role", sa.String(length=30), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_role", "users", ["role"], unique=False)

    op.create_table(
        "routes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("from_label", sa.String(length=120), nullable=False),
        sa.Column("to_label", sa.String(length=120), nullable=False),
        sa.Column("region", sa.String(length=80), nullable=False, server_default="Tanzania"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "slot_rules",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("route_id", sa.String(length=36), nullable=False),
        sa.Column("days_of_week", sa.String(length=30), nullable=False, server_default="0,1,2,3,4,5,6"),
        sa.Column("times", sa.String(length=200), nullable=False, server_default="09:00,11:00,16:00"),
        sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("price_usd", sa.Integer(), nullable=False, server_default="298"),
        sa.Column("capacity", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("flight_no_prefix", sa.String(length=20), nullable=False, server_default="FSB"),
        sa.Column("cabin", sa.String(length=30), nullable=False, server_default="Economy"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("horizon_days", sa.Integer(), nullable=False, server_default="90"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_slot_rules_route_id", "slot_rules", ["route_id"])

    op.create_table(
        "time_entries",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("route_id", sa.String(length=36), nullable=False),
        sa.Column("date_str", sa.String(length=10), nullable=False),
        sa.Column("start", sa.String(length=5), nullable=False),
        sa.Column("end", sa.String(length=5), nullable=False),
        sa.Column("price_usd", sa.Integer(), nullable=False),
        sa.Column("seats_available", sa.Integer(), nullable=False),
        sa.Column("flight_no", sa.String(length=30), nullable=False, server_default="FSB"),
        sa.Column("cabin", sa.String(length=30), nullable=False, server_default="Economy"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("route_id","date_str","start", name="uq_time_entry_route_date_start"),
    )
    op.create_index("ix_time_entries_route_id", "time_entries", ["route_id"])
    op.create_index("ix_time_entries_date_str", "time_entries", ["date_str"])

    op.create_table(
        "bookings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("booking_ref", sa.String(length=20), nullable=False),
        sa.Column("time_entry_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("pax", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="PENDING_PAYMENT"),
        sa.Column("payment_status", sa.String(length=30), nullable=False, server_default="unpaid"),
        sa.Column("hold_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_bookings_ref", "bookings", ["booking_ref"], unique=True)
    op.create_index("ix_bookings_time_entry_id", "bookings", ["time_entry_id"])
    op.create_index("ix_bookings_user_id", "bookings", ["user_id"])

    op.create_table(
        "passengers",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("booking_id", sa.String(length=36), nullable=False),
        sa.Column("first", sa.String(length=100), nullable=False),
        sa.Column("last", sa.String(length=100), nullable=False),
        sa.Column("gender", sa.String(length=20), nullable=False, server_default=""),
        sa.Column("dob", sa.String(length=20), nullable=False, server_default=""),
        sa.Column("nationality", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("id_type", sa.String(length=50), nullable=False, server_default=""),
        sa.Column("id_number", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("phone", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_passengers_booking_id", "passengers", ["booking_id"])

    op.create_table(
        "payments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("booking_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False, server_default="manual"),
        sa.Column("amount_usd", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default="USD"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("provider_ref", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_payments_booking_id", "payments", ["booking_id"])

    op.create_table(
        "pilot_assignments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("time_entry_id", sa.String(length=36), nullable=False),
        sa.Column("pilot_user_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="assigned"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_pilot_assignments_time_entry_id", "pilot_assignments", ["time_entry_id"])
    op.create_index("ix_pilot_assignments_pilot_user_id", "pilot_assignments", ["pilot_user_id"])

    op.create_table(
        "email_logs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("to_email", sa.String(length=320), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="queued"),
        sa.Column("related_booking_ref", sa.String(length=20), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_email_logs_to_email", "email_logs", ["to_email"])

def downgrade() -> None:
    op.drop_index("ix_email_logs_to_email", table_name="email_logs")
    op.drop_table("email_logs")
    op.drop_table("pilot_assignments")
    op.drop_table("payments")
    op.drop_table("passengers")
    op.drop_index("ix_bookings_user_id", table_name="bookings")
    op.drop_index("ix_bookings_time_entry_id", table_name="bookings")
    op.drop_index("ix_bookings_ref", table_name="bookings")
    op.drop_table("bookings")
    op.drop_table("time_entries")
    op.drop_table("slot_rules")
    op.drop_table("routes")
    op.drop_index("ix_users_role", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
