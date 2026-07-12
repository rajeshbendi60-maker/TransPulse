from models import db
from models import db


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    trip_id = db.Column(db.Integer, db.ForeignKey("trips.id"), nullable=True, index=True)
    
    title = db.Column(db.String(100), nullable=False, default="Notification")
    message = db.Column(db.String(300), nullable=False)
    type = db.Column(db.String(50), default="system")
    priority = db.Column(db.String(20), default="info")
    target_role = db.Column(db.String(20), nullable=True, index=True)
    related_bus_id = db.Column(db.Integer, db.ForeignKey("buses.id"), nullable=True, index=True)
    related_route_id = db.Column(db.Integer, db.ForeignKey("routes.id"), nullable=True, index=True)
    
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False, index=True)

    recipient = db.relationship("User", back_populates="notifications")
    trip = db.relationship("Trip", back_populates="notifications")
    related_bus = db.relationship("Bus", backref="notifications")
    related_route = db.relationship("Route", backref="notifications")

    __table_args__ = (
        db.Index("idx_notification_recipient_read_created", "recipient_id", "is_read", "created_at"),
    )

    def __init__(self, **kwargs):
        if "message" in kwargs and "title" not in kwargs:
            msg = kwargs["message"]
            title = "Notification"
            if msg.startswith("["):
                end = msg.find("]")
                if end > 1:
                    title = msg[1:end].title()
                    # Strip the prefix from the message for cleaner display
                    # kwargs["message"] = msg[end+1:].strip()
            elif "Delay" in msg:
                title = "Service Delay"
            elif "Complaint" in msg:
                title = "Complaint Update"
            elif "Lost" in msg:
                title = "Lost & Found Update"
            elif "SOS" in msg or "Emergency" in msg:
                title = "Emergency Alert"
            kwargs.setdefault("title", title)

        if "message" in kwargs and "type" not in kwargs:
            msg = kwargs["message"].lower()
            if "admin" in msg or "review it" in msg or "resolved by transport administration" in msg:
                kwargs["type"] = "admin"
            elif "driver" in msg or "duty pilot" in msg:
                kwargs["type"] = "driver"
            elif "passenger" in msg or "your " in msg:
                kwargs["type"] = "passenger"
            else:
                kwargs["type"] = "system"

        if "message" in kwargs and "priority" not in kwargs:
            msg = kwargs["message"].lower()
            if "sos" in msg or "emergency" in msg or "critical" in msg:
                kwargs["priority"] = "error"
            elif "delay" in msg or "offline" in msg or "warning" in msg:
                kwargs["priority"] = "warning"
            elif "resolved" in msg or "found" in msg or "success" in msg or "online" in msg:
                kwargs["priority"] = "success"
            else:
                kwargs["priority"] = "info"

        super(Notification, self).__init__(**kwargs)

    def __repr__(self) -> str:
        return f"<Notification to={self.recipient_id or self.target_role}>"

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "message": self.message,
            "type": self.type,
            "priority": self.priority,
            "is_read": self.is_read,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "related_bus_id": self.related_bus_id,
            "related_route_id": self.related_route_id
        }
