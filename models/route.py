from models import db

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

    stops = db.relationship("Stop", back_populates="route", lazy=True, cascade="all, delete-orphan")
    trips = db.relationship("Trip", back_populates="route", lazy=True)
    buses = db.relationship("Bus", back_populates="route", lazy=True)
    complaints = db.relationship("Complaint", back_populates="route", lazy=True)
    lost_and_found_items = db.relationship("LostAndFound", back_populates="route", lazy=True)
    sos_alerts = db.relationship("SOSAlert", back_populates="route", lazy=True)

    def __repr__(self) -> str:
        return f"<Route {self.route_code}>"
