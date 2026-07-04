from models import db


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    trip_id = db.Column(db.Integer, db.ForeignKey("trips.id"), nullable=True, index=True)
    message = db.Column(db.String(300), nullable=False)
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)

    recipient = db.relationship("User", back_populates="notifications")
    trip = db.relationship("Trip", back_populates="notifications")

    def __repr__(self) -> str:
        return f"<Notification to={self.recipient_id}>"

