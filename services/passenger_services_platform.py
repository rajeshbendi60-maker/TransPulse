import os
from werkzeug.utils import secure_filename
from extensions import db
from models.passenger_services import Complaint, ComplaintAttachment, LostItem, FoundItem, ClaimRequest, Feedback, SupportTicket, SupportMessage, EmergencyContact, ComplaintStatus, SupportStatus
from services.notification_engine import notification_engine
from models.notifications import NotificationCategory, NotificationPriority
from datetime import datetime

UPLOAD_FOLDER = 'uploads/media'

class UploadEngine:
    def save_multipart_file(self, file):
        if not file:
            return None
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        filename = secure_filename(file.filename)
        # Mocking cloud storage link mapping for now
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(file_path)
        return f"/media/{filename}" # Accessible via static route

class ComplaintEngine:
    def create_complaint(self, user_id, category, description, route_id=None, bus_id=None, lat=None, lon=None, files=None):
        complaint = Complaint(
            user_id=user_id,
            category=category,
            description=description,
            route_id=route_id,
            bus_id=bus_id,
            lat=lat,
            lon=lon
        )
        db.session.add(complaint)
        db.session.flush()
        
        if files:
            uploader = UploadEngine()
            for f in files:
                url = uploader.save_multipart_file(f)
                if url:
                    attachment = ComplaintAttachment(complaint_id=complaint.id, file_url=url)
                    db.session.add(attachment)
        
        db.session.commit()
        return complaint
        
    def update_complaint_status(self, complaint_id, new_status, admin_id=None):
        complaint = Complaint.query.get(complaint_id)
        if complaint:
            complaint.status = new_status
            db.session.commit()
            
            # Send Notification
            notification_engine.send_targeted_notification(
                user_id=complaint.user_id,
                token="mock_token", # In prod, fetch from User schema
                category=NotificationCategory.SYSTEM,
                priority=NotificationPriority.NORMAL,
                title="Complaint Status Update",
                body=f"Your complaint ({complaint.category}) is now: {new_status}",
                deep_link=f"transpulse://complaint/{complaint_id}"
            )
        return complaint

class LostFoundEngine:
    def report_lost_item(self, user_id, category, date_lost, route_id=None, bus_id=None, district_id=None, keywords=None, color=None, brand=None, description=None, file=None):
        image_url = None
        if file:
            image_url = UploadEngine().save_multipart_file(file)
            
        lost = LostItem(
            user_id=user_id,
            category=category,
            date_lost=date_lost,
            route_id=route_id,
            bus_id=bus_id,
            district_id=district_id,
            keywords=keywords,
            color=color,
            brand=brand,
            description=description,
            image_url=image_url
        )
        db.session.add(lost)
        db.session.commit()
        
        # Stage 2: Trigger Matcher
        self._run_matching_engine_for_lost_item(lost)
        return lost
        
    def _run_matching_engine_for_lost_item(self, lost_item):
        found_items = FoundItem.query.filter_by(status="UNCLAIMED").all()
        for found in found_items:
            score = self._calculate_similarity(lost_item, found)
            if score > 0.85:
                claim = ClaimRequest(
                    lost_item_id=lost_item.id,
                    found_item_id=found.id,
                    similarity_score=score
                )
                db.session.add(claim)
                
                notification_engine.send_targeted_notification(
                    user_id=lost_item.user_id,
                    token="mock_token",
                    category=NotificationCategory.SYSTEM,
                    priority=NotificationPriority.HIGH,
                    title="Possible Match Found!",
                    body=f"We may have found your lost {lost_item.category}. Please verify.",
                    deep_link=f"transpulse://lostfound/claim/{claim.id}"
                )
        db.session.commit()
        
    def _calculate_similarity(self, lost, found):
        score = 0.0
        weights = 0.0
        
        if lost.category == found.category:
            score += 0.4
        weights += 0.4
        
        if lost.date_lost == found.date_found:
            score += 0.2
        weights += 0.2
        
        if lost.route_id and found.route_id and lost.route_id == found.route_id:
            score += 0.15
        weights += 0.15
        
        if lost.color and found.color and lost.color.lower() == found.color.lower():
            score += 0.1
        weights += 0.1
        
        if lost.brand and found.brand and lost.brand.lower() == found.brand.lower():
            score += 0.15
        weights += 0.15
        
        return score / weights if weights > 0 else 0

class FeedbackEngine:
    def submit_feedback(self, user_id, overall, driver, vehicle, cleanliness, safety, comfort, punctuality, comments):
        feedback = Feedback(
            user_id=user_id,
            overall_rating=overall,
            driver_rating=driver,
            vehicle_rating=vehicle,
            cleanliness_rating=cleanliness,
            safety_rating=safety,
            comfort_rating=comfort,
            punctuality_rating=punctuality,
            comments=comments
        )
        db.session.add(feedback)
        db.session.commit()
        return feedback

class EmergencyEngine:
    def get_hierarchical_contacts(self):
        return EmergencyContact.query.order_by(EmergencyContact.level).all()

class PassengerServicesPlatform:
    def __init__(self):
        self.complaint_engine = ComplaintEngine()
        self.lost_found_engine = LostFoundEngine()
        self.feedback_engine = FeedbackEngine()
        self.emergency_engine = EmergencyEngine()

passenger_services_platform = PassengerServicesPlatform()
