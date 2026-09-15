from models import db

class Stop(db.Model):
    __tablename__ = "stops"

    id = db.Column(db.Integer, primary_key=True)
    stop_name = db.Column(db.String(120), nullable=False)
    eta_minutes = db.Column(db.Integer, nullable=True, default=0)
    scheduled_arrival_time = db.Column(db.String(20), nullable=True)
    scheduled_departure_time = db.Column(db.String(20), nullable=True)

    # --- GTFS PREPARATION FIELDS ---
    stop_code = db.Column(db.String(120), nullable=True, index=True)
    stop_desc = db.Column(db.String(255), nullable=True)
    stop_lat = db.Column(db.Float, nullable=True)
    stop_lon = db.Column(db.Float, nullable=True)
    zone_id = db.Column(db.String(120), nullable=True)
    stop_url = db.Column(db.String(255), nullable=True)
    location_type = db.Column(db.Integer, nullable=True, default=0)
    parent_station = db.Column(db.String(120), nullable=True)

    stop_times = db.relationship("StopTime", back_populates="stop", lazy=True, cascade="all, delete-orphan")
    subscriptions = db.relationship("Subscription", back_populates="stop", lazy=True, cascade="all, delete-orphan")

    __table_args__ = (
        db.Index("idx_stops_code_location", "stop_code", "stop_lat", "stop_lon"),
    )

    def __repr__(self) -> str:
        return f"<Stop {self.stop_name}>"

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

    __table_args__ = (
        db.UniqueConstraint("trip_id", "stop_sequence", name="uq_stop_time_trip_sequence"),
        db.Index("idx_stop_time_trip_sequence", "trip_id", "stop_sequence"),
        db.Index("idx_stop_time_stop_trip", "stop_id", "trip_id"),
    )
# TP-v2.0-Release
