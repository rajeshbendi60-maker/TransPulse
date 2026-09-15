from extensions import db
from datetime import datetime
import uuid

class BroadcastPriority:
    NORMAL = "NORMAL"
    IMPORTANT = "IMPORTANT"
    EMERGENCY = "EMERGENCY"

class BroadcastTarget:
    STATE = "STATE"
    DISTRICT = "DISTRICT"
    DEPOT = "DEPOT"
    ROUTE = "ROUTE"
    VEHICLE = "VEHICLE"
    DRIVERS = "DRIVERS"
    PASSENGERS = "PASSENGERS"

class StateAlert(db.Model):
    __tablename__ = 'state_alerts'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)
    priority = db.Column(db.String(50), nullable=False) # CRITICAL, HIGH
    source_district_id = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(50), default="OPEN")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class EmergencyBroadcast(db.Model):
    __tablename__ = 'emergency_broadcasts'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    admin_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    target_type = db.Column(db.String(50), nullable=False)
    target_id = db.Column(db.String(100), nullable=True)
    priority = db.Column(db.String(50), default=BroadcastPriority.EMERGENCY)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)

class ControlRoomLog(db.Model):
    __tablename__ = 'control_room_logs'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    operator_id = db.Column(db.Integer, nullable=False)
    action = db.Column(db.String(100), nullable=False)
    target_id = db.Column(db.String(100), nullable=True)
    details = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class SystemHealthSnapshot(db.Model):
    __tablename__ = 'system_health_snapshots'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    api_response_time_ms = db.Column(db.Integer, nullable=False)
    db_latency_ms = db.Column(db.Integer, nullable=False)
    gps_upload_rate = db.Column(db.Integer, nullable=False)
    online_drivers = db.Column(db.Integer, nullable=False)
    online_vehicles = db.Column(db.Integer, nullable=False)
    live_transit_status = db.Column(db.String(50), default="HEALTHY")
    eta_engine_status = db.Column(db.String(50), default="HEALTHY")
    journey_planner_status = db.Column(db.String(50), default="HEALTHY")
