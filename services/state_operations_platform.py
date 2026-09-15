from extensions import db
from models.state_control import StateAlert, EmergencyBroadcast, ControlRoomLog, SystemHealthSnapshot
from services.district_operations_engine import district_operations_engine
from datetime import datetime
import time
import logging

logger = logging.getLogger(__name__)

class DashboardEngine:
    def get_state_metrics(self):
        # Mock aggregation across all 26 districts for Phase 6
        return {
            "districts": 26,
            "vehicles": {
                "running": 3250,
                "delayed": 142,
                "maintenance": 81,
                "offline": 19
            },
            "drivers": {
                "on_duty": 3187,
                "break": 43,
                "sos": 2
            },
            "passengers": {
                "active": 18420
            },
            "average_eta_delay_mins": 2.3,
            "critical_incidents": 5
        }

class DistrictAggregator:
    def get_districts_overview(self):
        # List of districts
        return [
            {"id": 1, "name": "Visakhapatnam", "fleet_health": 95, "incidents": 2},
            {"id": 2, "name": "Vijayawada", "fleet_health": 88, "incidents": 5}
        ]

class FleetAggregator:
    def get_live_state_fleet(self, filters=None):
        # Generate 3000 mock vehicles for map testing
        import random
        vehicles = []
        base_lat, base_lon = 17.3850, 78.4867
        for i in range(3000):
            vehicles.append({
                "busId": i,
                "lat": base_lat + (random.random() - 0.5) * 2,
                "lon": base_lon + (random.random() - 0.5) * 2,
                "status": random.choice(["RUNNING", "DELAYED", "STOPPED"]),
                "routeId": f"route_{i%100}",
                "speed": random.randint(0, 60),
                "delay": random.randint(0, 5)
            })
        return vehicles

class EmergencyEngine:
    def get_sos_and_critical(self):
        return [
            {"id": "sos_1", "priority": "CRITICAL", "category": "SOS", "district": "Visakhapatnam"}
        ]
        
    def resolve_alert(self, alert_id, admin_id):
        return True

class BroadcastEngine:
    def send_broadcast(self, admin_id, target_type, target_id, message, priority, ip_address):
        broadcast = EmergencyBroadcast(
            admin_id=admin_id,
            message=message,
            target_type=target_type,
            target_id=target_id,
            priority=priority
        )
        db.session.add(broadcast)
        
        log = ControlRoomLog(
            operator_id=admin_id,
            action="BROADCAST",
            target_id=target_type,
            details=f"Sent {priority} broadcast to {target_type}: {message}",
            ip_address=ip_address
        )
        db.session.add(log)
        db.session.commit()
        return broadcast

class HealthEngine:
    def capture_system_health(self):
        # Real lightweight pinging
        start_time = time.time()
        # Mocking DB ping
        db.session.execute("SELECT 1")
        db_latency = int((time.time() - start_time) * 1000)
        
        health = SystemHealthSnapshot(
            api_response_time_ms=db_latency + 10, # Mock API latency
            db_latency_ms=db_latency,
            gps_upload_rate=450, # records per sec
            online_drivers=3187,
            online_vehicles=3250,
            live_transit_status="HEALTHY",
            eta_engine_status="HEALTHY",
            journey_planner_status="HEALTHY"
        )
        db.session.add(health)
        db.session.commit()
        return health

class AnalyticsAggregator:
    def get_trends(self):
        pass

class StateOperationsPlatform:
    def __init__(self):
        self.dashboard_engine = DashboardEngine()
        self.district_aggregator = DistrictAggregator()
        self.fleet_aggregator = FleetAggregator()
        self.emergency_engine = EmergencyEngine()
        self.broadcast_engine = BroadcastEngine()
        self.health_engine = HealthEngine()
        self.analytics_aggregator = AnalyticsAggregator()

state_operations_platform = StateOperationsPlatform()
