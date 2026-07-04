from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from . import db


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    full_name = db.Column(
        db.String(120),
        nullable=False
    )

    email = db.Column(
        db.String(120),
        nullable=False,
        unique=True,
        index=True
    )

    # REQUIRED BY CURRENT APP.PY
    transpulse_id = db.Column(
        db.String(20),
        unique=True,
        nullable=True,
        index=True
    )

    password_hash = db.Column(
        db.String(255),
        nullable=False
    )

    role = db.Column(
        db.String(20),
        nullable=False,
        index=True
    )

    driver_code = db.Column(
        db.String(20),
        unique=True,
        nullable=True
    )

    is_active_user = db.Column(
        db.Boolean,
        default=True,
        nullable=False
    )

    auth_provider = db.Column(
        db.String(20),
        default="local",
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        server_default=db.func.now(),
        nullable=False
    )

    feedbacks = db.relationship(
        "Feedback",
        back_populates="user",
        lazy=True,
        cascade="all, delete-orphan"
    )

    notifications = db.relationship(
        "Notification",
        back_populates="recipient",
        lazy=True
    )

    complaints = db.relationship(
        "Complaint",
        foreign_keys="Complaint.passenger_id",
        back_populates="passenger",
        lazy=True
    )

    driver_complaints = db.relationship(
        "Complaint",
        foreign_keys="Complaint.driver_id",
        back_populates="driver",
        lazy=True
    )

    subscriptions = db.relationship(
        "Subscription",
        back_populates="user",
        lazy=True,
        cascade="all, delete-orphan"
    )

    assigned_buses = db.relationship(
        "Bus",
        foreign_keys="Bus.assigned_driver_id",
        back_populates="driver",
        lazy=True
    )

    lost_and_found_reports = db.relationship(
        "LostAndFound",
        foreign_keys="LostAndFound.user_id",
        back_populates="user",
        lazy=True,
        cascade="all, delete-orphan"
    )

    assigned_lost_and_found_items = db.relationship(
        "LostAndFound",
        foreign_keys="LostAndFound.assigned_driver_id",
        back_populates="assigned_driver",
        lazy=True
    )

    claimed_lost_and_found_items = db.relationship(
        "LostAndFound",
        foreign_keys="LostAndFound.claimed_by",
        back_populates="claimed_user",
        lazy=True
    )

    sos_alerts = db.relationship(
        "SOSAlert",
        foreign_keys="SOSAlert.passenger_id",
        back_populates="passenger",
        lazy=True
    )

    driver_sos_alerts = db.relationship(
        "SOSAlert",
        foreign_keys="SOSAlert.driver_id",
        back_populates="driver",
        lazy=True
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_active(self):
        return self.is_active_user

    def to_dict(self):
        return {
            "id": self.id,
            "full_name": self.full_name,
            "email": self.email,
            "transpulse_id": self.transpulse_id,
            "role": self.role,
            "driver_code": self.driver_code,
            "auth_provider": self.auth_provider,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

    def __repr__(self):
        return f"<User {self.email} ({self.role})>"
