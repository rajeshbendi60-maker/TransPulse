from datetime import datetime
from models import db


class Feedback(db.Model):
    __tablename__ = "feedback"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True
    )

    rating = db.Column(
        db.Integer,
        nullable=False,
        default=5
    )

    comments = db.Column(
        db.Text,
        nullable=True
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    user = db.relationship(
        "User",
        back_populates="feedbacks"
    )

    def __repr__(self):
        return f"<Feedback {self.id}>"

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "rating": self.rating,
            "comments": self.comments,
            "created_at": self.created_at.isoformat()
        }
