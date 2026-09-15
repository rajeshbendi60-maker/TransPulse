from extensions import db
from datetime import datetime
import uuid

class VehiclePosition(db.Model):
    __tablename__ = 'vehicle_positions'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    bus_id = db.Column(db.Integer, db.ForeignKey('buses.id'), nullable=False, index=True)
    
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    speed = db.Column(db.Float, nullable=True) # km/h
    heading = db.Column(db.Float, nullable=True) # degrees (0-360)
    accuracy = db.Column(db.Float, nullable=True) # meters
    bearing = db.Column(db.Float, nullable=True) # alternative to heading
    
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    status = db.Column(db.String(50), nullable=False, default="Stopped") # Running, Stopped, Idle, Delayed, Offline, Maintenance, Out Of Service
    
    bus = db.relationship("Bus", backref=db.backref("live_positions", lazy=True, cascade="all, delete-orphan"))


class TripAssignment(db.Model):
    __tablename__ = 'trip_assignments'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    bus_id = db.Column(db.Integer, db.ForeignKey('buses.id'), nullable=False, index=True)
    route_id = db.Column(db.String(100), nullable=False) # GTFS Route
    trip_id = db.Column(db.String(100), nullable=False) # GTFS Trip
    
    start_time = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    end_time = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True, index=True)
    
    bus = db.relationship("Bus", backref=db.backref("trip_assignments", lazy=True))


class RouteDeviationEvent(db.Model):
    __tablename__ = 'route_deviation_events'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    bus_id = db.Column(db.Integer, db.ForeignKey('buses.id'), nullable=False)
    trip_id = db.Column(db.String(100), nullable=False)
    
    deviation_distance = db.Column(db.Float, nullable=False) # meters
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    nearest_shape_point = db.Column(db.String(100), nullable=True)
    
    severity = db.Column(db.String(50), nullable=False) # Minor, Major, Critical
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    resolved = db.Column(db.Boolean, default=False)
    
    bus = db.relationship("Bus", backref=db.backref("deviations", lazy=True))
