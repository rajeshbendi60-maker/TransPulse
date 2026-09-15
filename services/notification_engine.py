from extensions import db
from models.notifications import Notification, NotificationRecipient, NotificationPreference, NotificationDelivery, NotificationTopic, NotificationAuditLog, NotificationStatus
from datetime import datetime
import logging
import json

logger = logging.getLogger(__name__)

# Try to initialize Firebase
try:
    import firebase_admin
    from firebase_admin import credentials, messaging
    # Requires google-services.json/credentials to be available
    cred = credentials.Certificate('firebase-service-account.json')
    firebase_admin.initialize_app(cred)
    FIREBASE_ENABLED = True
except ImportError:
    logger.warning("firebase_admin module not installed. Push delivery will be simulated.")
    FIREBASE_ENABLED = False
except Exception as e:
    logger.warning(f"Firebase initialization failed: {e}. Notifications will be saved to DB but push delivery will be simulated.")
    FIREBASE_ENABLED = False

class PushNotificationEngine:
    def send_push(self, token, title, body, data):
        if not FIREBASE_ENABLED:
            logger.info(f"[SIMULATED FCM] Push to token {token}: {title} - {body}")
            return "simulated_message_id_123"
        
        try:
            message = messaging.Message(
                notification=messaging.Notification(title=title, body=body),
                data=data,
                token=token
            )
            response = messaging.send(message)
            return response
        except Exception as e:
            logger.error(f"FCM Push failed: {e}")
            raise e

class PreferenceEngine:
    def can_send(self, user_id, category):
        pref = NotificationPreference.query.filter_by(user_id=user_id, category=category).first()
        if pref and not pref.enabled:
            return False
        return True

class DeliveryTracker:
    def track_delivery(self, notification_id, user_id, fcm_message_id, status, error_message=None):
        delivery = NotificationDelivery(
            notification_id=notification_id,
            user_id=user_id,
            fcm_message_id=fcm_message_id,
            status=status,
            error_message=error_message
        )
        db.session.add(delivery)
        
        # Update Recipient status
        if status == NotificationStatus.SENT:
            recp = NotificationRecipient.query.filter_by(notification_id=notification_id, user_id=user_id).first()
            if recp:
                recp.status = NotificationStatus.SENT
        db.session.commit()

class NotificationHistoryEngine:
    def get_history(self, user_id, since=None):
        query = NotificationRecipient.query.filter_by(user_id=user_id)
        if since:
            try:
                since_dt = datetime.fromisoformat(since.replace('Z', '+00:00'))
                query = query.filter(NotificationRecipient.received_at > since_dt)
            except:
                pass
        
        recipients = query.all()
        results = []
        for r in recipients:
            n = Notification.query.get(r.notification_id)
            if n:
                results.append({
                    "id": n.id,
                    "title": n.title,
                    "body": n.body,
                    "category": n.category,
                    "priority": n.priority,
                    "deepLink": n.deep_link,
                    "createdAt": n.created_at.isoformat(),
                    "isRead": r.status == NotificationStatus.READ
                })
        return results

class NotificationEngine:
    def __init__(self):
        self.push_engine = PushNotificationEngine()
        self.preference_engine = PreferenceEngine()
        self.delivery_tracker = DeliveryTracker()
        self.history_engine = NotificationHistoryEngine()
        
    def send_targeted_notification(self, user_id, token, category, priority, title, body, deep_link=None):
        if not self.preference_engine.can_send(user_id, category):
            logger.info(f"Notification blocked by preference for user {user_id}, category {category}")
            return None
            
        notification = Notification(
            category=category,
            priority=priority,
            title=title,
            body=body,
            deep_link=deep_link
        )
        db.session.add(notification)
        db.session.commit()
        
        recipient = NotificationRecipient(
            notification_id=notification.id,
            user_id=user_id
        )
        db.session.add(recipient)
        db.session.commit()
        
        try:
            data = {"deepLink": deep_link} if deep_link else {}
            msg_id = self.push_engine.send_push(token, title, body, data)
            self.delivery_tracker.track_delivery(notification.id, user_id, msg_id, NotificationStatus.SENT)
            return True
        except Exception as e:
            self.delivery_tracker.track_delivery(notification.id, user_id, None, NotificationStatus.FAILED, str(e))
            return False

notification_engine = NotificationEngine()
# TP-v2.0-Release
