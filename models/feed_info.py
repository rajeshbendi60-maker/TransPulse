from models import db


class FeedInfo(db.Model):
    __tablename__ = "feed_info"

    id = db.Column(db.Integer, primary_key=True)
    feed_publisher_name = db.Column(db.String(255), nullable=False)
    feed_publisher_url = db.Column(db.String(255), nullable=False)
    feed_lang = db.Column(db.String(20), nullable=False)
    default_lang = db.Column(db.String(20), nullable=True)
    feed_start_date = db.Column(db.String(20), nullable=True)
    feed_end_date = db.Column(db.String(20), nullable=True)
    feed_version = db.Column(db.String(120), nullable=True, index=True)
    feed_contact_email = db.Column(db.String(255), nullable=True)
    feed_contact_url = db.Column(db.String(255), nullable=True)

    def __repr__(self) -> str:
        return f"<FeedInfo {self.feed_publisher_name}>"
