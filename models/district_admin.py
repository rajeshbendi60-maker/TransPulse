from extensions import db
from datetime import datetime
import uuid

class VehicleStatus:
    RUNNING = "RUNNING"
    DELAYED = "DELAYED"
    STOPPED = "STOPPED"
    MAINTENANCE = "MAINTENANCE"
    OFFLINE = "OFFLINE"
    OUT_OF_SERVICE = "OUT_OF_SERVICE"

class DriverStatus:
    AVAILABLE = "AVAILABLE"
    DRIVING = "DRIVING"
    BREAK = "BREAK"
    INSPECTION = "INSPECTION"
    OFFLINE = "OFFLINE"
    SOS = "SOS"

class IncidentPriority:
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

class AssignmentStatus:
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"

class Depot(db.Model):
    __tablename__ = 'depots'
    id = db.Column(db.Integer, primary_key=True)
    district_id = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    lat = db.Column(db.Float, nullable=True)
    lon = db.Column(db.Float, nullable=True)

class BusAllocation(db.Model):
    __tablename__ = 'bus_allocations'
    id = db.Column(db.Integer, primary_key=True)
    bus_id = db.Column(db.Integer, db.ForeignKey('buses.id'), nullable=False)
    depot_id = db.Column(db.Integer, db.ForeignKey('depots.id'), nullable=False)
    status = db.Column(db.String(50), default=VehicleStatus.OFFLINE)

class DriverAllocation(db.Model):
    __tablename__ = 'driver_allocations'
    id = db.Column(db.Integer, primary_key=True)
    driver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    depot_id = db.Column(db.Integer, db.ForeignKey('depots.id'), nullable=False)
    status = db.Column(db.String(50), default=DriverStatus.OFFLINE)

class ShiftAssignment(db.Model):
    __tablename__ = 'shift_assignments'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    driver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    bus_id = db.Column(db.Integer, db.ForeignKey('buses.id'), nullable=False)
    route_id = db.Column(db.String(100), nullable=False)
    depot_id = db.Column(db.Integer, db.ForeignKey('depots.id'), nullable=False)
    assigned_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.String(50), default=AssignmentStatus.PENDING)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    scheduled_date = db.Column(db.Date, nullable=False)

class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    admin_id = db.Column(db.Integer, nullable=False)
    action = db.Column(db.String(100), nullable=False)
    target_id = db.Column(db.String(100), nullable=True)
    details = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
# TP-v2.0-Release
