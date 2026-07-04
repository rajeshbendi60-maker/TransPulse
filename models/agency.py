from models import db

class Agency(db.Model):
    __tablename__ = "agency"
    
    id = db.Column(db.Integer, primary_key=True)
    agency_id = db.Column(db.String(120), index=True, nullable=True)
    agency_name = db.Column(db.String(120), nullable=False)
    agency_url = db.Column(db.String(255), nullable=False)
    agency_timezone = db.Column(db.String(50), nullable=False)
    agency_lang = db.Column(db.String(10), nullable=True)
    agency_phone = db.Column(db.String(50), nullable=True)

    def __repr__(self) -> str:
        return f"<Agency {self.agency_name}>"