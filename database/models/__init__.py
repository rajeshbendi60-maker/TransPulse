from backend.extensions import db, login_manager

from .user import User
from .bus import Bus
from .route import Route
from .stop import Stop, StopTime
from .trip import Trip
from .notification import Notification
from .complaint import Complaint
from .feedback import Feedback
from .lost_and_found import LostAndFound
from .sos_alert import SOSAlert
from .occupancy import BusOccupancy
from .subscription import Subscription
from .agency import Agency
from .calendar import Calendar
from .calendar_date import CalendarDate
from .feed_info import FeedInfo
from .shape import Shape
from .road_geometry_cache import RoadGeometryCache
from .favorite import Favorite
from .segment_speed import SegmentSpeed
from database.models.journey import Journey
from database.models.bus import Bus
from database.models.live_transit import VehiclePosition, TripAssignment, RouteDeviationEvent
from database.models.driver_operations import DriverSession, TripLog, VehicleInspection, IncidentReport, ShiftLifecycle, TripLifecycle, IncidentCategory
from database.models.district_admin import Depot, BusAllocation, DriverAllocation, ShiftAssignment, AuditLog, VehicleStatus, DriverStatus, IncidentPriority, AssignmentStatus
from database.models.state_control import StateAlert, EmergencyBroadcast, ControlRoomLog, SystemHealthSnapshot, BroadcastPriority, BroadcastTarget
from database.models.notifications import NotificationRecipient, NotificationPreference, NotificationDelivery, NotificationTopic, NotificationAuditLog, NotificationCategory, NotificationPriority, NotificationStatus
from database.models.passenger_services import Complaint, ComplaintAttachment, LostItem, FoundItem, ClaimRequest, Feedback, SupportTicket, SupportMessage, EmergencyContact, ComplaintStatus, SupportStatus
from database.models.analytics import DailyAnalytics, WeeklyAnalytics, MonthlyAnalytics, YearlyAnalytics, FleetMetrics, PassengerMetrics
from database.models.ai import PredictionSnapshot, AnomalyEvent, AiConversation
# TP-v2.0-Release
