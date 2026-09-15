from extensions import db
from models.driver_operations import DriverSession, TripLog, VehicleInspection, IncidentReport, ShiftLifecycle, TripLifecycle, IncidentCategory
from models.live_transit import VehiclePosition
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class ShiftEngine:
    def update_shift_status(self, session_id, new_status):
        session = DriverSession.query.get(session_id)
        if not session:
            raise ValueError("Session not found")
        
        session.status = new_status
        if new_status == ShiftLifecycle.ON_DUTY:
            session.started_at = datetime.utcnow()
        elif new_status == ShiftLifecycle.SHIFT_COMPLETED:
            session.ended_at = datetime.utcnow()
            
        db.session.commit()
        return session

class TripEngine:
    def update_trip_status(self, session_id, trip_id, new_status):
        trip_log = TripLog.query.filter_by(session_id=session_id, trip_id=trip_id).first()
        if not trip_log:
            # Create if assigned
            trip_log = TripLog(session_id=session_id, trip_id=trip_id)
            db.session.add(trip_log)
            
        trip_log.status = new_status
        if new_status == TripLifecycle.STARTED:
            trip_log.started_at = datetime.utcnow()
        elif new_status in [TripLifecycle.COMPLETED, TripLifecycle.CANCELLED]:
            trip_log.ended_at = datetime.utcnow()
            
        db.session.commit()
        return trip_log

class GpsEngine:
    def ingest_location(self, bus_id, lat, lon, heading, speed, accuracy):
        # Forward to Live Transit Engine
        from services.live_transit_engine import live_transit_engine
        return live_transit_engine.process_position_update(bus_id, lat, lon, heading, speed)

class InspectionEngine:
    def submit_inspection(self, session_id, bus_id, data):
        inspection = VehicleInspection(
            session_id=session_id,
            bus_id=bus_id,
            brakes_ok=data.get('brakes_ok', False),
            lights_ok=data.get('lights_ok', False),
            tyres_ok=data.get('tyres_ok', False),
            horn_ok=data.get('horn_ok', False),
            gps_ok=data.get('gps_ok', False),
            fuel_ok=data.get('fuel_ok', False),
            remarks=data.get('remarks')
        )
        db.session.add(inspection)
        db.session.commit()
        return inspection

class IncidentEngine:
    def report_incident(self, driver_id, bus_id, category, description, lat=None, lon=None):
        incident = IncidentReport(
            driver_id=driver_id,
            bus_id=bus_id,
            category=category,
            description=description,
            lat=lat,
            lon=lon
        )
        db.session.add(incident)
        db.session.commit()
        # TODO: Trigger control room notification
        return incident

class SosEngine:
    def trigger_sos(self, driver_id, bus_id, lat, lon):
        # Triggers high priority incident
        incident = IncidentReport(
            driver_id=driver_id,
            bus_id=bus_id,
            category=IncidentCategory.OTHER, # Maps to SOS internally or add SOS enum
            description="SOS TRIGGERED BY DRIVER",
            lat=lat,
            lon=lon,
            status="CRITICAL"
        )
        db.session.add(incident)
        db.session.commit()
        
        # TODO: Real-time broadcast to State Control Room & District Admin
        logger.critical(f"SOS Triggered by driver {driver_id} on bus {bus_id}")
        return incident

class DriverOperationsEngine:
    def __init__(self):
        self.shift_engine = ShiftEngine()
        self.trip_engine = TripEngine()
        self.gps_engine = GpsEngine()
        self.inspection_engine = InspectionEngine()
        self.incident_engine = IncidentEngine()
        self.sos_engine = SosEngine()

driver_operations_engine = DriverOperationsEngine()
# TP-v2.0-Release
