from models import db


class CalendarDate(db.Model):
    __tablename__ = "calendar_dates"

    id = db.Column(db.Integer, primary_key=True)
    service_id = db.Column(db.String(120), nullable=False, index=True)
    date = db.Column(db.String(20), nullable=False, index=True)
    exception_type = db.Column(db.Integer, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("service_id", "date", name="uq_calendar_date_service_date"),
    )

    def __repr__(self) -> str:
        return f"<CalendarDate {self.service_id} {self.date}>"
