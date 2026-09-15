from extensions import db
from models.analytics import DailyAnalytics, FleetMetrics, PassengerMetrics
from datetime import datetime, date

class KPIEngine:
    def get_live_dashboard_metrics(self):
        # In reality, this queries live tables for current states
        return {
            "passengers": {"value": 18240, "trend": "+8%"},
            "running_buses": {"value": 3241, "trend": "+2%"},
            "delayed": {"value": 146, "trend": "-5%"},
            "sos_events": {"value": 3, "trend": "0%"},
            "avg_eta_accuracy": {"value": "94%", "trend": "+1%"},
            "fleet_utilization": {"value": "91%", "trend": "+3%"},
            "complaints_resolved": {"value": "97%", "trend": "+2%"},
            "notification_delivery": {"value": "99%", "trend": "0%"}
        }

class ExportEngine:
    def export_pdf(self, metrics_data):
        # Mock PDF generation
        return "https://mock-storage.transpulse.com/reports/analytics_report.pdf"
        
    def export_excel(self, metrics_data):
        # Mock Excel generation
        return "https://mock-storage.transpulse.com/reports/analytics_report.xlsx"

    def export_csv(self, metrics_data):
        # Mock CSV generation
        return "https://mock-storage.transpulse.com/reports/analytics_report.csv"

class FleetAnalyticsEngine:
    def get_fleet_metrics(self, district_id=None):
        return [
            {"label": "Distance Covered", "value": 45000, "unit": "km"},
            {"label": "Maintenance Hours", "value": 120, "unit": "hrs"}
        ]

class HeatmapEngine:
    def get_density_data(self, map_type):
        # Returns GeoJSON points for MapLibre HeatmapLayer
        return {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "geometry": {"type": "Point", "coordinates": [78.4867, 17.3850]}, "properties": {"weight": 0.9}}
            ]
        }

class BusinessIntelligencePlatform:
    def __init__(self):
        self.kpi_engine = KPIEngine()
        self.fleet_engine = FleetAnalyticsEngine()
        self.heatmap_engine = HeatmapEngine()
        self.export_engine = ExportEngine()
        
    def generate_daily_snapshot(self):
        """Called by a background scheduler to pre-compute snapshots."""
        today = datetime.utcnow().date()
        existing = DailyAnalytics.query.filter_by(date=today).first()
        if not existing:
            snapshot = DailyAnalytics(
                date=today,
                total_passengers=18000,
                total_journeys=5400,
                avg_eta_accuracy=94.5,
                fleet_utilization=91.0
            )
            db.session.add(snapshot)
            db.session.commit()

bi_platform = BusinessIntelligencePlatform()
