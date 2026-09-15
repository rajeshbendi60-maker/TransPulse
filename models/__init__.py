from extensions import db, login_manager

from .user import User
from .bus import Bus
from .route import Route
from .stop import Stop
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
from models.journey import Journey
from models.bus import Bus
from models.live_transit import VehiclePosition, TripAssignment, RouteDeviationEvent
from models.driver_operations import DriverSession, TripLog, VehicleInspection, IncidentReport, ShiftLifecycle, TripLifecycle, IncidentCategory
from models.district_admin import Depot, BusAllocation, DriverAllocation, ShiftAssignment, AuditLog, VehicleStatus, DriverStatus, IncidentPriority, AssignmentStatus
from models.state_control import StateAlert, EmergencyBroadcast, ControlRoomLog, SystemHealthSnapshot, BroadcastPriority, BroadcastTarget
from models.notifications import NotificationRecipient, NotificationPreference, NotificationDelivery, NotificationTopic, NotificationAuditLog, NotificationCategory, NotificationPriority, NotificationStatus
from models.passenger_services import Complaint, ComplaintAttachment, LostItem, FoundItem, ClaimRequest, Feedback, SupportTicket, SupportMessage, EmergencyContact, ComplaintStatus, SupportStatus
from models.analytics import DailyAnalytics, WeeklyAnalytics, MonthlyAnalytics, YearlyAnalytics, FleetMetrics, PassengerMetrics
from models.ai import PredictionSnapshot, AnomalyEvent, AiConversation
