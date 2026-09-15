from extensions import db
import uuid
from datetime import datetime

class Journey(db.Model):
    __tablename__ = 'journeys'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # GTFS References
    route_id = db.Column(db.String(100), nullable=True)
    trip_id = db.Column(db.String(100), nullable=True) # GTFS Trip
    
    # Real-time / Live Tracking (Future)
    vehicle_id = db.Column(db.String(100), nullable=True)
    driver_id = db.Column(db.String(36), nullable=True)
    
    # Origin and Destination
    origin_stop_id = db.Column(db.String(100), nullable=True)
    destination_stop_id = db.Column(db.String(100), nullable=True)
    origin_stop_name = db.Column(db.String(255), nullable=True)
    destination_stop_name = db.Column(db.String(255), nullable=True)
    
    # Route details
    route_number = db.Column(db.String(50), nullable=True)
    route_name = db.Column(db.String(255), nullable=True)
    
    # Timings
    departure_time = db.Column(db.DateTime, nullable=True)
    arrival_time = db.Column(db.DateTime, nullable=True)
    travel_date = db.Column(db.Date, nullable=False, default=datetime.utcnow().date)
    travel_duration = db.Column(db.Integer, nullable=True) # in seconds
    
    # Metrics
    distance_km = db.Column(db.Float, nullable=True)
    fare = db.Column(db.Float, nullable=True)
    
    # Status: PLANNED, IN_PROGRESS, COMPLETED, CANCELLED, INTERRUPTED, MISSED
    journey_status = db.Column(db.String(50), nullable=False, default="PLANNED")
    eta_difference = db.Column(db.Integer, nullable=True) # in seconds (positive = early, negative = delayed)
    travel_mode = db.Column(db.String(50), nullable=True, default="BUS")
    
    # Sync metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    device_id = db.Column(db.String(255), nullable=True)

    # Relationships
    user = db.relationship('User', back_populates='journeys')

    def __repr__(self):
        return f"<Journey {self.id} Route {self.route_number} Status {self.journey_status}>"
