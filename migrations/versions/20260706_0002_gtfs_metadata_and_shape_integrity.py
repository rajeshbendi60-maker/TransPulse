"""gtfs metadata and shape integrity

Revision ID: 20260706_0002
Revises: 20260706_0001
Create Date: 2026-07-06
"""

from alembic import op
import sqlalchemy as sa

revision = "20260706_0002"
down_revision = "20260706_0001"
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


def _create_index_if_missing(bind, name, table_name, columns, unique=False, **kwargs):
    if table_name in _table_names(bind) and name not in _indexes(bind, table_name):
        op.create_index(name, table_name, columns, unique=unique, **kwargs)


def _drop_index_if_exists(bind, name, table_name):
    if table_name in _table_names(bind) and name in _indexes(bind, table_name):
        op.drop_index(name, table_name=table_name)


def upgrade():
    bind = op.get_bind()
    tables = _table_names(bind)

    created_calendar_dates = "calendar_dates" not in tables
    if created_calendar_dates:
        op.create_table(
            "calendar_dates",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("service_id", sa.String(length=120), nullable=False),
            sa.Column("date", sa.String(length=20), nullable=False),
            sa.Column("exception_type", sa.Integer(), nullable=False),
            sa.UniqueConstraint("service_id", "date", name="uq_calendar_date_service_date"),
        )
    else:
        bind.execute(sa.text(
            "DELETE FROM calendar_dates WHERE id NOT IN ("
            "SELECT MIN(id) FROM calendar_dates GROUP BY service_id, date)"
        ))
    _create_index_if_missing(bind, "ix_calendar_dates_service_id", "calendar_dates", ["service_id"])
    _create_index_if_missing(bind, "ix_calendar_dates_date", "calendar_dates", ["date"])
    if not created_calendar_dates:
        _create_index_if_missing(
            bind,
            "uq_calendar_date_service_date",
            "calendar_dates",
            ["service_id", "date"],
            unique=True,
        )

    if "feed_info" not in tables:
        op.create_table(
            "feed_info",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("feed_publisher_name", sa.String(length=255), nullable=False),
            sa.Column("feed_publisher_url", sa.String(length=255), nullable=False),
            sa.Column("feed_lang", sa.String(length=20), nullable=False),
            sa.Column("default_lang", sa.String(length=20), nullable=True),
            sa.Column("feed_start_date", sa.String(length=20), nullable=True),
            sa.Column("feed_end_date", sa.String(length=20), nullable=True),
            sa.Column("feed_version", sa.String(length=120), nullable=True),
            sa.Column("feed_contact_email", sa.String(length=255), nullable=True),
            sa.Column("feed_contact_url", sa.String(length=255), nullable=True),
        )
    _create_index_if_missing(bind, "ix_feed_info_feed_version", "feed_info", ["feed_version"])

    if "trips" in tables:
        trip_columns = _columns(bind, "trips")
        with op.batch_alter_table("trips") as batch_op:
            if "service_id" in trip_columns:
                batch_op.alter_column(
                    "service_id",
                    existing_type=sa.String(length=50),
                    type_=sa.String(length=120),
                    existing_nullable=True,
                )
            if "trip_short_name" in trip_columns:
                batch_op.alter_column(
                    "trip_short_name",
                    existing_type=sa.String(length=50),
                    type_=sa.String(length=120),
                    existing_nullable=True,
                )
            if "block_id" in trip_columns:
                batch_op.alter_column(
                    "block_id",
                    existing_type=sa.String(length=50),
                    type_=sa.String(length=120),
                    existing_nullable=True,
                )
            if "shape_id" in trip_columns:
                batch_op.alter_column(
                    "shape_id",
                    existing_type=sa.String(length=50),
                    type_=sa.String(length=120),
                    existing_nullable=True,
                )

    if "stops" in tables:
        stop_columns = _columns(bind, "stops")
        with op.batch_alter_table("stops") as batch_op:
            if "stop_code" in stop_columns:
                batch_op.alter_column(
                    "stop_code",
                    existing_type=sa.String(length=50),
                    type_=sa.String(length=120),
                    existing_nullable=True,
                )
            if "zone_id" in stop_columns:
                batch_op.alter_column(
                    "zone_id",
                    existing_type=sa.String(length=50),
                    type_=sa.String(length=120),
                    existing_nullable=True,
                )
            if "parent_station" in stop_columns:
                batch_op.alter_column(
                    "parent_station",
                    existing_type=sa.String(length=50),
                    type_=sa.String(length=120),
                    existing_nullable=True,
                )

    if "shapes" in tables:
        bind.execute(sa.text(
            "DELETE FROM shapes WHERE id NOT IN ("
            "SELECT MIN(id) FROM shapes GROUP BY shape_id, shape_pt_sequence)"
        ))
        _create_index_if_missing(bind, "uq_shape_id_sequence", "shapes", ["shape_id", "shape_pt_sequence"], unique=True)


def downgrade():
    bind = op.get_bind()
    _drop_index_if_exists(bind, "uq_shape_id_sequence", "shapes")
    _drop_index_if_exists(bind, "ix_feed_info_feed_version", "feed_info")
    _drop_index_if_exists(bind, "uq_calendar_date_service_date", "calendar_dates")
    _drop_index_if_exists(bind, "ix_calendar_dates_date", "calendar_dates")
    _drop_index_if_exists(bind, "ix_calendar_dates_service_id", "calendar_dates")
    if "feed_info" in _table_names(bind):
        op.drop_table("feed_info")
    if "calendar_dates" in _table_names(bind):
        op.drop_table("calendar_dates")
