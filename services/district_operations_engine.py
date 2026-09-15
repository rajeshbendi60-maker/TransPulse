from extensions import db
from models.district_admin import Depot, BusAllocation, DriverAllocation, ShiftAssignment, AuditLog, VehicleStatus, DriverStatus, AssignmentStatus
from models.live_transit import VehiclePosition
from models.driver_operations import IncidentReport
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class FleetEngine:
    def get_district_fleet_metrics(self, district_id):
        # Mocking for Phase 5
        return {
            "total": 120,
            "running": 98,
            "delayed": 8,
            "maintenance": 10,
            "offline": 4
        }
        
    def get_live_fleet_positions(self, depot_id):
        # Forward to Live Transit Engine, filtered by depot allocations
        return []

class AssignmentEngine:
    def create_assignment(self, driver_id, bus_id, route_id, depot_id, admin_id, scheduled_date):
        # 1. Validation
        existing_driver = ShiftAssignment.query.filter_by(
            driver_id=driver_id, scheduled_date=scheduled_date, status=AssignmentStatus.ACCEPTED
        ).first()
        if existing_driver:
            raise ValueError("Driver already assigned and accepted for this date")
            
        existing_bus = ShiftAssignment.query.filter_by(
            bus_id=bus_id, scheduled_date=scheduled_date, status=AssignmentStatus.ACCEPTED
        ).first()
        if existing_bus:
            raise ValueError("Bus already assigned and accepted for this date")
            
        assignment = ShiftAssignment(
            driver_id=driver_id,
            bus_id=bus_id,
            route_id=route_id,
            depot_id=depot_id,
            assigned_by=admin_id,
            scheduled_date=scheduled_date,
            status=AssignmentStatus.PENDING
        )
        db.session.add(assignment)
        
        # Log audit
        audit = AuditLog(
            admin_id=admin_id,
            action="CREATE_ASSIGNMENT",
            target_id=str(assignment.id),
            details=f"Assigned Driver {driver_id} to Bus {bus_id} on Route {route_id}",
            ip_address="127.0.0.1" # Mock IP
        )
        db.session.add(audit)
        
        db.session.commit()
        return assignment

class DriverEngine:
    def get_driver_metrics(self, district_id):
        return {
            "on_duty": 102,
            "break": 5,
            "inspection": 2,
            "sos": 1
        }

class IncidentAdminEngine:
    def get_incident_metrics(self, district_id):
        return {
            "critical": 1,
            "high": 3,
            "medium": 5,
            "low": 8
        }
        
    def resolve_incident(self, incident_id, admin_id):
        incident = IncidentReport.query.get(incident_id)
        if not incident:
            raise ValueError("Incident not found")
            
        incident.status = "RESOLVED"
        
        audit = AuditLog(
            admin_id=admin_id,
            action="RESOLVE_INCIDENT",
            target_id=incident_id
        )
        db.session.add(audit)
        db.session.commit()
        return True

class DistrictOperationsEngine:
    def __init__(self):
        self.fleet_engine = FleetEngine()
        self.assignment_engine = AssignmentEngine()
        self.driver_engine = DriverEngine()
        self.incident_engine = IncidentAdminEngine()

district_operations_engine = DistrictOperationsEngine()
