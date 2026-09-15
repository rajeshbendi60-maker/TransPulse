from extensions import db
from datetime import datetime
import uuid

class ShiftLifecycle:
    OFF_DUTY = "OFF_DUTY"
    ON_DUTY = "ON_DUTY"
    PRE_TRIP_INSPECTION = "PRE_TRIP_INSPECTION"
    READY = "READY"
    TRIP_ACTIVE = "TRIP_ACTIVE"
    BREAK = "BREAK"
    TRIP_RESUMED = "TRIP_RESUMED"
    TRIP_COMPLETED = "TRIP_COMPLETED"
    SHIFT_COMPLETED = "SHIFT_COMPLETED"

class TripLifecycle:
    ASSIGNED = "ASSIGNED"
    READY = "READY"
    STARTED = "STARTED"
    EN_ROUTE = "EN_ROUTE"
    AT_STOP = "AT_STOP"
    BREAK = "BREAK"
    RESUMED = "RESUMED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"

class IncidentCategory:
    BREAKDOWN = "BREAKDOWN"
    ACCIDENT = "ACCIDENT"
    TRAFFIC = "TRAFFIC"
    MEDICAL_EMERGENCY = "MEDICAL_EMERGENCY"
    ROAD_BLOCK = "ROAD_BLOCK"
    VEHICLE_ISSUE = "VEHICLE_ISSUE"
    PASSENGER_ISSUE = "PASSENGER_ISSUE"
    OTHER = "OTHER"

class DriverSession(db.Model):
    __tablename__ = 'driver_sessions'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    driver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    bus_id = db.Column(db.Integer, db.ForeignKey('buses.id'), nullable=True) # Assigned by District Admin
    status = db.Column(db.String(50), default=ShiftLifecycle.OFF_DUTY)
    started_at = db.Column(db.DateTime, nullable=True)
    ended_at = db.Column(db.DateTime, nullable=True)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class TripLog(db.Model):
    __tablename__ = 'trip_logs'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = db.Column(db.String(36), db.ForeignKey('driver_sessions.id'), nullable=False)
    trip_id = db.Column(db.String(100), nullable=False) # GTFS Trip ID
    status = db.Column(db.String(50), default=TripLifecycle.ASSIGNED)
    started_at = db.Column(db.DateTime, nullable=True)
    ended_at = db.Column(db.DateTime, nullable=True)

class VehicleInspection(db.Model):
    __tablename__ = 'vehicle_inspections'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = db.Column(db.String(36), db.ForeignKey('driver_sessions.id'), nullable=False)
    bus_id = db.Column(db.Integer, nullable=False)
    brakes_ok = db.Column(db.Boolean, default=False)
    lights_ok = db.Column(db.Boolean, default=False)
    tyres_ok = db.Column(db.Boolean, default=False)
    horn_ok = db.Column(db.Boolean, default=False)
    gps_ok = db.Column(db.Boolean, default=False)
    fuel_ok = db.Column(db.Boolean, default=False)
    remarks = db.Column(db.Text, nullable=True)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)

class IncidentReport(db.Model):
    __tablename__ = 'incident_reports'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    driver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    bus_id = db.Column(db.Integer, nullable=True)
    category = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text, nullable=False)
    lat = db.Column(db.Float, nullable=True)
    lon = db.Column(db.Float, nullable=True)
    reported_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(50), default="OPEN")
