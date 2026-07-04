from models import db

class Stop(db.Model):
    __tablename__ = "stops"

    id = db.Column(db.Integer, primary_key=True)
    route_id = db.Column(db.Integer, db.ForeignKey("routes.id"), nullable=True, index=True)
    stop_name = db.Column(db.String(120), nullable=False)
    stop_order = db.Column(db.Integer, nullable=True)
    eta_minutes = db.Column(db.Integer, nullable=True, default=0)
    scheduled_arrival_time = db.Column(db.String(20), nullable=True)
    scheduled_departure_time = db.Column(db.String(20), nullable=True)

    # --- GTFS PREPARATION FIELDS ---
    stop_code = db.Column(db.String(50), nullable=True, index=True)
    stop_desc = db.Column(db.String(255), nullable=True)
    stop_lat = db.Column(db.Float, nullable=True)
    stop_lon = db.Column(db.Float, nullable=True)
    zone_id = db.Column(db.String(50), nullable=True)
    stop_url = db.Column(db.String(255), nullable=True)
    location_type = db.Column(db.Integer, nullable=True, default=0)
    parent_station = db.Column(db.String(50), nullable=True)

    route = db.relationship("Route", back_populates="stops")
    stop_times = db.relationship("StopTime", back_populates="stop", lazy=True, cascade="all, delete-orphan")
    subscriptions = db.relationship("Subscription", back_populates="stop", lazy=True, cascade="all, delete-orphan")

    __table_args__ = (
        db.UniqueConstraint("route_id", "stop_order", name="uq_stop_route_order"),
    )

    def __repr__(self) -> str:
        return f"<Stop {self.stop_name} ({self.route_id})>"

class StopTime(db.Model):
    __tablename__ = "stop_times"

    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.Integer, db.ForeignKey("trips.id"), nullable=False, index=True)
    stop_id = db.Column(db.Integer, db.ForeignKey("stops.id"), nullable=False, index=True)
    arrival_time = db.Column(db.String(20), nullable=False)
    departure_time = db.Column(db.String(20), nullable=False)
    stop_sequence = db.Column(db.Integer, nullable=False)
    
    trip = db.relationship("Trip", back_populates="stop_times")
    stop = db.relationship("Stop", back_populates="stop_times")
