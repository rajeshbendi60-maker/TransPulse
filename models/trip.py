from models import db

class Trip(db.Model):
    __tablename__ = "trips"

    id = db.Column(db.Integer, primary_key=True)
    bus_id = db.Column(db.Integer, db.ForeignKey("buses.id"), nullable=True, index=True)
    route_id = db.Column(db.Integer, db.ForeignKey("routes.id"), nullable=False, index=True)
    start_time = db.Column(db.DateTime, nullable=True)
    end_time = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(30), nullable=False, default="scheduled")
    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)

    # --- GTFS PREPARATION FIELDS ---
    service_id = db.Column(db.String(50), nullable=True, index=True)
    trip_headsign = db.Column(db.String(120), nullable=True)
    trip_short_name = db.Column(db.String(50), nullable=True)
    direction_id = db.Column(db.Integer, nullable=True)
    block_id = db.Column(db.String(50), nullable=True)
    shape_id = db.Column(db.String(50), nullable=True)
    wheelchair_accessible = db.Column(db.Integer, nullable=True, default=0)
    bikes_allowed = db.Column(db.Integer, nullable=True, default=0)
   
    bus = db.relationship("Bus", back_populates="trips")
    route = db.relationship("Route", back_populates="trips")
    notifications = db.relationship("Notification", back_populates="trip", lazy=True)
    stop_times = db.relationship("StopTime", back_populates="trip", lazy=True, cascade="all, delete-orphan")
    occupancy_records = db.relationship("BusOccupancy", back_populates="trip", lazy=True, cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Trip bus={self.bus_id} route={self.route_id} status={self.status}>"
