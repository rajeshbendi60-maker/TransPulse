from datetime import datetime

from . import db


class RoadGeometryCache(db.Model):
    __tablename__ = "road_geometry_cache"

    id = db.Column(db.Integer, primary_key=True)

    cache_key = db.Column(
        db.String(64),
        unique=True,
        nullable=False,
        index=True
    )

    route_id = db.Column(
        db.Integer,
        nullable=True
    )

    shape_id = db.Column(
        db.String(120),
        nullable=True
    )

    stop_signature = db.Column(
        db.String(64),
        nullable=False
    )

    geometry_json = db.Column(
        db.Text,
        nullable=True
    )

    leg_end_indexes_json = db.Column(
        db.Text,
        nullable=True
    )

    status = db.Column(
        db.String(16),
        default="pending",
        nullable=False
    )

    last_error = db.Column(
        db.String(255),
        nullable=True
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    __table_args__ = (
        db.Index("idx_road_geometry_route_shape", "route_id", "shape_id"),
        db.Index("idx_road_geometry_status_updated", "status", "updated_at"),
    )

    def __repr__(self):
        return f"<RoadGeometryCache {self.cache_key}>"
