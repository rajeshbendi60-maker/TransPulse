from models import db
from datetime import datetime

class Complaint(db.Model):
    __tablename__ = 'complaint'
    
    id = db.Column(db.Integer, primary_key=True)
    passenger_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    bus_id = db.Column(db.Integer, db.ForeignKey('buses.id'), nullable=True)
    route_id = db.Column(db.Integer, db.ForeignKey('routes.id'), nullable=True)
    driver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    complaint_type = db.Column(db.String(100), nullable=False)  
    description = db.Column(db.Text, nullable=False)
    severity = db.Column(db.String(20), default='medium')  
    status = db.Column(db.String(20), default='open')  # open, in progress, resolved, closed
    evidence_image = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime, nullable=True)
    
    admin_notes = db.Column(db.Text, nullable=True)
    
    # FIXED: Safely mapped to User model variables
    passenger = db.relationship("User", foreign_keys=[passenger_id], back_populates="complaints")
    driver = db.relationship("User", foreign_keys=[driver_id], back_populates="driver_complaints")
    bus = db.relationship("Bus", back_populates="complaints")
    route = db.relationship("Route", back_populates="complaints")
    
    def __repr__(self):
        return f'<Complaint {self.id} - {self.complaint_type}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'passenger_id': self.passenger_id,
            'bus_id': self.bus_id,
            'route_id': self.route_id,
            'driver_id': self.driver_id,
            'complaint_type': self.complaint_type,
            'description': self.description,
            'severity': self.severity,
            'status': self.status,
            'evidence_image': self.evidence_image,
            'created_at': self.created_at.isoformat(),
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None,
            'admin_notes': self.admin_notes
        }
