from datetime import datetime
from models import db


class Bus(db.Model):
    __tablename__ = "buses"

    id = db.Column(db.Integer, primary_key=True)

    bus_number = db.Column(
        db.String(50),
        unique=True,
        nullable=False
    )

    registration_number = db.Column(
        db.String(50),
        unique=True,
        nullable=False
    )

    capacity = db.Column(
        db.Integer,
        nullable=False
    )

    assigned_driver_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=True
    )

    assigned_driver_code = db.Column(
        db.String(20),
        unique=True,
        nullable=True,
        index=True
    )

    assigned_driver_name = db.Column(
        db.String(120),
        nullable=True
    )

    route_id = db.Column(
        db.Integer,
        db.ForeignKey("routes.id"),
        nullable=True
    )

    is_active = db.Column(
        db.Boolean,
        default=True,
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    driver = db.relationship(
        "User",
        foreign_keys=[assigned_driver_id],
        back_populates="assigned_buses"
    )

    route = db.relationship(
        "Route",
        foreign_keys=[route_id],
        back_populates="buses",
        lazy=True
    )

    trips = db.relationship(
        "Trip",
        back_populates="bus",
        lazy=True,
        cascade="all, delete-orphan"
    )

    complaints = db.relationship(
        "Complaint",
        back_populates="bus",
        lazy=True
    )

    lost_and_found_items = db.relationship(
        "LostAndFound",
        back_populates="bus",
        lazy=True
    )

    sos_alerts = db.relationship(
        "SOSAlert",
        back_populates="bus",
        lazy=True
    )

    occupancy_records = db.relationship(
        "BusOccupancy",
        back_populates="bus",
        lazy=True,
        cascade="all, delete-orphan"
    )

    def to_dict(self):
        return {
            "id": self.id,
            "bus_number": self.bus_number,
            "registration_number": self.registration_number,
            "capacity": self.capacity,
            "assigned_driver_id": self.assigned_driver_id,
            "assigned_driver_code": self.assigned_driver_code,
            "assigned_driver_name": self.assigned_driver_name,
            "route_id": self.route_id,
            "is_active": self.is_active,
            "created_at": (
                self.created_at.isoformat()
                if self.created_at
                else None
            )
        }

    def __repr__(self):
        return f"<Bus {self.bus_number}>"
