from database.models import db

class Route(db.Model):
    __tablename__ = "routes"

    id = db.Column(db.Integer, primary_key=True)
    route_code = db.Column(db.String(30), nullable=False, unique=True, index=True)
    name = db.Column(db.String(120), nullable=False)
    origin = db.Column(db.String(120), nullable=False)
    destination = db.Column(db.String(120), nullable=False)
    distance_km = db.Column(db.Float, nullable=False)
    departure_time = db.Column(db.String(20), nullable=True)
    arrival_time = db.Column(db.String(20), nullable=True)
    is_operational = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)

    # --- GTFS PREPARATION FIELDS ---
    route_long_name = db.Column(db.String(255), nullable=True)
    route_type = db.Column(db.Integer, nullable=True, default=3)  # 3 = Bus
    route_url = db.Column(db.String(255), nullable=True)
    route_color = db.Column(db.String(6), nullable=True)
    route_text_color = db.Column(db.String(6), nullable=True)

    trips = db.relationship("Trip", back_populates="route", lazy=True)
    buses = db.relationship("Bus", back_populates="route", lazy=True)
    complaints = db.relationship("models.complaint.Complaint", back_populates="route", lazy=True)
    lost_and_found_items = db.relationship("LostAndFound", back_populates="route", lazy=True)
    sos_alerts = db.relationship("SOSAlert", back_populates="route", lazy=True)

    @property
    def route_name(self):
        return self.name

    @route_name.setter
    def route_name(self, value):
        self.name = value

    @property
    def intermediate_stops(self):
        # Try to get the manual template trip first
        trip = next((t for t in self.trips if t.gtfs_trip_id == f"TRIP_MANUAL_{self.id}_001"), None)
        
        # If no manual trip, fallback to any trip (e.g. for GTFS routes)
        if not trip and self.trips:
            trip = self.trips[0]
            
        if not trip:
            return ""
        
        stops = sorted(trip.stop_times, key=lambda st: st.stop_sequence)
        if len(stops) <= 2:
            return ""
            
        names = [st.stop.stop_name for st in stops[1:-1] if st.stop]
        return ", ".join(names)

    def __repr__(self) -> str:
        return f"<Route {self.route_code}>"
# TP-v2.0-Release
