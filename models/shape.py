from models import db


class Shape(db.Model):
    __tablename__ = "shapes"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    shape_id = db.Column(
        db.String(120),
        nullable=False,
        index=True
    )

    shape_pt_lat = db.Column(
        db.Float,
        nullable=False
    )

    shape_pt_lon = db.Column(
        db.Float,
        nullable=False
    )

    shape_pt_sequence = db.Column(
        db.Integer,
        nullable=False
    )

    __table_args__ = (
        db.Index(
            "idx_shape_sequence",
            "shape_id",
            "shape_pt_sequence"
        ),
    )

    def to_dict(self):
        return {
            "shape_id": self.shape_id,
            "lat": self.shape_pt_lat,
            "lng": self.shape_pt_lon,
            "sequence": self.shape_pt_sequence
        }

    def __repr__(self):
        return (
            f"<Shape {self.shape_id} "
            f"Seq:{self.shape_pt_sequence}>"
        )