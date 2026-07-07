"""production indexes and schema guards

Revision ID: 20260706_0001
Revises: None
Create Date: 2026-07-06
"""

from alembic import op
import sqlalchemy as sa

revision = "20260706_0001"
down_revision = None
branch_labels = None
depends_on = None


def _table_names(bind):
    return set(sa.inspect(bind).get_table_names())


def _columns(bind, table_name):
    if table_name not in _table_names(bind):
        return set()
    return {column["name"] for column in sa.inspect(bind).get_columns(table_name)}


def _indexes(bind, table_name):
    if table_name not in _table_names(bind):
        return set()
    return {index["name"] for index in sa.inspect(bind).get_indexes(table_name)}


def _add_column_if_missing(bind, table_name, column):
    if table_name in _table_names(bind) and column.name not in _columns(bind, table_name):
        op.add_column(table_name, column)


def _create_index_if_missing(bind, name, table_name, columns, unique=False, **kwargs):
    if table_name in _table_names(bind) and name not in _indexes(bind, table_name):
        op.create_index(name, table_name, columns, unique=unique, **kwargs)


def _drop_index_if_exists(bind, name, table_name):
    if table_name in _table_names(bind) and name in _indexes(bind, table_name):
        op.drop_index(name, table_name=table_name)


def upgrade():
    bind = op.get_bind()

    _add_column_if_missing(bind, "users", sa.Column("transpulse_id", sa.String(length=20), nullable=True))

    _add_column_if_missing(bind, "buses", sa.Column("assigned_driver_code", sa.String(length=20), nullable=True))
    _add_column_if_missing(bind, "buses", sa.Column("assigned_driver_name", sa.String(length=120), nullable=True))

    _add_column_if_missing(bind, "routes", sa.Column("is_operational", sa.Boolean(), nullable=False, server_default=sa.text("1")))
    _add_column_if_missing(bind, "routes", sa.Column("departure_time", sa.String(length=20), nullable=True))
    _add_column_if_missing(bind, "routes", sa.Column("arrival_time", sa.String(length=20), nullable=True))

    _add_column_if_missing(bind, "stops", sa.Column("scheduled_arrival_time", sa.String(length=20), nullable=True))
    _add_column_if_missing(bind, "stops", sa.Column("scheduled_departure_time", sa.String(length=20), nullable=True))

    _add_column_if_missing(bind, "trips", sa.Column("gtfs_trip_id", sa.String(length=120), nullable=True))

    _add_column_if_missing(bind, "complaint", sa.Column("bus_id", sa.Integer(), nullable=True))
    _add_column_if_missing(bind, "complaint", sa.Column("route_id", sa.Integer(), nullable=True))
    _add_column_if_missing(bind, "complaint", sa.Column("evidence_image", sa.Text(), nullable=True))
    _add_column_if_missing(bind, "complaint", sa.Column("created_at", sa.DateTime(), nullable=True))
    _add_column_if_missing(bind, "complaint", sa.Column("resolved_at", sa.DateTime(), nullable=True))
    _add_column_if_missing(bind, "complaint", sa.Column("admin_notes", sa.Text(), nullable=True))

    _add_column_if_missing(bind, "lost_and_found", sa.Column("driver_reply", sa.Text(), nullable=True))
    _add_column_if_missing(bind, "lost_and_found", sa.Column("assigned_driver_id", sa.Integer(), nullable=True))

    if "subscriptions" in _table_names(bind):
        bind.execute(sa.text(
            "DELETE FROM subscriptions WHERE id NOT IN ("
            "SELECT MIN(id) FROM subscriptions GROUP BY user_id, stop_id)"
        ))

    _create_index_if_missing(bind, "ix_users_transpulse_id", "users", ["transpulse_id"], unique=True)
    _create_index_if_missing(bind, "ix_buses_assigned_driver_code", "buses", ["assigned_driver_code"], unique=True)
    _create_index_if_missing(bind, "idx_stops_code_location", "stops", ["stop_code", "stop_lat", "stop_lon"])
    _create_index_if_missing(bind, "idx_stop_time_trip_sequence", "stop_times", ["trip_id", "stop_sequence"])
    _create_index_if_missing(bind, "idx_stop_time_stop_trip", "stop_times", ["stop_id", "trip_id"])
    _create_index_if_missing(bind, "idx_trip_route_status", "trips", ["route_id", "status"])
    _create_index_if_missing(bind, "idx_trip_shape_route", "trips", ["shape_id", "route_id"])
    _create_index_if_missing(bind, "idx_trip_bus_status", "trips", ["bus_id", "status"])
    _create_index_if_missing(bind, "ix_trips_gtfs_trip_id", "trips", ["gtfs_trip_id"], unique=True)
    _create_index_if_missing(bind, "idx_bus_occupancy_bus_recorded", "bus_occupancy", ["bus_id", "recorded_at"])
    _create_index_if_missing(bind, "idx_bus_occupancy_trip_recorded", "bus_occupancy", ["trip_id", "recorded_at"])
    _create_index_if_missing(bind, "uq_subscription_user_stop", "subscriptions", ["user_id", "stop_id"], unique=True)
    _create_index_if_missing(bind, "idx_notification_recipient_read_created", "notifications", ["recipient_id", "is_read", "created_at"])
    _create_index_if_missing(bind, "idx_sos_status_triggered", "sos_alert", ["status", "triggered_at"])
    _create_index_if_missing(bind, "idx_sos_bus_status", "sos_alert", ["bus_id", "status"])
    _create_index_if_missing(bind, "idx_road_geometry_route_shape", "road_geometry_cache", ["route_id", "shape_id"])
    _create_index_if_missing(bind, "idx_road_geometry_status_updated", "road_geometry_cache", ["status", "updated_at"])
    _create_index_if_missing(bind, "ix_complaint_status", "complaint", ["status"])
    _create_index_if_missing(bind, "ix_complaint_created_at", "complaint", ["created_at"])


def downgrade():
    bind = op.get_bind()

    for table_name, index_name in [
        ("complaint", "ix_complaint_created_at"),
        ("complaint", "ix_complaint_status"),
        ("road_geometry_cache", "idx_road_geometry_status_updated"),
        ("road_geometry_cache", "idx_road_geometry_route_shape"),
        ("sos_alert", "idx_sos_bus_status"),
        ("sos_alert", "idx_sos_status_triggered"),
        ("notifications", "idx_notification_recipient_read_created"),
        ("subscriptions", "uq_subscription_user_stop"),
        ("bus_occupancy", "idx_bus_occupancy_trip_recorded"),
        ("bus_occupancy", "idx_bus_occupancy_bus_recorded"),
        ("trips", "ix_trips_gtfs_trip_id"),
        ("trips", "idx_trip_bus_status"),
        ("trips", "idx_trip_shape_route"),
        ("trips", "idx_trip_route_status"),
        ("stop_times", "idx_stop_time_stop_trip"),
        ("stop_times", "idx_stop_time_trip_sequence"),
        ("stops", "idx_stops_code_location"),
        ("buses", "ix_buses_assigned_driver_code"),
        ("users", "ix_users_transpulse_id"),
    ]:
        _drop_index_if_exists(bind, index_name, table_name)
