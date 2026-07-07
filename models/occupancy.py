from models import db
from datetime import datetime

class BusOccupancy(db.Model):
    __tablename__ = 'bus_occupancy'
    
    id = db.Column(db.Integer, primary_key=True)
    bus_id = db.Column(db.Integer, db.ForeignKey('buses.id'), nullable=False, index=True)
    trip_id = db.Column(db.Integer, db.ForeignKey('trips.id'), nullable=False, index=True)
    
    total_seats = db.Column(db.Integer, nullable=False)
    occupied_seats = db.Column(db.Integer, default=0)
    
    occupancy_level = db.Column(db.String(20), default='low')  # low, medium, high
    occupancy_percentage = db.Column(db.Float, default=0.0)
    
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow)

    bus = db.relationship("Bus", back_populates="occupancy_records")
    trip = db.relationship("Trip", back_populates="occupancy_records")

    __table_args__ = (
        db.Index("idx_bus_occupancy_bus_recorded", "bus_id", "recorded_at"),
        db.Index("idx_bus_occupancy_trip_recorded", "trip_id", "recorded_at"),
    )
    
    def __repr__(self):
        return f'<BusOccupancy {self.bus_id} - {self.occupancy_level}>'
    
    def calculate_level(self):
        if self.total_seats > 0:
            self.occupancy_percentage = (self.occupied_seats / self.total_seats) * 100
            if self.occupancy_percentage < 40:
                self.occupancy_level = 'low'
            elif self.occupancy_percentage < 70:
                self.occupancy_level = 'medium'
            else:
                self.occupancy_level = 'high'
    
    def to_dict(self):
        return {
            'id': self.id,
            'bus_id': self.bus_id,
            'trip_id': self.trip_id,
            'total_seats': self.total_seats,
            'occupied_seats': self.occupied_seats,
            'available_seats': self.total_seats - self.occupied_seats,
            'occupancy_level': self.occupancy_level,
            'occupancy_percentage': round(self.occupancy_percentage, 2) if self.occupancy_percentage is not None else 0,
            'recorded_at': self.recorded_at.isoformat() if self.recorded_at else None
        }
