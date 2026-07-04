from models import db

class Calendar(db.Model):
    __tablename__ = "calendar"
    
    id = db.Column(db.Integer, primary_key=True)
    service_id = db.Column(db.String(120), index=True, nullable=False)
    monday = db.Column(db.Integer, nullable=False)
    tuesday = db.Column(db.Integer, nullable=False)
    wednesday = db.Column(db.Integer, nullable=False)
    thursday = db.Column(db.Integer, nullable=False)
    friday = db.Column(db.Integer, nullable=False)
    saturday = db.Column(db.Integer, nullable=False)
    sunday = db.Column(db.Integer, nullable=False)
    start_date = db.Column(db.String(20), nullable=False)
    end_date = db.Column(db.String(20), nullable=False)

    def __repr__(self) -> str:
        return f"<Calendar Service {self.service_id}>"