from datetime import datetime

from models import db


class Subscription(db.Model):
    __tablename__ = "subscriptions"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True
    )

    stop_id = db.Column(
        db.Integer,
        db.ForeignKey("stops.id"),
        nullable=False,
        index=True
    )

    active = db.Column(db.Boolean, default=True, nullable=False)

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    user = db.relationship(
        "User",
        back_populates="subscriptions"
    )

    stop = db.relationship(
        "Stop",
        back_populates="subscriptions"
    )

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "stop_id": self.stop_id,
            "active": self.active,
            "created_at": self.created_at.isoformat()
        }

    def __repr__(self):
        return f"<Subscription User:{self.user_id} Stop:{self.stop_id}>"
