from models import db
from datetime import datetime

class LostAndFound(db.Model):
    __tablename__ = 'lost_and_found'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    bus_id = db.Column(db.Integer, db.ForeignKey('buses.id'), nullable=False, index=True)
    route_id = db.Column(db.Integer, db.ForeignKey('routes.id'), nullable=False, index=True)
    
    item_type = db.Column(db.String(50), nullable=False)  # lost, found
    item_name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    
    color = db.Column(db.String(50), nullable=True)
    brand = db.Column(db.String(50), nullable=True)
    
    incident_date = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    contact_name = db.Column(db.String(100), nullable=False)
    contact_phone = db.Column(db.String(20), nullable=False)
    contact_email = db.Column(db.String(100), nullable=True)
    
    status = db.Column(db.String(20), default='open', index=True)  # open, claimed, resolved
    driver_reply = db.Column(db.Text, nullable=True)
    assigned_driver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    claimed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    claimed_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User", foreign_keys=[user_id], back_populates="lost_and_found_reports")
    bus = db.relationship("Bus", back_populates="lost_and_found_items")
    route = db.relationship("Route", back_populates="lost_and_found_items")
    assigned_driver = db.relationship("User", foreign_keys=[assigned_driver_id], back_populates="assigned_lost_and_found_items")
    claimed_user = db.relationship("User", foreign_keys=[claimed_by], back_populates="claimed_lost_and_found_items")
    
    def __repr__(self):
        return f'<LostAndFound {self.id} - {self.item_name}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'bus_id': self.bus_id,
            'route_id': self.route_id,
            'item_type': self.item_type,
            'item_name': self.item_name,
            'description': self.description,
            'color': self.color,
            'brand': self.brand,
            'incident_date': self.incident_date.isoformat(),
            'created_at': self.created_at.isoformat(),
            'contact_name': self.contact_name,
            'contact_phone': self.contact_phone,
            'contact_email': self.contact_email,
            'status': self.status,
            'driver_reply': self.driver_reply,
            'assigned_driver_id': self.assigned_driver_id,
            'claimed_by': self.claimed_by,
            'claimed_at': self.claimed_at.isoformat() if self.claimed_at else None
        }
