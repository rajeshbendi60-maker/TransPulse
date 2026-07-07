from models import db
from datetime import datetime

class SOSAlert(db.Model):
    __tablename__ = 'sos_alert'

    id = db.Column(db.Integer, primary_key=True)
    passenger_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    bus_id = db.Column(db.Integer, db.ForeignKey('buses.id'), nullable=False, index=True)
    route_id = db.Column(db.Integer, db.ForeignKey('routes.id'), nullable=False, index=True)
    driver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)

    reason = db.Column(db.String(200), nullable=True)
    description = db.Column(db.Text, nullable=True)
    severity = db.Column(db.String(20), default='medium')

    triggered_at = db.Column(db.DateTime, default=datetime.utcnow)
    acknowledged_at = db.Column(db.DateTime, nullable=True)
    resolved_at = db.Column(db.DateTime, nullable=True)

    status = db.Column(db.String(20), default='active', index=True)

    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)

    admin_notes = db.Column(db.Text, nullable=True)

    passenger = db.relationship("User", foreign_keys=[passenger_id], back_populates="sos_alerts")
    driver = db.relationship("User", foreign_keys=[driver_id], back_populates="driver_sos_alerts")
    bus = db.relationship("Bus", back_populates="sos_alerts")
    route = db.relationship("Route", back_populates="sos_alerts")

    __table_args__ = (
        db.Index("idx_sos_status_triggered", "status", "triggered_at"),
        db.Index("idx_sos_bus_status", "bus_id", "status"),
    )

    def __repr__(self):
        return f'<SOSAlert {self.id} - {self.severity}>'

    def to_dict(self):
        return {
            'id': self.id,
            'passenger_id': self.passenger_id,
            'bus_id': self.bus_id,
            'route_id': self.route_id,
            'driver_id': self.driver_id,
            'reason': self.reason,
            'description': self.description,
            'severity': self.severity,
            'triggered_at': self.triggered_at.isoformat(),
            'acknowledged_at': self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None,
            'status': self.status,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'admin_notes': self.admin_notes
        }
