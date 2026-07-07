from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

db = SQLAlchemy()
login_manager = LoginManager()

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
