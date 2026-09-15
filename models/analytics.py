from extensions import db
from datetime import datetime

class DailyAnalytics(db.Model):
    __tablename__ = 'daily_analytics'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    date = db.Column(db.Date, nullable=False, unique=True)
    total_passengers = db.Column(db.Integer, default=0)
    total_journeys = db.Column(db.Integer, default=0)
    total_complaints_resolved = db.Column(db.Integer, default=0)
    avg_eta_accuracy = db.Column(db.Float, default=0.0)
    fleet_utilization = db.Column(db.Float, default=0.0)
    notification_delivery_rate = db.Column(db.Float, default=0.0)
    total_sos_events = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class WeeklyAnalytics(db.Model):
    __tablename__ = 'weekly_analytics'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    start_date = db.Column(db.Date, nullable=False, unique=True)
    total_passengers = db.Column(db.Integer, default=0)
    total_journeys = db.Column(db.Integer, default=0)
    avg_eta_accuracy = db.Column(db.Float, default=0.0)
    fleet_utilization = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class MonthlyAnalytics(db.Model):
    __tablename__ = 'monthly_analytics'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    month = db.Column(db.Integer, nullable=False)
    year = db.Column(db.Integer, nullable=False)
    total_passengers = db.Column(db.Integer, default=0)
    total_journeys = db.Column(db.Integer, default=0)
    avg_eta_accuracy = db.Column(db.Float, default=0.0)
    fleet_utilization = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
class YearlyAnalytics(db.Model):
    __tablename__ = 'yearly_analytics'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    year = db.Column(db.Integer, nullable=False, unique=True)
    total_passengers = db.Column(db.Integer, default=0)
    total_journeys = db.Column(db.Integer, default=0)
    avg_eta_accuracy = db.Column(db.Float, default=0.0)
    fleet_utilization = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class FleetMetrics(db.Model):
    __tablename__ = 'fleet_metrics'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    date = db.Column(db.Date, nullable=False)
    bus_id = db.Column(db.Integer, nullable=False)
    distance_covered = db.Column(db.Float, default=0.0)
    downtime_hours = db.Column(db.Float, default=0.0)
    maintenance_hours = db.Column(db.Float, default=0.0)

class PassengerMetrics(db.Model):
    __tablename__ = 'passenger_metrics'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    date = db.Column(db.Date, nullable=False)
    route_id = db.Column(db.String(100), nullable=False)
    passenger_count = db.Column(db.Integer, default=0)
# TP-v2.0-Release
