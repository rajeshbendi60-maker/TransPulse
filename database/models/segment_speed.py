from backend.extensions import db

class SegmentSpeed(db.Model):
    __tablename__ = 'segment_speed'
    
    id = db.Column(db.Integer, primary_key=True)
    route_id = db.Column(db.Integer, db.ForeignKey('routes.id', ondelete='CASCADE'), index=True, nullable=False)
    direction_id = db.Column(db.Integer, index=True, nullable=False)
    segment_index = db.Column(db.Integer, nullable=False)
    distance_km = db.Column(db.Float, nullable=False)
    historical_speed = db.Column(db.Float, default=20.0, nullable=False)
    
    __table_args__ = (
        db.UniqueConstraint('route_id', 'direction_id', 'segment_index', name='uix_route_dir_seg'),
    )
