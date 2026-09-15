from extensions import db
from datetime import datetime

class PredictionSnapshot(db.Model):
    __tablename__ = 'prediction_snapshots'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    domain = db.Column(db.String(50), nullable=False) # ETA, Demand, Maintenance
    prediction = db.Column(db.String(255), nullable=False)
    confidence = db.Column(db.Float, nullable=False)
    reason = db.Column(db.Text, nullable=False)
    factors = db.Column(db.JSON, nullable=False)
    recommendation = db.Column(db.String(255), nullable=True)
    model_version = db.Column(db.String(50), default="v1.0.0-deterministic") # For model versioning
    actual_outcome = db.Column(db.String(255), nullable=True) # For tracking accuracy over time
    user_feedback = db.Column(db.Integer, nullable=True) # 1 for Useful, -1 for Not Useful
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class AnomalyEvent(db.Model):
    __tablename__ = 'anomaly_events'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    anomaly_type = db.Column(db.String(100), nullable=False) # GPS Disappeared, Passenger Surge
    severity = db.Column(db.String(20), nullable=False)
    description = db.Column(db.Text, nullable=False)
    detected_at = db.Column(db.DateTime, default=datetime.utcnow)
    resolved = db.Column(db.Boolean, default=False)

class AiConversation(db.Model):
    __tablename__ = 'ai_conversations'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, nullable=False)
    role = db.Column(db.String(20), nullable=False) # Passenger, Driver, Admin
    prompt = db.Column(db.Text, nullable=False)
    response = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
# TP-v2.0-Release
