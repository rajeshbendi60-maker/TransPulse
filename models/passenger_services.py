from extensions import db
from datetime import datetime
import uuid

class ComplaintStatus:
    SUBMITTED = "SUBMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    ASSIGNED = "ASSIGNED"
    INVESTIGATING = "INVESTIGATING"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"

class SupportStatus:
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    WAITING_FOR_PASSENGER = "WAITING_FOR_PASSENGER"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"

class Complaint(db.Model):
    __tablename__ = 'complaints'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    route_id = db.Column(db.String(100), nullable=True)
    bus_id = db.Column(db.Integer, nullable=True)
    lat = db.Column(db.Float, nullable=True)
    lon = db.Column(db.Float, nullable=True)
    status = db.Column(db.String(50), default=ComplaintStatus.SUBMITTED)
    priority = db.Column(db.String(50), default="NORMAL")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ComplaintAttachment(db.Model):
    __tablename__ = 'complaint_attachments'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    complaint_id = db.Column(db.String(36), db.ForeignKey('complaints.id'), nullable=False)
    file_url = db.Column(db.String(500), nullable=False)

class LostItem(db.Model):
    __tablename__ = 'lost_items'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    date_lost = db.Column(db.Date, nullable=False)
    route_id = db.Column(db.String(100), nullable=True)
    bus_id = db.Column(db.Integer, nullable=True)
    district_id = db.Column(db.Integer, nullable=True)
    keywords = db.Column(db.String(255), nullable=True)
    color = db.Column(db.String(50), nullable=True)
    brand = db.Column(db.String(100), nullable=True)
    description = db.Column(db.Text, nullable=True)
    image_url = db.Column(db.String(500), nullable=True)
    status = db.Column(db.String(50), default="SEARCHING")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class FoundItem(db.Model):
    __tablename__ = 'found_items'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    reported_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False) # Driver or Admin
    category = db.Column(db.String(100), nullable=False)
    date_found = db.Column(db.Date, nullable=False)
    route_id = db.Column(db.String(100), nullable=True)
    bus_id = db.Column(db.Integer, nullable=True)
    district_id = db.Column(db.Integer, nullable=True)
    keywords = db.Column(db.String(255), nullable=True)
    color = db.Column(db.String(50), nullable=True)
    brand = db.Column(db.String(100), nullable=True)
    description = db.Column(db.Text, nullable=True)
    image_url = db.Column(db.String(500), nullable=True)
    status = db.Column(db.String(50), default="UNCLAIMED")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ClaimRequest(db.Model):
    __tablename__ = 'claim_requests'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    lost_item_id = db.Column(db.String(36), db.ForeignKey('lost_items.id'), nullable=False)
    found_item_id = db.Column(db.String(36), db.ForeignKey('found_items.id'), nullable=False)
    similarity_score = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), default="PENDING_VERIFICATION")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Feedback(db.Model):
    __tablename__ = 'feedbacks'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True) # Anonymous allowed
    overall_rating = db.Column(db.Integer, nullable=False)
    driver_rating = db.Column(db.Integer, nullable=True)
    vehicle_rating = db.Column(db.Integer, nullable=True)
    cleanliness_rating = db.Column(db.Integer, nullable=True)
    safety_rating = db.Column(db.Integer, nullable=True)
    comfort_rating = db.Column(db.Integer, nullable=True)
    punctuality_rating = db.Column(db.Integer, nullable=True)
    comments = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class SupportTicket(db.Model):
    __tablename__ = 'support_tickets'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    subject = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(50), default=SupportStatus.OPEN)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class SupportMessage(db.Model):
    __tablename__ = 'support_messages'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    ticket_id = db.Column(db.String(36), db.ForeignKey('support_tickets.id'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_support_agent = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class EmergencyContact(db.Model):
    __tablename__ = 'emergency_contacts'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    level = db.Column(db.String(50), nullable=False) # NATIONAL, STATE, DISTRICT, DEPOT, TRANSPULSE
    entity_id = db.Column(db.Integer, nullable=True) # E.g. district_id
    name = db.Column(db.String(255), nullable=False)
    phone_number = db.Column(db.String(20), nullable=False)
# TP-v2.0-Release
