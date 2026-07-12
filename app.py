from datetime import datetime, timedelta, timezone
try:
    from datetime import UTC
except ImportError:
    UTC = timezone.utc
from functools import wraps
from typing import Optional
import logging
import math
import smtplib
import re
import time
import json
import secrets
import os
import hashlib
import random
import markdown
from email.message import EmailMessage
from urllib.error import URLError
from urllib.request import Request, urlopen

from flask import Flask, current_app, flash, jsonify, redirect, render_template, request, url_for, session
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import or_, func, case
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload
from flask_migrate import Migrate
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from flask_wtf.csrf import CSRFError, CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
try:
    import google.auth.transport.requests as google_requests
    from google.oauth2 import id_token as google_id_token
except ImportError:  # pragma: no cover - exercised only when optional dependency is absent
    google_requests = None
    google_id_token = None

from config import Config
from models import db, login_manager
from models.bus import Bus
from models.notification import Notification
from models.route import Route
from models.stop import Stop, StopTime
from models.trip import Trip
from models.user import User
from models.complaint import Complaint
from models.lost_and_found import LostAndFound
from models.sos_alert import SOSAlert
from models.occupancy import BusOccupancy
from models.subscription import Subscription
from models.shape import Shape
from models.road_geometry_cache import RoadGeometryCache

VALID_ROLES = {"admin", "driver", "passenger"}
TRIP_STATUS_OPTIONS = {"assigned", "ready", "active", "completed", "return_ready", "offline", "scheduled", "in_progress", "cancelled"}
ACTIVE_TRIP_STATUSES = ("active", "in_progress")
ACTIVE_SOS_STATUSES = ("NEW", "ACKNOWLEDGED", "active", "acknowledged")
SOS_EMERGENCY_TYPES = {
    "Medical Emergency",
    "Women Safety",
    "Security Threat",
    "Accident",
    "Fire",
    "Other Emergency",
}

LIVE_GPS_DATA = {}
BUS_COMPLETED_TRIPS = {}
LIVE_GPS_BREADCRUMBS = {}
DRIVER_RUNTIME_SESSIONS = {}
BUS_DELAY_DATA = {}
BUS_SIMULATION_STATE = {}
PASSENGER_TRACKING_SESSIONS = {}
_MAP_DEFAULT_CENTER = None

# Route Deviation Threshold Constants with configuration capability
ROUTE_DEVIATION_THRESHOLD_METERS = 200.0
ROUTE_DEVIATION_HEADING_THRESHOLD_DEGREES = 50.0
ROUTE_DEVIATION_MIN_METERS = 40.0

def _bearing_diff(b1: float, b2: float) -> float:
    """Return the absolute modular difference between two bearings in degrees."""
    if b1 is None or b2 is None:
        return 0.0
    diff = abs(float(b1) - float(b2)) % 360
    return min(diff, 360 - diff)

def _parse_time_str(t_str: str) -> Optional[int]:
    """Parse scheduled time format 'HH:MM AM/PM' or 'HH:MM' into integer minutes since midnight."""
    if not t_str or t_str == "--":
        return None
    m = re.match(r"^(\d{1,2}):(\d{2})\s*([AP]M)?$", str(t_str).strip(), re.IGNORECASE)
    if not m:
        return None
    h = int(m.group(1))
    m_val = int(m.group(2))
    suffix = m.group(3)
    if suffix:
        suffix = suffix.upper()
        if h == 12:
            h = 0
        if suffix == "PM":
            h += 12
    return h * 60 + m_val


def _clear_diversion_cache(trip_id: int) -> None:
    """Purge dynamic diversion cache entries for a given trip from persistent cache."""
    try:
        prefix = f"div_{trip_id}_"
        RoadGeometryCache.query.filter(RoadGeometryCache.cache_key.like(f"{prefix}%")).delete(synchronize_session=False)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.warning("[DIVERSION] Failed to clear diversion cache for trip %s: %s", trip_id, exc)


_FLEET_SNAPSHOT_CACHE = None
_FLEET_SNAPSHOT_CACHE_TIME = 0.0

def _invalidate_fleet_snapshot_cache():
    global _FLEET_SNAPSHOT_CACHE, _FLEET_SNAPSHOT_CACHE_TIME
    _FLEET_SNAPSHOT_CACHE = None
    _FLEET_SNAPSHOT_CACHE_TIME = 0.0


ALLOWED_DELAY_REASONS = {
    "Traffic",
    "Heavy Traffic",
    "Road Block",
    "Accident",
    "Mechanical Issue",
    "Bus Breakdown",
    "Passenger Emergency",
    "Heavy Rain",
    "Weather",
    "Diversion",
    "Construction Work",
    "Road Work",
    "Other",
}
DELAY_EVENT_CATALOG = (
    ("Traffic", 60, 240, 0.22),
    ("Heavy Traffic", 120, 300, 0.16),
    ("Weather", 60, 180, 0.10),
    ("Heavy Rain", 60, 180, 0.08),
    ("Construction Work", 120, 300, 0.09),
    ("Road Block", 120, 300, 0.05),
    ("Mechanical Issue", 120, 480, 0.04),
)
DELAY_PROFILE_TTL_SECONDS = 8 * 60 * 60
DELAY_NOTIFY_THRESHOLD_MINUTES = 3
DELAY_NOTIFY_DELTA_MINUTES = 2
DELAY_NOTIFY_COOLDOWN_SECONDS = 10 * 60
TRACKING_SESSION_TTL_SECONDS = 5 * 60
SIMULATION_STATE_TTL_SECONDS = 12 * 60 * 60
DRIVER_STOP_COMPLETION_THRESHOLD_KM = 0.12

# OSRM is used only to enrich the route drawn on the map.  Core tracking,
# timeline and GTFS shape calculations continue to use the imported data.
OSRM_BASE_URL = os.getenv("OSRM_BASE_URL", "https://router.project-osrm.org").rstrip("/")
OSRM_TIMEOUT_SECONDS = float(os.getenv("OSRM_TIMEOUT_SECONDS", "8"))
OSRM_MAX_WAYPOINTS = 90
ROAD_GEOMETRY_FAILURE_RETRY_SECONDS = 60 * 60

logger = logging.getLogger(__name__)
if not logging.getLogger().handlers:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

migrate = Migrate()


def _normalize_driver_code(raw: str) -> str:
    """Normalize driver codes DTP-1 through DTP-99999."""
    if not raw:
        return ""
    clean = re.sub(r"^(DTP|DRV|DVR)-", "", str(raw).upper().strip())
    try:
        num = int(clean)
        if 1 <= num <= 99999:
            return f"DTP-{num:03d}" if num < 1000 else f"DTP-{num}"
    except ValueError:
        pass
    return f"DTP-{clean}" if clean else ""


def _normalize_admin_transpulse_id(raw: str) -> str:
    """Normalize admin IDs like ADM-TP01, ADM-1, ADM-TP1."""
    if not raw:
        return ""
    val = str(raw).upper().strip()
    match = re.match(r"^ADM-TP(\d+)$", val)
    if match:
        return f"ADM-TP{int(match.group(1)):02d}"
    match = re.match(r"^ADM-(\d+)$", val)
    if match:
        return f"ADM-TP{int(match.group(1)):02d}"
    return val


def _admin_transpulse_id_for_user(user_id: int) -> str:
    return f"ADM-TP{user_id:02d}"




SHARED_DRIVER_EMAIL = "driver@transpulse.com"
DEFAULT_ADMIN_EMAIL = "admin@transpulse.com"
DEFAULT_ADMIN_PASSWORD = os.getenv("TRANSPULSE_DEFAULT_ADMIN_PASSWORD", "admin@tp")
DEFAULT_PASSENGER_EMAIL = os.getenv("TRANSPULSE_DEFAULT_PASSENGER_EMAIL", "passenger@transpulse.com")
DEFAULT_PASSENGER_PASSWORD = os.getenv("TRANSPULSE_DEFAULT_PASSENGER_PASSWORD") or secrets.token_urlsafe(24)
DEFAULT_DRIVER_PASSWORD = os.getenv("TRANSPULSE_DEFAULT_DRIVER_PASSWORD", "driver@tp")


def _shared_driver_user() -> Optional[User]:
    return User.query.filter_by(email=SHARED_DRIVER_EMAIL, role="driver").first()


def _cleanup_legacy_driver_accounts() -> None:
    """Remove per-driver user accounts; only the shared driver login remains."""
    legacy = User.query.filter(
        User.role == "driver",
        User.email != SHARED_DRIVER_EMAIL,
    ).all()
    if not legacy:
        return
    shared = _shared_driver_user()
    for user in legacy:
        Bus.query.filter_by(assigned_driver_id=user.id).update(
            {"assigned_driver_id": None},
            synchronize_session=False,
        )
        Notification.query.filter_by(recipient_id=user.id).delete(synchronize_session=False)
        Complaint.query.filter_by(driver_id=user.id).update(
            {"driver_id": shared.id if shared else None},
            synchronize_session=False,
        )
        LostAndFound.query.filter_by(assigned_driver_id=user.id).update(
            {"assigned_driver_id": shared.id if shared else None},
            synchronize_session=False,
        )
        db.session.delete(user)
    db.session.commit()
    logger.info("[DRIVER_CLEANUP] Removed %s legacy per-driver user accounts", len(legacy))


def _ensure_shared_driver_account() -> None:
    _cleanup_legacy_driver_accounts()
    driver = _shared_driver_user()
    if not driver:
        driver = User(
            full_name="TransPulse Driver",
            email=SHARED_DRIVER_EMAIL,
            role="driver",
            auth_provider="local",
        )
        driver.set_password("driver@tp")
        db.session.add(driver)
        db.session.commit()
    else:
        driver.email = SHARED_DRIVER_EMAIL
        driver.set_password("driver@tp")
        db.session.commit()


def _ensure_default_admin() -> None:
    admin = User.query.filter_by(role="admin").first()
    if not admin:
        admin = User(
            full_name="TransPulse Admin",
            email="admin@transpulse.com",
            role="admin",
            transpulse_id="ATP-01"
        )
        admin.set_password("admin@tp")
        db.session.add(admin)
        db.session.commit()
    else:
        admin.email = "admin@transpulse.com"
        admin.transpulse_id = "ATP-01"
        admin.set_password("admin@tp")
        db.session.commit()


def _bus_for_driver_code(raw: str) -> Optional[Bus]:
    """Find the bus assigned to a driver code (DRV-XXX)."""
    code = _normalize_driver_code(raw)
    if not code:
        return None
    return Bus.query.filter_by(assigned_driver_code=code).first()


def _driver_code_taken(driver_code: str, exclude_bus_id: Optional[int] = None) -> Optional[Bus]:
    if not driver_code:
        return None
    q = Bus.query.filter_by(assigned_driver_code=driver_code)
    if exclude_bus_id:
        q = q.filter(Bus.id != exclude_bus_id)
    return q.first()


def _get_session_driver_bus() -> Optional[Bus]:
    code = session.get("driver_code")
    if code:
        bus = Bus.query.filter_by(assigned_driver_code=code).first()
        if bus:
            return bus
    bus_id = session.get("assigned_bus_id")
    if bus_id:
        return db.session.get(Bus, bus_id)
    return None


def _driver_display_fields(bus: Optional[Bus]) -> tuple:
    if not bus:
        return "Unassigned", "--"
    code = bus.assigned_driver_code or "--"
    return code, code


def _occupancy_level_for_percentage(percentage: float) -> str:
    pct = max(0, min(100, int(round(percentage or 0))))
    if pct == 0:
        return "Empty"
    if pct >= 91:
        return "Full"
    if pct >= 71:
        return "High"
    if pct >= 31:
        return "Medium"
    return "Low"




def _latest_recorded_occupancy_for_bus(bus: Optional[Bus]) -> tuple[int, str]:
    if not bus:
        return 0, "Empty"
    trip = _active_trip_for_bus(bus)
    if not trip:
        return 0, "Empty"
    occ = BusOccupancy.query.filter_by(bus_id=bus.id, trip_id=trip.id).order_by(BusOccupancy.recorded_at.desc()).first()
    if not occ:
        return 0, "Empty"
    try:
        pct = int(round(float(occ.occupancy_percentage or 0)))
    except (TypeError, ValueError):
        pct = 0
    if pct <= 0 and occ.total_seats:
        pct = int(round((float(occ.occupied_seats or 0) / float(occ.total_seats)) * 100))
    pct = max(0, min(100, pct))
    level = (occ.occupancy_level or _occupancy_level_for_percentage(pct)).strip() or _occupancy_level_for_percentage(pct)
    return pct, level


def _display_occupancy_for_bus(bus: Optional[Bus]) -> tuple[int, str]:
    return _latest_recorded_occupancy_for_bus(bus)




def _validate_driver_code_input(raw: str) -> tuple:
    """Return (normalized_code, error_message)."""
    code = _normalize_driver_code(raw)
    if not code:
        return "", "Invalid Driver ID format."
    try:
        num = int(code.replace("DTP-", ""))
        if num < 1 or num > 99999:
            return "", "Driver ID must be between DTP-001 and DTP-99999."
    except ValueError:
        return "", "Invalid Driver ID format."
    return code, ""


PASSWORD_RESET_MAX_AGE_SECONDS = 15 * 60
PASSWORD_RESET_SALT = "transpulse-passenger-password-reset"
PASSWORD_MIN_LENGTH = 8
EMAIL_RE = re.compile(r"^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$", re.IGNORECASE)
GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}


def _is_valid_email(email: str) -> bool:
    return bool(email and EMAIL_RE.match(email))


def _validate_password_strength(password: str) -> Optional[str]:
    min_length = current_app.config.get("PASSWORD_MIN_LENGTH", PASSWORD_MIN_LENGTH)
    if len(password or "") < min_length:
        return f"Password must be at least {min_length} characters."
    return None


def _google_client_id() -> str:
    return (current_app.config.get("GOOGLE_CLIENT_ID") or os.getenv("GOOGLE_CLIENT_ID") or "").strip()


def _verified_google_profile(credential: str) -> dict:
    if not credential:
        raise ValueError("Google credential is missing.")

    client_id = _google_client_id()
    if not client_id:
        raise ValueError("Google authentication is not configured.")

    if google_id_token is not None and google_requests is not None:
        try:
            payload = google_id_token.verify_oauth2_token(
                credential,
                google_requests.Request(),
                client_id,
            )
        except Exception as exc:
            logger.warning("[GOOGLE_AUTH] ID token verification failed: %s", exc)
            raise ValueError("Google credential could not be verified.") from exc
    else:
        try:
            req = Request(
                f"https://oauth2.googleapis.com/tokeninfo?id_token={credential}",
                headers={"Accept": "application/json"},
            )
            with urlopen(req, timeout=8) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            logger.warning("[GOOGLE_AUTH] tokeninfo verification failed: %s", exc)
            raise ValueError("Google credential could not be verified.") from exc

    if payload.get("iss") not in GOOGLE_ISSUERS:
        raise ValueError("Google credential issuer is invalid.")
    if payload.get("aud") != client_id:
        raise ValueError("Google credential audience is invalid.")
    if not payload.get("sub"):
        raise ValueError("Google credential subject is missing.")
    email_verified = payload.get("email_verified")
    if str(email_verified).lower() not in {"true", "1"}:
        raise ValueError("Google account email is not verified.")

    email = (payload.get("email") or "").strip().lower()
    full_name = (payload.get("name") or payload.get("given_name") or email.split("@")[0]).strip()
    if not _is_valid_email(email):
        raise ValueError("Google account email is invalid.")
    if not full_name:
        raise ValueError("Google account profile name is invalid.")

    return {
        "email": email,
        "full_name": full_name[:120],
        "subject": payload["sub"],
    }


def _categorize_notification(message: str) -> str:
    msg = (message or "").upper()
    if "[DRIVER ALERT]" in msg:
        return "Driver"

    if "[LOST & FOUND]" in msg and ("YOUR REPORT" in msg or "STATUS" in msg):
        return "System"

    if (
        "COMPLAINT #" in msg
        or "COMPLAINT STATUS" in msg
        or "COMPLAINT RESOLVED" in msg
        or "COMPLAINT CLOSED" in msg
        or "COMPLAINT CMP-" in msg
    ):
        return "System"

    if (
        "[DELAY]" in msg
        or "BUS DELAY" in msg
        or "BUS DELAYED" in msg
        or "BACK ON SCHEDULE" in msg
        or "BUS CANCELLED" in msg
        or "BUS CANCELED" in msg
        or "ROUTE CHANGED" in msg
    ):
        return "System"

    if "LOST ITEM RETURNED" in msg or "ITEM RETURNED" in msg:
        return "System"

    passenger_markers = (
        "[PASSENGER ALERT]",
        "[COMPLAINT]",
        "[LOST & FOUND]",
        "[SOS",
        " SOS",
        "EMERGENCY",
        "DISTRESS",
        "PASSENGER",
        "FEEDBACK",
    )
    if any(marker in msg for marker in passenger_markers):
        return "Passenger"
    driver_markers = (
        "BUS DELAYED",
        "DELAY",
        "CANCELLED",
        "CANCELED",
        "ROUTE CHANGED",
        "DRIVER STATUS",
        "DRIVER INCIDENT",
        "DRIVER OPERATIONAL",
        "DRIVER EMERGENCY",
    )
    if any(marker in msg for marker in driver_markers):
        return "Driver"
    if msg.startswith("[") or "SYSTEM ALERT" in msg or "BROADCAST" in msg or "ANNOUNCEMENT" in msg:
        return "System"
    return "System"


def _notification_category_for_role(role: str, message: str) -> Optional[str]:
    category = _categorize_notification(message)
    if role == "passenger":
        return "System" if category == "System" else None

    if role == "driver":
        if category == "Passenger":
            return "Passenger"
        if category == "System":
            return "System"
        return None

    if role == "admin":
        if category in ("Passenger", "Driver"):
            return category
        return None

    return None


def _notification_priority(category: str, message: str) -> str:
    msg = (message or "").upper()
    if "SOS" in msg or "EMERGENCY" in msg or "DISTRESS" in msg:
        return "High"
    if category in ("Passenger", "Driver"):
        return "Medium"
    return "Low"


ACTIVE_RECORD_STATUSES = {"pending", "open", "assigned", "in_progress", "in progress", "investigating", "found", "not found", "ready_for_collection"}
INACTIVE_RECORD_STATUSES = {"resolved", "closed", "returned", "completed", "archived"}


def _normalize_record_status(status: Optional[str]) -> str:
    return (status or "").strip().lower().replace("-", " ").replace("_", " ")


def _is_active_record_status(status: Optional[str]) -> bool:
    normalized = _normalize_record_status(status)
    if normalized in INACTIVE_RECORD_STATUSES:
        return False
    return normalized in ACTIVE_RECORD_STATUSES or not normalized


def _is_inactive_record_status(status: Optional[str]) -> bool:
    return _normalize_record_status(status) in INACTIVE_RECORD_STATUSES


def _apply_lifecycle_filter(query, model, view: str):
    normalized_view = (view or "active").strip().lower()
    statuses = [s.upper() for s in INACTIVE_RECORD_STATUSES]
    db_status = func.upper(func.replace(func.replace(model.status, "_", " "), "-", " "))
    if normalized_view in ("history", "resolved", "returned", "inactive"):
        return query.filter(db_status.in_(statuses))
    if normalized_view in ("all", "any"):
        return query
    return query.filter(~db_status.in_(statuses))


def _password_reset_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt=PASSWORD_RESET_SALT)


def _password_hash_fingerprint(user: User) -> str:
    return hashlib.sha256((user.password_hash or "").encode("utf-8")).hexdigest()


def _generate_password_reset_token(user: User) -> str:
    return _password_reset_serializer().dumps({
        "user_id": user.id,
        "email": user.email,
        "password_hash": _password_hash_fingerprint(user),
        "nonce": secrets.token_urlsafe(24),
    })


def _load_password_reset_user(token: str) -> tuple[Optional[User], Optional[str]]:
    try:
        payload = _password_reset_serializer().loads(
            token,
            max_age=current_app.config.get("PASSWORD_RESET_MAX_AGE_SECONDS", PASSWORD_RESET_MAX_AGE_SECONDS),
        )
    except SignatureExpired:
        return None, "expired"
    except (BadSignature, TypeError, ValueError):
        return None, "invalid"

    user = db.session.get(User, payload.get("user_id"))
    if not user or user.role != "passenger":
        return None, "invalid"
    if user.email != payload.get("email"):
        return None, "invalid"
    if getattr(user, "auth_provider", "local") != "local":
        return None, "invalid"
    if payload.get("password_hash") != _password_hash_fingerprint(user):
        return None, "used"
    return user, None


def _mail_config_value(name: str, default=None):
    if name in current_app.config and current_app.config.get(name) not in (None, ""):
        return current_app.config.get(name)
    return globals().get(name, default)


def _truthy_config(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off"}
    return bool(value)


def _send_password_reset_email(recipient_email: str, reset_link: str) -> None:
    username = _mail_config_value("MAIL_USERNAME") or os.getenv("MAIL_USERNAME")
    password = (
        _mail_config_value("MAIL_PASSWORD")
        or os.getenv("TRANSPULSE_GMAIL_APP_PASSWORD")
        or os.getenv("MAIL_PASSWORD")
    )
    if not password:
        raise RuntimeError("Gmail SMTP password is not configured.")
    if not username:
        raise RuntimeError("SMTP username is not configured.")

    message = EmailMessage()
    message["Subject"] = "TransPulse Password Reset"
    message["From"] = username
    message["To"] = recipient_email
    message.set_content(
        "Click below link to reset your password:\n\n"
        f"{reset_link}\n\n"
        "This link expires in 15 minutes."
    )

    server = _mail_config_value("MAIL_SERVER", "smtp.gmail.com")
    port = int(_mail_config_value("MAIL_PORT", 587))
    use_tls = _truthy_config(_mail_config_value("MAIL_USE_TLS", True))
    with smtplib.SMTP(server, port, timeout=20) as smtp:
        if use_tls:
            smtp.starttls()
        smtp.login(username, password)
        smtp.send_message(message)


def _ensure_lost_found_columns() -> None:
    """Add new columns on existing SQLite databases."""
    try:
        from sqlalchemy import inspect, text
        inspector = inspect(db.engine)
        with db.engine.connect() as conn:
            if "lost_and_found" in inspector.get_table_names():
                cols = {c["name"] for c in inspector.get_columns("lost_and_found")}
                if "driver_reply" not in cols:
                    conn.execute(text("ALTER TABLE lost_and_found ADD COLUMN driver_reply TEXT"))
                if "assigned_driver_id" not in cols:
                    conn.execute(text("ALTER TABLE lost_and_found ADD COLUMN assigned_driver_id INTEGER"))

            if "complaint" in inspector.get_table_names():
                cols = {c["name"] for c in inspector.get_columns("complaint")}
                if "bus_id" not in cols:
                    conn.execute(text("ALTER TABLE complaint ADD COLUMN bus_id INTEGER"))
                if "route_id" not in cols:
                    conn.execute(text("ALTER TABLE complaint ADD COLUMN route_id INTEGER"))
                if "evidence_image" not in cols:
                    conn.execute(text("ALTER TABLE complaint ADD COLUMN evidence_image TEXT"))
                if "created_at" not in cols:
                    conn.execute(text("ALTER TABLE complaint ADD COLUMN created_at DATETIME"))
                    conn.execute(text("UPDATE complaint SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"))
                if "resolved_at" not in cols:
                    conn.execute(text("ALTER TABLE complaint ADD COLUMN resolved_at DATETIME"))
                if "admin_notes" not in cols:
                    conn.execute(text("ALTER TABLE complaint ADD COLUMN admin_notes TEXT"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_complaint_status ON complaint (status)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_complaint_created_at ON complaint (created_at)"))

            if "users" in inspector.get_table_names():
                cols = {c["name"] for c in inspector.get_columns("users")}
                if "transpulse_id" not in cols:
                    conn.execute(text("ALTER TABLE users ADD COLUMN transpulse_id VARCHAR(20)"))

            if "buses" in inspector.get_table_names():
                cols = {c["name"] for c in inspector.get_columns("buses")}
                if "assigned_driver_code" not in cols:
                    conn.execute(text("ALTER TABLE buses ADD COLUMN assigned_driver_code VARCHAR(20)"))
                if "assigned_driver_name" not in cols:
                    conn.execute(text("ALTER TABLE buses ADD COLUMN assigned_driver_name VARCHAR(120)"))
                conn.execute(text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_buses_assigned_driver_code "
                    "ON buses (assigned_driver_code) WHERE assigned_driver_code IS NOT NULL"
                ))

            if "routes" in inspector.get_table_names():
                cols = {c["name"] for c in inspector.get_columns("routes")}
                if "is_operational" not in cols:
                    conn.execute(text("ALTER TABLE routes ADD COLUMN is_operational BOOLEAN DEFAULT 0"))
                if "departure_time" not in cols:
                    conn.execute(text("ALTER TABLE routes ADD COLUMN departure_time VARCHAR(20)"))
                if "arrival_time" not in cols:
                    conn.execute(text("ALTER TABLE routes ADD COLUMN arrival_time VARCHAR(20)"))

            if "stops" in inspector.get_table_names():
                cols = {c["name"] for c in inspector.get_columns("stops")}
                if "scheduled_arrival_time" not in cols:
                    conn.execute(text("ALTER TABLE stops ADD COLUMN scheduled_arrival_time VARCHAR(20)"))
                if "scheduled_departure_time" not in cols:
                    conn.execute(text("ALTER TABLE stops ADD COLUMN scheduled_departure_time VARCHAR(20)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_stops_code_location ON stops (stop_code, stop_lat, stop_lon)"))

            if "stop_times" in inspector.get_table_names():
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_stop_time_trip_sequence ON stop_times (trip_id, stop_sequence)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_stop_time_stop_trip ON stop_times (stop_id, trip_id)"))

            if "trips" in inspector.get_table_names():
                cols = {c["name"] for c in inspector.get_columns("trips")}
                if "gtfs_trip_id" not in cols:
                    conn.execute(text("ALTER TABLE trips ADD COLUMN gtfs_trip_id VARCHAR(120)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_trip_route_status ON trips (route_id, status)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_trip_shape_route ON trips (shape_id, route_id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_trip_bus_status ON trips (bus_id, status)"))
                conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_trips_gtfs_trip_id ON trips (gtfs_trip_id) WHERE gtfs_trip_id IS NOT NULL"))

            if "bus_occupancy" in inspector.get_table_names():
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_bus_occupancy_bus_recorded ON bus_occupancy (bus_id, recorded_at)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_bus_occupancy_trip_recorded ON bus_occupancy (trip_id, recorded_at)"))

            if "subscriptions" in inspector.get_table_names():
                conn.execute(text(
                    "DELETE FROM subscriptions WHERE id NOT IN ("
                    "SELECT MIN(id) FROM subscriptions GROUP BY user_id, stop_id)"
                ))
                conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_subscription_user_stop ON subscriptions (user_id, stop_id)"))

            if "notifications" in inspector.get_table_names():
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_notification_recipient_read_created ON notifications (recipient_id, is_read, created_at)"))

            if "sos_alert" in inspector.get_table_names():
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_sos_status_triggered ON sos_alert (status, triggered_at)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_sos_bus_status ON sos_alert (bus_id, status)"))

            if "road_geometry_cache" in inspector.get_table_names():
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_road_geometry_route_shape ON road_geometry_cache (route_id, shape_id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_road_geometry_status_updated ON road_geometry_cache (status, updated_at)"))

            conn.commit()
    except Exception as exc:
        logger.warning("[SCHEMA] column migration skipped: %s", exc)


def _assign_driver_code_to_bus(bus: Bus, driver_code_raw: str) -> Optional[str]:
    """Assign a driver code to a bus. Returns error message or None on success."""
    raw = (driver_code_raw or "").strip()
    if not raw:
        bus.assigned_driver_id = None
        bus.assigned_driver_code = None
        bus.assigned_driver_name = None
        return None

    code, err = _validate_driver_code_input(raw)
    if err:
        return err

    taken = _driver_code_taken(code, exclude_bus_id=bus.id)
    if taken:
        return "Driver ID Already Assigned To Another Bus"

    bus.assigned_driver_id = None
    bus.assigned_driver_code = code
    bus.assigned_driver_name = code
    return None


def _compute_map_default_center() -> dict:
    result = (
        db.session.query(
            func.avg(Stop.stop_lat),
            func.avg(Stop.stop_lon)
        )
        .filter(
            Stop.stop_lat.isnot(None),
            Stop.stop_lon.isnot(None)
        )
        .first()
    )

    if result and result[0] is not None and result[1] is not None:
        return {
            "lat": float(result[0]),
            "lng": float(result[1])
        }

    return {
        "lat": 15.9129,
        "lng": 79.7400
    }

def _get_map_default_center() -> dict:
    global _MAP_DEFAULT_CENTER
    if _MAP_DEFAULT_CENTER is None:
        _MAP_DEFAULT_CENTER = _compute_map_default_center()
    return _MAP_DEFAULT_CENTER


def _resolve_trip_for_route(route: Route, trip=None):
    if trip and getattr(trip, "route_id", None) == route.id:
        return trip
    return _gtfs_backed_trip_for_route(route.id)


def _copy_stop_times_from_template(target_trip: Trip, template_trip: Optional[Trip]) -> None:
    if not target_trip or not template_trip or target_trip.id == template_trip.id:
        return
    existing = StopTime.query.filter_by(trip_id=target_trip.id).first()
    if existing:
        return
    template_stop_times = (
        StopTime.query
        .filter_by(trip_id=template_trip.id)
        .order_by(StopTime.stop_sequence.asc())
        .all()
    )
    for st in template_stop_times:
        db.session.add(StopTime(
            trip_id=target_trip.id,
            stop_id=st.stop_id,
            arrival_time=st.arrival_time,
            departure_time=st.departure_time,
            stop_sequence=st.stop_sequence,
        ))


def _copy_reversed_stop_times_from_trip(target_trip: Trip, source_trip: Optional[Trip]) -> None:
    if not target_trip or not source_trip or target_trip.id == source_trip.id:
        return
    StopTime.query.filter_by(trip_id=target_trip.id).delete(synchronize_session=False)
    source_stop_times = (
        StopTime.query
        .filter_by(trip_id=source_trip.id)
        .order_by(StopTime.stop_sequence.desc())
        .all()
    )
    start_minutes = _parse_time_to_minutes(
        source_stop_times[0].departure_time or source_stop_times[0].arrival_time
    ) if source_stop_times else None
    for index, st in enumerate(source_stop_times, start=1):
        scheduled_time = None
        original_minutes = _parse_time_to_minutes(st.departure_time or st.arrival_time)
        if start_minutes is not None and original_minutes is not None:
            scheduled_time = _minutes_to_storage_time(start_minutes + max(0, start_minutes - original_minutes))
        db.session.add(StopTime(
            trip_id=target_trip.id,
            stop_id=st.stop_id,
            arrival_time=scheduled_time or st.arrival_time,
            departure_time=scheduled_time or st.departure_time,
            stop_sequence=index,
        ))


def _parse_time_to_minutes(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None

    ampm_match = re.match(r"^(\d{1,2}):(\d{2})(?:\s*([AP]M))$", raw.upper())
    if ampm_match:
        hour = int(ampm_match.group(1))
        minute = int(ampm_match.group(2))
        suffix = ampm_match.group(3)
        if hour == 12:
            hour = 0
        if suffix == "PM":
            hour += 12
        return hour * 60 + minute

    parts = raw.split(":")
    if len(parts) < 2:
        return None
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError:
        return None
    return hour * 60 + minute


def _minutes_to_storage_time(minutes: Optional[int]) -> Optional[str]:
    if minutes is None:
        return None
    minutes = int(minutes) % (24 * 60)
    return f"{minutes // 60:02d}:{minutes % 60:02d}:00"


def _format_schedule_time(value: Optional[str]) -> str:
    minutes = _parse_time_to_minutes(value)
    if minutes is None:
        return "--"
    minutes = minutes % (24 * 60)
    hour_24 = minutes // 60
    minute = minutes % 60
    suffix = "AM" if hour_24 < 12 else "PM"
    hour_12 = hour_24 % 12 or 12
    return f"{hour_12:02d}:{minute:02d} {suffix}"


def _duration_label(minutes: Optional[int]) -> str:
    if minutes is None:
        return "--"
    minutes = max(0, int(minutes))
    hours = minutes // 60
    mins = minutes % 60
    if hours and mins:
        return f"{hours}h {mins}m"
    if hours:
        return f"{hours}h"
    return f"{mins}m"


def _service_day_minutes() -> int:
    now = datetime.now()
    return now.hour * 60 + now.minute


def _upcoming_schedule_delta(departure_minutes: Optional[int],
                             target_minutes: Optional[int] = None) -> int:
    if departure_minutes is None:
        return 24 * 60
    target = _service_day_minutes() if target_minutes is None else int(target_minutes)
    return (int(departure_minutes) - target) % (24 * 60)


def _ordered_stop_times_for_trip(trip_id: int) -> list:
    return (
        StopTime.query
        .options(joinedload(StopTime.stop))
        .filter_by(trip_id=trip_id)
        .order_by(StopTime.stop_sequence.asc())
        .all()
    )


def _trip_stop_signature(stop_times: list) -> list:
    signature = []
    for stop_time in stop_times:
        stop = stop_time.stop
        if not stop:
            continue
        signature.append({
            "stop_id": stop.id,
            "stop_code": stop.stop_code,
            "name": stop.stop_name,
            "sequence": stop_time.stop_sequence,
            "departure_minutes": _parse_time_to_minutes(stop_time.departure_time or stop_time.arrival_time),
        })
    return signature


def _gtfs_trip_candidates_for_route(route_id: int) -> list:
    return (
        Trip.query
        .filter(
            Trip.route_id == route_id,
            Trip.bus_id.is_(None),
        )
        .order_by(Trip.route_id.asc(), Trip.service_id.asc(), Trip.direction_id.asc(), Trip.id.asc())
        .all()
    )


def _score_gtfs_trip_candidate(trip: Trip,
                               target_departure_minutes: Optional[int] = None,
                               shape_point_count: Optional[int] = None) -> Optional[dict]:
    stop_times = _ordered_stop_times_for_trip(trip.id)
    signature = _trip_stop_signature(stop_times)
    if len(signature) < 2:
        return None

    first_stop = signature[0]
    departure_minutes = first_stop.get("departure_minutes")
    departure_delta = _upcoming_schedule_delta(departure_minutes, target_departure_minutes)
    shape_points = int(shape_point_count or 0)
    readiness_score = (20.0 if shape_points >= 2 else 0.0) + min(len(signature), 20)

    return {
        "trip": trip,
        "score": readiness_score,
        "departure_delta": departure_delta,
        "departure_minutes": departure_minutes,
        "shape_points": shape_points,
        "stop_count": len(signature),
    }


def _route_has_gtfs_stop_times(route_id: Optional[int]) -> bool:
    if not route_id:
        return False
    return (
        db.session.query(StopTime.id)
        .join(Trip, StopTime.trip_id == Trip.id)
        .join(Stop, StopTime.stop_id == Stop.id)
        .filter(
            Trip.route_id == route_id,
            Trip.bus_id.is_(None),
            Stop.stop_code.isnot(None),
        )
        .limit(1)
        .scalar()
        is not None
    )


def _manual_stop_names(route: Route, intermediates: str = "") -> list:
    names = []
    for name in [route.origin, *[s.strip() for s in (intermediates or "").split(",")], route.destination]:
        clean = (name or "").strip()
        if clean and (not names or names[-1].lower() != clean.lower()):
            names.append(clean)
    return names


def _manual_schedule_offsets(route: Route, stop_count: int) -> list:
    if stop_count <= 0:
        return []
    if stop_count == 1:
        return [0]
    total_minutes = int(round(((route.distance_km or 0) / 50.0) * 60)) if route.distance_km else 0
    total_minutes = max(total_minutes, (stop_count - 1) * 15)
    return [
        int(round((total_minutes * index) / (stop_count - 1)))
        for index in range(stop_count)
    ]


def _apply_manual_route_schedule(route: Route, intermediates: str = "", departure_time: Optional[str] = None) -> None:
    if not route or _route_has_gtfs_stop_times(route.id):
        return

    parsed_departure = _parse_time_to_minutes(departure_time) if departure_time else _parse_time_to_minutes(route.departure_time)
    if parsed_departure is not None:
        route.departure_time = _minutes_to_storage_time(parsed_departure)

    names = _manual_stop_names(route, intermediates)
    if not names:
        return

    existing_stops = Stop.query.filter_by(route_id=route.id).all()
    if any(stop.stop_code for stop in existing_stops):
        return

    Stop.query.filter_by(route_id=route.id).delete(synchronize_session=False)
    offsets = _manual_schedule_offsets(route, len(names))
    for index, name in enumerate(names):
        scheduled_minutes = parsed_departure + offsets[index] if parsed_departure is not None else None
        scheduled_time = _minutes_to_storage_time(scheduled_minutes)
        db.session.add(Stop(
            route_id=route.id,
            stop_name=name,
            stop_order=index + 1,
            eta_minutes=offsets[index],
            scheduled_arrival_time=scheduled_time,
            scheduled_departure_time=scheduled_time,
        ))
    if parsed_departure is not None and offsets:
        route.arrival_time = _minutes_to_storage_time(parsed_departure + offsets[-1])


def _ensure_trip_stop_times_from_route(trip: Trip, route: Route) -> None:
    if not trip or not route or StopTime.query.filter_by(trip_id=trip.id).first():
        return
    if _route_has_gtfs_stop_times(route.id):
        return

    stops = Stop.query.filter_by(route_id=route.id).order_by(Stop.stop_order.asc()).all()
    if not stops:
        _apply_manual_route_schedule(route)
        db.session.flush()
        stops = Stop.query.filter_by(route_id=route.id).order_by(Stop.stop_order.asc()).all()

    for index, stop in enumerate(stops):
        scheduled_time = (
            stop.scheduled_departure_time
            or stop.scheduled_arrival_time
            or route.departure_time
            or "00:00:00"
        )
        db.session.add(StopTime(
            trip_id=trip.id,
            stop_id=stop.id,
            arrival_time=stop.scheduled_arrival_time or scheduled_time,
            departure_time=stop.scheduled_departure_time or scheduled_time,
            stop_sequence=stop.stop_order or (index + 1),
        ))


def _route_schedule_for(route: Optional[Route], trip=None) -> dict:
    empty = {
        "departure_time": "--",
        "arrival_time": "--",
        "duration": "--",
        "duration_minutes": None,
        "stops": [],
        "source": "none",
    }
    if not route:
        return empty

    schedule_trip = _resolve_trip_for_route(route, trip)
    stop_times = []
    if schedule_trip and getattr(schedule_trip, "id", None):
        stop_times = (
            StopTime.query
            .filter_by(trip_id=schedule_trip.id)
            .order_by(StopTime.stop_sequence.asc())
            .all()
        )

    if stop_times:
        stops = []
        for st in stop_times:
            stop = st.stop
            stop_name = stop.stop_name if stop else f"Stop {st.stop_sequence}"
            scheduled_time = st.departure_time or st.arrival_time
            stops.append({
                "name": stop_name,
                "stop_order": st.stop_sequence,
                "arrival_time": _format_schedule_time(st.arrival_time),
                "departure_time": _format_schedule_time(st.departure_time),
                "scheduled_time": _format_schedule_time(scheduled_time),
            })
        first_time = stop_times[0].departure_time or stop_times[0].arrival_time
        last_time = stop_times[-1].arrival_time or stop_times[-1].departure_time
        first_minutes = _parse_time_to_minutes(first_time)
        last_minutes = _parse_time_to_minutes(last_time)
        duration_minutes = None
        if first_minutes is not None and last_minutes is not None:
            if last_minutes < first_minutes:
                last_minutes += 24 * 60
            duration_minutes = last_minutes - first_minutes
        return {
            "departure_time": _format_schedule_time(first_time),
            "arrival_time": _format_schedule_time(last_time),
            "duration": _duration_label(duration_minutes),
            "duration_minutes": duration_minutes,
            "stops": stops,
            "source": "gtfs" if any(st.stop and st.stop.stop_code for st in stop_times) else "admin",
        }

    stops = Stop.query.filter_by(route_id=route.id).order_by(Stop.stop_order.asc()).all()
    if not stops:
        names = _manual_stop_names(route)
        offsets = _manual_schedule_offsets(route, len(names))
        departure_minutes = _parse_time_to_minutes(route.departure_time)
        generated = []
        for index, name in enumerate(names):
            scheduled_minutes = departure_minutes + offsets[index] if departure_minutes is not None else None
            generated.append({
                "name": name,
                "stop_order": index + 1,
                "arrival_time": _format_schedule_time(_minutes_to_storage_time(scheduled_minutes)),
                "departure_time": _format_schedule_time(_minutes_to_storage_time(scheduled_minutes)),
                "scheduled_time": _format_schedule_time(_minutes_to_storage_time(scheduled_minutes)),
            })
        first_time = route.departure_time
        last_time = route.arrival_time or (_minutes_to_storage_time(departure_minutes + offsets[-1]) if departure_minutes is not None and offsets else None)
        duration_minutes = offsets[-1] if offsets else None
        return {
            "departure_time": _format_schedule_time(first_time),
            "arrival_time": _format_schedule_time(last_time),
            "duration": _duration_label(duration_minutes),
            "duration_minutes": duration_minutes,
            "stops": generated,
            "source": "admin",
        }

    rows = []
    for index, stop in enumerate(stops):
        scheduled_time = stop.scheduled_departure_time or stop.scheduled_arrival_time
        rows.append({
            "name": stop.stop_name,
            "stop_order": stop.stop_order or (index + 1),
            "arrival_time": _format_schedule_time(stop.scheduled_arrival_time),
            "departure_time": _format_schedule_time(stop.scheduled_departure_time),
            "scheduled_time": _format_schedule_time(scheduled_time),
        })

    first_time = stops[0].scheduled_departure_time or stops[0].scheduled_arrival_time or route.departure_time
    last_time = stops[-1].scheduled_arrival_time or stops[-1].scheduled_departure_time or route.arrival_time
    first_minutes = _parse_time_to_minutes(first_time)
    last_minutes = _parse_time_to_minutes(last_time)
    duration_minutes = None
    if first_minutes is not None and last_minutes is not None:
        if last_minutes < first_minutes:
            last_minutes += 24 * 60
        duration_minutes = last_minutes - first_minutes
    return {
        "departure_time": _format_schedule_time(first_time),
        "arrival_time": _format_schedule_time(last_time),
        "duration": _duration_label(duration_minutes),
        "duration_minutes": duration_minutes,
        "stops": rows,
        "source": "admin",
    }


def _route_schedule_for_assigned_trip(route: Optional[Route], trip=None) -> dict:
    """Live tracking schedule: only the assigned trip's stop_times are valid."""
    empty = {
        "departure_time": "Waiting for GPS",
        "arrival_time": "Calculating...",
        "duration": "Calculating...",
        "duration_minutes": None,
        "stops": [],
        "source": "assigned_trip",
    }
    if not route or not trip or getattr(trip, "route_id", None) != getattr(route, "id", None):
        return empty

    stop_times = (
        StopTime.query
        .filter_by(trip_id=trip.id)
        .order_by(StopTime.stop_sequence.asc())
        .all()
    )
    if not stop_times:
        return empty

    stops = []
    for st in stop_times:
        stop = st.stop
        stop_name = stop.stop_name if stop else f"Stop {st.stop_sequence}"
        scheduled_time = st.departure_time or st.arrival_time
        stops.append({
            "name": stop_name,
            "stop_order": st.stop_sequence,
            "arrival_time": _format_schedule_time(st.arrival_time),
            "departure_time": _format_schedule_time(st.departure_time),
            "scheduled_time": _format_schedule_time(scheduled_time),
        })

    first_time = stop_times[0].departure_time or stop_times[0].arrival_time
    last_time = stop_times[-1].arrival_time or stop_times[-1].departure_time
    first_minutes = _parse_time_to_minutes(first_time)
    last_minutes = _parse_time_to_minutes(last_time)
    duration_minutes = None
    if first_minutes is not None and last_minutes is not None:
        if last_minutes < first_minutes:
            last_minutes += 24 * 60
        duration_minutes = last_minutes - first_minutes

    return {
        "departure_time": _format_schedule_time(first_time),
        "arrival_time": _format_schedule_time(last_time),
        "duration": _duration_label(duration_minutes),
        "duration_minutes": duration_minutes,
        "stops": stops,
        "source": "assigned_trip",
    }


def _delay_minutes_from_seconds(delay_seconds: int) -> int:
    delay_seconds = max(0, int(delay_seconds or 0))
    if delay_seconds == 0:
        return 0
    return max(1, math.ceil(delay_seconds / 60))


def _delay_label_from_seconds(delay_seconds: int) -> str:
    minutes = _delay_minutes_from_seconds(delay_seconds)
    return f"+{minutes} min" if minutes else "0 min"


def _schedule_status_for_delay(delay_minutes: int) -> str:
    delay_minutes = max(0, int(delay_minutes or 0))
    if delay_minutes == 0:
        return "ON TIME"
    if delay_minutes <= 2:
        return "SLIGHTLY DELAYED"
    if delay_minutes <= 5:
        return "MODERATELY DELAYED"
    return "HEAVILY DELAYED"


def _trip_delay_key(route_id: Optional[int], trip=None, bus_id: Optional[int] = None) -> str:
    trip_id = getattr(trip, "id", None) if trip else None
    if trip_id:
        return f"trip:{trip_id}"
    shape_id = getattr(trip, "shape_id", None) if trip else None
    return f"route:{route_id or 'none'}:bus:{bus_id or 'none'}:shape:{shape_id or 'none'}"


def _delay_entry_for_bus(bus_id: Optional[int], route_id: Optional[int], trip=None) -> dict:
    if not bus_id:
        return {}
    now = time.time()
    trip_key = _trip_delay_key(route_id, trip, bus_id)
    entry = BUS_DELAY_DATA.get(bus_id)
    if (
        not entry
        or entry.get("trip_key") != trip_key
        or entry.get("route_id") != route_id
        or now - entry.get("timestamp", now) > DELAY_PROFILE_TTL_SECONDS
    ):
        entry = {
            "trip_key": trip_key,
            "route_id": route_id,
            "profiles": {},
            "manual_events": [],
            "timestamp": now,
            "last_notification_delay_minutes": 0,
            "last_notification_reason": None,
            "last_notification_at": 0,
        }
        BUS_DELAY_DATA[bus_id] = entry
    entry["timestamp"] = now
    return entry


def _delay_profile_seed(bus_id: Optional[int], route_id: Optional[int], trip, direction: str, stop_count: int) -> int:
    seed_source = "|".join([
        str(bus_id or "bus"),
        str(route_id or "route"),
        _trip_delay_key(route_id, trip, bus_id),
        str(getattr(trip, "shape_id", "") if trip else ""),
        direction or "forward",
        str(stop_count),
    ])
    return int(hashlib.sha256(seed_source.encode("utf-8")).hexdigest()[:16], 16)


def _generate_delay_profile(bus_id: Optional[int], route_id: Optional[int], trip,
                            direction: str, stop_count: int) -> dict:
    rng = random.Random(_delay_profile_seed(bus_id, route_id, trip, direction, stop_count))
    stop_delays = [0]
    stop_reasons = ["On time"]
    stop_events = [[]]

    for stop_index in range(1, max(1, stop_count)):
        delay_seconds = stop_delays[-1]
        events = []

        for name, min_seconds, max_seconds, probability in DELAY_EVENT_CATALOG:
            if rng.random() <= probability:
                added = rng.randint(min_seconds, max_seconds)
                delay_seconds += added
                events.append({"name": name, "seconds": added})
                if rng.random() < 0.58:
                    break

        if not events and rng.random() < 0.28:
            name, min_seconds, max_seconds, _ = rng.choice(DELAY_EVENT_CATALOG[:3])
            added = rng.randint(min_seconds, max_seconds)
            delay_seconds += added
            events.append({"name": name, "seconds": added})

        if delay_seconds >= 120 and rng.random() < 0.42:
            recovered = min(delay_seconds, rng.randint(30, 150))
            delay_seconds -= recovered
            events.append({"name": stop_reasons[-1] if stop_reasons else "Traffic", "seconds": -recovered})

        delay_seconds = max(0, min(delay_seconds, 20 * 60))
        positive_events = [event["name"] for event in events if event["seconds"] > 0]
        stop_delays.append(int(delay_seconds))
        stop_reasons.append(positive_events[-1] if positive_events else (stop_reasons[-1] if delay_seconds else "On time"))
        stop_events.append(events)

    if stop_count > 1 and max(stop_delays) == 0:
        added = 60
        stop_delays[1] = added
        stop_reasons[1] = "Traffic"
        stop_events[1] = [{"name": "Traffic", "seconds": added}]

    return {
        "stop_count": stop_count,
        "stop_delays_seconds": stop_delays[:stop_count],
        "stop_reasons": stop_reasons[:stop_count],
        "stop_events": stop_events[:stop_count],
        "generated_at": time.time(),
    }


def _delay_profile_for(entry: dict, bus_id: Optional[int], route_id: Optional[int], trip,
                       direction: str, stop_count: int) -> dict:
    if not entry:
        return _generate_delay_profile(bus_id, route_id, trip, direction, stop_count)
    profile_key = f"{direction or 'forward'}:{stop_count}"
    profiles = entry.setdefault("profiles", {})
    profile = profiles.get(profile_key)
    if not profile or profile.get("stop_count") != stop_count:
        profile = _generate_delay_profile(bus_id, route_id, trip, direction, stop_count)
        profiles[profile_key] = profile
    return profile


def _normalize_delay_reason(reason: Optional[str]) -> str:
    raw = (reason or "").strip()
    lookup = {
        "vehicle issue": "Bus Breakdown",
        "bus issue": "Bus Breakdown",
        "bus breakdown": "Bus Breakdown",
        "weather": "Heavy Rain",
        "heavy rain": "Heavy Rain",
        "mechanical issue": "Mechanical Issue",
        "road block": "Road Block",
        "road work": "Road Work",
        "traffic": "Traffic",
        "heavy traffic": "Heavy Traffic",
        "accident": "Accident",
        "passenger emergency": "Passenger Emergency",
        "diversion": "Diversion",
        "construction work": "Construction Work",
        "other": "Other",
    }
    normalized = lookup.get(raw.lower(), raw)
    return normalized if normalized in ALLOWED_DELAY_REASONS else "Traffic"


def _manual_delay_seconds_for_stop(entry: dict, direction: str, stop_index: int) -> tuple:
    total = 0
    reason = None
    for event in entry.get("manual_events", []) if entry else []:
        event_direction = event.get("direction") or direction
        event_start = int(event.get("start_index") or 0)
        if event_direction != direction:
            continue
        applies = stop_index >= event_start
        if applies:
            total += int(event.get("seconds") or 0)
            reason = event.get("reason") or reason
    return max(0, total), reason


def _record_driver_reported_delay(bus_id: Optional[int], route_id: Optional[int], trip,
                                  direction: str, start_index: int, reason: str,
                                  minutes: int) -> dict:
    entry = _delay_entry_for_bus(bus_id, route_id, trip)
    if not entry:
        return {}
    minutes = max(0, min(120, int(minutes or 0)))
    if minutes == 0:
        entry["manual_events"] = []
        entry["profiles"] = {}
        entry["suppress_generated_until"] = time.time() + DELAY_PROFILE_TTL_SECONDS
        entry["current_delay_minutes"] = 0
        entry["current_delay_seconds"] = 0
        entry["current_delay_reason"] = "On time"
        entry["timestamp"] = time.time()
        return entry
    entry.pop("suppress_generated_until", None)
    entry.setdefault("manual_events", []).append({
        "direction": direction or "forward",
        "start_index": max(0, int(start_index or 0)),
        "seconds": minutes * 60,
        "reason": _normalize_delay_reason(reason),
        "timestamp": time.time(),
    })
    entry["timestamp"] = time.time()
    return entry


def _current_bus_delay_minutes(bus_id: Optional[int]) -> int:
    if not bus_id:
        return 0
    entry = BUS_DELAY_DATA.get(bus_id)
    if not entry:
        return 0
    if time.time() - entry.get("timestamp", 0) > DELAY_PROFILE_TTL_SECONDS:
        BUS_DELAY_DATA.pop(bus_id, None)
        return 0
    return int(entry.get("current_delay_minutes") or 0)


def _schedule_time_with_delay_seconds(value: Optional[str], delay_seconds: int) -> str:
    scheduled_minutes = _parse_time_to_minutes(value)
    if scheduled_minutes is None:
        return "--"
    return _format_schedule_time(
        _minutes_to_storage_time(scheduled_minutes + _delay_minutes_from_seconds(delay_seconds))
    )


def _schedule_time_with_delay(value: Optional[str], delay_minutes: int) -> str:
    return _schedule_time_with_delay_seconds(value, int(delay_minutes or 0) * 60)


def _delay_schedule_payload(bus_id: Optional[int], route: Optional[Route], trip, direction: str,
                            stops: list, current_stop_idx: int, next_stop_idx: int,
                            phase_progress: float = 0.0) -> dict:
    stop_count = len(stops)
    route_id = getattr(route, "id", None) if route else None
    if stop_count == 0:
        return {
            "stops": [],
            "current_delay_seconds": 0,
            "current_delay_minutes": 0,
            "current_delay_label": "0 min",
            "current_delay_reason": "On time",
            "delay_status": "ON TIME",
            "next_stop_expected_time": "--",
            "updated_arrival_time": "--",
            "remaining_delay_minutes": 0,
        }

    direction = direction or "forward"
    entry = _delay_entry_for_bus(bus_id, route_id, trip)
    profile = _delay_profile_for(entry, bus_id, route_id, trip, direction, stop_count)
    profile_delays = profile.get("stop_delays_seconds") or [0] * stop_count
    profile_reasons = profile.get("stop_reasons") or ["On time"] * stop_count

    enriched_stops = []
    stop_delay_seconds = []
    suppress_generated = time.time() < float(entry.get("suppress_generated_until") or 0) if entry else False
    for idx, stop in enumerate(stops):
        generated_seconds = 0 if suppress_generated else int(profile_delays[idx] if idx < len(profile_delays) else profile_delays[-1])
        manual_seconds, manual_reason = _manual_delay_seconds_for_stop(entry, direction, idx)
        total_seconds = max(0, generated_seconds + manual_seconds)
        reason = manual_reason or (profile_reasons[idx] if idx < len(profile_reasons) else "Traffic")
        scheduled = stop.get("scheduled_time") or stop.get("arrival_time") or "--"
        actual = _schedule_time_with_delay_seconds(scheduled, total_seconds)
        delay_minutes = _delay_minutes_from_seconds(total_seconds)
        enriched = {
            **stop,
            "scheduled_time": scheduled,
            "actual_time": actual,
            "expected_time": actual,
            "delay_seconds": total_seconds,
            "delay_minutes": delay_minutes,
            "delay_label": _delay_label_from_seconds(total_seconds),
            "delay_reason": reason,
            "delay_status": _schedule_status_for_delay(delay_minutes),
        }
        enriched_stops.append(enriched)
        stop_delay_seconds.append(total_seconds)

    current_stop_idx = max(0, min(current_stop_idx or 0, stop_count - 1))
    next_stop_idx = max(0, min(next_stop_idx or current_stop_idx, stop_count - 1))
    current_seconds = stop_delay_seconds[current_stop_idx]
    next_seconds = stop_delay_seconds[next_stop_idx]
    if next_stop_idx != current_stop_idx:
        progress = max(0.0, min(1.0, float(phase_progress or 0.0)))
        current_seconds = int(round(current_seconds + ((next_seconds - current_seconds) * progress)))

    current_delay_minutes = _delay_minutes_from_seconds(current_seconds)
    current_reason = enriched_stops[next_stop_idx if next_stop_idx != current_stop_idx else current_stop_idx].get("delay_reason") or "Traffic"
    final_seconds = stop_delay_seconds[-1]
    next_expected_time = enriched_stops[next_stop_idx].get("expected_time", "--")
    updated_arrival = _schedule_time_with_delay_seconds(
        enriched_stops[-1].get("scheduled_time") or enriched_stops[-1].get("arrival_time"),
        final_seconds,
    )

    if entry:
        entry["current_delay_minutes"] = current_delay_minutes
        entry["current_delay_seconds"] = current_seconds
        entry["current_delay_reason"] = current_reason

    return {
        "stops": enriched_stops,
        "current_delay_seconds": current_seconds,
        "current_delay_minutes": current_delay_minutes,
        "current_delay_label": _delay_label_from_seconds(current_seconds),
        "current_delay_reason": current_reason,
        "delay_status": _schedule_status_for_delay(current_delay_minutes),
        "next_stop_expected_time": next_expected_time,
        "updated_arrival_time": updated_arrival,
        "remaining_delay_minutes": current_delay_minutes,
    }


def _bus_schedule_payload(route: Optional[Route], trip=None, bus_id: Optional[int] = None,
                          current_stop_idx: int = 0, next_stop_idx: int = 0,
                          display_points: Optional[list] = None,
                          direction: str = "forward",
                          phase_progress: float = 0.0,
                          assigned_trip_only: bool = False) -> dict:
    schedule = (
        _route_schedule_for_assigned_trip(route, trip)
        if assigned_trip_only
        else _route_schedule_for(route, trip)
    )
    source_stops = schedule.get("stops") or []
    stops = source_stops
    if display_points and source_stops:
        unused = list(source_stops)
        aligned = []
        for index, point in enumerate(display_points):
            point_name = (point.get("name") or "").strip().lower()
            match_index = next(
                (
                    candidate_index
                    for candidate_index, candidate in enumerate(unused)
                    if (candidate.get("name") or "").strip().lower() == point_name
                ),
                None,
            )
            if match_index is None:
                aligned.append(source_stops[index] if index < len(source_stops) else {})
            else:
                aligned.append(unused.pop(match_index))
        stops = aligned
    current_row = stops[current_stop_idx] if 0 <= current_stop_idx < len(stops) else {}
    next_row = stops[next_stop_idx] if 0 <= next_stop_idx < len(stops) else {}
    current_scheduled = current_row.get("scheduled_time") or current_row.get("arrival_time") or "--"
    next_scheduled = next_row.get("scheduled_time") or next_row.get("arrival_time") or "--"
    delay_payload = _delay_schedule_payload(
        bus_id,
        route,
        trip,
        direction,
        stops,
        current_stop_idx,
        next_stop_idx,
        phase_progress,
    )
    enriched_stops = delay_payload.get("stops") or stops
    delay_minutes = delay_payload.get("current_delay_minutes", 0)
    schedule_with_delay = {**schedule, "stops": enriched_stops}
    return {
        "schedule": schedule_with_delay,
        "departure_time": schedule.get("departure_time", "--"),
        "arrival_time": schedule.get("arrival_time", "--"),
        "updated_arrival_time": delay_payload.get("updated_arrival_time", schedule.get("arrival_time", "--")),
        "journey_duration": schedule.get("duration", "--"),
        "journey_duration_minutes": schedule.get("duration_minutes"),
        "schedule_status": delay_payload.get("delay_status", _schedule_status_for_delay(delay_minutes)),
        "delay_status": delay_payload.get("delay_status", _schedule_status_for_delay(delay_minutes)),
        "current_delay_minutes": delay_minutes,
        "current_delay_seconds": delay_payload.get("current_delay_seconds", delay_minutes * 60),
        "current_delay_label": delay_payload.get("current_delay_label", f"+{delay_minutes} min" if delay_minutes else "0 min"),
        "current_delay_reason": delay_payload.get("current_delay_reason", "On time"),
        "remaining_delay_minutes": delay_payload.get("remaining_delay_minutes", delay_minutes),
        "current_stop_scheduled_time": current_scheduled,
        "current_stop_actual_time": (
            enriched_stops[current_stop_idx].get("actual_time")
            if 0 <= current_stop_idx < len(enriched_stops)
            else _schedule_time_with_delay(current_scheduled, delay_minutes)
        ),
        "next_stop_scheduled_time": next_scheduled,
        "next_stop_expected_time": delay_payload.get("next_stop_expected_time", _schedule_time_with_delay(next_scheduled, delay_minutes)),
        "display_schedule_stops": enriched_stops,
    }


def _gtfs_backed_trip_for_route(route_id: Optional[int], reverse: bool = False) -> Optional[Trip]:
    if not route_id:
        return None
    route = db.session.get(Route, route_id)
    if not route:
        return None

    target_departure = _parse_time_to_minutes(route.departure_time)
    candidates = _gtfs_trip_candidates_for_route(route_id)
    expected_direction = 1 if reverse else 0
    direction_candidates = [
        candidate for candidate in candidates
        if getattr(candidate, "direction_id", None) is not None
        and int(candidate.direction_id) == expected_direction
    ]
    if direction_candidates:
        candidates = direction_candidates
    shape_ids = {candidate.shape_id for candidate in candidates if candidate.shape_id}
    shape_counts = {}
    if shape_ids:
        shape_counts = {
            shape_id: count
            for shape_id, count in (
                db.session.query(Shape.shape_id, func.count(Shape.id))
                .filter(Shape.shape_id.in_(shape_ids))
                .group_by(Shape.shape_id)
                .all()
            )
        }
    scored = []
    for candidate in candidates:
        score = _score_gtfs_trip_candidate(
            candidate,
            target_departure,
            shape_counts.get(candidate.shape_id, 0),
        )
        if score:
            scored.append(score)

    if not scored:
        logger.warning(
            "[GTFS_ASSIGNMENT] no schedulable trip route_id=%s route_code=%s reverse=%s",
            route.id, route.route_code, reverse,
        )
        return None

    best = sorted(
        scored,
        key=lambda item: (
            item["departure_delta"],
            -item["shape_points"],
            -item["stop_count"],
            -item["score"],
            item["trip"].id,
        ),
    )[0]
    logger.info(
        "[GTFS_ASSIGNMENT] route_id=%s route_code=%s selected_trip=%s reverse=%s score=%.2f departure_delta=%s shape_points=%s stop_count=%s",
        route.id,
        route.route_code,
        best["trip"].id,
        reverse,
        best["score"],
        best["departure_delta"],
        best["shape_points"],
        best["stop_count"],
    )
    return best["trip"]






def _bus_chain_debug(bus: Bus) -> dict:
    trip = _active_trip_for_bus(bus)
    route = db.session.get(Route, trip.route_id if trip else bus.route_id)
    stop_times_count = StopTime.query.filter_by(trip_id=trip.id).count() if trip else 0
    shape_points_count = (
        Shape.query.filter_by(shape_id=trip.shape_id).count()
        if trip and trip.shape_id else 0
    )
    geometry_available = bool(
        trip and route and trip.shape_id and stop_times_count > 0 and shape_points_count > 0
    )
    current_stop = None
    next_stop = None
    if geometry_available:
        gps = _fresh_gps_packet(bus.id, time.time())
        points = _route_points_for(route, trip) if gps else []
        if points:
            current_stop_idx = _nearest_route_index(gps["lat"], gps["lon"], points)
            next_stop_idx = min(current_stop_idx + 1, len(points) - 1)
            current_stop = points[current_stop_idx]["name"]
            next_stop = points[next_stop_idx]["name"]
    return {
        "bus_id": bus.id,
        "bus_number": bus.bus_number,
        "route_id": route.id if route else None,
        "route_code": route.route_code if route else None,
        "trip_id": trip.id if trip else None,
        "shape_id": trip.shape_id if trip else None,
        "stop_times_count": stop_times_count,
        "shape_points_count": shape_points_count,
        "geometry_available": geometry_available,
        "current_stop": current_stop,
        "next_stop": next_stop,
    }




def _route_has_geometry(route: Route, trip=None) -> bool:
    trip = _resolve_trip_for_route(route, trip)
    if trip and _shape_path_for_trip(trip):
        return True
    if trip:
        count = (
            StopTime.query
            .join(Stop, StopTime.stop_id == Stop.id)
            .filter(
                StopTime.trip_id == trip.id,
                Stop.stop_lat.isnot(None),
                Stop.stop_lon.isnot(None)
            )
            .count()
        )
        if count >= 2:
            return True
    stops_with_coords = Stop.query.filter_by(route_id=route.id).filter(
        Stop.stop_lat.isnot(None),
        Stop.stop_lon.isnot(None)
    ).count()
    return stops_with_coords >= 2


def _is_operational_route(route: Route) -> bool:
    """Route is operational when flagged or assigned to an active bus with GTFS geometry."""
    if getattr(route, "is_operational", False):
        return True
    has_bus = Bus.query.filter_by(route_id=route.id, is_active=True).first() is not None
    if not has_bus:
        return False
    return _route_has_geometry(route)


def _mark_route_operational(route_id: Optional[int]) -> None:
    if not route_id:
        return
    route = db.session.get(Route, route_id)
    if route:
        route.is_operational = True


def _bus_report_context(bus: Optional[Bus]) -> dict:
    if not bus:
        return {}
    trip = _driver_dashboard_trip_for_bus(bus)
    route = db.session.get(Route, trip.route_id if trip else bus.route_id)
    driver_name, driver_code = _driver_display_fields(bus)
    current_stop = None
    if route and trip:
        gps = _fresh_gps_packet(bus.id, time.time())
        points = _route_points_for_assigned_trip(route, trip)
        if points:
            current_stop = (
                points[_nearest_route_index(gps["lat"], gps["lon"], points)]["name"]
                if gps
                else points[0]["name"]
            )
    return {
        "bus_number": bus.bus_number,
        "registration_number": bus.registration_number,
        "driver_name": driver_name,
        "driver_code": driver_code,
        "route_name": route.name if route else None,
        "route_code": route.route_code if route else None,
        "route_id": route.id if route else None,
        "trip_id": trip.id if trip and getattr(trip, "id", None) else None,
        "current_stop": current_stop,
    }


def _clean_complaint_evidence_image(value: Optional[str]) -> Optional[str]:
    raw = (value or "").strip()
    if not raw:
        return None
    if not re.match(r"^data:image/(png|jpe?g|webp);base64,[A-Za-z0-9+/=\s]+$", raw, re.IGNORECASE):
        raise ValueError("Invalid complaint image upload.")
    if len(raw) > 2_000_000:
        raise ValueError("Complaint image is too large.")
    return re.sub(r"\s+", "", raw)


def _parse_iso_date(value: Optional[str]) -> Optional[datetime]:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("Date must be in YYYY-MM-DD format.") from exc


def _find_or_create_route(route_code: str, route_name: str, origin: str, destination: str,
                          distance_km: float, intermediates: str = "") -> Route:
    """Prevent duplicate routes by route_code. Stops come from GTFS import only."""
    existing = Route.query.filter_by(route_code=route_code.upper()).first()
    if existing:
        logger.info("[ROUTE_ASSIGN] Reusing existing route id=%s code=%s", existing.id, existing.route_code)
        return existing

    route = Route(
        route_code=route_code.upper(),
        name=route_name or f"{origin} to {destination}",
        origin=origin,
        destination=destination,
        distance_km=distance_km,
        is_operational=True
    )
    db.session.add(route)
    db.session.flush()
    return route

def create_app() -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    if app.config.get("SESSION_COOKIE_SECURE") and app.config.get("SECRET_KEY") and os.getenv("SECRET_KEY") is None:
        logger.warning("[SECURITY] Production should set a stable SECRET_KEY environment variable.")

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = "login_page"
    csrf = CSRFProtect(app)
    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=["100000 per day", "10000 per hour"],
        storage_uri=app.config.get("RATELIMIT_STORAGE_URI", "memory://")
    )
    app.csrf = csrf
    app.limiter = limiter

    @app.errorhandler(CSRFError)
    def handle_csrf_error(error):
        if _request_wants_json():
            return jsonify({"success": False, "error": error.description}), 400
        flash("Your session security token expired. Please try again.", "warning")
        return redirect(request.referrer or url_for("index"))

    @app.errorhandler(404)
    def handle_not_found(error):
        if _request_wants_json() or request.path.startswith("/api/"):
            return jsonify({"success": False, "error": "Not found"}), 404
        return render_template("error.html", error="Page not found"), 404

    @app.errorhandler(500)
    def handle_internal_error(error):
        db.session.rollback()
        logger.exception("[APP_ERROR] Unhandled request failure on %s", request.path)
        if _request_wants_json() or request.path.startswith("/api/"):
            return jsonify({"success": False, "error": "Internal server error"}), 500
        return render_template("error.html", error="Something went wrong. Please try again."), 500

    @app.after_request
    def set_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy",
            "geolocation=(self), camera=(), microphone=()",
        )
        return response

    @app.cli.command("import-gtfs")
    def import_gtfs_command():
        from import_apsrtc_data import process_extracted_gtfs
        process_extracted_gtfs()

    register_routes(app)
    with app.app_context():
        initialize_database()
        _ensure_lost_found_columns()
        _backfill_transpulse_ids()
        _repair_route_assignments()
        _repair_live_trip_stop_times_from_gtfs()
        _validate_data_integrity()

    return app

@login_manager.user_loader
def load_user(user_id: str):
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        logger.warning("[AUTH] Invalid user id in session: %r", user_id)
        return None

@login_manager.unauthorized_handler
def unauthorized():
    if _request_wants_json() or request.path.startswith("/api/"):
        return jsonify({"success": False, "error": "Authentication required"}), 401
    flash("Please log in to continue.", "warning")
    return redirect(url_for("login_page"))

def role_required(*allowed_roles):
    def decorator(func):
        @wraps(func)
        @login_required
        def wrapper(*args, **kwargs):
            if current_user.role not in allowed_roles:
                if _request_wants_json() or request.path.startswith("/api/"):
                    return jsonify({"success": False, "error": "Forbidden"}), 403
                flash("You do not have access to this page.", "danger")
                return redirect(url_for("index"))
            return func(*args, **kwargs)
        return wrapper
    return decorator

def _dashboard_route_for_role(role: str) -> str:
    if role == "admin": return "admin_dashboard"
    if role == "driver": return "driver_dashboard"
    return "passenger_dashboard"

def _request_wants_json() -> bool:
    return (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.accept_mimetypes.best == "application/json"
    )

def _coordinate(raw_value):
    try:
        return float(raw_value) if raw_value not in (None, "") else None
    except (TypeError, ValueError):
        return None

def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    if lat1 is None or lng1 is None or lat2 is None or lng2 is None: return 0.0
    radius = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = (math.sin(d_lat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lng / 2) ** 2)
    return 2 * radius * math.asin(math.sqrt(a))


def _path_indexes_for_stops(points: list, path: list) -> list:
    """Find ordered path indexes nearest to each GTFS stop, for map rendering."""
    if not points or not path:
        return []

    indexes = []
    search_start = 0
    for point in points:
        best_index = search_start
        best_distance = float("inf")
        for path_index in range(search_start, len(path)):
            candidate = path[path_index]
            distance = _haversine_km(
                point["lat"], point["lng"], candidate["lat"], candidate["lng"]
            )
            if distance < best_distance:
                best_distance = distance
                best_index = path_index
        indexes.append(best_index)
        search_start = best_index

    indexes[0] = 0
    indexes[-1] = len(path) - 1
    for index in range(1, len(indexes)):
        indexes[index] = max(indexes[index], indexes[index - 1])
    return indexes


def _gtfs_shape_has_sufficient_detail(points: list, shape_path: list) -> bool:
    """Identify simplified GTFS shapes that should receive road geometry."""
    if len(points) < 2 or len(shape_path) < 2:
        return False

    leg_count = len(points) - 1
    minimum_points = max(8, leg_count * 4 + 1)
    if len(shape_path) < minimum_points:
        return False

    stop_distance_km = sum(
        _haversine_km(start["lat"], start["lng"], end["lat"], end["lng"])
        for start, end in zip(points, points[1:])
    )
    # Dense city routes do not need hundreds of points, while long corridors
    # with a point every several kilometres are visually simplified.
    return stop_distance_km <= 0 or (stop_distance_km / len(shape_path)) <= 2.5


def _road_geometry_cache_identity(route: Route, trip, points: list) -> tuple[str, str]:
    stop_payload = [
        [
            point.get("stop_order"),
            round(float(point["lat"]), 6),
            round(float(point["lng"]), 6),
        ]
        for point in points
    ]
    stop_signature = hashlib.sha256(
        json.dumps(stop_payload, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    cache_payload = {
        "route_id": route.id,
        "shape_id": getattr(trip, "shape_id", None),
        "stop_signature": stop_signature,
    }
    cache_key = hashlib.sha256(
        json.dumps(cache_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return cache_key, stop_signature


def _decode_cached_road_geometry(cache_entry: RoadGeometryCache) -> tuple[list, list]:
    try:
        path = json.loads(cache_entry.geometry_json or "[]")
        leg_end_indexes = json.loads(cache_entry.leg_end_indexes_json or "[]")
    except (TypeError, ValueError):
        return [], []

    if not isinstance(path, list) or len(path) < 2 or not isinstance(leg_end_indexes, list):
        return [], []
    if not all(isinstance(point, dict) and "lat" in point and "lng" in point for point in path):
        return [], []
    return path, leg_end_indexes


def _osrm_route_for_stop_sequence(points: list) -> list:
    """Route through every ordered GTFS stop; OSRM solves consecutive legs."""
    if len(points) < 2:
        return []

    path = []
    # The public OSRM service limits waypoints.  Adjacent chunks share their
    # boundary stop so every generated segment remains stop-to-stop.
    for start_index in range(0, len(points) - 1, OSRM_MAX_WAYPOINTS - 1):
        waypoint_chunk = points[start_index:start_index + OSRM_MAX_WAYPOINTS]
        coordinates = ";".join(
            f"{float(point['lng']):.6f},{float(point['lat']):.6f}"
            for point in waypoint_chunk
        )
        url = (
            f"{OSRM_BASE_URL}/route/v1/driving/{coordinates}"
            "?overview=full&geometries=geojson&steps=false"
        )
        try:
            request_object = Request(url, headers={"User-Agent": "TransPulse/1.0"})
            with urlopen(request_object, timeout=OSRM_TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read().decode("utf-8"))

            route = (payload.get("routes") or [None])[0]
            coordinates_out = ((route or {}).get("geometry") or {}).get("coordinates") or []
            segment = [
                {"lat": float(latitude), "lng": float(longitude)}
                for longitude, latitude in coordinates_out
                if latitude is not None and longitude is not None
            ]
            if len(segment) < 2:
                raise ValueError("OSRM returned no usable road geometry")
        except Exception as exc:
            logger.warning("[OSRM] Chunk query failed, falling back to leg-by-leg: %s", exc)
            segment = []
            for i in range(len(waypoint_chunk) - 1):
                p1 = waypoint_chunk[i]
                p2 = waypoint_chunk[i + 1]
                leg_coords = f"{float(p1['lng']):.6f},{float(p1['lat']):.6f};{float(p2['lng']):.6f},{float(p2['lat']):.6f}"
                leg_url = (
                    f"{OSRM_BASE_URL}/route/v1/driving/{leg_coords}"
                    "?overview=full&geometries=geojson&steps=false"
                )
                leg_segment = []
                try:
                    leg_request = Request(leg_url, headers={"User-Agent": "TransPulse/1.0"})
                    with urlopen(leg_request, timeout=OSRM_TIMEOUT_SECONDS) as response:
                        leg_payload = json.loads(response.read().decode("utf-8"))
                    leg_route = (leg_payload.get("routes") or [None])[0]
                    leg_coords_out = ((leg_route or {}).get("geometry") or {}).get("coordinates") or []
                    leg_segment = [
                        {"lat": float(latitude), "lng": float(longitude)}
                        for longitude, latitude in leg_coords_out
                        if latitude is not None and longitude is not None
                    ]
                except Exception as leg_exc:
                    logger.warning("[OSRM] Leg query failed between %s and %s: %s", p1, p2, leg_exc)

                if len(leg_segment) < 2:
                    leg_segment = [
                        {"lat": float(p1["lat"]), "lng": float(p1["lng"])},
                        {"lat": float(p2["lat"]), "lng": float(p2["lng"])},
                    ]

                if segment and leg_segment[0] == segment[-1]:
                    leg_segment = leg_segment[1:]
                segment.extend(leg_segment)

        if path and segment[0] == path[-1]:
            segment = segment[1:]
        path.extend(segment)

    if len(path) < 2:
        raise ValueError("OSRM returned no usable road geometry")
    return path


def _cache_road_geometry_failure(
    cache_entry: Optional[RoadGeometryCache],
    cache_key: str,
    stop_signature: str,
    route: Route,
    trip,
    error: Exception,
) -> Optional[RoadGeometryCache]:
    message = str(error)[:255] or error.__class__.__name__
    if not cache_entry:
        existing = RoadGeometryCache.query.filter_by(cache_key=cache_key).first()
        if existing:
            return existing
        cache_entry = RoadGeometryCache(
            cache_key=cache_key,
            route_id=route.id,
            shape_id=getattr(trip, "shape_id", None),
            stop_signature=stop_signature,
        )
        db.session.add(cache_entry)
    cache_entry.status = "failed"
    cache_entry.geometry_json = None
    cache_entry.leg_end_indexes_json = None
    cache_entry.last_error = message
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return RoadGeometryCache.query.filter_by(cache_key=cache_key).first()
    logger.warning(
        "[ROAD_GEOMETRY] OSRM fallback route_id=%s shape_id=%s reason=%s",
        route.id, getattr(trip, "shape_id", None), message,
    )


def _road_geometry_failure_is_recent(cache_entry: RoadGeometryCache) -> bool:
    if not cache_entry or not cache_entry.updated_at:
        return False
    updated_at = cache_entry.updated_at
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=UTC)
    return (datetime.now(UTC) - updated_at).total_seconds() < ROAD_GEOMETRY_FAILURE_RETRY_SECONDS


def _display_geometry_for_map(route: Route, trip, points: list, shape_path: list) -> dict:
    """Return a rendering-only geometry, never changing GTFS or tracking paths."""
    gtfs_points = len(shape_path) if shape_path else 0
    stop_points = len(points) if points else 0

    # If GTFS shapes are unavailable or simplified (stop-to-stop straight lines), 
    # check cache or generate using OSRM.
    if len(points) >= 2:
        cache_key, stop_signature = _road_geometry_cache_identity(route, trip, points)
        cache_entry = RoadGeometryCache.query.filter_by(cache_key=cache_key).first()

        # 2. Try Cached road geometry
        if cache_entry and cache_entry.status == "ready":
            cached_path, cached_leg_indexes = _decode_cached_road_geometry(cache_entry)
            if len(cached_path) >= 2 and len(cached_leg_indexes) == len(points):
                source = "road_cache"
                display_points_cnt = len(cached_path)
                logger.info(
                    "[GEOMETRY] source=%s gtfs_points=%s display_points=%s stop_points=%s",
                    source, gtfs_points, display_points_cnt, stop_points
                )
                return {
                    "path": cached_path,
                    "leg_end_indexes": cached_leg_indexes,
                    "source": source,
                    "generated_point_count": len(cached_path),
                }

        # 3. If cache entry is not failed recently, try generating via OSRM
        if not (cache_entry and cache_entry.status == "failed" and _road_geometry_failure_is_recent(cache_entry)):
            try:
                generated_path = _osrm_route_for_stop_sequence(points)
                leg_end_indexes = _path_indexes_for_stops(points, generated_path)
                if len(leg_end_indexes) != len(points):
                    raise ValueError("OSRM geometry could not be aligned to GTFS stops")

                if not cache_entry:
                    existing = RoadGeometryCache.query.filter_by(cache_key=cache_key).first()
                    if existing:
                        cached_path, cached_leg_indexes = _decode_cached_road_geometry(existing)
                        if existing.status == "ready" and len(cached_path) >= 2 and len(cached_leg_indexes) == len(points):
                            source = "road_cache"
                            display_points_cnt = len(cached_path)
                            logger.info(
                                "[GEOMETRY] source=%s gtfs_points=%s display_points=%s stop_points=%s",
                                source, gtfs_points, display_points_cnt, stop_points
                            )
                            return {
                                "path": cached_path,
                                "leg_end_indexes": cached_leg_indexes,
                                "source": source,
                                "generated_point_count": len(cached_path),
                            }
                        cache_entry = existing
                    else:
                        cache_entry = RoadGeometryCache(
                            cache_key=cache_key,
                            route_id=route.id,
                            shape_id=getattr(trip, "shape_id", None),
                            stop_signature=stop_signature,
                        )
                        db.session.add(cache_entry)

                cache_entry.status = "ready"
                cache_entry.geometry_json = json.dumps(generated_path, separators=(",", ":"))
                cache_entry.leg_end_indexes_json = json.dumps(leg_end_indexes, separators=(",", ":"))
                cache_entry.last_error = None
                try:
                    db.session.commit()
                except IntegrityError:
                    db.session.rollback()
                    existing = RoadGeometryCache.query.filter_by(cache_key=cache_key).first()
                    if existing:
                        cached_path, cached_leg_indexes = _decode_cached_road_geometry(existing)
                        if existing.status == "ready" and len(cached_path) >= 2 and len(cached_leg_indexes) == len(points):
                            source = "road_cache"
                            display_points_cnt = len(cached_path)
                            logger.info(
                                "[GEOMETRY] source=%s gtfs_points=%s display_points=%s stop_points=%s",
                                source, gtfs_points, display_points_cnt, stop_points
                            )
                            return {
                                "path": cached_path,
                                "leg_end_indexes": cached_leg_indexes,
                                "source": source,
                                "generated_point_count": len(cached_path),
                            }

                source = "generated"
                display_points_cnt = len(generated_path)
                logger.info(
                    "[GEOMETRY] source=%s gtfs_points=%s display_points=%s stop_points=%s",
                    source, gtfs_points, display_points_cnt, stop_points
                )
                return {
                    "path": generated_path,
                    "leg_end_indexes": leg_end_indexes,
                    "source": source,
                    "generated_point_count": len(generated_path),
                }
            except (URLError, TimeoutError, ValueError, OSError, json.JSONDecodeError) as error:
                _cache_road_geometry_failure(
                    cache_entry, cache_key, stop_signature, route, trip, error
                )
                try:
                    other_cache = RoadGeometryCache.query.filter_by(route_id=route.id, status="ready").first()
                    if other_cache:
                        cached_path, cached_leg_indexes = _decode_cached_road_geometry(other_cache)
                        if len(cached_path) >= 2 and len(cached_leg_indexes) == len(points):
                            source = "road_cache"
                            display_points_cnt = len(cached_path)
                            logger.info(
                                "[GEOMETRY] fallback_source=%s gtfs_points=%s display_points=%s stop_points=%s",
                                source, gtfs_points, display_points_cnt, stop_points
                            )
                            return {
                                "path": cached_path,
                                "leg_end_indexes": cached_leg_indexes,
                                "source": source,
                                "generated_point_count": len(cached_path),
                            }
                except Exception as fallback_exc:
                    logger.warning("[GEOMETRY] Fallback cache lookup failed: %s", fallback_exc)

    # 4. Check if GTFS shapes exist and are sufficiently detailed as a fallback
    if shape_path and _gtfs_shape_has_sufficient_detail(points, shape_path):
        source = "gtfs"
        display_path = shape_path
        display_points_cnt = len(display_path)
        logger.info(
            "[GEOMETRY] fallback_source=%s gtfs_points=%s display_points=%s stop_points=%s",
            source, gtfs_points, display_points_cnt, stop_points
        )
        return {
            "path": display_path,
            "leg_end_indexes": _path_indexes_for_stops(points, display_path),
            "source": source,
            "generated_point_count": 0,
        }

    # 5. Fallback to stop coordinates (stops)
    fallback_path = shape_path if len(shape_path) >= 2 else [{"lat": p["lat"], "lng": p["lng"]} for p in points]
    source = "stops"
    display_points_cnt = len(fallback_path)
    logger.info(
        "[GEOMETRY] source=%s gtfs_points=%s display_points=%s stop_points=%s",
        source, gtfs_points, display_points_cnt, stop_points
    )
    return {
        "path": fallback_path,
        "leg_end_indexes": _path_indexes_for_stops(points, fallback_path),
        "source": source,
        "generated_point_count": 0,
    }

def _shape_path_for_trip(trip) -> list:
    if not trip or not getattr(trip, "shape_id", None):
        return []
    shapes = (
        Shape.query
        .filter(Shape.shape_id == trip.shape_id)
        .order_by(Shape.shape_pt_sequence.asc())
        .all()
    )
    return [
        {
            "lat": float(s.shape_pt_lat),
            "lng": float(s.shape_pt_lon),
            "sequence": int(s.shape_pt_sequence),
            "shape_index": index,
        }
        for index, s in enumerate(shapes)
        if s.shape_pt_lat is not None and s.shape_pt_lon is not None
    ]


def _route_points_for_assigned_trip(route: Route, trip) -> list:
    """Live tracking points: Trip -> StopTime -> Stop only, no route/template fallback."""
    if not route or not trip or getattr(trip, "route_id", None) != getattr(route, "id", None):
        return []
    stop_times = (
        StopTime.query
        .filter_by(trip_id=trip.id)
        .order_by(StopTime.stop_sequence.asc())
        .all()
    )
    points = []
    for st in stop_times:
        stop = st.stop
        if not stop or stop.stop_lat is None or stop.stop_lon is None:
            continue
        points.append({
            "name": stop.stop_name,
            "lat": float(stop.stop_lat),
            "lng": float(stop.stop_lon),
            "stop_order": st.stop_sequence,
        })

    # Reverse if direction is backward and points are in forward order
    direction_id = getattr(trip, "direction_id", 0)
    is_return = (direction_id == 1 or getattr(trip, "status", "") in ("return_ready", "return_running", "return_completed"))
    if is_return and points:
        forward_stops = Stop.query.filter_by(route_id=route.id).order_by(Stop.stop_order.asc()).all()
        if forward_stops and points[0]["name"] == forward_stops[0].stop_name:
            points = list(reversed(points))
            for idx, pt in enumerate(points):
                pt["stop_order"] = idx + 1

    return points if len(points) >= 2 else []



def _route_geometry_path_for_assigned_trip(trip) -> list:
    """Live tracking shape: assigned trip shape only, never stop or route fallback."""
    shape_path = _shape_path_for_trip(trip)
    if not shape_path or len(shape_path) < 2:
        return shape_path if shape_path else []
    if trip:
        stop_times = _ordered_stop_times_for_trip(trip.id)
        valid_stops = [st.stop for st in stop_times if st.stop and st.stop.stop_lat is not None and st.stop.stop_lon is not None]
        if valid_stops:
            first_lat = float(valid_stops[0].stop_lat)
            first_lon = float(valid_stops[0].stop_lon)
            dist_start = _haversine_km(first_lat, first_lon, shape_path[0]["lat"], shape_path[0]["lng"])
            dist_end = _haversine_km(first_lat, first_lon, shape_path[-1]["lat"], shape_path[-1]["lng"])
            if dist_end < dist_start:
                return list(reversed(shape_path))
    return shape_path


def _ensure_trip_shape_from_stop_times(trip) -> bool:
    if not trip:
        return False
    if _route_geometry_path_for_assigned_trip(trip):
        return True

    stop_times = _ordered_stop_times_for_trip(trip.id)
    points = []
    for stop_time in stop_times:
        stop = stop_time.stop
        if stop and stop.stop_lat is not None and stop.stop_lon is not None:
            points.append((float(stop.stop_lat), float(stop.stop_lon)))
    if len(points) < 2:
        return False

    if not getattr(trip, "shape_id", None):
        trip.shape_id = f"tp-generated-trip-{trip.id}"

    existing_count = Shape.query.filter_by(shape_id=trip.shape_id).count()
    if existing_count >= 2:
        return True
    if existing_count:
        Shape.query.filter_by(shape_id=trip.shape_id).delete(synchronize_session=False)

    for sequence, (lat, lon) in enumerate(points, start=1):
        db.session.add(Shape(
            shape_id=trip.shape_id,
            shape_pt_lat=lat,
            shape_pt_lon=lon,
            shape_pt_sequence=sequence,
        ))
    db.session.flush()
    logger.warning(
        "[GTFS_ASSIGNMENT] generated fallback shape from stop_times trip_id=%s shape_id=%s points=%s",
        trip.id,
        trip.shape_id,
        len(points),
    )
    return True


def _assigned_trip_validation_error(route: Optional[Route], trip, points: list, route_path: list) -> Optional[str]:
    if not trip:
        return "Validation error: no assigned trip is active for this bus."
    if not route:
        return f"Validation error: assigned trip {trip.id} has no valid route."
    if getattr(trip, "route_id", None) != getattr(route, "id", None):
        return (
            f"Validation error: assigned trip {trip.id} belongs to route "
            f"{getattr(trip, 'route_id', None)}, not route {getattr(route, 'id', None)}."
        )
    stop_time_count = StopTime.query.filter_by(trip_id=trip.id).count()
    if stop_time_count < 2:
        return f"Validation error: assigned trip {trip.id} has no complete stop-time timeline."
    if len(points) < 2:
        return f"Validation error: assigned trip {trip.id} stop times do not have usable stop coordinates."
    if not getattr(trip, "shape_id", None) or len(route_path) < 2:
        _ensure_trip_shape_from_stop_times(trip)
        route_path = _route_geometry_path_for_assigned_trip(trip)
    if not getattr(trip, "shape_id", None):
        return f"Validation error: assigned trip {trip.id} has no GTFS shape and no generated shape could be built."
    if getattr(trip, "shape_id", None) and len(route_path) < 2:
        logger.warning(
            "[GTFS_ASSIGNMENT] trip %s shape %s has no usable shape points; road geometry fallback will be used",
            trip.id,
            trip.shape_id,
        )
    return None


def _bearing_between_points(start: dict, end: dict) -> float:
    if not start or not end:
        return 0.0
    return math.degrees(math.atan2(
        float(end["lng"]) - float(start["lng"]),
        float(end["lat"]) - float(start["lat"]),
    ))


def _position_on_path(path: list, progress: float) -> tuple:
    """Return an interpolated coordinate and bearing at distance progress."""
    if not path:
        return None, None, 0.0, 0
    if len(path) == 1:
        return path[0]["lat"], path[0]["lng"], 0.0, 0

    progress = max(0.0, min(1.0, progress))
    if progress <= 0:
        start, end = path[0], path[1]
        bearing = _bearing_between_points(start, end)
        return start["lat"], start["lng"], bearing, 0
    if progress >= 1:
        start, end = path[-2], path[-1]
        bearing = _bearing_between_points(start, end)
        return end["lat"], end["lng"], bearing, len(path) - 1

    segments = []
    total_dist = 0.0
    for i in range(len(path) - 1):
        seg_dist = _haversine_km(
            path[i]["lat"], path[i]["lng"],
            path[i + 1]["lat"], path[i + 1]["lng"]
        )
        segments.append(seg_dist)
        total_dist += seg_dist

    if total_dist == 0:
        return path[0]["lat"], path[0]["lng"], 0.0, 0

    target_dist = progress * total_dist
    travelled = 0.0
    for i, seg_dist in enumerate(segments):
        if seg_dist <= 0:
            continue
        if target_dist <= travelled + seg_dist or i == len(segments) - 1:
            start = path[i]
            end = path[i + 1]
            segment_progress = max(0.0, min(1.0, (target_dist - travelled) / seg_dist))
            lat = start["lat"] + ((end["lat"] - start["lat"]) * segment_progress)
            lng = start["lng"] + ((end["lng"] - start["lng"]) * segment_progress)
            bearing = _bearing_between_points(start, end)
            return lat, lng, bearing, i
        travelled += seg_dist

    point = path[-1]
    return point["lat"], point["lng"], 0.0, len(path) - 1


def _route_points_for(route, trip=None):
    """GTFS stop sequence: Trip → StopTime → Stop ordered by stop_sequence."""
    trip = _resolve_trip_for_route(route, trip)

    if trip:
        stop_times = (
            StopTime.query
            .filter_by(trip_id=trip.id)
            .order_by(StopTime.stop_sequence.asc())
            .all()
        )
        points = []
        for st in stop_times:
            stop = st.stop
            if not stop or stop.stop_lat is None or stop.stop_lon is None:
                continue
            points.append({
                "name": stop.stop_name,
                "lat": float(stop.stop_lat),
                "lng": float(stop.stop_lon),
                "stop_order": st.stop_sequence
            })
        if len(points) >= 2:
            return points

    stops = (
        Stop.query
        .filter_by(route_id=route.id)
        .order_by(Stop.stop_order.asc())
        .all()
    )
    points = []
    for stop in stops:
        if stop.stop_lat is None or stop.stop_lon is None:
            continue
        points.append({
            "name": stop.stop_name,
            "lat": float(stop.stop_lat),
            "lng": float(stop.stop_lon),
            "stop_order": stop.stop_order or (len(points) + 1),
        })
    if len(points) >= 2:
        return points

    return []


def _shape_point_count_db(shape_id: Optional[str]) -> int:
    if not shape_id:
        return 0
    return Shape.query.filter_by(shape_id=shape_id).count()


def _snap_stop_to_shape_index(stop_lat: float, stop_lng: float, shape_path: list) -> int:
    min_dist = float("inf")
    best_idx = 0
    for i, pt in enumerate(shape_path):
        d = _haversine_km(stop_lat, stop_lng, pt["lat"], pt["lng"])
        if d < min_dist:
            min_dist = d
            best_idx = i
    return best_idx


def _path_segment_distance(path_segment: list) -> float:
    total = 0.0
    for i in range(len(path_segment) - 1):
        total += _haversine_km(
            path_segment[i]["lat"], path_segment[i]["lng"],
            path_segment[i + 1]["lat"], path_segment[i + 1]["lng"]
        )
    return total


def _known_stop_point_by_name(name: str) -> Optional[dict]:
    clean = (name or "").strip()
    if not clean:
        return None
    stop = (
        Stop.query
        .filter(
            func.lower(Stop.stop_name) == clean.lower(),
            Stop.stop_lat.isnot(None),
            Stop.stop_lon.isnot(None),
        )
        .order_by(Stop.stop_code.desc())
        .first()
    )
    if not stop:
        return None
    return {
        "name": stop.stop_name,
        "lat": float(stop.stop_lat),
        "lng": float(stop.stop_lon),
    }


def _known_points_for_manual_route(route: Route, intermediates: str = "") -> list:
    points = []
    for name in _manual_stop_names(route, intermediates):
        point = _known_stop_point_by_name(name)
        if not point:
            return []
        points.append(point)
    return points


def _auto_route_distance_km(route: Route, intermediates: str = "") -> float:
    trip = _resolve_trip_for_route(route)
    shape_path = _shape_path_for_trip(trip) if trip else []
    if len(shape_path) >= 2:
        return round(_path_segment_distance(shape_path), 2)

    points = _route_points_for(route, trip)
    if len(points) < 2:
        points = _known_points_for_manual_route(route, intermediates)

    if len(points) >= 2:
        try:
            road_path = _osrm_route_for_stop_sequence(points)
            if len(road_path) >= 2:
                return round(_path_segment_distance(road_path), 2)
        except (URLError, TimeoutError, ValueError, OSError, json.JSONDecodeError):
            pass
        return round(_path_segment_distance(points), 2)

    return round(float(route.distance_km or 0.0), 2)


def _extract_shape_segment(shape_path: list, start_idx: int, end_idx: int) -> list:
    if start_idx <= end_idx:
        return shape_path[start_idx:end_idx + 1]
    return list(reversed(shape_path[end_idx:start_idx + 1]))


def _path_index_at_distance_fraction(path: list, fraction: float) -> int:
    """Find the rendered-path point at the same travelled-distance fraction."""
    if len(path) < 2:
        return 0
    fraction = max(0.0, min(1.0, fraction))
    if fraction == 0:
        return 0
    total_distance = _path_segment_distance(path)
    if total_distance <= 0:
        return 0

    target_distance = total_distance * fraction
    travelled = 0.0
    for index in range(len(path) - 1):
        travelled += _haversine_km(
            path[index]["lat"], path[index]["lng"],
            path[index + 1]["lat"], path[index + 1]["lng"],
        )
        if travelled >= target_distance:
            return index + 1
    return len(path) - 1


def _simulation_signature(bus: Bus, trip, route: Route) -> str:
    return "|".join([
        str(getattr(bus, "id", "bus")),
        str(getattr(bus, "bus_number", "")),
        str(getattr(route, "id", "")),
        str(getattr(trip, "id", "") if trip else ""),
        str(getattr(trip, "shape_id", "") if trip else ""),
    ])


def _simulation_seed(bus: Bus, trip, route: Route) -> int:
    return int(hashlib.sha256(_simulation_signature(bus, trip, route).encode("utf-8")).hexdigest()[:16], 16)


def _datetime_epoch_seconds(value) -> Optional[float]:
    if not value:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.timestamp()
    return None


def _persistent_trip_started_at(trip) -> Optional[float]:
    return _datetime_epoch_seconds(getattr(trip, "start_time", None) if trip else None)


def _reset_bus_simulation_state(bus_id: Optional[int], route_id: Optional[int] = None,
                                trip_id: Optional[int] = None, start_time: Optional[float] = None) -> None:
    if not bus_id:
        return
    bus_key = int(bus_id)
    BUS_DELAY_DATA.pop(bus_key, None)
    BUS_SIMULATION_STATE[bus_key] = {
        "route_id": route_id,
        "trip_id": trip_id,
        "started_at": float(start_time or time.time()),
        "timestamp": time.time(),
    }




def _tracking_geometry_for_route(route: Route, trip, points: list, shape_path: list) -> dict:
    """Live movement uses stored/GTFS route geometry, never direct stop links."""
    if len(shape_path) >= 2:
        display_geometry = _display_geometry_for_map(route, trip, points, shape_path)
        path = display_geometry.get("path") or shape_path
        if len(path) >= 2:
            return display_geometry
    if len(points) >= 2:
        display_geometry = _display_geometry_for_map(route, trip, points, [])
        path = display_geometry.get("path") or []
        if len(path) >= 2:
            return display_geometry
    return {
        "path": [],
        "leg_end_indexes": [],
        "source": "unavailable",
        "generated_point_count": 0,
    }










def _route_geometry_path(route, trip=None) -> list:
    if isinstance(route, int):
        route = db.session.get(Route, route)
    if not route:
        return []
    trip = _resolve_trip_for_route(route, trip)
    shape_path = _route_geometry_path_for_assigned_trip(trip) if trip else []
    if shape_path:
        return shape_path
    points = _route_points_for(route, trip)
    return [{"lat": p["lat"], "lng": p["lng"]} for p in points]


def _complete_active_trips(bus_id: int, exclude_trip_id: Optional[int] = None) -> None:
    query = Trip.query.filter(
        Trip.bus_id == bus_id,
        Trip.status.in_(ACTIVE_TRIP_STATUSES)
    )
    if exclude_trip_id is not None:
        query = query.filter(Trip.id != exclude_trip_id)
    query.update(
        {"status": "completed", "end_time": datetime.now(UTC)},
        synchronize_session=False
    )


def _retire_pending_assignment_trips(bus_id: int) -> None:
    Trip.query.filter(
        Trip.bus_id == bus_id,
        Trip.status.in_(("assigned", "ready", "scheduled", "return_ready"))
    ).update(
        {"status": "cancelled", "end_time": datetime.now(UTC)},
        synchronize_session=False
    )


def _create_trip_for_bus(bus: Bus, route_id: int) -> Trip:
    template_trip = _gtfs_backed_trip_for_route(route_id)
    route = db.session.get(Route, route_id)
    if not template_trip and _route_has_gtfs_stop_times(route_id):
        raise ValueError("No scheduled GTFS trip with complete stop times was found for this route. Assignment was not saved.")
    new_trip = Trip(
        bus_id=bus.id,
        route_id=route_id,
        shape_id=template_trip.shape_id if template_trip else None,
        direction_id=getattr(template_trip, "direction_id", None) if template_trip else None,
        service_id=getattr(template_trip, "service_id", None) if template_trip else None,
        gtfs_trip_id=None,
        trip_headsign=getattr(template_trip, "trip_headsign", None) if template_trip else None,
        trip_short_name=getattr(template_trip, "trip_short_name", None) if template_trip else None,
        block_id=getattr(template_trip, "block_id", None) if template_trip else None,
        wheelchair_accessible=getattr(template_trip, "wheelchair_accessible", 0) if template_trip else 0,
        bikes_allowed=getattr(template_trip, "bikes_allowed", 0) if template_trip else 0,
        start_time=None,
        status="assigned"
    )
    db.session.add(new_trip)
    db.session.flush()
    if template_trip:
        new_trip.gtfs_trip_id = _assignment_gtfs_trip_id(template_trip, new_trip.id)
    if template_trip:
        _copy_stop_times_from_template(new_trip, template_trip)
    else:
        if route:
            _ensure_trip_stop_times_from_route(new_trip, route)
    if template_trip:
        _ensure_trip_shape_from_stop_times(new_trip)
        points = _route_points_for_assigned_trip(route, new_trip) if route else []
        route_path = _route_geometry_path_for_assigned_trip(new_trip)
        validation_error = _assigned_trip_validation_error(route, new_trip, points, route_path)
        if validation_error:
            logger.warning(
                "[GTFS_ASSIGNMENT] selected template trip failed assignment validation route_id=%s template_trip_id=%s reason=%s",
                route_id,
                template_trip.id,
                validation_error,
            )
            raise ValueError("The selected GTFS trip failed structural validation. Assignment was not saved.")
    logger.info(
        "[ROUTE_ASSIGN] bus_id=%s bus_number=%s bus.route_id=%s trip.route_id=%s shape_id=%s",
        bus.id, bus.bus_number, route_id, route_id,
        new_trip.shape_id
    )
    return new_trip


def _active_trip_for_bus(bus: Bus) -> Optional[Trip]:
    if not bus:
        return None

    order_by = []
    if bus.route_id:
        order_by.append(case((Trip.route_id == bus.route_id, 0), else_=1))
    order_by.extend([Trip.start_time.desc(), Trip.created_at.desc(), Trip.id.desc()])

    trip = (
        Trip.query.filter(
            Trip.bus_id == bus.id,
            Trip.status.in_(ACTIVE_TRIP_STATUSES)
        )
        .order_by(*order_by)
        .first()
    )

    logger.info(
        "[ACTIVE_TRIP] bus=%s route=%s trip=%s status=%s",
        bus.id,
        bus.route_id,
        trip.id if trip else None,
        trip.status if trip else None,
    )

    return trip

def _driver_dashboard_trip_for_bus(bus: Optional[Bus]) -> Optional[Trip]:
    if not bus:
        return None
    active_trip = _active_trip_for_bus(bus)
    if active_trip:
        return active_trip
    if not bus.route_id:
        return None

    in_cooldown = False
    if bus.id in BUS_COMPLETED_TRIPS:
        elapsed = time.time() - BUS_COMPLETED_TRIPS[bus.id]
        if elapsed < 15.0:
            in_cooldown = True
        else:
            BUS_COMPLETED_TRIPS.pop(bus.id, None)

    if not in_cooldown:
        trip = (
            Trip.query.filter(
                Trip.bus_id == bus.id,
                Trip.route_id == bus.route_id,
                Trip.status.in_(("active", "in_progress", "return_ready", "assigned", "ready", "scheduled"))
            )
            .order_by(
                case(
                    (Trip.status.in_(ACTIVE_TRIP_STATUSES), 0),
                    (Trip.status == "return_ready", 1),
                    (Trip.status == "assigned", 2),
                    (Trip.status.in_(("ready", "scheduled")), 3),
                    else_=3,
                ),
                Trip.created_at.desc(),
                Trip.id.desc(),
            )
            .first()
        )
        if trip:
            return trip

    return (
        Trip.query.filter(
            Trip.bus_id == bus.id,
            Trip.route_id == bus.route_id,
            Trip.status.in_(("completed", "return_completed"))
        )
        .order_by(Trip.created_at.desc(), Trip.id.desc())
        .first()
    )


def _is_tracking_available(trip_status: str, gps_status: str) -> bool:
    running_states = {"RUNNING", "RETURN_RUNNING", "active", "in_progress"}
    return (trip_status in running_states and gps_status in ("Online", "LIVE GPS"))


def _trip_state_label(trip: Optional[Trip], bus: Optional[Bus] = None) -> str:
    if not trip:
        return "OFFLINE"
    status = (trip.status or "").strip().lower()
    
    # Active / Running states
    if status in {"active", "in_progress", "running"} or status in ACTIVE_TRIP_STATUSES:
        if getattr(trip, "direction_id", 0) == 1:
            return "RETURN_RUNNING"
        return "RUNNING"
        
    # Return ready state
    if status == "return_ready":
        return "RETURN_READY"
        
    # Completed states
    if status in {"completed", "return_completed", "arrived_destination", "waiting_for_next_assignment"}:
        if getattr(trip, "direction_id", 0) == 1:
            return "RETURN_COMPLETED"
        return "COMPLETED"
        
    # WAITING_TO_DEPART states
    if status in {"assigned", "ready", "scheduled", "waiting_to_depart"}:
        return "WAITING_TO_DEPART"
        
    # Fallback checking bus activity
    if bus and not bus.is_active:
        return "OFFLINE"
        
    return "WAITING_TO_DEPART"




def _assignment_gtfs_trip_id(template_trip: Optional[Trip], assignment_trip_id: int) -> str:
    source_id = (
        getattr(template_trip, "gtfs_trip_id", None)
        or (f"trip-{getattr(template_trip, 'id', assignment_trip_id)}" if template_trip else f"trip-{assignment_trip_id}")
    )
    suffix = f"::assigned-{assignment_trip_id}"
    return f"{str(source_id)[:max(1, 120 - len(suffix))]}{suffix}"


def _copy_gtfs_trip_metadata(target_trip: Trip, template_trip: Optional[Trip]) -> None:
    if not target_trip or not template_trip:
        return
    target_trip.shape_id = getattr(template_trip, "shape_id", None) or target_trip.shape_id
    if target_trip.direction_id is None:
        target_trip.direction_id = getattr(template_trip, "direction_id", None)
    target_trip.service_id = getattr(template_trip, "service_id", None) or target_trip.service_id
    target_trip.trip_headsign = getattr(template_trip, "trip_headsign", None) or target_trip.trip_headsign
    target_trip.trip_short_name = getattr(template_trip, "trip_short_name", None) or target_trip.trip_short_name
    target_trip.block_id = getattr(template_trip, "block_id", None) or target_trip.block_id
    target_trip.wheelchair_accessible = getattr(template_trip, "wheelchair_accessible", target_trip.wheelchair_accessible)
    target_trip.bikes_allowed = getattr(template_trip, "bikes_allowed", target_trip.bikes_allowed)


def _ensure_assigned_trip_gtfs_metadata(bus: Optional[Bus], trip: Optional[Trip], route: Optional[Route] = None) -> Optional[Trip]:
    if not trip:
        return None
    reverse = getattr(trip, "direction_id", 0) == 1
    template_trip = _gtfs_backed_trip_for_route(trip.route_id, reverse=reverse)
    if template_trip and template_trip.direction_id is not None and int(template_trip.direction_id) != (1 if reverse else 0):
        template_trip = None
    if template_trip:
        _copy_gtfs_trip_metadata(trip, template_trip)
        if StopTime.query.filter_by(trip_id=trip.id).count() < 2:
            _copy_stop_times_from_template(trip, template_trip)
    if trip.direction_id is None:
        trip.direction_id = 0
    if not getattr(trip, "gtfs_trip_id", None):
        db.session.flush()
        trip.gtfs_trip_id = _assignment_gtfs_trip_id(template_trip or trip, trip.id)
    if not getattr(trip, "shape_id", None):
        _ensure_trip_shape_from_stop_times(trip)
    return template_trip


def _validate_driver_start_trip_gtfs(bus: Bus, trip: Optional[Trip]) -> Route:
    if not bus:
        raise ValueError("Assigned bus was not found.")
    if not trip:
        raise ValueError("No assigned GTFS trip is available for this bus.")

    route = db.session.get(Route, trip.route_id)
    if not route:
        raise ValueError("Assigned GTFS trip has no valid route.")

    _ensure_assigned_trip_gtfs_metadata(bus, trip, route)
    points = _route_points_for_assigned_trip(route, trip)
    route_path = _route_geometry_path_for_assigned_trip(trip)
    validation_error = _assigned_trip_validation_error(route, trip, points, route_path)
    if validation_error:
        raise ValueError(validation_error)

    missing = []
    if not getattr(trip, "gtfs_trip_id", None):
        missing.append("gtfs_trip_id")
    if not getattr(trip, "service_id", None):
        missing.append("service_id")
    if getattr(trip, "direction_id", None) is None:
        missing.append("direction_id")
    if not getattr(trip, "shape_id", None):
        missing.append("shape_id")
    if StopTime.query.filter_by(trip_id=trip.id).count() < 2:
        missing.append("stop_times")
    if missing:
        raise ValueError(f"Assigned GTFS trip is incomplete: {', '.join(missing)}.")
    return route


def _driver_runtime_session_payload(bus: Bus, trip: Trip, gps_state: str = "ACTIVE") -> dict:
    route = db.session.get(Route, trip.route_id) if trip else None
    points = _route_points_for_assigned_trip(route, trip) if route and trip else []
    now = datetime.now(UTC)
    start_time = trip.start_time or now
    driver_user_id = current_user.id if getattr(current_user, "is_authenticated", False) else bus.assigned_driver_id
    return {
        "session_id": f"driver:{bus.id}:{trip.id}",
        "start_time": start_time.isoformat(),
        "driver_id": driver_user_id,
        "driver_code": bus.assigned_driver_code,
        "bus_id": bus.id,
        "bus_number": bus.bus_number,
        "trip_id": trip.id,
        "route_id": trip.route_id,
        "shape_id": trip.shape_id,
        "service_id": trip.service_id,
        "direction_id": trip.direction_id,
        "gtfs_trip_id": trip.gtfs_trip_id,
        "driver_state": "ON_DUTY",
        "bus_state": "ACTIVE",
        "gps_state": gps_state,
        "last_update_timestamp": now.isoformat(),
        "current_stop": points[0]["name"] if points else "--",
        "next_stop": points[1]["name"] if len(points) > 1 else "--",
        "trip_progress": 0,
        "distance_travelled_km": 0,
        "speed": 0,
        "heading": None,
        "delay_minutes": 0,
    }


def _activate_driver_runtime_session(bus: Bus, trip: Trip) -> dict:
    session_payload = _driver_runtime_session_payload(bus, trip, "ACTIVE")
    DRIVER_RUNTIME_SESSIONS[bus.id] = session_payload
    return session_payload


def _mark_driver_runtime_gps_state(bus_id: Optional[int], state: str) -> None:
    if not bus_id:
        return
    runtime = DRIVER_RUNTIME_SESSIONS.get(bus_id)
    if runtime:
        runtime["gps_state"] = state
        runtime["last_update_timestamp"] = datetime.now(UTC).isoformat()


def _complete_driver_runtime_session(bus: Bus, trip: Trip) -> None:
    runtime = DRIVER_RUNTIME_SESSIONS.get(bus.id)
    if not runtime:
        runtime = _driver_runtime_session_payload(bus, trip, "OFF")
        DRIVER_RUNTIME_SESSIONS[bus.id] = runtime
    runtime.update({
        "driver_state": "OFF_DUTY",
        "bus_state": "OFFLINE",
        "gps_state": "OFF",
        "ended_at": datetime.now(UTC).isoformat(),
        "last_update_timestamp": datetime.now(UTC).isoformat(),
    })


def _runtime_state_for_bus(bus_id: Optional[int]) -> dict:
    if not bus_id:
        return {}
    runtime = DRIVER_RUNTIME_SESSIONS.get(bus_id)
    if not runtime:
        # Recover from database if bus is active but session was lost/cleared
        bus = db.session.get(Bus, bus_id)
        if bus and bus.is_active:
            trip = _driver_dashboard_trip_for_bus(bus)
            if trip:
                gps = LIVE_GPS_DATA.get(bus_id)
                gps_state = "ACTIVE"
                if gps:
                    now = time.time()
                    if now - float(gps.get("timestamp") or 0) > 60:
                        gps_state = "STALE"
                else:
                    gps_state = "OFF"
                runtime = _driver_runtime_session_payload(bus, trip, gps_state)
                if gps:
                    points = _route_points_for_assigned_trip(db.session.get(Route, trip.route_id), trip)
                    current_stop_idx = int(gps.get("current_stop_index") or 0)
                    runtime.update({
                        "driver_location": {"lat": float(gps.get("lat")), "lng": float(gps.get("lon"))},
                        "bus_location": {"lat": float(gps.get("lat")), "lng": float(gps.get("lon"))},
                        "trip_progress": float(gps.get("trip_progress") or 0),
                        "distance_travelled_km": float(gps.get("distance_covered_km") or 0.0),
                        "speed": float(gps.get("speed") or 0.0),
                        "heading": gps.get("bearing"),
                        "last_update_timestamp": datetime.fromtimestamp(gps["timestamp"], UTC).isoformat(),
                        "current_stop": points[current_stop_idx]["name"] if points and current_stop_idx < len(points) else "--",
                        "next_stop": points[current_stop_idx + 1]["name"] if points and current_stop_idx + 1 < len(points) else "--",
                    })
                DRIVER_RUNTIME_SESSIONS[bus_id] = runtime
    return runtime or {}


def _prepare_return_trip(bus: Bus, completed_trip: Trip) -> Trip:
    existing = (
        Trip.query.filter_by(bus_id=bus.id, route_id=completed_trip.route_id, status="return_ready")
        .order_by(Trip.id.desc())
        .first()
    )

    direction = 0 if getattr(completed_trip, "direction_id", 0) == 1 else 1
    target_template = _gtfs_backed_trip_for_route(completed_trip.route_id, reverse=(direction == 1))
    if target_template and target_template.direction_id is not None and int(target_template.direction_id) != direction:
        target_template = None

    if existing:
        existing_first = (
            StopTime.query
            .filter_by(trip_id=existing.id)
            .order_by(StopTime.stop_sequence.asc())
            .first()
        )
        completed_last = (
            StopTime.query
            .filter_by(trip_id=completed_trip.id)
            .order_by(StopTime.stop_sequence.desc())
            .first()
        )
        if (
            StopTime.query.filter_by(trip_id=existing.id).count() == 0
            or (existing_first and completed_last and existing_first.stop_id != completed_last.stop_id)
        ):
            if target_template:
                _copy_gtfs_trip_metadata(existing, target_template)
                _copy_stop_times_from_template(existing, target_template)
            else:
                _copy_reversed_stop_times_from_trip(existing, completed_trip)
        if target_template and not existing.gtfs_trip_id:
            existing.gtfs_trip_id = _assignment_gtfs_trip_id(target_template, existing.id)
        if existing.direction_id is None:
            existing.direction_id = direction
        return existing

    return_trip = Trip(
        bus_id=bus.id,
        route_id=completed_trip.route_id,
        shape_id=target_template.shape_id if target_template else completed_trip.shape_id,
        direction_id=direction,
        service_id=getattr(target_template, "service_id", None) if target_template else completed_trip.service_id,
        gtfs_trip_id=None,
        trip_headsign=getattr(target_template, "trip_headsign", None) if target_template else completed_trip.trip_headsign,
        trip_short_name=getattr(target_template, "trip_short_name", None) if target_template else completed_trip.trip_short_name,
        block_id=getattr(target_template, "block_id", None) if target_template else completed_trip.block_id,
        wheelchair_accessible=getattr(target_template, "wheelchair_accessible", 0) if target_template else completed_trip.wheelchair_accessible,
        bikes_allowed=getattr(target_template, "bikes_allowed", 0) if target_template else completed_trip.bikes_allowed,
        start_time=None,
        end_time=None,
        status="return_ready",
    )
    db.session.add(return_trip)
    db.session.flush()
    if target_template:
        return_trip.gtfs_trip_id = _assignment_gtfs_trip_id(target_template, return_trip.id)
    if target_template:
        _copy_stop_times_from_template(return_trip, target_template)
    else:
        _copy_reversed_stop_times_from_trip(return_trip, completed_trip)
    return return_trip


def _repair_live_trip_stop_times_from_gtfs() -> list:
    repairs = []
    repair_statuses = ("active", "in_progress", "assigned", "ready", "scheduled")
    trips = (
        Trip.query
        .filter(Trip.bus_id.isnot(None), Trip.status.in_(repair_statuses))
        .order_by(Trip.id.asc())
        .all()
    )
    for trip in trips:
        route = db.session.get(Route, trip.route_id)
        if not route:
            continue
        points = _route_points_for_assigned_trip(route, trip)
        route_path = _route_geometry_path_for_assigned_trip(trip)
        validation_error = _assigned_trip_validation_error(route, trip, points, route_path)
        if not validation_error:
            continue

        template_trip = _gtfs_backed_trip_for_route(
            trip.route_id,
            reverse=(getattr(trip, "direction_id", 0) == 1),
        )
        if not template_trip:
            repairs.append({
                "trip_id": trip.id,
                "route_id": trip.route_id,
                "repaired": False,
                "reason": validation_error,
            })
            continue

        before = (points[0]["name"], points[-1]["name"]) if len(points) >= 2 else (None, None)
        StopTime.query.filter_by(trip_id=trip.id).delete(synchronize_session=False)
        trip.shape_id = template_trip.shape_id
        trip.direction_id = template_trip.direction_id
        _copy_stop_times_from_template(trip, template_trip)
        db.session.flush()
        after_points = _route_points_for_assigned_trip(route, trip)
        after = (after_points[0]["name"], after_points[-1]["name"]) if len(after_points) >= 2 else (None, None)
        _ensure_trip_shape_from_stop_times(trip)
        after_path = _route_geometry_path_for_assigned_trip(trip)
        repairs.append({
            "trip_id": trip.id,
            "route_id": trip.route_id,
            "template_trip_id": template_trip.id,
            "repaired": _assigned_trip_validation_error(route, trip, after_points, after_path) is None,
            "before": before,
            "after": after,
        })

    if repairs:
        logger.debug("[GTFS_TRACKING_REPAIR] %s", repairs)
    return repairs


def _compute_return_trip_start_indexes(lat: float, lon: float, trip, route) -> tuple[int, int]:
    pts = _route_points_for_assigned_trip(route, trip) if route else []
    route_path = _route_geometry_path_for_assigned_trip(trip)
    start_stop_idx = 0
    start_shape_idx = 0
    if lat is not None and lon is not None and pts:
        min_dist = float('inf')
        for i, pt in enumerate(pts):
            try:
                d = _haversine_km(lat, lon, pt["lat"], pt["lng"])
                if d < min_dist:
                    min_dist = d
                    start_stop_idx = i
            except (KeyError, TypeError):
                continue
                
    if lat is not None and lon is not None and route_path:
        start_shape_idx = _nearest_route_index(lat, lon, route_path)
        
    return start_stop_idx, start_shape_idx


def _start_driver_trip(bus: Bus, requested_return: bool = False, start_lat: float = None, start_lon: float = None) -> Trip:
    if not bus.route_id:
        raise ValueError("Assigned bus has no route.")

    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("=========================================")
        logger.debug("[START TRIP DEBUG] BEFORE TRIP SELECTION")
        logger.debug("Bus ID: %s", bus.id)
        logger.debug("Bus Route ID: %s", bus.route_id)
        logger.debug("Driver ID: %s", bus.assigned_driver_code)
        logger.debug("Requested Return Trip: %s", requested_return)

    trip = None
    selection_reason = ""

    if requested_return:
        trip = (
            Trip.query.filter_by(bus_id=bus.id, route_id=bus.route_id, status="return_ready")
            .order_by(Trip.id.desc())
            .first()
        )
        if trip:
            selection_reason = "return_ready trip"
            logger.debug("Query matched return_ready trip.")

    if not trip:
        trip = (
            Trip.query.filter(
                Trip.bus_id == bus.id,
                Trip.route_id == bus.route_id,
                Trip.status.in_(("assigned", "ready", "scheduled", "return_ready"))
            )
            .order_by(
                case((Trip.status == "return_ready", 0), else_=1),
                Trip.id.desc(),
            )
            .first()
        )
        if trip:
            selection_reason = f"existing {trip.status.upper()} trip"
            logger.debug("Query matched existing %s trip.", trip.status)

    route = db.session.get(Route, bus.route_id)

    # Discard only structurally invalid trips. Route origin/destination are display fields
    # and must never decide GTFS assignment validity.
    if trip:
        pts = _route_points_for_assigned_trip(route, trip) if route else []
        route_path = _route_geometry_path_for_assigned_trip(trip)
        discard_reason = _assigned_trip_validation_error(route, trip, pts, route_path)
        if discard_reason:
            logger.debug("DISCARDING Trip %s: %s", trip.id, discard_reason)
            db.session.delete(trip)
            db.session.flush()
            trip = None

    if not trip:
        trip = _create_trip_for_bus(bus, bus.route_id)
        selection_reason = "newly created trip"

    _validate_driver_start_trip_gtfs(bus, trip)

    # Log selected trip details
    pts = _route_points_for_assigned_trip(route, trip) if route else []
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("Selected Trip ID: %s", trip.id)
        logger.debug("Selected Trip Status: %s", trip.status)
        logger.debug("Selected Trip Route ID: %s", trip.route_id)
        logger.debug("Selected Trip Direction ID: %s", trip.direction_id)
        logger.debug("Selected Trip Shape ID: %s", trip.shape_id)
        logger.debug("Selected Trip First Stop: %s", pts[0]["name"] if len(pts) > 0 else "None")
        logger.debug("Selected Trip Last Stop: %s", pts[-1]["name"] if len(pts) > 0 else "None")
        logger.debug("Reason for Selection: %s", selection_reason)
        logger.debug("=========================================")

    old_gps = LIVE_GPS_DATA.get(bus.id, {})
    old_lat = old_gps.get("lat")
    old_lon = old_gps.get("lon")
    
    _complete_active_trips(bus.id, exclude_trip_id=trip.id)
    trip.status = "active"
    trip.start_time = datetime.now(UTC)
    trip.end_time = None
    route = db.session.get(Route, trip.route_id)
    _validate_driver_start_trip_gtfs(bus, trip)
    bus.is_active = True
    LIVE_GPS_DATA[bus.id] = {
        "timestamp": time.time(),
        "trip_id": trip.id,
        "route_id": trip.route_id,
        "speed": 0.0,
        "bearing": 0.0,
        "distance_covered_km": 0.0,
        "gps_delta_km": 0.0,
        "elapsed_seconds": 0.0,
        "current_stop_index": 0,
        "completed_stops": 0,
        "max_path_index": 0,
        "at_stop": True,
    }
    
    if start_lat is None or start_lon is None:
        if old_lat is not None and old_lon is not None:
            start_lat, start_lon = old_lat, old_lon

    if requested_return and start_lat is not None and start_lon is not None:
        s_idx, sh_idx = _compute_return_trip_start_indexes(start_lat, start_lon, trip, route)
        LIVE_GPS_DATA[bus.id]["return_start_stop_index"] = s_idx
        LIVE_GPS_DATA[bus.id]["return_start_shape_index"] = sh_idx
    elif start_lat is None and pts:
        start_lat, start_lon = pts[0]["lat"], pts[0]["lng"]
        
    LIVE_GPS_DATA[bus.id].update({
        "lat": start_lat,
        "lon": start_lon
    })

    LIVE_GPS_BREADCRUMBS.pop(bus.id, None)
    BUS_DELAY_DATA.pop(bus.id, None)
    runtime = _activate_driver_runtime_session(bus, trip)
    logger.info(
        "[DRIVER_SESSION] started bus_id=%s trip_id=%s route_id=%s shape_id=%s service_id=%s direction_id=%s",
        runtime["bus_id"], runtime["trip_id"], runtime["route_id"], runtime["shape_id"],
        runtime["service_id"], runtime["direction_id"],
    )
    return trip


def _end_driver_trip(bus: Bus) -> tuple[Trip, Trip]:
    trip = _active_trip_for_bus(bus)
    if not trip:
        raise ValueError("No active trip to end.")
    if getattr(trip, "direction_id", 0) == 1:
        trip.status = "return_completed"
        LIVE_GPS_DATA.pop(bus.id, None)
    else:
        trip.status = "completed"
    
    trip.end_time = datetime.now(UTC)
    bus.is_active = False
    LIVE_GPS_BREADCRUMBS.pop(bus.id, None)
    BUS_DELAY_DATA.pop(bus.id, None)
    _complete_driver_runtime_session(bus, trip)

    return_trip = None
    if getattr(trip, "direction_id", 0) == 0:
        return_trip = _prepare_return_trip(bus, trip)

    return trip, return_trip


def _repair_route_assignments() -> None:
    """Fix Bus.route_id values that accidentally reference Trip.id instead of Route.id."""
    route_ids = {r.id for r in Route.query.with_entities(Route.id).all()}
    repaired = False
    for bus in Bus.query.filter(Bus.route_id.isnot(None)).all():
        if bus.route_id not in route_ids:
            trip = db.session.get(Trip, bus.route_id)
            if trip and trip.route_id in route_ids:
                logger.warning(
                    "[REPAIR] Bus %s route_id %s corrected to Route.id %s",
                    bus.bus_number, bus.route_id, trip.route_id
                )
                bus.route_id = trip.route_id
                repaired = True
    if repaired:
        db.session.commit()


def _validate_data_integrity() -> list:
    issues = []
    route_ids = {r.id for r in Route.query.with_entities(Route.id).all()}
    trip_ids = {t.id for t in Trip.query.with_entities(Trip.id).all()}
    shape_ids = {s.shape_id for s in Shape.query.with_entities(Shape.shape_id).distinct().all()}

    for bus in Bus.query.filter(Bus.route_id.isnot(None)).all():
        if bus.route_id not in route_ids:
            trip_match = bus.route_id in trip_ids
            issues.append(
                f"Bus {bus.bus_number} (id={bus.id}): route_id={bus.route_id} "
                f"invalid — {'looks like Trip.id' if trip_match else 'no matching Route'}"
            )

    for trip in Trip.query.all():
        if trip.route_id not in route_ids:
            issues.append(f"Trip id={trip.id}: route_id={trip.route_id} has no matching Route")
        if trip.shape_id and trip.shape_id not in shape_ids:
            issues.append(f"Trip id={trip.id}: shape_id={trip.shape_id} not found in shapes table")

    for stop in Stop.query.filter(Stop.route_id.isnot(None)).all():
        if stop.route_id not in route_ids:
            issues.append(f"Stop id={stop.id} ({stop.stop_name}): route_id={stop.route_id} invalid")

    for issue in issues:
        logger.warning("[DATA_INTEGRITY] %s", issue)
    if not issues:
        logger.info("[DATA_INTEGRITY] All FK references validated OK")
    return issues



def _cleanup_tracking_sessions(now: Optional[float] = None) -> None:
    now = now or time.time()
    expired = [
        user_id for user_id, session_data in PASSENGER_TRACKING_SESSIONS.items()
        if now - float(session_data.get("timestamp") or 0) > TRACKING_SESSION_TTL_SECONDS
    ]
    for user_id in expired:
        PASSENGER_TRACKING_SESSIONS.pop(user_id, None)


def _cleanup_live_state(now: Optional[float] = None) -> None:
    now = now or time.time()
    stale_gps = [
        bus_id for bus_id, gps in LIVE_GPS_DATA.items()
        if now - float(gps.get("timestamp") or 0) > 60
    ]
    for bus_id in stale_gps:
        # Keep last known GPS coordinates and breadcrumbs during signal loss
        # DO NOT pop from LIVE_GPS_DATA or LIVE_GPS_BREADCRUMBS
        _mark_driver_runtime_gps_state(bus_id, "STALE")

    stale_delay = [
        bus_id for bus_id, entry in BUS_DELAY_DATA.items()
        if now - float(entry.get("timestamp") or 0) > DELAY_PROFILE_TTL_SECONDS
    ]
    for bus_id in stale_delay:
        BUS_DELAY_DATA.pop(bus_id, None)

    stale_simulation = [
        bus_id for bus_id, state in BUS_SIMULATION_STATE.items()
        if now - float(state.get("timestamp") or 0) > SIMULATION_STATE_TTL_SECONDS
    ]
    for bus_id in stale_simulation:
        BUS_SIMULATION_STATE.pop(bus_id, None)

    _cleanup_tracking_sessions(now)


def _record_passenger_tracking_session(user_id: int, bus_id: Optional[int],
                                       route_id: Optional[int], trip_id: Optional[int]) -> None:
    if not user_id or not bus_id:
        return
    PASSENGER_TRACKING_SESSIONS[user_id] = {
        "bus_id": int(bus_id),
        "route_id": int(route_id) if route_id else None,
        "trip_id": int(trip_id) if trip_id else None,
        "timestamp": time.time(),
    }


def _tracking_passenger_ids_for_bus(bus_id: Optional[int], trip_id: Optional[int] = None) -> set:
    if not bus_id:
        return set()
    _cleanup_tracking_sessions()
    passenger_ids = set()
    for user_id, session_data in PASSENGER_TRACKING_SESSIONS.items():
        if int(session_data.get("bus_id") or 0) == int(bus_id):
            passenger_ids.add(user_id)
        elif trip_id and int(session_data.get("trip_id") or 0) == int(trip_id):
            passenger_ids.add(user_id)
    return passenger_ids


def _passenger_ids_for_trip_notifications(trip_id: Optional[int]) -> set:
    if not trip_id:
        return set()
    return {
        row[0]
        for row in db.session.query(Notification.recipient_id)
        .join(User, User.id == Notification.recipient_id)
        .filter(Notification.trip_id == trip_id, User.role == "passenger")
        .distinct()
        .all()
    }


def _passenger_ids_for_route(route_id: Optional[int], trip=None) -> set:
    if not route_id:
        return set()
    stop_ids = {
        row[0]
        for row in db.session.query(Stop.id)
        .filter(Stop.route_id == route_id)
        .all()
    }

    trip_id = getattr(trip, "id", None) if trip else None
    if trip_id:
        stop_ids.update(
            row[0]
            for row in db.session.query(StopTime.stop_id)
            .filter(StopTime.trip_id == trip_id)
            .distinct()
            .all()
        )
    else:
        stop_ids.update(
            row[0]
            for row in db.session.query(StopTime.stop_id)
            .join(Trip, StopTime.trip_id == Trip.id)
            .filter(Trip.route_id == route_id)
            .distinct()
            .all()
        )

    if not stop_ids:
        return set()
    return {
        row[0]
        for row in db.session.query(Subscription.user_id)
        .filter(Subscription.active.is_(True), Subscription.stop_id.in_(stop_ids))
        .distinct()
        .all()
    }


def _passenger_ids_for_delay_targets(bus_id: Optional[int], route_id: Optional[int], trip=None) -> set:
    trip_id = getattr(trip, "id", None) if trip else None
    passenger_ids = set()
    passenger_ids.update(_passenger_ids_for_route(route_id, trip))
    passenger_ids.update(_tracking_passenger_ids_for_bus(bus_id, trip_id))
    passenger_ids.update(_passenger_ids_for_trip_notifications(trip_id))
    return passenger_ids


def _queue_meaningful_delay_notifications(bus_data: dict, route: Optional[Route], trip=None,
                                          respect_cooldown: bool = True) -> int:
    delay_minutes = int(bus_data.get("current_delay_minutes") or 0)
    bus_id = bus_data.get("bus_id")
    route_id = getattr(route, "id", None) if route else bus_data.get("route_id")
    entry = _delay_entry_for_bus(bus_id, route_id, trip)
    now = time.time()
    last_delay = int(entry.get("last_notification_delay_minutes") or 0) if entry else 0
    reason = _normalize_delay_reason(bus_data.get("current_delay_reason") or "Traffic")
    last_reason = entry.get("last_notification_reason") if entry else None
    last_at = float(entry.get("last_notification_at") or 0) if entry else 0

    delay_delta = abs(delay_minutes - last_delay)
    threshold_crossed = delay_minutes >= DELAY_NOTIFY_THRESHOLD_MINUTES and last_delay < DELAY_NOTIFY_THRESHOLD_MINUTES
    significant_change = last_delay > 0 and delay_delta >= DELAY_NOTIFY_DELTA_MINUTES
    schedule_recovered = delay_minutes == 0 and last_delay > 0
    reason_changed = bool(last_reason and reason != last_reason and delay_minutes >= DELAY_NOTIFY_THRESHOLD_MINUTES)
    if not (threshold_crossed or significant_change or schedule_recovered or reason_changed):
        return 0
    if respect_cooldown and not schedule_recovered and last_at and now - last_at < DELAY_NOTIFY_COOLDOWN_SECONDS:
        return 0

    passenger_ids = _passenger_ids_for_delay_targets(bus_id, route_id, trip)
    if not passenger_ids:
        if entry:
            entry["last_notification_delay_minutes"] = delay_minutes
            entry["last_notification_reason"] = reason
            entry["last_notification_at"] = now
        return 0

    route_name = getattr(route, "name", None) or bus_data.get("route_name") or "Assigned Route"
    expected_arrival = bus_data.get("updated_arrival_time") or bus_data.get("arrival_time") or "--"
    eta_text = expected_arrival if expected_arrival and expected_arrival != "--" else f"{bus_data.get('updated_eta_minutes') or bus_data.get('eta_minutes') or delay_minutes} min"
    if schedule_recovered:
        message = f"[DELAY] Bus {bus_data.get('bus_number')} is back on schedule. Route: {route_name}."
    else:
        message = (
            f"Bus Delay Alert\n\n"
            f"Bus: {bus_data.get('bus_number')}\n\n"
            f"Current Delay: +{delay_minutes} minutes\n\n"
            f"Reason:\n{reason}\n\n"
            f"Updated ETA:\n{eta_text}"
        )
    for user_id in passenger_ids:
        db.session.add(Notification(
            recipient_id=user_id,
            trip_id=getattr(trip, "id", None) if trip else None,
            message=message,
        ))

    db.session.add(Notification(
        target_role="admin",
        trip_id=getattr(trip, "id", None) if trip else None,
        message=message,
        related_bus_id=bus_id,
        related_route_id=route_id
    ))

    if entry:
        entry["last_notification_delay_minutes"] = delay_minutes
        entry["last_notification_reason"] = reason
        entry["last_notification_at"] = now
    return len(passenger_ids)


def _fresh_gps_packet(bus_id: int, now_seconds: float) -> Optional[dict]:
    gps = LIVE_GPS_DATA.get(bus_id)
    if not gps:
        return None
    try:
        timestamp = float(gps.get("timestamp") or 0)
        lat = float(gps.get("lat"))
        lon = float(gps.get("lon"))
    except (TypeError, ValueError):
        return None
    if now_seconds - timestamp >= 60:
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    packet = dict(gps)
    packet.update({"timestamp": timestamp, "lat": lat, "lon": lon})
    return packet


def _nearest_route_index(lat: float, lon: float, points: list) -> int:
    if not points:
        return 0
    nearest_idx = 0
    nearest_dist = float("inf")
    for idx, point in enumerate(points):
        point_lat = point.get("lat")
        point_lon = point.get("lng", point.get("lon"))
        if point_lat is None or point_lon is None:
            continue
        dist = _haversine_km(lat, lon, float(point_lat), float(point_lon))
        if dist < nearest_dist:
            nearest_idx = idx
            nearest_dist = dist
    return nearest_idx


def _project_point_onto_segment(lat: float, lon: float, path: list, nearest_idx: int) -> dict:
    """Return a {lat, lng} point projected onto the nearest path segment.

    This ensures the completed/remaining split lands exactly beneath the
    vehicle marker rather than at the nearest discrete path vertex.
    """
    if not path or nearest_idx >= len(path) - 1:
        return {"lat": lat, "lng": lon}

    p1 = path[nearest_idx]
    p2 = path[nearest_idx + 1]
    try:
        ax, ay = float(p1["lat"]), float(p1["lng"])
        bx, by = float(p2["lat"]), float(p2["lng"])
        dx, dy = bx - ax, by - ay
        len_sq = dx * dx + dy * dy
        if len_sq < 1e-18:
            return {"lat": lat, "lng": lon}
        t = max(0.0, min(1.0, ((lat - ax) * dx + (lon - ay) * dy) / len_sq))
        return {"lat": ax + t * dx, "lng": ay + t * dy}
    except (TypeError, ValueError, KeyError):
        return {"lat": lat, "lng": lon}


def _build_geometry_sections(
    lat: float,
    lon: float,
    route_path: list,
    nearest_idx: int,
    is_diverged: bool,
    diversion_road: list,
    original_path: list,
) -> dict:
    """Compute four geometry sections for full-journey rendering.

    Returns a dict with keys: completed, planned, dynamic, remaining.

    completed  – Travelled portion (gray)
    planned    – Bypassed original route during diversion (light-blue, dashed)
    dynamic    – Actual diversion path (orange)
    remaining  – Remaining official route (cyan)
    """
    if not route_path or len(route_path) < 2:
        return {"completed": [], "planned": [], "dynamic": [], "remaining": route_path or []}

    # Interpolate projected split point exactly under the marker
    projected = _project_point_onto_segment(lat, lon, route_path, nearest_idx)
    split_idx = nearest_idx

    completed_geom: list = route_path[:split_idx + 1] + [projected]
    remaining_geom: list = [projected] + route_path[split_idx + 1:]

    dynamic_geom: list = []
    planned_geom: list = []

    if is_diverged and diversion_road and len(diversion_road) >= 2:
        dynamic_geom = diversion_road

        # Compute the bypassed planned segment using the original GTFS path
        if original_path and len(original_path) >= 2:
            try:
                div_start_pt = diversion_road[0]
                div_start_idx = _nearest_route_index(
                    float(div_start_pt.get("lat")),
                    float(div_start_pt.get("lng")),
                    original_path,
                )
                div_end_pt = diversion_road[-1]
                div_end_idx = _nearest_route_index(
                    float(div_end_pt.get("lat", lat)),
                    float(div_end_pt.get("lng", lon)),
                    original_path,
                )
                
                # New simplified standard for Frontend: 
                # completed = path up to diversion
                # remaining = active diversion path
                completed_geom = original_path[:div_start_idx + 1]
                remaining_geom = diversion_road
                
                # Legacy compatibility
                if div_end_idx > div_start_idx:
                    planned_geom = original_path[div_start_idx:div_end_idx + 1]
                elif div_end_idx == div_start_idx:
                    planned_geom = [original_path[div_start_idx]]
            except (TypeError, ValueError, KeyError):
                planned_geom = []

    return {
        "completed": completed_geom,
        "planned":   planned_geom,
        "dynamic":   dynamic_geom,
        "remaining": remaining_geom,
    }




def _live_tracking_validation_snapshot(bus: Bus, trip, route: Optional[Route], message: str,
                                       gps: Optional[dict] = None) -> dict:
    if not isinstance(gps, dict):
        gps = {}
    driver_name_out, driver_code_out = _driver_display_fields(bus)
    occ_pct, occ_level = _latest_recorded_occupancy_for_bus(bus)
    trip_id = getattr(trip, "id", None) if trip else None
    shape_id = getattr(trip, "shape_id", None) if trip else None
    route_id = getattr(route, "id", None) if route else getattr(trip, "route_id", None)
    route_code = getattr(route, "route_code", None) if route else None
    route_name = getattr(route, "name", None) if route else None
    now_iso = datetime.now(UTC).isoformat()
    runtime = _runtime_state_for_bus(bus.id)

    gps_is_valid = bool(gps and gps.get("lat") is not None and gps.get("lon") is not None)

    formatted_gps_timestamp = now_iso
    if gps and gps.get("timestamp") is not None:
        try:
            formatted_gps_timestamp = datetime.fromtimestamp(float(gps["timestamp"]), UTC).isoformat()
        except (TypeError, ValueError, OverflowError, OSError):
            pass

    res = {
        "bus_id": bus.id,
        "bus_number": bus.bus_number,
        "registration_number": bus.registration_number,
        "driver_id": driver_code_out,
        "driver_name": driver_name_out,
        "assigned_driver_id": bus.assigned_driver_id,
        "assigned_driver_code": driver_code_out,
        "assigned_driver_name": driver_name_out,
        "driver_state": runtime.get("driver_state") or ("ON_DUTY" if bus.is_active else "OFF_DUTY"),
        "bus_state": runtime.get("bus_state") or ("ACTIVE" if bus.is_active else "OFFLINE"),
        "gps_state": runtime.get("gps_state") or ("ACTIVE" if gps_is_valid else "OFF"),
        "last_update_timestamp": runtime.get("last_update_timestamp") or now_iso,
        "sos_active": False,
        "route_id": route_id,
        "route_code": route_code or "BUS-RT",
        "route_name": route_name or "Tracking Validation Error",
        "status": "Validation Error",
        "service_status": "validation_error",
        "bus_status": "ACTIVE" if bus.is_active else "OFFLINE",
        "trip_status": _trip_state_label(trip, bus),
        "gps_status": "Online" if gps_is_valid else "Offline",
        "tracking_available": False,
        "speed": None,
        "occupancy_pct": occ_pct,
        "occupancy_level": occ_level,
        "direction": "backward" if getattr(trip, "direction_id", 0) == 1 else "forward",
        "current_stop_index": 0,
        "completed_stops": 0,
        "trip_progress": 0,
        "source_stop": getattr(route, "origin", None) or "Source",
        "destination_stop": getattr(route, "destination", None) or "Destination",
        "current_stop": "Source",
        "next_stop": "Next Scheduled Stop",
        "distance_remaining_km": 0,
        "distance_covered_km": 0,
        "eta_minutes": None,
        "base_eta_minutes": None,
        "updated_eta_minutes": None,
        "next_stop_eta_minutes": None,
        "eta_label": "Calculating..." if gps_is_valid else "Scheduled",
        "bearing": None,
        "current_lat": gps.get("lat") if gps_is_valid else None,
        "current_lon": gps.get("lon") if gps_is_valid else None,
        "is_live_gps": gps_is_valid,
        "gps_timestamp": formatted_gps_timestamp if gps_is_valid else now_iso,
        "shape_id": shape_id,
        "shape_point_count": 0,
        "shape_points_db": _shape_point_count_db(shape_id),
        "shape_points_api": 0,
        "points_removed": _shape_point_count_db(shape_id),
        "shape_point_index": None,
        "movement_state": "validation_error",
        "path": [],
        "display_path": [],
        "display_geometry_source": "unavailable",
        "geometry_source": "unavailable",
        "generated_road_geometry_points": 0,
        "stops": [],
        "geometry_available": False,
        "geometry_message": message,
        "validation_error": message,
        "trip_id": trip_id,
        "schedule": _route_schedule_for_assigned_trip(route, trip),
        "departure_time": "Scheduled",
        "arrival_time": "Scheduled",
        "updated_arrival_time": "Scheduled",
        "journey_duration": "Scheduled",
        "journey_duration_minutes": None,
        "schedule_status": "VALIDATION ERROR",
        "delay_status": "VALIDATION ERROR",
        "current_delay_minutes": 0,
        "current_delay_seconds": 0,
        "current_delay_label": "0 min",
        "current_delay_reason": message,
        "remaining_delay_minutes": 0,
        "current_stop_scheduled_time": "Scheduled",
        "current_stop_actual_time": "--",
        "next_stop_scheduled_time": "Scheduled",
        "next_stop_expected_time": "Scheduled",
        "display_schedule_stops": [],
    }
    return _enrich_snapshot_with_defaults(res, bus)


def _format_eta_display(bus_data: dict) -> str:
    trip_status = (bus_data.get("trip_status") or "").upper()
    status = (bus_data.get("status") or "").upper()
    
    # 1. Finished states
    if trip_status in ("COMPLETED", "RETURN_COMPLETED", "ARRIVED_DESTINATION") or status in ("COMPLETED", "RETURN_COMPLETED"):
        return "Arrived"
        
    # 2. Waiting states
    if trip_status in ("WAITING_TO_DEPART", "RETURN_READY", "OFFLINE") or status == "OFFLINE":
        return "Waiting to Depart"
        
    # 3. Active running state
    eta_mins = bus_data.get("eta_minutes")
    if eta_mins is None:
        eta_mins = bus_data.get("updated_eta_minutes") or bus_data.get("base_eta_minutes")
        
    if eta_mins is None:
        if trip_status in ("RUNNING", "RETURN_RUNNING"):
            return "Calculating..."
        return "Waiting to Depart"
        
    try:
        eta_mins = int(eta_mins)
    except (TypeError, ValueError):
        return "Calculating..."
        
    if eta_mins <= 0:
        return "Arrived"
        
    if eta_mins >= 60:
        h = eta_mins // 60
        m = eta_mins % 60
        if m > 0:
            return f"{h} hr {m} min"
        else:
            return f"{h} hr"
    else:
        return f"{eta_mins} min"


def _enrich_snapshot_with_defaults(bus_data: dict, bus: Bus) -> dict:
    if not isinstance(bus_data, dict):
        bus_data = {}
    
    # Resolve driver_code and driver_name
    driver_code = (
        bus_data.get("assigned_driver_code") or 
        bus_data.get("driver_id") or 
        getattr(bus, "assigned_driver_code", None) or 
        "--"
    )
    driver_name = (
        bus_data.get("assigned_driver_name") or 
        bus_data.get("driver_name") or 
        getattr(bus, "assigned_driver_name", None) or 
        driver_code
    )

    # Defaults mapping
    defaults = {
        "tracking_available": False,
        "gps_status": "Offline",
        "trip_status": "OFFLINE",
        "direction_id": 0,
        "current_lat": None,
        "current_lon": None,
        "display_path": [],
        "display_geometry_source": "unavailable",
        "stops": [],
        "current_stop_index": 0,
        "completed_stops": 0,
        "remaining_stops": 0,
        "progress": 0.0,
        "trip_progress": 0.0,
        "distance_remaining": 0.0,
        "distance_remaining_km": 0.0,
        "eta_minutes": 0,
        "vehicle_id": bus.bus_number,
        "bus_number": bus.bus_number,
        "driver_code": driver_code,
        "driver_name": driver_name,
        "status": "Offline",
        "speed": 0.0,
        "is_live_gps": False,
        "geometry_sections": {"completed": [], "planned": [], "dynamic": [], "remaining": []}
    }

    # Apply defaults if missing or None
    for key, def_val in defaults.items():
        if key not in bus_data or bus_data[key] is None:
            bus_data[key] = def_val

    # Resolve coordinates defaults to origin stop if None
    if bus_data.get("current_lat") is None:
        if bus_data.get("stops"):
            bus_data["current_lat"] = bus_data["stops"][0].get("lat")
        else:
            bus_data["current_lat"] = 0.0

    if bus_data.get("current_lon") is None:
        if bus_data.get("stops"):
            bus_data["current_lon"] = bus_data["stops"][0].get("lng")
        else:
            bus_data["current_lon"] = 0.0

    # Ensure compatibility mappings
    bus_data["progress"] = bus_data["trip_progress"]
    bus_data["distance_remaining"] = bus_data["distance_remaining_km"]
    bus_data["vehicle_id"] = bus_data["bus_number"]
    bus_data["driver_code"] = driver_code
    bus_data["driver_name"] = driver_name
    bus_data["current_speed"] = bus_data["speed"]
    
    bearing = bus_data.get("bearing")
    if bearing is None:
        bearing = bus_data.get("heading")
    if bearing is None:
        bearing = 0.0
    bus_data["current_heading"] = bearing

    # Route status mapping: ON_ROUTE, DYNAMIC_ROUTE, ROAD_GEOMETRY_UNAVAILABLE, RETURN_ROUTE, OFFLINE
    is_offline = (bus_data.get("trip_status") == "OFFLINE" or bus_data.get("status") == "Offline" or not bus_data.get("tracking_available"))
    is_return = (bus_data.get("direction") == "backward" or bus_data.get("trip_status") in ("RETURN_READY", "RETURN_RUNNING", "RETURN_COMPLETED"))
    is_diverged = bus_data.get("is_diverged", False) or (bus_data.get("display_geometry_source") == "dynamic_diversion")
    geometry_unavail = (bus_data.get("display_geometry_source") == "unavailable" or not bus_data.get("display_path"))
    
    if is_offline:
        bus_data["route_status"] = "OFFLINE"
    elif is_diverged:
        bus_data["route_status"] = "DYNAMIC_ROUTE"
    elif is_return:
        bus_data["route_status"] = "RETURN_ROUTE"
    elif geometry_unavail:
        bus_data["route_status"] = "ROAD_GEOMETRY_UNAVAILABLE"
    else:
        bus_data["route_status"] = "ON_ROUTE"

    # ETA Confidence mapping
    confidence = 100
    delay_mins = abs(int(bus_data.get("current_delay_minutes") or 0))
    confidence -= min(25, delay_mins * 1.5)
    
    if bus_data.get("gps_status", "Offline") == "Offline":
        confidence -= 40
    if is_diverged:
        confidence -= 15
        
    rem_km = bus_data.get("distance_remaining_km") or 0.0
    try:
        rem_km = float(rem_km)
    except (TypeError, ValueError):
        rem_km = 0.0
    if rem_km > 50.0:
        confidence -= 10
        
    bus_data["eta_confidence"] = max(10, min(100, int(confidence)))
    bus_data["eta_display"] = _format_eta_display(bus_data)

    return bus_data



def _calculate_realistic_eta(remaining_km: float, speed_to_use: float, delay_minutes: int, scheduled_remaining: float,
                             traffic_factor: float = 1.0, weather_factor: float = 1.0) -> int:
    """Calculate the realistic ETA in minutes using a weighted formula.
    Supports future expansion for traffic_factor, weather_factor, etc."""
    travel_time_by_speed = (remaining_km / speed_to_use) * 60.0 if speed_to_use > 0 else 0.0
    adjusted_travel_time = travel_time_by_speed * traffic_factor * weather_factor
    base_eta = 0.8 * adjusted_travel_time + 0.2 * scheduled_remaining
    return max(1, int(math.ceil(base_eta + delay_minutes)))


def _real_gps_bus_snapshot(bus: Bus, trip, route: Route, gps: Optional[dict] = None) -> dict:
    if not isinstance(gps, dict):
        gps = {}
        
    def _optional_float(*keys):
        if not gps:
            return None
        for key in keys:
            value = gps.get(key)
            if value is None:
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return None

    points = _route_points_for_assigned_trip(route, trip)
    route_path = _route_geometry_path_for_assigned_trip(trip)
    display_geometry = {"path": route_path, "source": "gtfs", "generated_point_count": 0}
    validation_error = _assigned_trip_validation_error(route, trip, points, route_path)
    if validation_error:
        return _live_tracking_validation_snapshot(bus, trip, route, validation_error, gps)
    direction = "backward" if getattr(trip, "direction_id", 0) == 1 else "forward"
    is_return = getattr(trip, "direction_id", 0) == 1

    if is_return and points and route_path:
        start_stop_idx = gps.get("return_start_stop_index")
        start_shape_idx = gps.get("return_start_shape_index")
        if start_stop_idx is None or start_shape_idx is None:
            # Deterministic Runtime Cache Safety Recomputation
            calc_lat = gps.get("lat")
            calc_lon = gps.get("lon")
            if calc_lat is not None and calc_lon is not None:
                try:
                    s_idx, sh_idx = _compute_return_trip_start_indexes(float(calc_lat), float(calc_lon), trip, route)
                    gps["return_start_stop_index"] = s_idx
                    gps["return_start_shape_index"] = sh_idx
                    start_stop_idx, start_shape_idx = s_idx, sh_idx
                except (ValueError, TypeError):
                    start_stop_idx, start_shape_idx = 0, 0
            else:
                start_stop_idx, start_shape_idx = 0, 0

    default_lat = points[0]["lat"] if points else 0.0
    default_lon = points[0]["lng"] if points else 0.0
    lat_raw = gps.get("lat")
    lon_raw = gps.get("lon")
    try:
        lat = float(lat_raw) if lat_raw is not None else default_lat
    except (TypeError, ValueError):
        lat = default_lat
    try:
        lon = float(lon_raw) if lon_raw is not None else default_lon
    except (TypeError, ValueError):
        lon = default_lon
    has_gps_coordinates = (
        lat_raw is not None
        and lon_raw is not None
        and -90 <= lat <= 90
        and -180 <= lon <= 180
    )

    now_seconds = time.time()
    gps_timestamp = now_seconds
    if gps:
        try:
            ts_val = gps.get("timestamp")
            if ts_val is not None:
                gps_timestamp = float(ts_val)
        except (TypeError, ValueError):
            pass
    gps_age = now_seconds - gps_timestamp
    is_gps_lost = (gps_age >= 60.0) if has_gps_coordinates else True

    if points and route_path:
        dist_start = _haversine_km(points[0]["lat"], points[0]["lng"], route_path[0]["lat"], route_path[0]["lng"])
        dist_end = _haversine_km(points[0]["lat"], points[0]["lng"], route_path[-1]["lat"], route_path[-1]["lng"])
        if dist_end < dist_start:
            route_path = list(reversed(route_path))

    try:
        covered_km = float(gps.get("distance_covered_km") or 0.0)
    except (TypeError, ValueError):
        covered_km = 0.0
    covered_km = max(0.0, covered_km)
    
    movement_begun = covered_km > 0.001 or has_gps_coordinates

    # Speed extraction & smoothing rolling average
    live_speed = _optional_float("speed", "velocity")
    bearing = _optional_float("bearing", "heading", "course")
    
    recent_speeds = gps.setdefault("recent_speeds", [])
    if live_speed is not None:
        recent_speeds.append(live_speed)
    if len(recent_speeds) > 10:
        recent_speeds = recent_speeds[-10:]
    elif not recent_speeds:
        recent_speeds.append(0.0)
    avg_live_speed = sum(recent_speeds) / len(recent_speeds)

    # Initial stop state values
    if not movement_begun:
        if points and not has_gps_coordinates:
            lat = points[0]["lat"]
            lon = points[0]["lng"]
        path_index = 0
        max_path_index = 0
        current_stop_idx = 0
        next_stop_idx = min(1, len(points) - 1) if points else 0
        completed_stops = 0
        remaining_km = 0.0
        trip_progress = 0.0
        delay_minutes = 0
        eta_minutes = None
        eta_label = "--"
        active_stop_index = 0
        is_diverged = False
        display_geometry_source = "gtfs"
    else:
        path_index = _nearest_route_index(lat, lon, route_path)
        try:
            max_path_index_val = gps.get("max_path_index")
            if max_path_index_val is not None:
                max_path_index = int(max_path_index_val)
            else:
                max_path_index = path_index
        except (TypeError, ValueError):
            max_path_index = path_index
            
        nearest_stop_idx = 0
        min_dist = float('inf')
        if points:
            for idx, pt in enumerate(points):
                dist = _haversine_km(lat, lon, pt["lat"], pt["lng"])
                if dist < min_dist:
                    min_dist = dist
                    nearest_stop_idx = idx

        prev_stop_idx = int(gps.get("current_stop_index") or 0) if gps else 0
        current_stop_idx = max(prev_stop_idx, nearest_stop_idx) if gps else nearest_stop_idx
        completed_stops = current_stop_idx
        next_stop_idx = min(current_stop_idx + 1, len(points) - 1) if points else 0

        # State lock filtering for deviation/recovery
        dev_count = int(gps.get("deviation_count") or 0)
        rec_count = int(gps.get("recovery_count") or 0)
        currently_diverged = bool(gps.get("is_diverged", False))
        
        is_diverged = currently_diverged
        display_geometry_source = "gtfs"
        original_gtfs_path: list = []  # saved for geometry_sections
        
        if has_gps_coordinates and route_path and points:
            threshold_meters = current_app.config.get("ROUTE_DEVIATION_THRESHOLD_METERS", ROUTE_DEVIATION_THRESHOLD_METERS)
            heading_threshold = current_app.config.get("ROUTE_DEVIATION_HEADING_THRESHOLD_DEGREES", ROUTE_DEVIATION_HEADING_THRESHOLD_DEGREES)
            min_deviation_meters = current_app.config.get("ROUTE_DEVIATION_MIN_METERS", ROUTE_DEVIATION_MIN_METERS)
            
            threshold_km = threshold_meters / 1000.0
            min_deviation_km = min_deviation_meters / 1000.0
            
            nearest_idx = _nearest_route_index(lat, lon, route_path)
            dist_to_route = _haversine_km(lat, lon, route_path[nearest_idx]["lat"], route_path[nearest_idx]["lng"])
            
            deviating_now = False
            if dist_to_route > threshold_km:
                deviating_now = True
            elif dist_to_route > min_deviation_km and bearing is not None:
                if nearest_idx < len(route_path) - 1:
                    p1 = route_path[nearest_idx]
                    p2 = route_path[nearest_idx + 1]
                    route_bearing = _bearing_between_points(p1, p2)
                    if _bearing_diff(bearing, route_bearing) > heading_threshold:
                        deviating_now = True
                        
            if deviating_now:
                dev_count += 1
                rec_count = max(0, rec_count - 1)
            else:
                rec_count += 1
                dev_count = max(0, dev_count - 1)
                
            if dev_count >= 3:
                is_diverged = True
            elif rec_count >= 3:
                is_diverged = False
                
            # Corridor rejoining route recovery
            if is_diverged:
                original_route_path = _route_geometry_path_for_assigned_trip(trip)
                if original_route_path:
                    if direction == "backward":
                        original_route_path = list(reversed(original_route_path))
                    
                    # Upgrade straight-line GTFS shape to OSRM geometry
                    original_display = _display_geometry_for_map(route, trip, points, original_route_path)
                    original_route_path = original_display.get("path") or original_route_path
                    
                    original_gtfs_path = original_route_path  # save for geometry_sections
                    orig_nearest_idx = _nearest_route_index(lat, lon, original_route_path)
                    dist_to_original = _haversine_km(lat, lon, original_route_path[orig_nearest_idx]["lat"], original_route_path[orig_nearest_idx]["lng"])
                    if dist_to_original < 0.10:
                        is_diverged = False
                        dev_count = 0
                        rec_count = 3
                        _clear_diversion_cache(trip.id)
                        
            gps["deviation_count"] = dev_count
            gps["recovery_count"] = rec_count
            gps["is_diverged"] = is_diverged
            # Write deviation state back into LIVE_GPS_DATA so it persists
            # across polls (fresh_gps_packet returns a shallow copy).
            if bus.id in LIVE_GPS_DATA:
                LIVE_GPS_DATA[bus.id]["deviation_count"] = dev_count
                LIVE_GPS_DATA[bus.id]["recovery_count"] = rec_count
                LIVE_GPS_DATA[bus.id]["is_diverged"] = is_diverged


        # Persistent database cache OSRM diversion routing
        if is_diverged and has_gps_coordinates and points:
            cache_key = hashlib.md5(f"div_{route.id}_{direction}_{next_stop_idx}".encode("utf-8")).hexdigest()
            cache_entry = RoadGeometryCache.query.filter_by(cache_key=cache_key).first()
            
            upcoming_stops = points[next_stop_idx:] if next_stop_idx < len(points) else [points[-1]]
            waypoints = [{"lat": lat, "lng": lon}] + upcoming_stops
            stop_signature = hashlib.md5(str(waypoints).encode("utf-8")).hexdigest()
            
            diversion_road = None
            if cache_entry and cache_entry.status == "ready" and cache_entry.geometry_json:
                try:
                    diversion_road = json.loads(cache_entry.geometry_json)
                except Exception:
                    pass
                    
            if diversion_road and len(diversion_road) >= 2:
                path_idx = _nearest_route_index(lat, lon, diversion_road)
                route_path = [{"lat": lat, "lng": lon}] + diversion_road[path_idx:]
                display_geometry_source = "dynamic_diversion"
            else:
                try:
                    diversion_road = _osrm_route_for_stop_sequence(waypoints)
                    if diversion_road and len(diversion_road) >= 2:
                        if not cache_entry:
                            cache_entry = RoadGeometryCache(
                                cache_key=cache_key,
                                route_id=route.id,
                                shape_id=getattr(trip, "shape_id", None),
                                stop_signature=stop_signature,
                                geometry_json=json.dumps(diversion_road, separators=(",", ":")),
                                status="ready"
                            )
                            db.session.add(cache_entry)
                        else:
                            cache_entry.status = "ready"
                            cache_entry.geometry_json = json.dumps(diversion_road, separators=(",", ":"))
                            cache_entry.stop_signature = stop_signature
                        
                        try:
                            db.session.commit()
                        except Exception:
                            db.session.rollback()
                            
                        route_path = diversion_road
                        display_geometry_source = "dynamic_diversion"
                except Exception as exc:
                    logger.warning("[DIVERSION] OSRM generation failed: %s", exc)

        # Resolve normal geometry if not diverged
        if not is_diverged:
            display_geometry = _display_geometry_for_map(route, trip, points, route_path)
            route_path = display_geometry.get("path") or route_path
            display_geometry_source = display_geometry.get("source")
        else:
            display_geometry = {
                "path": route_path,
                "source": display_geometry_source,
                "generated_point_count": len(route_path)
            }
            
        # Clean up straight line fallbacks
        if display_geometry_source == "stops":
            display_geometry_source = "unavailable"
            route_path = []

    at_stop_val = gps.get("at_stop", False)
    if isinstance(at_stop_val, str):
        at_stop = at_stop_val.strip().lower() in ("true", "1", "yes")
    else:
        at_stop = bool(at_stop_val)

    driver_name_out, driver_code_out = _driver_display_fields(bus)
    occ_pct, occ_level = _latest_recorded_occupancy_for_bus(bus)
    
    schedule_payload = _bus_schedule_payload(
        route,
        trip,
        bus.id,
        current_stop_idx,
        next_stop_idx,
        points,
        direction,
        0.0,
        assigned_trip_only=True,
    )
    schedule_stops = schedule_payload.get("display_schedule_stops") or []
    stop_payload = []
    for idx, point in enumerate(points):
        scheduled = schedule_stops[idx] if idx < len(schedule_stops) else {}
        stop_payload.append({
            "name": point["name"],
            "lat": point["lat"],
            "lng": point["lng"],
            "stop_order": idx + 1,
            "arrival_time": scheduled.get("arrival_time", "--"),
            "departure_time": scheduled.get("departure_time", "--"),
            "scheduled_time": scheduled.get("scheduled_time", "--"),
            "actual_time": scheduled.get("actual_time", "--"),
            "expected_time": scheduled.get("expected_time", "--"),
            "delay_minutes": scheduled.get("delay_minutes", 0),
            "delay_label": scheduled.get("delay_label", "0 min"),
            "delay_reason": scheduled.get("delay_reason", "On time"),
            "delay_status": scheduled.get("delay_status", "ON TIME"),
        })

    shape_id = getattr(trip, "shape_id", None) if trip else None
    
    if movement_begun:
        delay_minutes = int(schedule_payload.get("current_delay_minutes") or 0)
        
        # Remaining Distance calculation using actual road geometry or stop sequence fallback
        remaining_km = 0.0
        if route_path and max_path_index < len(route_path):
            remaining_km = _path_segment_distance(route_path[max_path_index:])
        else:
            remaining_stops = points[current_stop_idx:]
            if len(remaining_stops) >= 2:
                for idx in range(len(remaining_stops) - 1):
                    remaining_km += _haversine_km(
                        remaining_stops[idx]["lat"], remaining_stops[idx]["lng"],
                        remaining_stops[idx+1]["lat"], remaining_stops[idx+1]["lng"]
                    )
                    
        total_dist = _path_segment_distance(route_path) if route_path else 0.0
        if total_dist == 0.0:
            total_dist = remaining_km
        travelled_dist = max(0.0, total_dist - remaining_km)
        trip_progress = (travelled_dist / total_dist * 100.0) if total_dist > 0.0 else 0.0
        
        # Dynamic Speed calculation using smoothed average speed
        journey_duration_minutes = schedule_payload.get("journey_duration_minutes")
        scheduled_speed = (total_dist / (float(journey_duration_minutes or 60.0) / 60.0)) if (total_dist > 0.0) else 35.0
        scheduled_speed = max(15.0, min(80.0, scheduled_speed))
        historical_avg = 35.0
        speed_to_use = (0.5 * avg_live_speed) + (0.3 * historical_avg) + (0.2 * scheduled_speed)
        
        # Stabilized ETA calculation (prevents oscillation)
        recalculate = True
        last_eta = gps.get("last_calculated_eta")
        last_lat = gps.get("last_calculated_eta_lat")
        last_lon = gps.get("last_calculated_eta_lon")
        last_speed = gps.get("last_calculated_eta_speed")
        last_stop = gps.get("last_calculated_eta_stop")
        last_delay = gps.get("last_calculated_eta_delay")
        last_div = gps.get("last_calculated_eta_diverged")
        last_ts = gps.get("last_calculated_eta_ts")
        
        if (last_eta is not None and 
            last_lat is not None and 
            last_lon is not None and 
            last_ts is not None):
            
            dist_moved = _haversine_km(lat, lon, last_lat, last_lon)
            speed_diff = abs((live_speed or 0.0) - (last_speed or 0.0))
            time_elapsed = now_seconds - last_ts
            
            if (dist_moved < 0.05 and 
                speed_diff < 10.0 and 
                last_stop == current_stop_idx and 
                last_delay == delay_minutes and 
                last_div == is_diverged and 
                time_elapsed < 30.0):
                recalculate = False
                minutes_elapsed = int(time_elapsed // 60)
                eta_minutes = max(1, last_eta - minutes_elapsed)
                
        if recalculate:
            dest_sched = points[-1].get("scheduled_time") or (schedule_stops[-1].get("scheduled_time") if (len(points) - 1) < len(schedule_stops) else "--")
            curr_sched = points[current_stop_idx].get("scheduled_time") or (schedule_stops[current_stop_idx].get("scheduled_time") if current_stop_idx < len(schedule_stops) else "--")
            dest_mins = _parse_time_str(dest_sched)
            curr_mins = _parse_time_str(curr_sched)
            if dest_mins is not None and curr_mins is not None:
                scheduled_remaining = float(max(0, dest_mins - curr_mins))
            else:
                journey_mins = float(journey_duration_minutes or 60.0)
                progress_ratio = float(current_stop_idx) / float(max(1, len(points) - 1))
                scheduled_remaining = (1.0 - progress_ratio) * journey_mins
                
            eta_minutes = _calculate_realistic_eta(remaining_km, speed_to_use, delay_minutes, scheduled_remaining)
            
            # Save calculations to gps dictionary state
            gps["last_calculated_eta"] = eta_minutes
            gps["last_calculated_eta_lat"] = lat
            gps["last_calculated_eta_lon"] = lon
            gps["last_calculated_eta_speed"] = live_speed
            gps["last_calculated_eta_stop"] = current_stop_idx
            gps["last_calculated_eta_delay"] = delay_minutes
            gps["last_calculated_eta_diverged"] = is_diverged
            gps["last_calculated_eta_ts"] = now_seconds
            
        eta_label = f"{eta_minutes} min"
        active_stop_index = min(current_stop_idx, max(0, len(points) - 1)) if points else 0

    formatted_gps_timestamp = None
    if gps and gps.get("timestamp") is not None:
        try:
            formatted_gps_timestamp = datetime.fromtimestamp(float(gps["timestamp"]), UTC).isoformat()
        except (TypeError, ValueError, OverflowError, OSError):
            pass

    # Build four-section geometry for full-journey rendering (Google Maps style)
    # Uses the fully resolved route_path and diversion_road after all geometry
    # decisions have been made.  Additive only – nothing upstream is changed.
    _diversion_road_for_sections: list = diversion_road if (is_diverged and isinstance(diversion_road, list)) else []
    if has_gps_coordinates and route_path and len(route_path) >= 2 and movement_begun:
        _split_idx = _nearest_route_index(lat, lon, route_path)
        geometry_sections = _build_geometry_sections(
            lat,
            lon,
            route_path,
            _split_idx,
            is_diverged,
            _diversion_road_for_sections,
            original_gtfs_path,
        )
    elif route_path and len(route_path) >= 2:
        # Trip not yet started or no GPS – entire route is "remaining"
        geometry_sections = {
            "completed": [],
            "planned":   [],
            "dynamic":   [],
            "remaining": route_path,
        }
    else:
        geometry_sections = {"completed": [], "planned": [], "dynamic": [], "remaining": []}
        
    route_source_name = route.origin or "--"
    route_dest_name = route.destination or "--"
    
    if is_return:
        route_source_name, route_dest_name = route_dest_name, route_source_name
        route_name_out = f"{route_source_name} - {route_dest_name}"
    else:
        route_name_out = route.name or "Tracking Active"

    res = {
        "bus_id": bus.id,
        "bus_number": bus.bus_number,
        "registration_number": bus.registration_number,
        "driver_id": driver_code_out,
        "driver_name": driver_name_out,
        "is_diverged": is_diverged,
        "assigned_driver_id": bus.assigned_driver_id,
        "assigned_driver_code": driver_code_out,
        "assigned_driver_name": driver_name_out,
        "sos_active": False,
        "route_id": route.id,
        "route_code": route.route_code or "BUS-RT",
        "route_name": route_name_out,
        "status": _trip_state_label(trip, bus),
        "service_status": "gps_lost" if is_gps_lost else ("delayed" if delay_minutes > 0 else "on_time"),
        "bus_status": "Running",
        "trip_status": _trip_state_label(trip, bus),
        "gps_status": "Offline" if is_gps_lost else "Online",
        "tracking_available": _is_tracking_available(_trip_state_label(trip, bus), "Offline" if is_gps_lost else "Online"),
        "speed": live_speed,
        "occupancy_pct": occ_pct,
        "occupancy_level": occ_level,
        "direction": direction,
        "current_stop_index": current_stop_idx,
        "completed_stops": completed_stops,
        "remaining_stops": max(0, len(points) - completed_stops),
        "active_stop_index": active_stop_index,
        "trip_progress": round(trip_progress, 3),
        "source_stop": points[0]["name"] if points else route_source_name,
        "destination_stop": route_dest_name,
        "current_stop": f"{points[current_stop_idx]['name']} (Arrived)" if points and at_stop and not (gps and gps.get("distance_covered_km", 0.0) == 0.0) else (points[current_stop_idx]["name"] if points else "--"),
        "next_stop": points[next_stop_idx]["name"] if points else "--",
        "distance_remaining_km": round(remaining_km, 2) if isinstance(remaining_km, (int, float)) else remaining_km,
        "distance_covered_km": round(covered_km, 2),
        "eta_minutes": eta_minutes,
        "base_eta_minutes": eta_minutes,
        "updated_eta_minutes": eta_minutes,
        "next_stop_eta_minutes": eta_minutes,
        "eta_label": eta_label,
        "bearing": _optional_float("bearing", "heading", "course"),
        "current_lat": lat,
        "current_lon": lon,
        "is_live_gps": not is_gps_lost,
        "gps_timestamp": formatted_gps_timestamp,
        "shape_id": shape_id,
        "shape_point_count": len(route_path),
        "shape_points_db": _shape_point_count_db(shape_id),
        "shape_points_api": len(route_path),
        "points_removed": max(0, _shape_point_count_db(shape_id) - len(route_path)),
        "shape_point_index": path_index if route_path else None,
        "movement_state": "live_gps",
        "path": route_path,
        "display_path": display_geometry.get("path") or route_path,
        "display_geometry_source": display_geometry.get("source"),
        "geometry_source": display_geometry.get("source"),
        "generated_road_geometry_points": display_geometry.get("generated_point_count", 0),
        "stops": stop_payload,
        "geometry_available": True,
        "geometry_message": None,
        "geometry_sections": geometry_sections,
        "trip_id": trip.id if trip and getattr(trip, "id", None) else None,
        "actual_departure_time": trip.start_time.strftime("%H:%M") if trip and trip.start_time else "--",
        "actual_arrival_time": trip.end_time.strftime("%H:%M") if trip and trip.end_time else "--",
        **schedule_payload,
    }
    return _enrich_snapshot_with_defaults(res, bus)


def _completed_trip_snapshot(bus: Bus, trip: Trip, route: Route) -> dict:
    if trip.end_time:
        if trip.end_time.tzinfo is None:
            et_aware = trip.end_time.replace(tzinfo=UTC)
        else:
            et_aware = trip.end_time
        ist_offset = timezone(timedelta(hours=5, minutes=30))
        et_ist = et_aware.astimezone(ist_offset)
        arrival_time_str = et_ist.strftime("%I:%M %p")
    else:
        arrival_time_str = "--"

    points = _route_points_for_assigned_trip(route, trip)
    route_path = _route_geometry_path_for_assigned_trip(trip)
    validation_error = _assigned_trip_validation_error(route, trip, points, route_path)
    
    has_return_ready_trip = Trip.query.filter_by(
        bus_id=bus.id,
        route_id=route.id,
        status="return_ready"
    ).first() is not None

    if validation_error:
        completed_message = f"Trip Completed. {validation_error}"
        snapshot = _live_tracking_validation_snapshot(bus, trip, route, completed_message, None)
        direction_id_err = getattr(trip, "direction_id", 0) if trip else 0
        status_err = "RETURN_COMPLETED" if direction_id_err == 1 else "COMPLETED"
        snapshot.update({
            "status": status_err,
            "service_status": "completed",
            "bus_status": "OFFLINE",
            "trip_status": status_err,
            "direction_id": direction_id_err,
            "gps_status": "Offline",
            "eta_label": "Completed",
            "geometry_message": completed_message,
            "validation_error": validation_error,
            "gps_timestamp": trip.end_time.isoformat() if trip.end_time else snapshot.get("gps_timestamp"),
            "completed_at": trip.end_time.isoformat() if trip.end_time else None,
            "trip_progress": 100,
            "completed_stops": len(points) if points else 0,
            "remaining_stops": 0,
            "current_stop_index": max(0, len(points) - 1) if points else 0,
            "at_stop": True,
            "arrival_time": arrival_time_str,
            "updated_arrival_time": arrival_time_str,
            "current_stop": points[-1]["name"] if points else (route.destination or "--"),
            "next_stop": "—",
            "return_trip_ready": has_return_ready_trip,
            "geometry_sections": {
                "completed": [],  # Route unavailable, but trip is completed
                "planned": [],
                "dynamic": [],
                "remaining": [],
            },
        })
        return snapshot

    direction = "backward" if getattr(trip, "direction_id", 0) == 1 else "forward"
    if direction == "backward":
        route_path = list(reversed(route_path))
    display_geometry = _display_geometry_for_map(route, trip, points, route_path)
    route_path = display_geometry.get("path") or route_path

    final_idx = max(0, len(points) - 1)
    driver_name_out, driver_code_out = _driver_display_fields(bus)
    occ_pct, occ_level = _latest_recorded_occupancy_for_bus(bus)
    schedule_payload = _bus_schedule_payload(
        route,
        trip,
        bus.id,
        final_idx,
        final_idx,
        points,
        direction,
        0.0,
        assigned_trip_only=True,
    )
    schedule_stops = schedule_payload.get("display_schedule_stops") or []
    stop_payload = []
    for idx, point in enumerate(points):
        scheduled = schedule_stops[idx] if idx < len(schedule_stops) else {}
        
        arr_t = scheduled.get("arrival_time", "--")
        act_t = scheduled.get("actual_time", "--")
        if idx == len(points) - 1:
            arr_t = arrival_time_str
            act_t = arrival_time_str
            
        stop_payload.append({
            "name": point["name"],
            "lat": point["lat"],
            "lng": point["lng"],
            "stop_order": idx + 1,
            "arrival_time": arr_t,
            "departure_time": scheduled.get("departure_time", "--"),
            "scheduled_time": scheduled.get("scheduled_time", "--"),
            "actual_time": act_t,
            "expected_time": scheduled.get("expected_time", "--"),
            "delay_minutes": scheduled.get("delay_minutes", 0),
            "delay_label": scheduled.get("delay_label", "0 min"),
            "delay_reason": scheduled.get("delay_reason", "On time"),
            "delay_status": scheduled.get("delay_status", "ON TIME"),
        })

    final_point = points[final_idx] if points else None
    path_distance_km = _path_segment_distance(route_path) if len(route_path) >= 2 else 0.0
    shape_id = getattr(trip, "shape_id", None) if trip else None
    status_str = "RETURN_COMPLETED" if (trip and (trip.status == "return_completed" or direction == "backward")) else "COMPLETED"
    direction_id_val = getattr(trip, "direction_id", 0) if trip else 0

    route_name_out = route.name or "Tracking Completed"
    if getattr(trip, "direction_id", 0) == 1 or getattr(trip, "status", "") in ("return_ready", "return_running", "return_completed"):
        if points and len(points) >= 2:
            route_name_out = f"{points[0]['name']} - {points[-1]['name']}"
        elif route.destination and route.origin:
            route_name_out = f"{route.destination} - {route.origin}"

    res = {
        "bus_id": bus.id,
        "bus_number": bus.bus_number,
        "registration_number": bus.registration_number,
        "driver_id": driver_code_out,
        "driver_name": driver_name_out,
        "assigned_driver_id": bus.assigned_driver_id,
        "assigned_driver_code": driver_code_out,
        "assigned_driver_name": driver_name_out,
        "sos_active": False,
        "route_id": route.id,
        "route_code": route.route_code or "BUS-RT",
        "route_name": route_name_out,
        "status": status_str,
        "service_status": "completed",
        "bus_status": "OFFLINE",
        "trip_status": status_str,
        "gps_status": "Offline",
        "tracking_available": False,
        "speed": 0,
        "occupancy_pct": occ_pct,
        "occupancy_level": occ_level,
        "direction": direction,
        "direction_id": direction_id_val,
        "current_stop_index": final_idx,
        "completed_stops": len(points),
        "remaining_stops": 0,
        "trip_progress": 100,
        "source_stop": points[0]["name"] if points else (route.origin or "--"),
        "destination_stop": points[-1]["name"] if points else (route.destination or "--"),
        "current_stop": points[-1]["name"] if points else (route.destination or "--"),
        "next_stop": "—",
        "return_trip_ready": has_return_ready_trip,
        "distance_remaining_km": 0,
        "distance_covered_km": round(path_distance_km, 2),
        "eta_minutes": 0,
        "base_eta_minutes": 0,
        "updated_eta_minutes": 0,
        "next_stop_eta_minutes": 0,
        "eta_label": "Arrived",
        "bearing": 0,
        "current_lat": final_point["lat"] if final_point else None,
        "current_lon": final_point["lng"] if final_point else None,
        "display_current_lat": final_point["lat"] if final_point else None,
        "display_current_lon": final_point["lng"] if final_point else None,
        "is_live_gps": False,
        "gps_timestamp": trip.end_time.isoformat() if trip.end_time else None,
        "completed_at": trip.end_time.isoformat() if trip.end_time else None,
        "shape_id": shape_id,
        "shape_point_count": len(route_path),
        "shape_points_db": _shape_point_count_db(shape_id),
        "shape_points_api": len(route_path),
        "points_removed": max(0, _shape_point_count_db(shape_id) - len(route_path)),
        "shape_point_index": len(route_path) - 1 if route_path else None,
        "movement_state": "completed",
        "path": route_path,
        "display_path": route_path,
        "display_geometry_source": display_geometry.get("source"),
        "geometry_source": display_geometry.get("source"),
        "generated_road_geometry_points": display_geometry.get("generated_point_count", 0),
        "stops": stop_payload,
        "geometry_available": True,
        "geometry_message": None,
        "trip_id": trip.id if trip and getattr(trip, "id", None) else None,
        # Completed trip geometry: entire route is 'completed' (rendered gray)
        "geometry_sections": {
            "completed": route_path,
            "planned": [],
            "dynamic": [],
            "remaining": [],
        },
        **schedule_payload,
        "arrival_time": arrival_time_str,
        "updated_arrival_time": arrival_time_str,
        "current_stop_index": final_idx,
        "completed_stops": len(points),
        "remaining_stops": 0,
        "trip_progress": 100,
        "at_stop": True,
        "gps_status": "Offline",
    }
    return _enrich_snapshot_with_defaults(res, bus)


def _planned_assignment_snapshot(bus: Bus, trip, route: Route, now_seconds: Optional[float] = None,
                                 active_without_gps: bool = False) -> dict:
    now_seconds = now_seconds or time.time()
    points = _route_points_for_assigned_trip(route, trip) if trip else _route_points_for(route, None)
    route_path = _route_geometry_path_for_assigned_trip(trip) if trip else _route_geometry_path(route)
    validation_error = _assigned_trip_validation_error(route, trip, points, route_path) if trip else None
    if validation_error:
        return _live_tracking_validation_snapshot(bus, trip, route, validation_error, None)

    if points and route_path:
        dist_start = _haversine_km(points[0]["lat"], points[0]["lng"], route_path[0]["lat"], route_path[0]["lng"])
        dist_end = _haversine_km(points[0]["lat"], points[0]["lng"], route_path[-1]["lat"], route_path[-1]["lng"])
        if dist_end < dist_start:
            route_path = list(reversed(route_path))

    display_geometry = _display_geometry_for_map(route, trip, points, route_path) if points else {"path": route_path, "source": "gtfs", "generated_point_count": 0}
    display_path = display_geometry.get("path") or route_path
    direction = "backward" if getattr(trip, "direction_id", 0) == 1 else "forward"
    schedule_payload = _bus_schedule_payload(
        route,
        trip,
        bus.id,
        0,
        1 if len(points) > 1 else 0,
        points,
        direction,
        0.0,
        assigned_trip_only=bool(trip),
    )
    schedule_stops = schedule_payload.get("display_schedule_stops") or []
    stops_payload = []
    for idx, point in enumerate(points):
        scheduled = schedule_stops[idx] if idx < len(schedule_stops) else {}
        stops_payload.append({
            "name": point["name"],
            "lat": point["lat"],
            "lng": point["lng"],
            "stop_order": idx + 1,
            "arrival_time": scheduled.get("arrival_time", "--"),
            "departure_time": scheduled.get("departure_time", "--"),
            "scheduled_time": scheduled.get("scheduled_time", "--"),
            "actual_time": "--",
            "expected_time": scheduled.get("scheduled_time", "--"),
            "delay_minutes": 0,
            "delay_label": "0 min",
            "delay_reason": "Waiting for driver",
            "delay_status": "ON TIME",
        })

    driver_name_out, driver_code_out = _driver_display_fields(bus)
    occ_pct, occ_level = _latest_recorded_occupancy_for_bus(bus)
    route_distance_km = round(_path_segment_distance(display_path), 2) if len(display_path) >= 2 else round(float(route.distance_km or 0), 2)
    duration_minutes = schedule_payload.get("journey_duration_minutes")
    eta_label = _duration_label(duration_minutes) if duration_minutes is not None else schedule_payload.get("journey_duration", "--")
    trip_state = _trip_state_label(trip, bus)
    bus_status = "Offline"
    gps_status = "Offline"
    gps_state_val = "OFFLINE"
    status_label = "Waiting to Depart"
    
    current_lat = points[0]["lat"] if (points and active_without_gps) else None
    current_lon = points[0]["lng"] if (points and active_without_gps) else None

    runtime = _runtime_state_for_bus(bus.id)
    now_iso = datetime.fromtimestamp(now_seconds, UTC).isoformat()
    res = {
        "bus_id": bus.id,
        "bus_number": bus.bus_number,
        "registration_number": bus.registration_number,
        "driver_id": driver_code_out,
        "driver_name": driver_name_out,
        "assigned_driver_id": bus.assigned_driver_id,
        "assigned_driver_code": driver_code_out,
        "assigned_driver_name": driver_name_out,
        "driver_state": runtime.get("driver_state") or ("ON_DUTY" if bus.is_active else "OFF_DUTY"),
        "bus_state": runtime.get("bus_state") or ("ACTIVE" if bus.is_active else "OFFLINE"),
        "gps_state": runtime.get("gps_state") or gps_state_val,
        "last_update_timestamp": runtime.get("last_update_timestamp") or now_iso,
        "sos_active": False,
        "route_id": route.id,
        "route_code": route.route_code or "BUS-RT",
        "route_name": route.name or route.route_code or "Assigned Route",
        "status": status_label,
        "service_status": "running" if active_without_gps else "offline",
        "bus_status": bus_status,
        "trip_status": trip_state,
        "gps_status": gps_status,
        "tracking_available": False,
        "speed": 0,
        "occupancy_pct": occ_pct,
        "occupancy_level": occ_level,
        "direction": direction,
        "direction_id": getattr(trip, "direction_id", 0) if trip else 0,
        "current_stop_index": 0,
        "completed_stops": 0,
        "remaining_stops": len(points),
        "active_stop_index": 0,
        "trip_progress": 0,
        "source_stop": points[0]["name"] if points else (route.origin or "--"),
        "destination_stop": points[-1]["name"] if points else (route.destination or "--"),
        "current_stop": points[0]["name"] if points else (route.origin or "--"),
        "next_stop": points[1]["name"] if len(points) > 1 else (route.destination or "--"),
        "distance_remaining_km": "--",
        "distance_covered_km": 0,
        "eta_minutes": None,
        "base_eta_minutes": None,
        "updated_eta_minutes": None,
        "next_stop_eta_minutes": None,
        "eta_label": "--",
        "current_delay_minutes": 0,
        "current_delay_label": "0 min",
        "current_delay_reason": "Waiting to Depart" if not active_without_gps else "On time",
        "bearing": None,
        "current_lat": current_lat,
        "current_lon": current_lon,
        "planned_marker_lat": points[0]["lat"] if points else None,
        "planned_marker_lon": points[0]["lng"] if points else None,
        "is_live_gps": active_without_gps,
        "gps_timestamp": datetime.fromtimestamp(now_seconds, UTC).isoformat(),
        "shape_id": getattr(trip, "shape_id", None) if trip else None,
        "shape_point_count": len(display_path),
        "shape_points_db": _shape_point_count_db(getattr(trip, "shape_id", None) if trip else None),
        "shape_points_api": len(display_path),
        "points_removed": 0,
        "shape_point_index": None,
        "movement_state": "waiting_for_driver" if not active_without_gps else "gps_pending",
        "path": display_path,
        "display_path": display_path,
        "display_geometry_source": display_geometry.get("source"),
        "geometry_source": display_geometry.get("source"),
        "generated_road_geometry_points": display_geometry.get("generated_point_count", 0),
        "travelled_path": [],
        "stops": stops_payload,
        "geometry_available": bool(display_path and points),
        "geometry_message": None if display_path and points else "Assigned route geometry is not available.",
        "trip_id": getattr(trip, "id", None) if trip else None,
        "assigned": True,
        # Planned snapshot: entire route is 'remaining' (rendered cyan)
        "geometry_sections": {
            "completed": [],
            "planned": [],
            "dynamic": [],
            "remaining": display_path,
        },
        **schedule_payload,
    }
    return _enrich_snapshot_with_defaults(res, bus)


def _log_fleet_exclusion(bus: Optional[Bus], reason: str, trip=None, route: Optional[Route] = None) -> None:
    logger.warning(
        "[FLEET] excluded bus_id=%s bus_number=%s trip_id=%s trip_status=%s route_id=%s reason=%s",
        getattr(bus, "id", None),
        getattr(bus, "bus_number", None),
        getattr(trip, "id", None),
        getattr(trip, "status", None),
        getattr(route, "id", None) if route else getattr(trip, "route_id", None),
        reason,
    )


def _log_fleet_snapshot_exception(stage: str, bus: Bus, trip, route: Optional[Route], exc: Exception) -> None:
    logger.exception(
        "[FLEET] %s snapshot failed bus_id=%s bus_number=%s trip_id=%s trip_status=%s route_id=%s error=%s",
        stage,
        getattr(bus, "id", None),
        getattr(bus, "bus_number", None),
        getattr(trip, "id", None),
        getattr(trip, "status", None),
        getattr(route, "id", None) if route else getattr(trip, "route_id", None),
        exc,
    )


def _log_fleet_snapshot_selection(bus: Bus, trip, selected_snapshot: str, reason: str,
                                  route: Optional[Route] = None) -> None:
    logger.info(
        "[FLEET_SNAPSHOT_SELECTION] bus_id=%s bus_number=%s trip_id=%s trip_status=%s "
        "bus_is_active=%s route_id=%s selected_snapshot=%s reason=%s",
        getattr(bus, "id", None),
        getattr(bus, "bus_number", None),
        getattr(trip, "id", None),
        getattr(trip, "status", None),
        bool(getattr(bus, "is_active", False)),
        getattr(route, "id", None) if route else getattr(trip, "route_id", None),
        selected_snapshot,
        reason,
    )


def _live_fleet_snapshot() -> list:
    global _FLEET_SNAPSHOT_CACHE, _FLEET_SNAPSHOT_CACHE_TIME
    now_seconds = time.time()
    if _FLEET_SNAPSHOT_CACHE is not None and (now_seconds - _FLEET_SNAPSHOT_CACHE_TIME) < 2.0:
        return _FLEET_SNAPSHOT_CACHE

    snapshot = []
    _cleanup_live_state(now_seconds)
    queued_delay_notifications = 0
    active_sos_bus_ids = {
        row[0]
        for row in db.session.query(SOSAlert.bus_id)
        .filter(SOSAlert.status.in_(ACTIVE_SOS_STATUSES))
        .all()
    }

    active_buses = Bus.query.filter(
        Bus.assigned_driver_code.isnot(None),
        or_(Bus.route_id.isnot(None), Bus.is_active.is_(True))
    ).order_by(Bus.bus_number.asc()).all()

    for bus in active_buses:
        real_gps = _fresh_gps_packet(bus.id, now_seconds)
        gps_to_use = real_gps
        if not gps_to_use:
            stale_gps = LIVE_GPS_DATA.get(bus.id)
            if stale_gps:
                gps_to_use = stale_gps
        active_trip = _active_trip_for_bus(bus)
        trip_selection_reason = "active trip selected for live polling" if active_trip else "dashboard/planned assignment selected"
        trip = active_trip or _driver_dashboard_trip_for_bus(bus)
        if not trip:
            _log_fleet_exclusion(bus, "no dashboard trip found for assigned bus")
            continue

        route = db.session.get(Route, trip.route_id)
        if route is None:
            _log_fleet_exclusion(bus, "trip route not found", trip=trip)
            continue

        if trip.status in ("completed", "return_completed"):
            try:
                bus_data = _completed_trip_snapshot(bus, trip, route)
                _log_fleet_snapshot_selection(bus, trip, "COMPLETED", "completed trip status", route)
            except Exception as exc:
                _log_fleet_snapshot_exception("completed", bus, trip, route, exc)
                continue
        elif trip.status in ("active", "in_progress"):
            try:
                bus_data = _real_gps_bus_snapshot(bus, trip, route, gps_to_use)
                bus_data["travelled_path"] = LIVE_GPS_BREADCRUMBS.get(bus.id, [])
                gps_reason = "fresh GPS" if real_gps else ("last known GPS" if gps_to_use else "active trip without GPS packet")
                _log_fleet_snapshot_selection(
                    bus,
                    trip,
                    "ACTIVE",
                    f"{trip_selection_reason}; {gps_reason}",
                    route,
                )
            except Exception as exc:
                _log_fleet_snapshot_exception("active-real-gps", bus, trip, route, exc)
                raise
        else:
            try:
                if bus.is_active:
                    logger.warning(
                        "[FLEET_SNAPSHOT_ANOMALY] active bus selected planned snapshot bus_id=%s trip_id=%s "
                        "trip_status=%s reason=no active trip found",
                        bus.id,
                        getattr(trip, "id", None),
                        getattr(trip, "status", None),
                    )
                bus_data = _planned_assignment_snapshot(
                    bus,
                    trip,
                    route,
                    now_seconds,
                    active_without_gps=bool(bus.is_active),
                )
                _log_fleet_snapshot_selection(bus, trip, "PLANNED", trip_selection_reason, route)
            except Exception as exc:
                _log_fleet_snapshot_exception("planned-assignment", bus, trip, route, exc)
                continue

        if bus_data:
            bus_data["bus_is_active"] = bool(bus.is_active)
            bus_data["sos_active"] = bus.id in active_sos_bus_ids
            if bus_data.get("is_live_gps"):
                try:
                    queued_delay_notifications += _queue_meaningful_delay_notifications(bus_data, route, trip)
                except Exception as exc:
                    logger.warning("[DELAY_NOTIFY] skipped for bus %s: %s", bus.bus_number, exc)
            snapshot.append(bus_data)
        else:
            _log_fleet_exclusion(bus, "snapshot builder returned no bus data", trip=trip, route=route)

    if queued_delay_notifications:
        try:
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            logger.warning("[DELAY_NOTIFY] commit failed: %s", exc)

    _FLEET_SNAPSHOT_CACHE = snapshot
    _FLEET_SNAPSHOT_CACHE_TIME = now_seconds
    return snapshot


def _admin_shell_metrics(include_snapshot: bool = True) -> dict:
    """Return admin page metrics without forcing live telemetry simulation."""
    total_buses = Bus.query.count()
    snapshot = _live_fleet_snapshot() if include_snapshot else []
    
    waiting_to_depart = 0
    running = 0
    completed = 0
    return_ready = 0
    
    for b in snapshot:
        trip_st = b.get("trip_status", "")
        if trip_st == "WAITING_TO_DEPART":
            waiting_to_depart += 1
        elif trip_st in ("RUNNING", "RETURN_RUNNING"):
            running += 1
        elif trip_st in ("COMPLETED", "RETURN_COMPLETED"):
            completed += 1
        elif trip_st == "RETURN_READY":
            return_ready += 1

    offline = max(0, total_buses - (waiting_to_depart + running + completed + return_ready))

    return {
        "total_buses": total_buses,
        "active_buses": Bus.query.filter_by(is_active=True).count(),
        "waiting_to_depart": waiting_to_depart,
        "running": running,
        "offline": offline,
        "return_ready": return_ready,
        "completed_buses": completed,
        "total_routes": Route.query.count(),
        "total_drivers": Bus.query.filter(Bus.assigned_driver_code.isnot(None)).count(),
        "total_passengers": User.query.filter_by(role='passenger').count(),
        "open_complaints": _apply_lifecycle_filter(Complaint.query, Complaint, "active").count(),
        "sos_alerts": SOSAlert.query.filter(SOSAlert.status.in_(ACTIVE_SOS_STATUSES)).count(),
        "fleet_snapshot": snapshot,
    }

def register_routes(app: Flask) -> None:
    @app.get("/")
    def index(): return render_template("index.html")

    @app.route("/admin/docs", defaults={'filename': 'README.md'})
    @app.route("/admin/docs/<path:filename>")
    @role_required("admin")
    def admin_docs(filename):
        allowed_files = ['README.md', 'QUICK_REFERENCE.md', 'UPGRADES.md', 'IMPLEMENTATION_SUMMARY.md', 'PHASE9_IMPLEMENTATION.md']
        if filename not in allowed_files:
            flash("Document not found or access denied.", "danger")
            return redirect(url_for("admin_dashboard"))

        filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
        if not os.path.exists(filepath):
            flash(f"Document {filename} not found on server.", "danger")
            return redirect(url_for("admin_dashboard"))

        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        html_content = markdown.markdown(content, extensions=['fenced_code', 'tables'])
        return render_template("admin_docs.html", html_content=html_content, current_doc=filename, allowed_files=allowed_files)

    @app.route("/register", methods=["GET", "POST"])
    @app.limiter.limit("10 per hour")
    def register_page():
        if current_user.is_authenticated: return redirect(url_for(_dashboard_route_for_role(current_user.role)))
        if request.method == "POST":
            full_name = (request.form.get("full_name") or "").strip()
            email = (request.form.get("email") or "").strip().lower()
            password = request.form.get("password") or ""
            confirm_password = request.form.get("confirm_password") or ""
            if not all([full_name, email, password]):
                flash("All fields are required.", "danger")
                return render_template("register.html")
            if not _is_valid_email(email):
                flash("Enter a valid email address.", "danger")
                return render_template("register.html")
            password_error = _validate_password_strength(password)
            if password_error:
                flash(password_error, "danger")
                return render_template("register.html")
            if password != confirm_password:
                flash("Passwords do not match.", "danger")
                return render_template("register.html")
            if User.query.filter_by(email=email).first():
                flash("Email already exists. Please login.", "warning")
                return redirect(url_for("login_page"))

            user = User(full_name=full_name, email=email, role="passenger", auth_provider="local")
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            db.session.refresh(user)
            flash("Registration successful.", "success")
            return redirect(url_for("login_page"))
        return render_template("register.html")

    @app.route("/google_register", methods=["POST"])
    @app.limiter.limit("10 per hour")
    def google_register():
        try:
            profile = _verified_google_profile(request.form.get("credential") or "")
        except ValueError as exc:
            flash(str(exc), "danger")
            return redirect(url_for("register_page"))
        full_name = profile["full_name"]
        email = profile["email"]
        user = User.query.filter_by(email=email).first()
        if user:
            flash("Email already exists. Please log in.", "warning")
            return redirect(url_for("login_page"))

        random_password = secrets.token_urlsafe(32)
        new_user = User(full_name=full_name, email=email, role="passenger", auth_provider="google")
        new_user.set_password(random_password)
        db.session.add(new_user)
        db.session.commit()
        session.clear()

        flash("Registration successful. Please sign in with Google.", "success")

        return redirect(url_for("login_page"))

    @app.route("/forgot-password", methods=["GET", "POST"])
    @app.limiter.limit("5 per hour", methods=["POST"])
    def forgot_password():
        if current_user.is_authenticated:
            return redirect(url_for(_dashboard_route_for_role(current_user.role)))

        submitted_email = ""
        if request.method == "POST":
            wants_json = _request_wants_json()
            submitted_email = (request.form.get("email") or "").strip().lower()
            if not submitted_email or not _is_valid_email(submitted_email):
                if wants_json:
                    return jsonify({
                        "success": False,
                        "message": "A valid registered passenger email is required.",
                    }), 400
                flash("A valid registered passenger email is required.", "danger")
                return render_template("forgot_password.html", email=submitted_email)

            user = User.query.filter_by(email=submitted_email, role="passenger").first()
            if user and getattr(user, "auth_provider", "local") == "local":
                token = _generate_password_reset_token(user)
                base_url = (current_app.config.get("PASSWORD_RESET_BASE_URL") or "").strip()
                reset_path = url_for("reset_password", token=token)
                reset_link = f"{base_url.rstrip('/')}{reset_path}" if base_url else url_for(
                    "reset_password",
                    token=token,
                    _external=True,
                )
                try:
                    _send_password_reset_email(user.email, reset_link)
                except Exception as exc:
                    logger.exception("[PASSWORD_RESET] Failed to send reset email to %s: %s", user.email, exc)
                    if wants_json:
                        return jsonify({
                            "success": False,
                            "message": "Password reset email could not be sent right now.",
                        }), 500
                    flash("Password reset email could not be sent right now.", "danger")
                    return render_template("forgot_password.html", email=submitted_email)

            if wants_json:
                return jsonify({
                    "success": True,
                    "message": "If that passenger account exists, a reset link has been sent.",
                }), 200
            flash("If that passenger account exists, a reset link has been sent.", "success")
            return redirect(url_for("login_page"))

        return render_template("forgot_password.html", email=submitted_email)

    @app.route("/reset-password/<token>", methods=["GET", "POST"])
    @app.limiter.limit("10 per hour", methods=["POST"])
    def reset_password(token):
        if current_user.is_authenticated:
            return redirect(url_for(_dashboard_route_for_role(current_user.role)))

        user, token_error = _load_password_reset_user(token)
        if token_error:
            if token_error == "expired":
                flash("Password reset link has expired. Please request a new one.", "danger")
            elif token_error == "used":
                flash("Password reset link has already been used. Please request a new one.", "danger")
            else:
                flash("Password reset link is invalid. Please request a new one.", "danger")
            return redirect(url_for("forgot_password"))

        min_length = current_app.config.get("PASSWORD_MIN_LENGTH", PASSWORD_MIN_LENGTH)
        if request.method == "POST":
            password = request.form.get("password") or ""
            confirm_password = request.form.get("confirm_password") or ""
            password_error = _validate_password_strength(password)
            if password_error:
                flash(password_error, "danger")
                return render_template("reset_password.html", token=token, min_length=min_length)
            if password != confirm_password:
                flash("Passwords do not match.", "danger")
                return render_template("reset_password.html", token=token, min_length=min_length)

            user.set_password(password)
            db.session.commit()
            flash("Password updated. Please sign in with your new password.", "success")
            return redirect(url_for("login_page"))

        return render_template("reset_password.html", token=token, min_length=min_length)

    @app.route("/login", methods=["GET", "POST"])
    @app.limiter.limit("20 per hour", methods=["POST"])
    def login_page():
        if current_user.is_authenticated: return redirect(url_for(_dashboard_route_for_role(current_user.role)))
        if request.method == "POST":
            email = (request.form.get("email") or "").strip().lower()
            password = request.form.get("password") or ""
            login_type = request.form.get("login_type") or "passenger"
            driver_id = request.form.get("driver_id")
            admin_id = request.form.get("admin_id")

            if not email or not password or not _is_valid_email(email):
                flash("Email and password are required.", "danger")
                return render_template("login.html")

            user = User.query.filter_by(email=email).first()
            if user and getattr(user, 'auth_provider', 'local') == "google":
                flash("Please sign in with Google.", "warning")
                return render_template("login.html")
            if user is None or not user.check_password(password):
                flash("Invalid credentials.", "danger")
                return render_template("login.html")

            if login_type == "driver":
                if email != SHARED_DRIVER_EMAIL:
                    flash("Drivers must log in with driver@transpulse.com.", "danger")
                    return render_template("login.html")
                if user.role != "driver":
                    flash("Account is not a driver profile.", "danger")
                    return render_template("login.html")
                formatted_code, code_err = _validate_driver_code_input(driver_id or "")
                if code_err:
                    flash(code_err, "danger")
                    return render_template("login.html")
                assigned_bus = _bus_for_driver_code(formatted_code)
                if not assigned_bus:
                    flash("No Bus Assigned.", "danger")
                    return render_template("login.html")
                session["driver_code"] = formatted_code
                session["assigned_bus_id"] = assigned_bus.id

            if login_type == "admin":
                if email != "admin@transpulse.com":
                    flash("Admin must log in with admin@transpulse.com.", "danger")
                    return render_template("login.html")
                if user.role != "admin":
                    flash("Account is not an admin profile.", "danger")
                    return render_template("login.html")
                if (admin_id or "").strip() != "ATP-01":
                    flash("Invalid Admin Security Code.", "danger")
                    return render_template("login.html")

            driver_session = {}
            if login_type == "driver":
                driver_session = {
                    "driver_code": session.get("driver_code"),
                    "assigned_bus_id": session.get("assigned_bus_id"),
                }
            session.clear()
            login_user(user)
            if login_type == "driver":
                session["driver_code"] = driver_session.get("driver_code")
                session["assigned_bus_id"] = driver_session.get("assigned_bus_id")
            return redirect(url_for(_dashboard_route_for_role(current_user.role)))
        return render_template("login.html")

    @app.route("/google_login", methods=["POST"])
    @app.limiter.limit("20 per hour")
    def google_login():
        try:
            profile = _verified_google_profile(request.form.get("credential") or "")
        except ValueError as exc:
            flash(str(exc), "danger")
            return redirect(url_for("login_page"))
        email = profile["email"]
        user = User.query.filter_by(email=email).first()
        if not user:
            flash("Google account not found. Please register first.", "danger")
            return redirect(url_for("register_page"))
        if getattr(user, 'auth_provider', 'local') != "google":
            flash("This account was created locally. Please sign in with your password.", "warning")
            return redirect(url_for("login_page"))
        session.clear()
        login_user(user)
        session.permanent = True
        session.modified = True
        return redirect(url_for(_dashboard_route_for_role(current_user.role)))

    @app.post("/logout")
    @login_required
    def logout_page():
        session.pop("driver_code", None)
        session.pop("assigned_bus_id", None)
        logout_user()
        flash("Logged out successfully.", "info")
        return redirect(url_for("index"))

    @app.route("/dashboard/admin")
    @app.route('/admin_dashboard')
    @role_required("admin")
    def admin_dashboard():
        return render_template('admin_dashboard.html', **_admin_shell_metrics(),
                               show_fleet_only_table=False, show_tracking_search=False)

    @app.route("/admin/live-fleet", methods=["GET"])
    @role_required("admin")
    def live_fleet_monitoring():
        return render_template('admin_dashboard.html', **_admin_shell_metrics(),
                               show_fleet_only_table=True, show_tracking_search=False)

    @app.route("/admin/tracking-search")
    @role_required("admin")
    def admin_tracking_search():
        return render_template('admin_dashboard.html', **_admin_shell_metrics(),
                               show_fleet_only_table=False, show_tracking_search=True)

    @app.route("/admin/buses", methods=["GET", "POST"])
    @role_required("admin")
    def admin_buses():
        if request.method == "POST":
            action = (request.form.get("action") or "assign_bus").strip()

            bus_number = (request.form.get("bus_number") or "").strip().upper()
            registration_number = (request.form.get("registration_number") or "").strip().upper()
            capacity_raw = (request.form.get("capacity") or "").strip()
            assigned_driver_code_raw = (request.form.get("assigned_driver_code") or "").strip()

            route_code = (request.form.get("route_code") or "").strip().upper()
            route_name = (request.form.get("route_name") or "").strip()
            origin = (request.form.get("origin") or "").strip()
            destination = (request.form.get("destination") or "").strip()
            intermediates = (request.form.get("intermediate_stops") or "").strip()
            departure_time = (request.form.get("departure_time") or "").strip()

            if not bus_number or not registration_number or not capacity_raw:
                flash("Bus configuration constraints cannot be empty.", "danger")
                return redirect(url_for("admin_buses"))

            try:
                capacity = int(capacity_raw)
            except ValueError:
                flash("Parsing parameters error encountered.", "danger")
                return redirect(url_for("admin_buses"))
            if capacity <= 0:
                flash("Bus capacity must be greater than zero.", "danger")
                return redirect(url_for("admin_buses"))

            route_id = None
            existing_route_id_raw = (request.form.get("existing_route_id") or "").strip()
            manual_schedule_route = None

            if existing_route_id_raw:
                try:
                    selected_route_id = int(existing_route_id_raw)
                    selected_route = db.session.get(Route, selected_route_id)
                    if not selected_route:
                        flash("Selected route not found.", "danger")
                        return redirect(url_for("admin_buses"))
                    route_id = selected_route.id
                    logger.info("[ROUTE_ASSIGN] Using existing route id=%s code=%s", route_id, selected_route.route_code)
                except ValueError:
                    flash("Invalid route selection.", "danger")
                    return redirect(url_for("admin_buses"))
            elif route_code and origin and destination:
                existing = Route.query.filter_by(route_code=route_code).first()
                if existing:
                    route_id = existing.id
                    manual_schedule_route = existing if (departure_time or intermediates) else None
                    if manual_schedule_route:
                        manual_schedule_route.distance_km = _auto_route_distance_km(manual_schedule_route, intermediates)
                    flash(f"Route {route_code} already exists — bus assigned to existing route.", "info")
                    logger.info("[ROUTE_ASSIGN] Duplicate prevented, using route id=%s", route_id)
                else:
                    route = Route(
                        route_code=route_code,
                        name=route_name or f"{origin} to {destination}",
                        origin=origin,
                        destination=destination,
                        distance_km=0.0,
                        departure_time=departure_time or None,
                        is_operational=True
                    )

                    db.session.add(route)
                    db.session.flush()
                    route.distance_km = _auto_route_distance_km(route, intermediates)
                    _apply_manual_route_schedule(route, intermediates, departure_time)

                    route_id = route.id
                    manual_schedule_route = route
                    logger.info("[ROUTE_ASSIGN] Created new route id=%s code=%s", route_id, route_code)

            if manual_schedule_route and not _route_has_gtfs_stop_times(manual_schedule_route.id):
                _apply_manual_route_schedule(manual_schedule_route, intermediates, departure_time)

            bus = Bus.query.filter_by(bus_number=bus_number).first()

            existing_reg = Bus.query.filter_by(registration_number=registration_number).first()
            if existing_reg and (bus is None or existing_reg.id != bus.id):
                flash("Registration Number Already Exists", "danger")
                return redirect(url_for("admin_buses"))

            if bus is None:
                bus = Bus(
                    bus_number=bus_number,
                    registration_number=registration_number,
                    capacity=capacity,
                    route_id=route_id,
                    is_active=False
                )
                db.session.add(bus)
                db.session.flush()
                logger.info("[ROUTE_ASSIGN] Created bus id=%s route_id=%s", bus.id, route_id)

            else:
                bus.registration_number = registration_number
                bus.capacity = capacity
                if route_id is not None:
                    bus.route_id = route_id
                    logger.info("[ROUTE_ASSIGN] Updated bus id=%s route_id=%s", bus.id, route_id)
                bus.is_active = False

            if assigned_driver_code_raw:
                driver_err = _assign_driver_code_to_bus(bus, assigned_driver_code_raw)
                if driver_err:
                    db.session.rollback()
                    flash(driver_err, "danger")
                    return redirect(url_for("admin_buses"))
            else:
                _assign_driver_code_to_bus(bus, "")

            try:
                _mark_route_operational(route_id)

                if route_id:
                    _complete_active_trips(bus.id)
                    _retire_pending_assignment_trips(bus.id)
                    _create_trip_for_bus(bus, route_id)
                    LIVE_GPS_DATA.pop(bus.id, None)
                    LIVE_GPS_BREADCRUMBS.pop(bus.id, None)
                    BUS_DELAY_DATA.pop(bus.id, None)

                db.session.commit()
                _invalidate_fleet_snapshot_cache()
                _live_fleet_snapshot()
                flash(f"Bus {bus_number} saved successfully.", "success")
            except ValueError as exc:
                db.session.rollback()
                flash(str(exc), "danger")
            except IntegrityError:
                db.session.rollback()
                if assigned_driver_code_raw and _driver_code_taken(_normalize_driver_code(assigned_driver_code_raw)):
                    flash("Driver ID Already Assigned To Another Bus", "danger")
                else:
                    flash("Registration Number Already Exists", "danger")

            return redirect(url_for("admin_buses"))

        buses = Bus.query.order_by(Bus.created_at.desc()).all()
        for b in buses:
            trip = _active_trip_for_bus(b) or _driver_dashboard_trip_for_bus(b)
            route_ref = b.route_id or (trip.route_id if trip else None)
            b.route = db.session.get(Route, route_ref) if route_ref else None
            if b.route:
                t = trip or _resolve_trip_for_route(b.route)
                stops_data = _route_points_for(b.route, t)
                names = [s["name"] for s in stops_data[1:-1]]
                if len(names) > 3:
                    b.route.intermediate_stops = ", ".join(names[:3]) + f", +{len(names) - 3} more"
                elif names:
                    b.route.intermediate_stops = ", ".join(names)
                else:
                    b.route.intermediate_stops = "None"

        all_routes = Route.query.order_by(Route.route_code.asc()).all()
        return render_template("bus_management.html", buses=buses, routes=all_routes, fleet_snapshot=[])

    @app.route("/admin/buses/<int:bus_id>/edit", methods=["GET", "POST"])
    @role_required("admin")
    def edit_bus(bus_id: int):
        bus = db.get_or_404(Bus, bus_id)
        trip = _active_trip_for_bus(bus)
        assigned_route = (
            db.session.get(Route, bus.route_id)
            if bus.route_id
            else (db.session.get(Route, trip.route_id) if trip else None)
        )

        if request.method == "POST":
            bus.bus_number = request.form.get("bus_number", bus.bus_number).strip().upper()
            bus.registration_number = request.form.get("registration_number", bus.registration_number).strip().upper()
            try:
                bus.capacity = int(request.form.get("capacity", bus.capacity))
            except (TypeError, ValueError):
                flash("Bus capacity must be a valid number.", "danger")
                return redirect(url_for("edit_bus", bus_id=bus.id))
            if bus.capacity <= 0:
                flash("Bus capacity must be greater than zero.", "danger")
                return redirect(url_for("edit_bus", bus_id=bus.id))
            assigned_driver_code_raw = (request.form.get("assigned_driver_code") or "").strip()

            existing_route_id_raw = (request.form.get("existing_route_id") or "").strip()
            route_code = (request.form.get("route_code") or "").strip().upper()
            route_name = (request.form.get("route_name") or "").strip()
            origin = (request.form.get("origin") or "").strip()
            destination = (request.form.get("destination") or "").strip()
            intermediates = (request.form.get("intermediate_stops") or "").strip()
            departure_time = (request.form.get("departure_time") or "").strip()

            if assigned_driver_code_raw:
                driver_err = _assign_driver_code_to_bus(bus, assigned_driver_code_raw)
                if driver_err:
                    flash(driver_err, "danger")
                    return redirect(url_for("edit_bus", bus_id=bus.id))
            else:
                _assign_driver_code_to_bus(bus, "")

            new_route_id = None
            manual_schedule_route = None

            if existing_route_id_raw:
                try:
                    selected_route_id = int(existing_route_id_raw)
                    selected_route = db.session.get(Route, selected_route_id)
                    if selected_route:
                        new_route_id = selected_route.id
                        logger.info("[ROUTE_ASSIGN] edit_bus bus=%s assigned existing route_id=%s", bus.id, new_route_id)
                except ValueError:
                    flash("Invalid route selection.", "danger")
                    return redirect(url_for("edit_bus", bus_id=bus.id))
            elif route_code and origin and destination:
                existing = Route.query.filter_by(route_code=route_code).first()
                if existing:
                    new_route_id = existing.id
                    manual_schedule_route = existing if (departure_time or intermediates) else None
                    if manual_schedule_route:
                        manual_schedule_route.distance_km = _auto_route_distance_km(manual_schedule_route, intermediates)
                    logger.info("[ROUTE_ASSIGN] edit_bus duplicate prevented, using route_id=%s", new_route_id)
                else:
                    route = Route(
                        route_code=route_code,
                        name=route_name or f"{origin} to {destination}",
                        origin=origin,
                        destination=destination,
                        distance_km=0.0,
                        departure_time=departure_time or None,
                        is_operational=True
                    )

                    db.session.add(route)
                    db.session.flush()
                    route.distance_km = _auto_route_distance_km(route, intermediates)
                    _apply_manual_route_schedule(route, intermediates, departure_time)
                    new_route_id = route.id
                    manual_schedule_route = route
                    logger.info("[ROUTE_ASSIGN] edit_bus bus=%s created route_id=%s", bus.id, new_route_id)

            if manual_schedule_route and not _route_has_gtfs_stop_times(manual_schedule_route.id):
                _apply_manual_route_schedule(manual_schedule_route, intermediates, departure_time)

            if new_route_id is not None:
                try:
                    if bus.route_id != new_route_id:
                        bus.route_id = new_route_id
                        bus.is_active = False
                        _complete_active_trips(bus.id)
                        _retire_pending_assignment_trips(bus.id)
                        _create_trip_for_bus(bus, new_route_id)
                        _mark_route_operational(new_route_id)
                        LIVE_GPS_DATA.pop(bus.id, None)
                        LIVE_GPS_BREADCRUMBS.pop(bus.id, None)
                        BUS_DELAY_DATA.pop(bus.id, None)
                        
                        db.session.add(Notification(
                            title="Route Assignment Updated",
                            type="admin",
                            priority="info",
                            target_role="admin",
                            message=f"Bus {bus.bus_number} assigned to a new route.",
                            related_bus_id=bus.id,
                            related_route_id=new_route_id
                        ))
                except ValueError as exc:
                    db.session.rollback()
                    flash(str(exc), "danger")
                    return redirect(url_for("edit_bus", bus_id=bus.id))

            existing_reg = Bus.query.filter_by(registration_number=bus.registration_number).first()
            if existing_reg and existing_reg.id != bus.id:
                flash("Registration Number Already Exists", "danger")
                return redirect(url_for("edit_bus", bus_id=bus.id))

            try:
                db.session.commit()
                _invalidate_fleet_snapshot_cache()
                _live_fleet_snapshot()
                flash(f"Bus {bus.bus_number} updated successfully.", "success")
            except ValueError as exc:
                db.session.rollback()
                flash(str(exc), "danger")
            except IntegrityError:
                db.session.rollback()
                if assigned_driver_code_raw and _driver_code_taken(_normalize_driver_code(assigned_driver_code_raw), exclude_bus_id=bus.id):
                    flash("Driver ID Already Assigned To Another Bus", "danger")
                else:
                    flash("Registration Number Already Exists", "danger")
            return redirect(url_for("admin_buses"))

        all_routes = Route.query.order_by(Route.route_code.asc()).all()
        intermediates_str = ""
        if assigned_route:
            stops = Stop.query.filter_by(route_id=assigned_route.id).order_by(Stop.stop_order.asc()).all()
            if len(stops) > 2:
                intermediates_str = ", ".join([s.stop_name for s in stops[1:-1]])
            elif trip:
                stops_data = _route_points_for(assigned_route, trip)
                if len(stops_data) > 2:
                    intermediates_str = ", ".join([s["name"] for s in stops_data[1:-1]])
        return render_template("bus_edit.html", bus=bus, assigned_route=assigned_route, routes=all_routes, intermediates_str=intermediates_str)

    @app.route("/admin/buses/delete/<int:bus_id>", methods=["POST"])
    @login_required
    @role_required("admin")
    def delete_bus(bus_id: int):
        bus = db.get_or_404(Bus, bus_id)
        bus_number = bus.bus_number

        try:
            Trip.query.filter_by(bus_id=bus.id).delete(synchronize_session=False)
            Complaint.query.filter_by(bus_id=bus.id).delete(synchronize_session=False)
            LostAndFound.query.filter_by(bus_id=bus.id).delete(synchronize_session=False)
            SOSAlert.query.filter_by(bus_id=bus.id).delete(synchronize_session=False)
            BusOccupancy.query.filter_by(bus_id=bus.id).delete(synchronize_session=False)


            db.session.delete(bus)

            db.session.commit()
            _invalidate_fleet_snapshot_cache()
            _live_fleet_snapshot()

            flash(f"Bus '{bus_number}' deleted successfully.", "success")

            return jsonify({
                "success": True,
                "message": f"Bus '{bus_number}' deleted successfully."
            }), 200

        except Exception as exc:
            db.session.rollback()

            logger.exception(
               "[ADMIN_BUS_DELETE] Failed to delete bus %s",
                bus_id
            )

            return jsonify({
                "success": False,
                "message": str(exc)
            }), 500

    @app.route("/admin/routes", methods=["GET", "POST"])
    @role_required("admin")
    def admin_routes():
        if request.method == "POST":
            route_code = (request.form.get("route_code") or "").strip().upper()
            name = (request.form.get("name") or "").strip()
            origin = (request.form.get("origin") or "").strip()
            destination = (request.form.get("destination") or "").strip()
            departure_time = (request.form.get("departure_time") or "").strip()
            intermediates = (request.form.get("intermediate_stops") or "").strip()

            if not all([route_code, name, origin, destination]):
                flash("All route fields are required.", "danger")
                return redirect(url_for("admin_routes"))

            route = Route(
                route_code=route_code,
                name=name,
                origin=origin,
                destination=destination,
                distance_km=0.0,
                departure_time=departure_time or None,
                is_operational=True
            )
            db.session.add(route)
            db.session.flush()
            route.distance_km = _auto_route_distance_km(route, intermediates)
            _apply_manual_route_schedule(route, intermediates, departure_time)
            try:
                db.session.commit()
                _invalidate_fleet_snapshot_cache()
                _live_fleet_snapshot()
                flash(f"Route {route_code} created. Assign GTFS geometry via import or link to an imported route.", "success")
            except IntegrityError:
                db.session.rollback()
                flash("Route code already exists.", "danger")
            return redirect(url_for("admin_routes"))

        routes = Route.query.order_by(Route.route_code.asc()).all()
        return render_template("route_management.html", routes=routes)

    @app.route("/admin/routes/<int:route_id>/edit", methods=["GET", "POST"])
    @role_required("admin")
    def edit_route(route_id: int):
        route = db.get_or_404(Route, route_id)
        if request.method == "POST":
            route.route_code = request.form.get("route_code", "").strip().upper()
            route.name = request.form.get("name", "").strip()
            route.origin = request.form.get("origin", "").strip()
            route.destination = request.form.get("destination", "").strip()
            departure_time = (request.form.get("departure_time") or "").strip()
            intermediates = (request.form.get("intermediate_stops") or "").strip()
            route.distance_km = _auto_route_distance_km(route, intermediates)
            if departure_time:
                route.departure_time = departure_time
            _apply_manual_route_schedule(route, intermediates, departure_time)
            try:
                db.session.commit()
                _invalidate_fleet_snapshot_cache()
                _live_fleet_snapshot()
                flash(f"Route {route.route_code} updated successfully.", "success")
            except IntegrityError:
                db.session.rollback()
                flash("Route code already exists.", "danger")
                return redirect(url_for("edit_route", route_id=route.id))
            return redirect(url_for("admin_buses"))
        return render_template("route_edit.html", route=route)

    @app.route("/dashboard/driver", methods=["GET", "POST"])
    @role_required("driver")
    def driver_dashboard():
        assigned_bus = _get_session_driver_bus()
        driver_code = session.get("driver_code") or (assigned_bus.assigned_driver_code if assigned_bus else "")
        assigned_trip = None
        assigned_route = None
        driver_route_points = []
        driver_initial_context = {}
        driver_trip_state = "OFFLINE"

        if assigned_bus:
            assigned_trip = _driver_dashboard_trip_for_bus(assigned_bus)

            if assigned_trip:
                assigned_route = db.session.get(Route, assigned_trip.route_id)
            elif assigned_bus.route_id:
                assigned_route = db.session.get(Route, assigned_bus.route_id)

            driver_trip_state = _trip_state_label(assigned_trip, assigned_bus)

            if assigned_route and assigned_trip:
                driver_route_points = _route_points_for_assigned_trip(assigned_route, assigned_trip)
                driver_schedule = _route_schedule_for_assigned_trip(assigned_route, assigned_trip)
                route_path = _route_geometry_path_for_assigned_trip(assigned_trip)
                route_distance = round(_path_segment_distance(route_path), 2) if len(route_path) >= 2 else 0.0
            elif assigned_route:
                driver_route_points = _route_points_for(assigned_route, None)
                driver_schedule = _route_schedule_for(assigned_route, None)
                route_distance = round(assigned_route.distance_km, 2) if assigned_route else 0.0
            else:
                driver_schedule = {}
                route_distance = 0.0

            direction_label = "Return" if assigned_trip and getattr(assigned_trip, "direction_id", 0) == 1 else "Forward"
            driver_initial_context = {
                "busNumber": assigned_bus.bus_number,
                "driverCode": driver_code or assigned_bus.assigned_driver_code or "--",
                "routeName": assigned_route.name if assigned_route else "--",
                "routeCode": assigned_route.route_code if assigned_route else "--",
                "tripId": assigned_trip.id if assigned_trip else None,
                "tripStatus": driver_trip_state,
                "direction": direction_label,
                "busStatus": "OFFLINE",
                "gpsStatus": "OFFLINE",
                # For return trips, endpoints are already reversed in driver_route_points
                "sourceStop": (
                    driver_route_points[0]["name"] if driver_route_points
                    else (assigned_route.origin if assigned_route else "--")
                ),
                "destinationStop": (
                    driver_route_points[-1]["name"] if driver_route_points
                    else (assigned_route.destination if assigned_route else "--")
                ),
                "currentStop": driver_route_points[0]["name"] if driver_route_points else "--",
                "nextStop": driver_route_points[1]["name"] if len(driver_route_points) > 1 else "--",
                "totalStops": len(driver_route_points),
                "scheduledDeparture": driver_schedule.get("departure_time", "--"),
                "scheduledArrival": driver_schedule.get("arrival_time", "--"),
                "scheduledEta": driver_schedule.get("duration", "--"),
                "scheduledEtaMinutes": driver_schedule.get("duration_minutes"),
                "routeDistance": route_distance,
            }

        if request.method == "POST":
            action = request.form.get("action")
            if not assigned_trip: return redirect(url_for("driver_dashboard"))

            active_trip = _active_trip_for_bus(assigned_bus)
            try:
                if action == "start":
                    if active_trip:
                        flash("Trip is already active and running.", "danger")
                    else:
                        _start_driver_trip(assigned_bus, requested_return=(assigned_trip.status == "return_ready"))
                        db.session.commit()
                        _invalidate_fleet_snapshot_cache()
                        _live_fleet_snapshot()
                elif action == "end":
                    if not active_trip:
                        flash("No active trip to end.", "danger")
                    else:
                        _end_driver_trip(assigned_bus)
                        db.session.commit()
                        _invalidate_fleet_snapshot_cache()
                        _live_fleet_snapshot()
            except Exception as exc:
                db.session.rollback()
                flash(str(exc), "danger")

            return redirect(url_for("driver_dashboard"))

        return render_template("driver_dashboard.html", assigned_bus=assigned_bus, assigned_route=assigned_route,
                               assigned_trip=assigned_trip, trip_status_options=sorted(TRIP_STATUS_OPTIONS),
                               driver_id=driver_code or "--",
                               driver_trip_state=driver_trip_state,
                               has_assigned_bus=assigned_bus is not None, ap_center=_get_map_default_center(),
                               driver_route_points=driver_route_points,
                               driver_initial_context=driver_initial_context)

    @app.route("/api/driver/start-trip", methods=["POST"])
    @login_required
    @role_required("driver")
    def api_driver_start_trip():
        assigned_bus = _get_session_driver_bus()
        if not assigned_bus:
            return jsonify({"success": False, "error": "No assigned bus"}), 404
        data = request.get_json(silent=True) or {}
        requested_return = bool(data.get("return_trip"))
        try:
            start_lat = float(data.get("lat")) if data.get("lat") is not None else None
            start_lon = float(data.get("lon")) if data.get("lon") is not None else None
        except (TypeError, ValueError):
            start_lat, start_lon = None, None

        # Duplicate / Conflict checks
        active_trip = _active_trip_for_bus(assigned_bus)
        if active_trip:
            return jsonify({"success": False, "error": "Trip is already active and running"}), 409

        if requested_return:
            forward_completed = Trip.query.filter_by(
                bus_id=assigned_bus.id,
                route_id=assigned_bus.route_id,
                direction_id=0,
                status="completed"
            ).first()
            if not forward_completed:
                return jsonify({"success": False, "error": "Cannot start return trip: forward trip is not completed yet"}), 400

            return_trip = Trip.query.filter(
                Trip.bus_id == assigned_bus.id,
                Trip.route_id == assigned_bus.route_id,
                Trip.status == "return_ready"
            ).order_by(Trip.id.desc()).first()
            if not return_trip:
                return jsonify({"success": False, "error": "No return_ready trip available to start"}), 400
        else:
            forward_trip = Trip.query.filter(
                Trip.bus_id == assigned_bus.id,
                Trip.route_id == assigned_bus.route_id,
                Trip.direction_id == 0
            ).order_by(Trip.id.desc()).first()
            if forward_trip and forward_trip.status == "completed":
                return jsonify({"success": False, "error": "Forward trip has already been completed"}), 409

        try:
            trip = _start_driver_trip(
                assigned_bus,
                requested_return=requested_return,
                start_lat=start_lat,
                start_lon=start_lon
            )
            
            trip_type = "return trip" if requested_return else "forward trip"
            db.session.add(Notification(
                title="Trip Started",
                type="system",
                priority="info",
                target_role="admin",
                message=f"Bus {assigned_bus.bus_number} has started its {trip_type}.",
                related_bus_id=assigned_bus.id,
                trip_id=trip.id
            ))
            
            db.session.commit()
            BUS_COMPLETED_TRIPS.pop(assigned_bus.id, None)
            _invalidate_fleet_snapshot_cache()
            _live_fleet_snapshot()
            return jsonify({
                "success": True,
                "trip_id": trip.id,
                "trip_status": _trip_state_label(trip, assigned_bus),
                "bus_status": "ACTIVE",
                "gps_enabled": True,
            }), 200
        except Exception as exc:
            db.session.rollback()
            logger.exception("[DRIVER_TRIP] start failed: %s", exc)
            return jsonify({"success": False, "error": str(exc)}), 400

    @app.route("/api/driver/end-trip", methods=["POST"])
    @login_required
    @role_required("driver")
    def api_driver_end_trip():
        assigned_bus = _get_session_driver_bus()
        if not assigned_bus:
            return jsonify({"success": False, "error": "No assigned bus"}), 404

        active_trip = _active_trip_for_bus(assigned_bus)
        if not active_trip:
            last_trip = Trip.query.filter(
                Trip.bus_id == assigned_bus.id,
                Trip.route_id == assigned_bus.route_id
            ).order_by(Trip.id.desc()).first()
            if last_trip and last_trip.status in ("completed", "return_completed"):
                return jsonify({"success": False, "error": "Trip is already completed"}), 409
            return jsonify({"success": False, "error": "No active trip to end"}), 400

        try:
            completed_trip, return_trip = _end_driver_trip(assigned_bus)
            
            db.session.add(Notification(
                title="Trip Ended",
                type="system",
                priority="info",
                target_role="admin",
                message=f"Bus {assigned_bus.bus_number} has ended its trip.",
                related_bus_id=assigned_bus.id,
                trip_id=completed_trip.id
            ))
            
            db.session.commit()
            BUS_COMPLETED_TRIPS[assigned_bus.id] = time.time()
            _invalidate_fleet_snapshot_cache()
            _live_fleet_snapshot()
            next_state = _trip_state_label(return_trip, assigned_bus) if return_trip else "OFFLINE"
            return jsonify({
                "success": True,
                "completed_trip_id": completed_trip.id,
                "return_trip_id": return_trip.id if return_trip else None,
                "trip_status": "COMPLETED",
                "next_trip_status": next_state,
                "bus_status": "OFFLINE",
                "gps_enabled": False,
            }), 200
        except Exception as exc:
            db.session.rollback()
            logger.exception("[DRIVER_TRIP] end failed: %s", exc)
            return jsonify({"success": False, "error": str(exc)}), 400

    @app.route("/api/driver/update-occupancy", methods=["POST"])
    @login_required
    @role_required("driver")
    def api_driver_update_occupancy():
        assigned_bus = _get_session_driver_bus()
        if not assigned_bus:
            return jsonify({"success": False, "error": "No assigned bus"}), 404
        trip = _active_trip_for_bus(assigned_bus)
        if not trip:
            return jsonify({"success": False, "error": "Start a trip before updating occupancy."}), 400

        data = request.get_json(silent=True) or {}
        level = (data.get("level") or "").strip().lower()
        level_percentages = {"low": 25, "medium": 55, "high": 85}
        if level not in level_percentages:
            return jsonify({"success": False, "error": "Invalid occupancy level."}), 400

        percentage = level_percentages[level]
        occupied_seats = max(0, min(assigned_bus.capacity, int(round(assigned_bus.capacity * (percentage / 100)))))
        occ = BusOccupancy(
            bus_id=assigned_bus.id,
            trip_id=trip.id,
            total_seats=assigned_bus.capacity,
            occupied_seats=occupied_seats,
            occupancy_level=level,
            occupancy_percentage=percentage,
        )
        db.session.add(occ)
        try:
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            logger.exception("[DRIVER_OCCUPANCY] update failed: %s", exc)
            return jsonify({"success": False, "error": "Occupancy could not be updated."}), 500
        return jsonify({"success": True, "occupancy": occ.to_dict()}), 200

    @app.route("/api/driver/location", methods=["POST"])
    @login_required
    @role_required("driver")
    def api_driver_location():
        data = request.get_json(silent=True) or {}

        try:
            lat = float(data.get("lat"))
            lng = float(data.get("lng"))
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid coordinates"}), 400

        if not (-90 <= lat <= 90):
            return jsonify({"error": "Latitude out of range"}), 400

        if not (-180 <= lng <= 180):
            return jsonify({"error": "Longitude out of range"}), 400

        assigned_bus = _get_session_driver_bus()

        if not assigned_bus:
            return jsonify({"error": "No assigned bus"}), 404

        active_trip = _active_trip_for_bus(assigned_bus)
        if not active_trip or not assigned_bus.is_active:
            if not assigned_bus.is_active:
                LIVE_GPS_DATA.pop(assigned_bus.id, None)
                LIVE_GPS_BREADCRUMBS.pop(assigned_bus.id, None)
            _mark_driver_runtime_gps_state(assigned_bus.id, "OFF")
            return jsonify({"error": "Trip is not active or ready"}), 409

        now_seconds = time.time()
        previous = LIVE_GPS_DATA.get(assigned_bus.id)
        same_trip = previous and previous.get("trip_id") == active_trip.id
        covered_km = float(previous.get("distance_covered_km") or 0.0) if same_trip else 0.0
        completed_stops = int(previous.get("completed_stops") or 0) if same_trip else 0
        elapsed_seconds = None
        gps_delta_km = 0.0
        derived_speed_kmh = None

        if same_trip:
            try:
                prev_lat = float(previous.get("lat"))
                prev_lon = float(previous.get("lon"))
                prev_ts = float(previous.get("timestamp") or now_seconds)
                elapsed_seconds = max(0.0, now_seconds - prev_ts)
                gps_delta_km = _haversine_km(prev_lat, prev_lon, lat, lng)
                max_reasonable_delta = max(0.25, (elapsed_seconds / 3600.0) * 140.0)
                if elapsed_seconds > 0 and gps_delta_km <= max_reasonable_delta:
                    covered_km += gps_delta_km
                    derived_speed_kmh = (gps_delta_km / elapsed_seconds) * 3600.0
                    prev_speed = float(previous.get("speed") or 0.0)
                    if prev_speed > 0:
                        derived_speed_kmh = (0.3 * derived_speed_kmh) + (0.7 * prev_speed)
            except (TypeError, ValueError):
                pass

        payload_speed = None
        for key in ("speed_kmh", "speed"):
            try:
                raw_speed = data.get(key)
                if raw_speed is not None:
                    payload_speed = float(raw_speed)
                    break
            except (TypeError, ValueError):
                payload_speed = None
        if payload_speed is None:
            try:
                raw_speed_mps = data.get("speed_mps")
                if raw_speed_mps is not None:
                    payload_speed = float(raw_speed_mps) * 3.6
            except (TypeError, ValueError):
                payload_speed = None
        speed_kmh = payload_speed if payload_speed is not None and payload_speed >= 0 else derived_speed_kmh
        if speed_kmh is not None:
            speed_kmh = max(0.0, min(140.0, float(speed_kmh)))

        route = db.session.get(Route, active_trip.route_id)
        route_path = _route_geometry_path_for_assigned_trip(active_trip)
        current_path_index = _nearest_route_index(lat, lng, route_path) if route_path else 0

        route_points = _route_points_for_assigned_trip(route, active_trip) if route else []
        
        # Monotonic max_path_index calculation
        max_path_index = int(previous.get("max_path_index") or 0) if same_trip else 0
        reversal_threshold = max(5, int(len(route_path) * 0.10)) if route_path else 100
        if current_path_index > max_path_index:
            max_path_index = current_path_index
        elif max_path_index - current_path_index > reversal_threshold:
            max_path_index = current_path_index

        # Compute nearest stop index
        nearest_stop_idx = 0
        min_dist = float('inf')
        if route_points:
            for idx, pt in enumerate(route_points):
                dist = _haversine_km(lat, lng, pt["lat"], pt["lng"])
                if dist < min_dist:
                    min_dist = dist
                    nearest_stop_idx = idx

        # Monotonic constraint
        prev_stop_idx = int(previous.get("current_stop_index") or 0) if same_trip else 0
        current_stop_index = max(prev_stop_idx, nearest_stop_idx) if same_trip else nearest_stop_idx
        completed_stops = current_stop_index

        # Configurable stop radius check
        stop_radius = current_app.config.get("STOP_RADIUS_KM", 0.03)
        at_stop = False
        if route_points and min_dist <= stop_radius:
            at_stop = True

        bearing = None
        for key in ("bearing", "heading", "course"):
            try:
                raw_bearing = data.get(key)
                if raw_bearing is not None:
                    bearing = float(raw_bearing)
                    break
            except (TypeError, ValueError):
                bearing = None

        new_gps_data = {
            "lat": lat,
            "lon": lng,
            "timestamp": now_seconds,
            "trip_id": active_trip.id,
            "route_id": active_trip.route_id,
            "speed": speed_kmh,
            "bearing": bearing,
            "distance_covered_km": max(0.0, covered_km),
            "gps_delta_km": gps_delta_km,
            "elapsed_seconds": elapsed_seconds,
            "current_stop_index": current_stop_index,
            "completed_stops": completed_stops,
            "max_path_index": max_path_index,
            "at_stop": at_stop,
        }
        if previous:
            for k, v in previous.items():
                if k not in new_gps_data:
                    new_gps_data[k] = v
        LIVE_GPS_DATA[assigned_bus.id] = new_gps_data
        breadcrumbs = LIVE_GPS_BREADCRUMBS.setdefault(assigned_bus.id, [])
        breadcrumbs.append({
            "lat": lat,
            "lng": lng,
            "timestamp": now_seconds,
            "speed": speed_kmh,
        })
        if len(breadcrumbs) > 1000:
            LIVE_GPS_BREADCRUMBS[assigned_bus.id] = breadcrumbs[-1000:]

        runtime = DRIVER_RUNTIME_SESSIONS.setdefault(
            assigned_bus.id,
            _driver_runtime_session_payload(assigned_bus, active_trip, "ACTIVE"),
        )
        total_dist = _path_segment_distance(route_path)
        travelled_dist = _path_segment_distance(route_path[:max_path_index + 1]) if route_path else 0.0
        trip_progress = (
            round((travelled_dist / total_dist) * 100.0, 3)
            if total_dist > 0.0 else 0.0
        )
        if runtime.get("gps_state") == "OFF":
            db.session.add(Notification(
                title="GPS Online",
                type="system",
                priority="success",
                target_role="admin",
                message=f"Bus {assigned_bus.bus_number} GPS has come online.",
                related_bus_id=assigned_bus.id,
                trip_id=active_trip.id
            ))
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()

        runtime.update({
            "driver_location": {"lat": lat, "lng": lng},
            "bus_location": {"lat": lat, "lng": lng},
            "trip_progress": trip_progress,
            "distance_travelled_km": round(max(0.0, covered_km), 3),
            "speed": speed_kmh,
            "heading": bearing,
            "last_update_timestamp": datetime.fromtimestamp(now_seconds, UTC).isoformat(),
            "current_stop": route_points[current_stop_index]["name"] if route_points else "--",
            "next_stop": route_points[current_stop_index + 1]["name"] if (route_points and current_stop_index + 1 < len(route_points)) else "--",
            "delay_minutes": _current_bus_delay_minutes(assigned_bus.id),
            "gps_state": "ACTIVE",
            "driver_state": "ON_DUTY",
            "bus_state": "ACTIVE",
        })

        _invalidate_fleet_snapshot_cache()
        _live_fleet_snapshot()

        return jsonify({"success": True})

    @app.route("/api/driver/location/off", methods=["POST"])
    @login_required
    @role_required("driver")
    def api_driver_location_off():
        assigned_bus = _get_session_driver_bus()
        if not assigned_bus:
            return jsonify({"success": False, "error": "No assigned bus"}), 404
        active_trip = _active_trip_for_bus(assigned_bus)
        if active_trip and assigned_bus.is_active:
            _mark_driver_runtime_gps_state(assigned_bus.id, "OFF")
            db.session.add(Notification(
                title="GPS Offline",
                type="system",
                priority="warning",
                target_role="admin",
                message=f"Bus {assigned_bus.bus_number} GPS has gone offline.",
                related_bus_id=assigned_bus.id,
                trip_id=active_trip.id
            ))
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
            _invalidate_fleet_snapshot_cache()
            return jsonify({
                "success": True,
                "bus_id": assigned_bus.id,
                "gps_enabled": False,
                "last_known_gps_preserved": True,
            }), 200
        LIVE_GPS_DATA.pop(assigned_bus.id, None)
        LIVE_GPS_BREADCRUMBS.pop(assigned_bus.id, None)
        _mark_driver_runtime_gps_state(assigned_bus.id, "OFF")
        return jsonify({
            "success": True,
            "bus_id": assigned_bus.id,
            "gps_enabled": False,
        }), 200

    @app.route("/api/buses/route-info", methods=["GET"])
    @login_required
    def get_bus_route_info():
        bus_number = request.args.get("bus_number", "").strip().upper()
        if not bus_number:
            return jsonify({"found": False})
        bus = Bus.query.filter(or_(Bus.bus_number == bus_number, Bus.registration_number == bus_number)).first()
        if bus and bus.route:
            return jsonify({
                "found": True,
                "bus_number": bus.bus_number,
                "route_id": bus.route_id,
                "route_name": bus.route.name
            })
        return jsonify({"found": False})


    @app.route("/api/driver/report-delay", methods=["POST"])
    @app.route("/api/buses/delay", methods=["POST"])
    @login_required
    @role_required("driver")
    def report_bus_delay_endpoint():
        data = request.get_json(silent=True) or request.form.to_dict()
        try:
            minutes = int(data.get("duration", 20))
        except ValueError:
            minutes = 20
        minutes = max(0, min(120, minutes))
        reason = _normalize_delay_reason(data.get("reason"))

        assigned_bus = _get_session_driver_bus()
        if not assigned_bus: return jsonify({"error": "No assigned bus profile found for active session."}), 404

        trip = _active_trip_for_bus(assigned_bus)
        if not trip or not assigned_bus.is_active:
            return jsonify({"error": "Start a trip before reporting a delay."}), 400

        route_obj = db.session.get(Route, trip.route_id)
        if not route_obj:
            return jsonify({"error": "Assigned route not found for delay report."}), 404

        route_name = route_obj.name if route_obj else "Assigned Route"
        active_trip = trip

        gps = _fresh_gps_packet(assigned_bus.id, time.time())
        route_points = _route_points_for_assigned_trip(route_obj, active_trip) if gps else []
        current_index = _nearest_route_index(gps["lat"], gps["lon"], route_points) if route_points else 0
        next_index = min(current_index + 1, len(route_points) - 1) if route_points else 0
        direction = "backward" if getattr(active_trip, "direction_id", 0) == 1 else "forward"
        _record_driver_reported_delay(
            assigned_bus.id,
            route_obj.id,
            active_trip,
            direction,
            current_index,
            reason,
            minutes,
        )
        schedule_after = _bus_schedule_payload(
            route_obj,
            active_trip,
            assigned_bus.id,
            current_index,
            next_index,
            route_points,
            direction,
            0.0,
            assigned_trip_only=True,
        )
        updated_eta = None
        updated_eta = updated_eta or minutes
        total_delay = schedule_after.get("current_delay_minutes") or minutes
        expected_arrival = schedule_after.get("updated_arrival_time") or schedule_after.get("arrival_time")
        expected_arrival = expected_arrival or "--"

        if total_delay == 0:
            unified_message = f"{assigned_bus.bus_number} - {route_name}: bus is back on schedule."
        else:
            unified_message = (
                f"{assigned_bus.bus_number} - {route_name} delay +{minutes} min due to {reason}. "
                f"Current delay: {total_delay} min. Updated ETA: {updated_eta} min. "
                f"Expected arrival: {expected_arrival}."
            )
        for admin in User.query.filter_by(role="admin").all():
            db.session.add(Notification(
                recipient_id=admin.id,
                trip_id=getattr(trip, "id", None) if trip else None,
                message=f"[DRIVER ALERT] {unified_message}",
            ))
        db.session.add(Notification(
            recipient_id=current_user.id,
            trip_id=getattr(trip, "id", None) if trip else None,
            message=f"[DELAY] {unified_message}",
        ))

        delay_bus_data = {
            "bus_id": assigned_bus.id,
            "bus_number": assigned_bus.bus_number,
            "route_id": route_obj.id,
            "route_name": route_name,
            "updated_eta_minutes": updated_eta,
            **schedule_after,
        }
        passenger_notifications = _queue_meaningful_delay_notifications(
            delay_bus_data,
            route_obj,
            active_trip,
            respect_cooldown=False,
        )

        try:
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            logger.exception("[DRIVER_DELAY] report failed: %s", exc)
            return jsonify({"success": False, "error": "Delay report could not be saved."}), 500
        return jsonify({
            "success": True,
            "message": "Delay notifications dispatched completely.",
            "current_delay_minutes": total_delay,
            "delay_reason": reason,
            "updated_eta_minutes": updated_eta,
            "expected_arrival": expected_arrival,
            "passenger_notifications": passenger_notifications,
        }), 200

    @app.route("/dashboard/passenger")
    @login_required
    def passenger_dashboard(): return render_template("passenger_dashboard.html")

    @app.route("/tracking/<path:bus_id>")
    @login_required
    def tracking_page(bus_id):
        source = (request.args.get("source") or "").strip()
        if current_user.role == "admin":
            back_url = url_for("admin_tracking_search")
        elif source == "search":
            back_url = url_for("passenger_dashboard") + "#search"
        elif source == "live_fleet":
            back_url = url_for("passenger_dashboard") + "#live-fleet"
        elif source == "live_tracking":
            back_url = url_for("passenger_dashboard") + "#live-tracking"
        elif source == "routes":
            back_url = url_for("passenger_dashboard") + "#routes"
        else:
            back_url = url_for("passenger_dashboard")
        return render_template("tracking.html", bus_identifier=bus_id, back_url=back_url)

    @app.route("/api/tracking/<bus_number>", methods=["GET"])
    @login_required
    def api_tracking_single_bus(bus_number):
        def norm(val):
            if not val:
                return ""
            return re.sub(r'[^a-zA-Z0-9]', '', str(val)).lower()

        norm_target = norm(bus_number)
        
        # Look up the bus in the database
        db_bus = Bus.query.filter(
            (func.lower(Bus.bus_number) == bus_number.lower()) |
            (func.lower(Bus.registration_number) == bus_number.lower()) |
            (Bus.id == bus_number)
        ).first()

        if not db_bus:
            all_buses = Bus.query.all()
            for b in all_buses:
                if (norm(b.id) == norm_target or 
                    norm(b.bus_number) == norm_target or 
                    norm(b.registration_number) == norm_target):
                    db_bus = b
                    break

        if not db_bus:
            return jsonify({"error": f"Bus {bus_number} not found"}), 404

        # Search active trips first
        trip = _active_trip_for_bus(db_bus)
        if trip:
            route = db.session.get(Route, trip.route_id)
            real_gps = _fresh_gps_packet(db_bus.id, time.time())
            if not real_gps:
                real_gps = LIVE_GPS_DATA.get(db_bus.id)
            snapshot = _real_gps_bus_snapshot(db_bus, trip, route, real_gps)
        else:
            # If inactive, look up the appropriate waiting or completed snapshot
            trip = _driver_dashboard_trip_for_bus(db_bus)
            route = db.session.get(Route, trip.route_id) if trip else None
            if db_bus.route_id and not route:
                route = db.session.get(Route, db_bus.route_id)

            if trip and route:
                if trip.status in ("completed", "return_completed"):
                    snapshot = _completed_trip_snapshot(db_bus, trip, route)
                else:
                    snapshot = _planned_assignment_snapshot(db_bus, trip, route)
            elif route:
                snapshot = _planned_assignment_snapshot(db_bus, None, route)
            else:
                snapshot = {
                    "bus_id": db_bus.id,
                    "bus_number": db_bus.bus_number,
                    "registration_number": db_bus.registration_number,
                    "tracking_available": False,
                    "gps_status": "Offline",
                    "trip_status": "OFFLINE",
                    "status": "Offline",
                    "current_lat": None,
                    "current_lon": None,
                }
                snapshot = _enrich_snapshot_with_defaults(snapshot, db_bus)

        return jsonify(snapshot), 200


    @app.route("/api/tracking/completed/<bus_identifier>", methods=["GET"])
    @login_required
    def api_tracking_completed(bus_identifier):
        bus = Bus.query.filter(
            (Bus.bus_number == bus_identifier) | (Bus.id == str(bus_identifier))
        ).first()
        if not bus:
            return jsonify({"error": "Bus not found"}), 404

        recent_cutoff = datetime.now(UTC) - timedelta(hours=1)
        last_trip = Trip.query.filter(
            Trip.bus_id == bus.id,
            Trip.status == "completed",
            Trip.end_time >= recent_cutoff
        ).order_by(Trip.end_time.desc()).first()

        if not last_trip:
            return jsonify({"error": "No recent completed trip found"}), 404

        route = db.session.get(Route, last_trip.route_id)
        if not route:
            return jsonify({"error": "Route not found"}), 404

        try:
            snapshot = _completed_trip_snapshot(bus, last_trip, route)
            return jsonify({"bus": snapshot}), 200
        except Exception as exc:
            logger.exception("[TRACKING] completed trip snapshot failed for bus %s: %s", bus.bus_number, exc)
            return jsonify({"error": "Internal server error"}), 500

    @app.route("/api/tracking/session", methods=["POST"])
    @login_required
    def api_tracking_session():
        data = request.get_json(silent=True) or request.form.to_dict()
        try:
            bus_id = int(data.get("bus_id")) if data.get("bus_id") is not None else None
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": "Valid bus_id is required"}), 400
        if bus_id is None or not db.session.get(Bus, bus_id):
            return jsonify({"success": False, "error": "Bus not found"}), 404

        try:
            route_id = int(data.get("route_id")) if data.get("route_id") not in (None, "") else None
            trip_id = int(data.get("trip_id")) if data.get("trip_id") not in (None, "") else None
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": "Invalid route or trip identifier"}), 400

        _record_passenger_tracking_session(current_user.id, bus_id, route_id, trip_id)
        return jsonify({"success": True}), 200

    @app.route("/notifications", methods=["GET", "POST"])
    @login_required
    def notifications_center():
        if request.method == "POST":
            wants_json = _request_wants_json()
            if current_user.role != "admin":
                if wants_json:
                    return jsonify({"success": False, "message": "Only administrators can send announcements."}), 403
                return redirect(url_for("notifications_center"))
            title = (request.form.get("title") or "System Alert").strip()
            message = (request.form.get("message") or "").strip()
            target = (request.form.get("target") or "all").strip()

            if not message:
                if wants_json:
                    return jsonify({"success": False, "message": "Announcement message is required."}), 400
                return redirect(url_for("notifications_center"))
            full_msg = f"[{title}] {message}"
            recipients_query = User.query
            if target == "drivers":
                recipients_query = recipients_query.filter_by(role="driver")
            elif target == "passengers":
                recipients_query = recipients_query.filter_by(role="passenger")
            elif target != "all":
                try:
                    recipients_query = recipients_query.filter_by(id=int(target))
                except ValueError:
                    if wants_json:
                        return jsonify({"success": False, "message": "Invalid notification target."}), 400
                    flash("Invalid notification target.", "danger")
                    return redirect(url_for("notifications_center"))

            recipient_ids = {u.id for u in recipients_query.all() if u}
            reference = f"ANN-{secrets.randbelow(100000):05d}"
            try:
                for u_id in recipient_ids:
                    db.session.add(Notification(recipient_id=u_id, message=full_msg))
                db.session.commit()
            except Exception as exc:
                db.session.rollback()
                logger.exception("[ANNOUNCEMENT] Broadcast failed: %s", exc)
                if wants_json:
                    return jsonify({
                        "success": False,
                        "message": "Announcement could not be delivered right now.",
                    }), 500
                flash("Announcement could not be delivered right now.", "danger")
                return redirect(url_for("notifications_center"))
            if wants_json:
                return jsonify({
                    "success": True,
                    "message": "Your announcement has been delivered successfully.",
                    "reference": reference,
                    "recipient_count": len(recipient_ids),
                }), 200
            flash("Announcement sent successfully.", "success")
            return redirect(url_for("notifications_center"))

        notifications = (
            Notification.query
            .filter_by(recipient_id=current_user.id)
            .order_by(Notification.created_at.desc())
            .limit(100)
            .all()
        )
        notifications = [
            n for n in notifications
            if _notification_category_for_role(current_user.role, n.message)
        ]
        users = User.query.order_by(User.full_name.asc()).all() if current_user.role == "admin" else []
        return render_template("notifications.html", notifications=notifications, users=users)

    @app.route("/api/alerts/subscribe", methods=["POST"])
    @login_required
    @role_required("passenger")
    def api_alerts_subscribe():
        data = request.get_json(silent=True) or {}

        try:
            stop_id = int(data.get("stop_id"))
        except (TypeError, ValueError):
            return jsonify({"error": "Valid stop_id is required"}), 400

        stop = db.session.get(Stop, stop_id)
        if not stop:
            return jsonify({"error": "Stop not found"}), 404

        sub = Subscription.query.filter_by(
            user_id=current_user.id,
            stop_id=stop_id
        ).first()

        if sub:
            sub.active = not sub.active
        else:
            sub = Subscription(
                user_id=current_user.id,
                stop_id=stop_id,
                active=True
            )
            db.session.add(sub)

        bus_id_raw = data.get("bus_id")
        if bus_id_raw not in (None, ""):
            try:
                bus_id = int(bus_id_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "Invalid bus_id"}), 400

            if bus_id <= 0:
                return jsonify({"error": "Invalid bus_id"}), 400

            bus = db.session.get(Bus, bus_id)
            if not bus:
                return jsonify({"error": "Bus not found"}), 404

            try:
                route_id = int(data.get("route_id")) if data.get("route_id") not in (None, "") else None
            except (TypeError, ValueError):
                route_id = None

            try:
                trip_id = int(data.get("trip_id")) if data.get("trip_id") not in (None, "") else None
            except (TypeError, ValueError):
                trip_id = None

            _record_passenger_tracking_session(
                current_user.id,
                bus_id,
                route_id,
                trip_id
            )

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return jsonify({"error": "Subscription could not be saved"}), 409
        except Exception as exc:
            db.session.rollback()
            logger.exception("[ALERT_SUBSCRIBE] update failed: %s", exc)
            return jsonify({"error": "Subscription could not be updated"}), 500

        return jsonify({"success": True, "active": sub.active, "stop_id": stop.id}), 200

    @app.route("/api/notifications/<int:notif_id>/read", methods=["POST"])
    @login_required
    def api_notifications_read(notif_id):
        notif = db.get_or_404(Notification, notif_id)
        if notif.recipient_id != current_user.id and notif.target_role != current_user.role:
            return jsonify({"error": "Unauthorized"}), 403
        notif.is_read = True
        db.session.commit()
        return jsonify({"success": True}), 200

    @app.route("/complaints", methods=["GET", "POST"])
    @login_required
    def complaints_page(): return render_template("complaints.html")

    @app.route("/api/complaints/<int:complaint_id>/reply", methods=["POST"])
    @role_required("admin")
    def add_complaint_reply_api(complaint_id):
        data = request.get_json(silent=True) or request.form.to_dict()
        reply_message = data.get("reply_message")
        new_status = (data.get("status", "resolved") or "resolved").strip().lower()
        if not reply_message: return jsonify({"error": "Reply text required"}), 400
        if new_status not in {"open", "in progress", "resolved", "closed"}:
            return jsonify({"error": "Invalid status"}), 400

        comp = db.get_or_404(Complaint, complaint_id)
        old_status = comp.status
        if _is_inactive_record_status(old_status) and _is_active_record_status(new_status):
            return jsonify({"error": "Resolved complaints cannot be reopened."}), 400

        comp.admin_notes = reply_message
        comp.status = new_status
        if _is_inactive_record_status(new_status): comp.resolved_at = datetime.now(UTC)
        complaint_bus = db.session.get(Bus, comp.bus_id) if comp.bus_id else None
        complaint_bus_label = complaint_bus.bus_number if complaint_bus else (f"Bus ID {comp.bus_id}" if comp.bus_id else "Unknown Bus")
        reporter = db.session.get(User, comp.passenger_id)
        reference = f"CMP-{comp.id:04d}"
        status_changed = _normalize_record_status(old_status) != _normalize_record_status(new_status)
        if _is_inactive_record_status(new_status) and status_changed:
            if reporter and reporter.role == "driver":
                db.session.add(Notification(
                    recipient_id=reporter.id,
                    message=f"Complaint Closed\n\nComplaint {reference} has been resolved by Transport Administration."
                ))
            else:
                db.session.add(Notification(
                    recipient_id=comp.passenger_id,
                    message=f"✅ Complaint Resolved\n\nYour complaint has been successfully resolved.\n\nReference:\n{reference}"
                ))
            driver_recipient_ids = set()
            if comp.driver_id:
                driver_recipient_ids.add(comp.driver_id)
            shared_driver = _shared_driver_user()
            if complaint_bus and complaint_bus.assigned_driver_code and shared_driver:
                driver_recipient_ids.add(shared_driver.id)
            driver_recipient_ids.discard(comp.passenger_id)
            for driver_id in driver_recipient_ids:
                db.session.add(Notification(
                    recipient_id=driver_id,
                    message=f"Complaint Closed\n\nComplaint {reference} has been resolved by Transport Administration."
                ))
        elif status_changed:
            db.session.add(Notification(
                recipient_id=comp.passenger_id,
                message=f"[COMPLAINT STATUS] Complaint {reference} for {complaint_bus_label} status: {new_status.upper()}. Reply: {reply_message}"
            ))
        db.session.commit()
        return jsonify({"success": True}), 200

    @app.route("/api/complaints", methods=["GET", "POST"])
    @login_required
    def complaints_api():
        if request.method == "POST":
            data = request.get_json(silent=True) or request.form.to_dict()
            action = data.get("action")
            if action == "delete":
                comp = db.session.get(Complaint, data.get("complaint_id"))
                if comp and (current_user.role == 'admin' or comp.passenger_id == current_user.id):
                    comp.status = "archived"
                    comp.resolved_at = datetime.now(UTC)
                    db.session.commit()
                    return jsonify({"message": "Success"}), 200
                return jsonify({"error": "Unauthorized"}), 403

            if action == "edit":
                comp = db.session.get(Complaint, data.get("complaint_id"))
                if comp and (current_user.role == 'admin' or comp.passenger_id == current_user.id):
                    if _is_inactive_record_status(comp.status):
                        return jsonify({"error": "Closed complaints cannot be edited."}), 400
                    comp.complaint_type = data.get("complaint_type", comp.complaint_type)
                    if comp.complaint_type == "Other" and data.get("custom_complaint_type"): comp.complaint_type = data.get("custom_complaint_type")
                    comp.description = data.get("detailed_description", "") if data.get("complaint_type") == "Other" else data.get("description", "")
                    comp.severity = data.get("severity", comp.severity)
                    if "evidence_image" in data:
                        try:
                            comp.evidence_image = _clean_complaint_evidence_image(data.get("evidence_image"))
                        except ValueError as exc:
                            return jsonify({"error": str(exc)}), 400
                    if current_user.role == "driver":
                        driver_bus = _get_session_driver_bus()
                        if driver_bus:
                            comp.bus_id = driver_bus.id
                            comp.route_id = driver_bus.route_id
                    else:
                        bus_input = str(data.get("bus_id") or data.get("bus_number") or "").strip().upper()
                        matched_bus = Bus.query.filter(or_(Bus.bus_number == bus_input, Bus.registration_number == bus_input)).first() if bus_input else None
                        route_raw = str(data.get("route_id") or "").strip()
                        if route_raw and not route_raw.isdigit():
                            return jsonify({"error": "Invalid route selected"}), 400
                        comp.bus_id = matched_bus.id if matched_bus else None
                        comp.route_id = int(route_raw) if route_raw else None
                    db.session.commit()
                    return jsonify({"message": "Success"}), 200
                return jsonify({"error": "Unauthorized"}), 403

            if current_user.role == "admin":
                return jsonify({"error": "Admins cannot create complaints."}), 403

            ctype = data.get("complaint_type", "general")
            if ctype == "Other" and data.get("custom_complaint_type"): ctype = data.get("custom_complaint_type")
            desc = data.get("detailed_description", "") if ctype == data.get("custom_complaint_type") else data.get("description", "")
            try:
                evidence_image = _clean_complaint_evidence_image(data.get("evidence_image"))
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400

            selected_route_id = None
            route_raw = str(data.get("route_id") or "").strip()
            if route_raw:
                try:
                    selected_route_id = int(route_raw)
                except ValueError:
                    return jsonify({"error": "Invalid route selected"}), 400

            matched_bus = None
            if current_user.role == "driver":
                matched_bus = _get_session_driver_bus()
            else:
                bus_input = str(data.get("bus_id") or data.get("bus_number") or "").strip().upper()
                matched_bus = Bus.query.filter(or_(Bus.bus_number == bus_input, Bus.registration_number == bus_input)).first() if bus_input else None

            bus_id_val = matched_bus.id if matched_bus else None

            driver_user = None
            shared_driver = _shared_driver_user()
            if matched_bus and matched_bus.assigned_driver_code and shared_driver:
                driver_user = shared_driver
            elif current_user.role == "driver":
                driver_user = current_user

            did = driver_user.id if driver_user else None
            route_id_val = selected_route_id
            if matched_bus:
                trip = _active_trip_for_bus(matched_bus)
                if route_id_val is None and trip:
                    route_id_val = trip.route_id
                if route_id_val is None and matched_bus.route_id:
                    route_id_val = matched_bus.route_id

            if route_id_val is not None and not db.session.get(Route, route_id_val):
                return jsonify({"error": "Selected route not found"}), 400
            if current_user.role == "passenger" and (bus_id_val is None or route_id_val is None):
                return jsonify({"error": "Please select a valid bus and route."}), 400
            if current_user.role == "driver" and (bus_id_val is None or route_id_val is None):
                return jsonify({"error": "Assigned bus and route not found for driver."}), 400

            complaint = Complaint(passenger_id=current_user.id, driver_id=did, bus_id=bus_id_val, route_id=route_id_val, complaint_type=ctype, description=desc, severity=data.get("severity", "medium"), status="open", evidence_image=evidence_image)
            db.session.add(complaint)
            db.session.flush()
            reporter_label = "driver" if current_user.role == "driver" else "passenger"
            bus_label = matched_bus.bus_number if matched_bus else f"Bus ID {bus_id_val}"
            for admin in User.query.filter_by(role="admin").all():
                db.session.add(Notification(
                    recipient_id=admin.id,
                    message=f"[COMPLAINT] New {reporter_label} complaint CMP-{complaint.id:04d} for {bus_label}: {ctype}. Review it in Complaints Management."
                ))
            if did and current_user.role == "passenger":
                db.session.add(Notification(
                    recipient_id=did,
                    message=f"[COMPLAINT] New passenger complaint for {matched_bus.bus_number}: {ctype}. Review it in Complaints Management."
                ))
            db.session.commit()
            ctx = _bus_report_context(matched_bus)
            return jsonify({
                "message": "Complaint submitted",
                "complaint_id": complaint.id,
                **ctx
            }), 201

        view = request.args.get("view", "active")
        if current_user.role == "admin":
            complaints_query = Complaint.query
        elif current_user.role == "driver":
            driver_bus = _get_session_driver_bus()
            complaints_query = Complaint.query.filter_by(bus_id=driver_bus.id) if driver_bus else Complaint.query.filter(Complaint.id == -1)
        else:
            complaints_query = Complaint.query.filter_by(passenger_id=current_user.id)
        complaints = (
            _apply_lifecycle_filter(complaints_query, Complaint, view)
            .options(
                joinedload(Complaint.passenger),
                joinedload(Complaint.bus),
                joinedload(Complaint.route),
                joinedload(Complaint.driver),
            )
            .order_by(Complaint.created_at.desc())
            .all()
        )
        payload = []
        for c in complaints:
            cd = c.to_dict()
            user = c.passenger
            cd['author_name'] = user.full_name if user else "Passenger User"
            cd['author_role'] = user.role if user else "passenger"
            bus = c.bus
            route = c.route
            driver = c.driver
            ctx = _bus_report_context(bus)
            cd.update({
                'bus_number': ctx.get('bus_number') or (bus.bus_number if bus else None),
                'driver_name': ctx.get('driver_name') or (bus.assigned_driver_name if bus and bus.assigned_driver_name else (driver.full_name if driver else None)),
                'driver_code': ctx.get('driver_code') or (bus.assigned_driver_code if bus and bus.assigned_driver_code else (driver.transpulse_id or driver.driver_code if driver else None)),
                'route_name': ctx.get('route_name') or (route.name if route else None),
                'route_code': ctx.get('route_code') or (route.route_code if route else None),
                'trip_id': ctx.get('trip_id'),
                'current_stop': ctx.get('current_stop'),
            })
            payload.append(cd)
        return jsonify(payload)

    @app.route("/api/lost-and-found", methods=["GET", "POST"])
    @login_required
    def lost_and_found_api():
        if request.method == "POST":
            data = request.get_json(silent=True) or request.form.to_dict()
            action = data.get("action")
            if action == "delete":
                item = db.session.get(LostAndFound, data.get("report_id"))
                if item and (current_user.role == 'admin' or item.user_id == current_user.id):
                    item.status = "Archived"
                    db.session.commit()
                    return jsonify({"message": "Success"}), 200
                return jsonify({"error": "Unauthorized"}), 403

            if action == "edit":
                item = db.session.get(LostAndFound, data.get("report_id"))
                if item and (current_user.role == 'admin' or item.user_id == current_user.id):
                    if _is_inactive_record_status(item.status):
                        return jsonify({"error": "Closed reports cannot be edited."}), 400
                    item.item_name = data.get("item_category", item.item_name)
                    item.description = data.get("other_description", "") if item.item_name == "Other" else data.get("description", "")
                    item.color = data.get("color", item.color)
                    item.brand = data.get("brand", item.brand)
                    try:
                        parsed_date = _parse_iso_date(data.get("lost_date"))
                    except ValueError as exc:
                        return jsonify({"error": str(exc)}), 400
                    if parsed_date:
                        item.incident_date = parsed_date
                    item.contact_phone = data.get("contact_number", item.contact_phone)
                    if "evidence_image" in data:
                        item.evidence_image = _clean_complaint_evidence_image(data.get("evidence_image"))
                    db.session.commit()
                    return jsonify({"message": "Success"}), 200
                return jsonify({"error": "Unauthorized"}), 403

            desc = data.get("other_description", "") if data.get("item_category") == "Other" else data.get("description", "")
            bus_input = str(data.get("bus_id") or data.get("bus_number") or "").strip().upper()
            matched_bus = Bus.query.filter(or_(Bus.bus_number == bus_input, Bus.registration_number == bus_input)).first() if bus_input else None
            bus_id_val = matched_bus.id if matched_bus else None

            route_id_val = None
            assigned_driver_id = None
            shared_driver = _shared_driver_user()
            if matched_bus:
                trip = _active_trip_for_bus(matched_bus)
                if trip:
                    route_id_val = trip.route_id
                elif matched_bus.route_id:
                    route_id_val = matched_bus.route_id
                if matched_bus.assigned_driver_code and shared_driver:
                    assigned_driver_id = shared_driver.id

            if route_id_val is None and matched_bus and matched_bus.route_id:
                route_id_val = matched_bus.route_id

            if bus_id_val is None or route_id_val is None:
                return jsonify({"error": "Valid bus number required. Bus must have an assigned route."}), 400

            try:
                incident_date = _parse_iso_date(data.get("lost_date")) or datetime.now(UTC)
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400

            evidence_image = _clean_complaint_evidence_image(data.get("evidence_image"))

            item = LostAndFound(
                user_id=current_user.id,
                item_name=data.get("item_category", "Unknown"),
                description=desc,
                evidence_image=evidence_image,
                color=data.get("color", ""),
                brand=data.get("brand", ""),
                incident_date=incident_date,
                contact_name=current_user.full_name,
                contact_phone=data.get("contact_number", ""),
                status="Open",
                bus_id=bus_id_val,
                route_id=route_id_val,
                assigned_driver_id=assigned_driver_id,
                item_type="lost"
            )
            db.session.add(item)
            db.session.flush()

            if assigned_driver_id:
                route_obj = db.session.get(Route, route_id_val)
                route_label = route_obj.name if route_obj else "Route"
                bus_label = matched_bus.bus_number if matched_bus else str(bus_id_val)
                db.session.add(Notification(
                    recipient_id=assigned_driver_id,
                    message=f"[LOST & FOUND] New report on {bus_label} ({route_label}): {item.item_name}. Check Lost & Found dashboard."
                ))
            route_obj = db.session.get(Route, route_id_val)
            route_label = route_obj.name if route_obj else "Route"
            bus_label = matched_bus.bus_number if matched_bus else str(bus_id_val)
            for admin in User.query.filter_by(role="admin").all():
                db.session.add(Notification(
                    recipient_id=admin.id,
                    message=f"[LOST & FOUND] New report LF-{item.id:04d} on {bus_label} ({route_label}): {item.item_name}. Review Lost & Found."
                ))

            db.session.commit()
            ctx = _bus_report_context(matched_bus)
            return jsonify({
                "message": "Report submitted",
                "report_id": item.id,
                **ctx
            }), 201

        view = request.args.get("view", "active")
        items_query = LostAndFound.query
        if current_user.role == "driver":
            driver_bus = _get_session_driver_bus()
            if driver_bus:
                items_query = items_query.filter(LostAndFound.bus_id == driver_bus.id)
            else:
                items_query = items_query.filter(LostAndFound.id == -1)
        elif current_user.role == "passenger":
            items_query = items_query.filter_by(user_id=current_user.id)
        items_query = _apply_lifecycle_filter(items_query, LostAndFound, view)
        items = (
            items_query
            .options(
                joinedload(LostAndFound.bus),
                joinedload(LostAndFound.route),
                joinedload(LostAndFound.assigned_driver),
            )
            .order_by(LostAndFound.created_at.desc())
            .all()
        )

        payload = []
        for i in items:
            bus = i.bus
            route = i.route
            driver = i.assigned_driver
            trip = _active_trip_for_bus(bus) if bus else None
            ctx = _bus_report_context(bus)
            payload.append({
                'id': i.id,
                'user_id': i.user_id,
                'passenger_name': i.contact_name,
                'bus_id': i.bus_id,
                'bus_number': bus.bus_number if bus else str(i.bus_id),
                'route_id': i.route_id,
                'route_name': route.name if route else '',
                'trip_id': trip.id if trip else ctx.get('trip_id'),
                'current_stop': ctx.get('current_stop'),
                'item_name': i.item_name,
                'description': i.description,
                'status': i.status,
                'driver_reply': i.driver_reply,
                'color': i.color,
                'brand': i.brand,
                'contact_phone': i.contact_phone,
                'incident_date': i.incident_date.isoformat() if i.incident_date else None,
                'assigned_driver_id': i.assigned_driver_id,
                'driver_name': (bus.assigned_driver_name if bus and bus.assigned_driver_name else (driver.full_name if driver else '')),
                'driver_code': (bus.assigned_driver_code if bus and bus.assigned_driver_code else (driver.transpulse_id or driver.driver_code if driver else '')),
            })
        return jsonify(payload)

    @app.route("/api/lost-and-found/<int:report_id>/return", methods=["POST"])
    @login_required
    @role_required("driver")
    def lost_and_found_return_api(report_id: int):
        item = db.get_or_404(LostAndFound, report_id)
        driver_bus = _get_session_driver_bus()
        if not driver_bus or item.bus_id != driver_bus.id:
            return jsonify({"error": "Unauthorized"}), 403
        if _is_inactive_record_status(item.status):
            return jsonify({"success": True, "status": item.status}), 200

        item.status = "Returned"
        item.claimed_by = item.user_id
        item.claimed_at = datetime.now(UTC)
        if not item.driver_reply:
            item.driver_reply = "Item returned to passenger."
        reference = f"LF-{item.id:04d}"
        db.session.add(Notification(
            recipient_id=item.user_id,
            message=f"Your lost item has been returned successfully.\n\nReference:\n{reference}"
        ))
        db.session.commit()
        return jsonify({"success": True, "status": item.status}), 200

    @app.route("/api/lost-and-found/<int:report_id>/reply", methods=["POST"])
    @login_required
    @role_required("driver", "admin")
    def lost_and_found_reply_api(report_id: int):
        data = request.get_json(silent=True) or {}
        reply_message = (data.get("reply_message") or "").strip()
        new_status = (data.get("status") or "OPEN").strip()
        if new_status.upper() not in ("OPEN", "FOUND", "NOT FOUND", "RETURNED"):
            return jsonify({"error": "Invalid status"}), 400

        item = db.get_or_404(LostAndFound, report_id)
        if current_user.role == "driver":
            driver_bus = _get_session_driver_bus()
            if not driver_bus or item.bus_id != driver_bus.id:
                return jsonify({"error": "Unauthorized"}), 403

        old_status = item.status
        if _is_inactive_record_status(old_status) and _is_active_record_status(new_status):
            return jsonify({"error": "Closed reports cannot be reopened."}), 400

        item.driver_reply = reply_message
        item.status = {
            "open": "Open",
            "found": "Found",
            "not found": "Not Found",
            "returned": "Returned",
        }[_normalize_record_status(new_status)]
        if _normalize_record_status(item.status) == "returned":
            item.claimed_by = item.user_id
            item.claimed_at = datetime.now(UTC)

        reference = f"LF-{item.id:04d}"
        status_changed = _normalize_record_status(old_status) != _normalize_record_status(item.status)
        if _normalize_record_status(item.status) == "returned" and status_changed:
            db.session.add(Notification(
                recipient_id=item.user_id,
                message=f"Your lost item has been returned successfully.\n\nReference:\n{reference}"
            ))
        elif status_changed:
            status_message = {
                "found": "Your lost item has been found.",
                "not found": "Unfortunately your item could not be located.",
            }.get(_normalize_record_status(item.status), f"[LOST & FOUND] Your report ({item.item_name}) status: {item.status}.")
            db.session.add(Notification(
                recipient_id=item.user_id,
                message=status_message
            ))

        if current_user.role == "admin" and status_changed and item.assigned_driver_id:
            db.session.add(Notification(
                recipient_id=item.assigned_driver_id,
                message=f"[LOST & FOUND STATUS] Report {reference} status changed to {item.status} by Transport Administration."
            ))
        db.session.commit()
        return jsonify({"success": True, "status": item.status}), 200

    @app.route("/api/occupancy/live", methods=["GET"])
    @login_required
    def occupancy_live_api():
        occupancy_data = {}
        for bus in Bus.query.all():
            occ = BusOccupancy.query.filter_by(bus_id=bus.id).order_by(BusOccupancy.recorded_at.desc()).first()
            if not occ:
                trip = _active_trip_for_bus(bus)
                pct, level = _display_occupancy_for_bus(bus)
                occupied_seats = max(0, min(bus.capacity, int(round(bus.capacity * (pct / 100)))))
                if not trip:
                    occupancy_data[str(bus.id)] = {
                        "bus_id": bus.id,
                        "trip_id": None,
                        "total_seats": bus.capacity,
                        "occupied_seats": occupied_seats,
                        "available_seats": max(0, bus.capacity - occupied_seats),
                        "occupancy_level": level.lower(),
                        "occupancy_percentage": pct,
                        "recorded_at": None
                    }
                    continue
                occ = BusOccupancy(
                    bus_id=bus.id,
                    trip_id=trip.id,
                    total_seats=bus.capacity,
                    occupied_seats=occupied_seats
                )
                occ.calculate_level()
                db.session.add(occ)
            occ_data = occ.to_dict()
            pct = int(round(float(occ_data.get("occupancy_percentage") or 0)))
            if pct <= 0:
                pct, level = _display_occupancy_for_bus(bus)
                occ_data["occupancy_percentage"] = pct
                occ_data["occupied_seats"] = max(0, min(bus.capacity, int(round(bus.capacity * (pct / 100)))))
                occ_data["available_seats"] = max(0, bus.capacity - occ_data["occupied_seats"])
            else:
                level = _occupancy_level_for_percentage(pct)
            occ_data["occupancy_level"] = level.lower()
            occupancy_data[str(bus.id)] = occ_data
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            return jsonify({"error": "Failed to update occupancy"}), 500

        return jsonify(occupancy_data)

    @app.route("/api/complaints/buses", methods=["GET"])
    @login_required
    def api_complaints_buses():
        active_buses = Bus.query.filter(
            Bus.assigned_driver_code.isnot(None),
            Bus.route_id.isnot(None)
        ).all()
        cutoff = datetime.now(UTC) - timedelta(hours=24)
        completed_trips = Trip.query.filter(
            Trip.status == "completed",
            Trip.end_time >= cutoff
        ).order_by(Trip.end_time.desc()).all()

        bus_map = {}
        for b in active_buses:
            route = db.session.get(Route, b.route_id) if b.route_id else None
            trip = _driver_dashboard_trip_for_bus(b)
            driver_name, driver_code = _driver_display_fields(b)
            bus_map[b.id] = {
                "id": b.id,
                "bus_number": b.bus_number,
                "registration_number": b.registration_number,
                "route_id": b.route_id,
                "route_code": route.route_code if route else None,
                "route_name": route.name if route else None,
                "origin": route.origin if route else None,
                "destination": route.destination if route else None,
                "driver_code": driver_code,
                "driver_name": driver_name,
                "trip_id": trip.id if trip else None,
                "status": "Active" if b.is_active else "Offline"
            }
        for t in completed_trips:
            if t.bus_id not in bus_map:
                b = db.session.get(Bus, t.bus_id)
                if b:
                    bus_map[b.id] = {
                        "id": b.id,
                        "bus_number": b.bus_number,
                        "registration_number": b.registration_number,
                        "route_id": t.route_id,
                        "status": f"Completed ({t.end_time.strftime('%H:%M')})" if t.end_time else "Completed"
                    }
        return jsonify({"buses": list(bus_map.values())})

    @app.route("/api/buses/offline", methods=["GET"])
    @login_required
    def api_buses_offline():
        results = [
            bus for bus in _live_fleet_snapshot()
            if not bus.get("is_live_gps") and bus.get("service_status") != "completed"
        ]
        return jsonify({"updated_at": datetime.now(UTC).isoformat() + "Z", "buses": results})

    @app.route("/api/buses/live", methods=["GET"])
    @login_required
    def api_buses_live():
        return jsonify({"updated_at": datetime.now(UTC).isoformat() + "Z", "buses": _live_fleet_snapshot()})

    @app.route("/api/map/center", methods=["GET"])
    @login_required
    def api_map_center():
        return jsonify(_get_map_default_center())

    @app.route("/api/routes/live", methods=["GET"])
    @login_required
    def api_routes_live():
        fleet = _live_fleet_snapshot()
        route_bus_count = {}
        route_eta_values = {}
        for b in fleet:
            if b.get("service_status") == "completed":
                continue
            rid = b.get("route_id")
            if not rid:
                continue
            route_bus_count[rid] = route_bus_count.get(rid, 0) + 1
            eta_value = b.get("updated_eta_minutes", b.get("eta_minutes"))
            try:
                if eta_value is not None:
                    route_eta_values.setdefault(rid, []).append(float(eta_value))
            except (TypeError, ValueError):
                pass

        assigned_route_counts = {
            route_id: count
            for route_id, count in (
                db.session.query(Bus.route_id, func.count(Bus.id))
                .filter(
                    Bus.route_id.isnot(None),
                    Bus.assigned_driver_code.isnot(None),
                )
                .group_by(Bus.route_id)
                .all()
            )
        }

        active_route_ids = set(route_bus_count.keys()) | set(assigned_route_counts.keys())
        for bus in Bus.query.filter(Bus.route_id.isnot(None)).all():
            active_route_ids.add(bus.route_id)

        if not active_route_ids:
            for trip in Trip.query.filter(Trip.status.in_(ACTIVE_TRIP_STATUSES)).all():
                active_route_ids.add(trip.route_id)

        payload = []
        if not active_route_ids:
            return jsonify({"routes": payload})

        for route in Route.query.filter(Route.id.in_(active_route_ids)).order_by(Route.route_code.asc()).all():
            if not _is_operational_route(route):
                continue
            if not route.route_code and not route.origin and not route.destination:
                continue
            active_bus = (
                Bus.query
                .filter(
                    Bus.route_id == route.id,
                    Bus.assigned_driver_code.isnot(None),
                )
                .order_by(case((Bus.is_active.is_(True), 0), else_=1), Bus.id.asc())
                .first()
            )
            logger.info(
                "[ROUTE_LIVE] "
                "route_id=%s "
                "route_code=%s "
                "active_bus_id=%s "
                "bus_active=%s "
                "fleet_count=%s "
                "assigned_count=%s",
                route.id,
                route.route_code,
                getattr(active_bus, "id", None),
                getattr(active_bus, "is_active", None),
                route_bus_count.get(route.id, 0),
                assigned_route_counts.get(route.id, 0),
            )
            
            
            
            trip = _driver_dashboard_trip_for_bus(active_bus) if active_bus else None
            if not trip:
                trip = _resolve_trip_for_route(route)
            points_from_active_trip = bool(active_bus and trip)
            points = _route_points_for_assigned_trip(route, trip) if points_from_active_trip else _route_points_for(route, trip)
            if not points and active_bus:
                fallback_trip = _resolve_trip_for_route(route)
                fallback_points = _route_points_for(route, fallback_trip)
                if fallback_points:
                    logger.warning(
                        "[ROUTES_LIVE] using route fallback geometry route_id=%s route_code=%s active_bus_id=%s active_trip_id=%s",
                        route.id,
                        route.route_code,
                        active_bus.id,
                        getattr(trip, "id", None),
                    )
                    trip = fallback_trip or trip
                    points = fallback_points
                    points_from_active_trip = False
            if not points:
                logger.warning(
                    "[ROUTES_LIVE] excluded route_id=%s route_code=%s active_bus_id=%s trip_id=%s reason=no usable stops",
                    route.id,
                    route.route_code,
                    getattr(active_bus, "id", None),
                    getattr(trip, "id", None),
                )
                continue
            gtfs_path = (
                _route_geometry_path_for_assigned_trip(trip)
                if points_from_active_trip and trip
                else _route_geometry_path(route, trip)
            )
            direction = "backward" if getattr(trip, "direction_id", 0) == 1 else "forward"
            if points_from_active_trip and direction == "backward":
                gtfs_path = list(reversed(gtfs_path))
            display_geometry = _display_geometry_for_map(route, trip, points, gtfs_path)
            geom_path = display_geometry["path"] or gtfs_path
            etas = route_eta_values.get(route.id, [])
            avg_eta = int(sum(etas) / len(etas)) if etas else None
            schedule = (
                _route_schedule_for_assigned_trip(route, trip)
                if points_from_active_trip and trip
                else _route_schedule_for(route, trip)
            )
            schedule_stops = schedule.get("stops") or []
            stops_payload = []
            for idx, point in enumerate(points):
                scheduled = schedule_stops[idx] if idx < len(schedule_stops) else {}
                stops_payload.append({
                    **point,
                    "arrival_time": scheduled.get("arrival_time", "--"),
                    "departure_time": scheduled.get("departure_time", "--"),
                    "scheduled_time": scheduled.get("scheduled_time", "--"),
                })
            payload.append({
                "route_id": route.id,
                "route_code": route.route_code,
                "route_name": route.name,
                "source_stop": route.origin or (points[0]["name"] if points else ""),
                "destination_stop": route.destination or (points[-1]["name"] if points else ""),
                "stops": stops_payload,
                "path": [{"lat": p["lat"], "lng": p["lng"], "name": p.get("name")} for p in (geom_path if geom_path else points)],
                "display_path": [{"lat": p["lat"], "lng": p["lng"]} for p in (geom_path if geom_path else points)],
                "display_geometry_source": display_geometry["source"],
                "geometry_source": display_geometry["source"],
                "generated_road_geometry_points": display_geometry["generated_point_count"],
                "active_bus_count": max(route_bus_count.get(route.id, 0), assigned_route_counts.get(route.id, 0)),
                "eta_minutes": avg_eta,
                "eta_label": f"{avg_eta} min" if avg_eta is not None else "Calculating...",
                "departure_time": schedule.get("departure_time", "--"),
                "arrival_time": schedule.get("arrival_time", "--"),
                "journey_duration": schedule.get("duration", "--"),
                "journey_duration_minutes": schedule.get("duration_minutes"),
                "schedule": schedule,
            })
        return jsonify({"routes": payload})

    @app.route("/api/admin/data-integrity", methods=["GET"])
    @role_required("admin")
    def api_data_integrity():
        issues = _validate_data_integrity()
        return jsonify({"valid": len(issues) == 0, "issues": issues, "checked_at": datetime.now(UTC).isoformat() + "Z"})

    @app.route("/api/driver/analytics", methods=["GET"])
    @login_required
    @role_required("admin")
    def driver_analytics_api():
        assigned_buses = Bus.query.filter(Bus.assigned_driver_code.isnot(None)).all()
        payload = []
        for bus in assigned_buses:
            code = bus.assigned_driver_code
            trips_count = Trip.query.filter_by(bus_id=bus.id).count()
            completed = Trip.query.filter_by(bus_id=bus.id, status="completed").count()
            in_progress = Trip.query.filter(Trip.bus_id == bus.id, Trip.status.in_(ACTIVE_TRIP_STATUSES)).count()
            payload.append({
                "id": bus.id,
                "name": code,
                "driver_code": code,
                "trips_completed": completed,
                "active_trips": in_progress,
                "total_trips": trips_count,
                "on_time_percentage": 0 if trips_count == 0 else min(100, int((completed / max(1, trips_count)) * 100)),
                "average_delay": 0,
                "driver_score": min(100, completed * 10 + in_progress * 5),
                "rating": 4.0 if trips_count == 0 else round(min(5.0, 3.5 + completed * 0.1), 1),
                "distance_covered": 0,
            })
        return jsonify({"drivers": sorted(payload, key=lambda x: x['driver_score'], reverse=True), "analytics": {"total_drivers": len(assigned_buses)}})

    @app.route("/api/notifications", methods=["GET"])
    @login_required
    def api_notifications_list():
        notifs = (
            Notification.query
            .filter(db.or_(Notification.recipient_id == current_user.id, Notification.target_role == current_user.role))
            .order_by(Notification.created_at.desc())
            .limit(100)
            .all()
        )
        payload = [n.to_dict() for n in notifs]
        return jsonify({"notifications": payload})

    @app.route("/api/notifications/unread", methods=["GET"])
    @login_required
    def get_unread_notifications():
        count = Notification.query.filter(
            db.or_(Notification.recipient_id == current_user.id, Notification.target_role == current_user.role),
            Notification.is_read == False
        ).count()
        return jsonify({"unread_count": count})

    @app.route("/api/sos/trigger", methods=["POST"])
    @login_required
    @role_required("passenger")
    def sos_trigger_api():
        data = request.get_json(silent=True) or request.form.to_dict()
        bus_id_val = None
        bus_input = str(data.get("bus_id") or data.get("bus_number") or "").strip().upper()
        if bus_input:
            matched = Bus.query.filter(or_(Bus.bus_number == bus_input, Bus.registration_number == bus_input)).first()
            if matched:
                bus_id_val = matched.id
        if bus_id_val is None:
            try:
                bus_id_val = int(data.get("bus_id")) if data.get("bus_id") else None
            except ValueError:
                bus_id_val = None

        if bus_id_val is None:
            _cleanup_tracking_sessions()
            session_data = PASSENGER_TRACKING_SESSIONS.get(current_user.id) or {}
            bus_id_val = session_data.get("bus_id")

        if bus_id_val is None:
            return jsonify({"error": "Bus number is required for SOS alert."}), 400

        trip = None
        route_id_val = None
        if bus_id_val:
            bus_obj = db.session.get(Bus, bus_id_val)
            trip = _active_trip_for_bus(bus_obj) if bus_obj else None
            if trip:
                route_id_val = trip.route_id
            else:
                if bus_obj and bus_obj.route_id:
                    route_id_val = bus_obj.route_id

        if route_id_val is None:
            return jsonify({"error": "Could not resolve route for this bus."}), 400

        reason = (data.get("emergency_type") or data.get("reason") or "").strip()
        if reason not in SOS_EMERGENCY_TYPES:
            return jsonify({"error": "Valid emergency type is required."}), 400
        bus_obj = db.session.get(Bus, bus_id_val)
        bus_label = bus_obj.bus_number if bus_obj else str(bus_id_val)
        driver_recipient_id = None
        if bus_obj:
            if bus_obj.assigned_driver_id:
                driver_recipient_id = bus_obj.assigned_driver_id
            elif bus_obj.assigned_driver_code:
                shared_driver = _shared_driver_user()
                if shared_driver:
                    driver_recipient_id = shared_driver.id

        sos_msg = f"[SOS EMERGENCY] {bus_label}: {reason} - passenger {current_user.full_name} ({current_user.transpulse_id or current_user.id}) needs immediate assistance."

        sos = SOSAlert(
            passenger_id=current_user.id,
            bus_id=bus_id_val,
            route_id=route_id_val,
            driver_id=driver_recipient_id,
            reason=reason,
            severity=data.get("severity") or "critical",
            status="NEW",
            latitude=_coordinate(data.get("latitude")),
            longitude=_coordinate(data.get("longitude")),
        )
        db.session.add(sos)

        for admin in User.query.filter_by(role="admin").all():
            db.session.add(Notification(recipient_id=admin.id, message=sos_msg))
        if driver_recipient_id:
            db.session.add(Notification(recipient_id=driver_recipient_id, message=sos_msg))

        db.session.commit()
        ctx = _bus_report_context(bus_obj)
        return jsonify({
            "message": "SOS triggered",
            "id": sos.id,
            "bus_id": bus_id_val,
            "emergency_type": reason,
            **ctx
        }), 201

    @app.route("/api/driver/sos", methods=["POST"])
    @login_required
    @role_required("driver")
    def driver_sos_trigger_api():
        assigned_bus = _get_session_driver_bus()
        if not assigned_bus:
            return jsonify({"success": False, "error": "No assigned bus"}), 404

        active_trip = _active_trip_for_bus(assigned_bus)
        if not active_trip or not assigned_bus.is_active:
            return jsonify({"success": False, "error": "Start a trip before sending SOS."}), 400

        route = db.session.get(Route, active_trip.route_id)
        if not route:
            return jsonify({"success": False, "error": "Assigned route not found."}), 404

        data = request.get_json(silent=True) or request.form.to_dict()


        gps = _fresh_gps_packet(assigned_bus.id, time.time())
        latitude = _coordinate(data.get("latitude"))
        longitude = _coordinate(data.get("longitude"))
        if gps:
            latitude = latitude if latitude is not None else gps.get("lat")
            longitude = longitude if longitude is not None else gps.get("lon")

        reason = (data.get("emergency_type") or data.get("reason") or "Driver Emergency").strip()[:200]
        severity = (data.get("severity") or "critical").strip().lower()
        if severity not in {"low", "medium", "high", "critical"}:
            severity = "critical"

        driver_name, driver_code = _driver_display_fields(assigned_bus)
        reference = f"SOS-{secrets.randbelow(100000):05d}"
        message = (
            f"[SOS EMERGENCY] {assigned_bus.bus_number}: {reason} - "
            f"driver {driver_code} needs immediate assistance. Ref: {reference}."
        )

        sos = SOSAlert(
            passenger_id=current_user.id,
            bus_id=assigned_bus.id,
            route_id=route.id,
            driver_id=current_user.id,
            reason=reason,
            description=f"Driver-originated SOS from {driver_name} ({driver_code}).",
            severity=severity,
            status="NEW",
            latitude=latitude,
            longitude=longitude,
        )
        db.session.add(sos)

        for admin in User.query.filter_by(role="admin").all():
            db.session.add(Notification(
                recipient_id=admin.id,
                trip_id=active_trip.id,
                message=message,
            ))
        db.session.add(Notification(
            recipient_id=current_user.id,
            trip_id=active_trip.id,
            message=message,
        ))

        try:
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            logger.exception("[DRIVER_SOS] trigger failed: %s", exc)
            return jsonify({"success": False, "error": "SOS could not be sent."}), 500

        return jsonify({
            "success": True,
            "message": "SOS triggered",
            "id": sos.id,
            "reference": reference,
            "bus_id": assigned_bus.id,
            "route_id": route.id,
            "trip_id": active_trip.id,
            "emergency_type": reason,
            "latitude": latitude,
            "longitude": longitude,
        }), 201

    @app.route("/api/sos/<int:alert_id>/status", methods=["GET"])
    @login_required
    @role_required("passenger")
    def passenger_sos_status_api(alert_id: int):
        alert = db.get_or_404(SOSAlert, alert_id)
        if alert.passenger_id != current_user.id:
            return jsonify({"error": "Unauthorized"}), 403
        status = (alert.status or "").strip()
        timer_active = status.lower() not in ("acknowledged", "resolved")
        return jsonify({
            "id": alert.id,
            "status": status,
            "timer_active": timer_active,
            "triggered_at": alert.triggered_at.isoformat() if alert.triggered_at else "",
            "acknowledged_at": alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
            "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
        })

    @app.route("/api/admin/sos", methods=["GET"])
    @role_required("admin", "driver")
    def admin_sos_list_api():
        alerts_query = SOSAlert.query.filter(SOSAlert.status.in_(ACTIVE_SOS_STATUSES))
        if current_user.role == "driver":
            driver_bus = _get_session_driver_bus()
            if not driver_bus:
                return jsonify({"alerts": []})
            alerts_query = alerts_query.filter_by(bus_id=driver_bus.id)
        alerts = alerts_query.order_by(SOSAlert.triggered_at.desc()).all()
        payload = []
        for alert in alerts:
            passenger = db.session.get(User, alert.passenger_id)
            bus = db.session.get(Bus, alert.bus_id)
            route = db.session.get(Route, alert.route_id)
            ctx = _bus_report_context(bus)
            reporter_is_driver = bool(passenger and passenger.role == "driver" and alert.driver_id == alert.passenger_id)
            reporter_name = (
                f"Driver {ctx.get('driver_code') or passenger.full_name}"
                if reporter_is_driver and passenger
                else (passenger.full_name if passenger else "Unknown")
            )
            reporter_id = (
                ctx.get("driver_code")
                if reporter_is_driver
                else ((passenger.transpulse_id or passenger.id) if passenger else alert.passenger_id)
            )
            payload.append({
                "id": alert.id,
                "passenger_name": reporter_name,
                "passenger_id": reporter_id,
                "reporter_role": "driver" if reporter_is_driver else "passenger",
                "bus_number": bus.bus_number if bus else "Unknown",
                "route_name": route.name if route else "Unknown",
                "trip_id": ctx.get("trip_id"),
                "current_stop": ctx.get("current_stop"),
                "driver_name": ctx.get("driver_name"),
                "driver_code": ctx.get("driver_code"),
                "reason": alert.reason or "Emergency",
                "emergency_type": alert.reason or "Emergency",
                "severity": alert.severity or "critical",
                "status": alert.status,
                "triggered_at": alert.triggered_at.isoformat() if alert.triggered_at else "",
                "latitude": alert.latitude,
                "longitude": alert.longitude,
                "can_acknowledge": current_user.role == "driver",
                "can_resolve": current_user.role == "admin",
            })
        return jsonify({"alerts": payload})

    @app.route("/api/admin/sos/<int:alert_id>/status", methods=["POST"])
    @role_required("admin", "driver")
    def admin_sos_status_update_api(alert_id: int):
        data = request.get_json(silent=True) or {}
        requested_status = (data.get("status") or "").strip().lower()
        if requested_status not in ["acknowledged", "resolved"]: return jsonify({"error": "Invalid status"}), 400
        alert = db.get_or_404(SOSAlert, alert_id)
        if current_user.role == "driver":
            driver_bus = _get_session_driver_bus()
            if requested_status != "acknowledged":
                return jsonify({"error": "Drivers can only acknowledge SOS alerts."}), 403
            if not driver_bus or alert.bus_id != driver_bus.id:
                return jsonify({"error": "Unauthorized"}), 403
        if requested_status == "acknowledged":
            alert.acknowledged_at = datetime.now(UTC)
            alert.status = "ACKNOWLEDGED"
        else:
            alert.status = "RESOLVED"
            alert.resolved_at = datetime.now(UTC)
        db.session.commit()
        return jsonify({"message": "Success"})

    @app.route("/api/sos/driver/acknowledge/<int:alert_id>", methods=["POST"])
    @role_required("driver")
    def driver_sos_acknowledge_api(alert_id: int):
        alert = db.get_or_404(SOSAlert, alert_id)
        driver_bus = _get_session_driver_bus()
        if not driver_bus or alert.bus_id != driver_bus.id:
            return jsonify({"success": False, "error": "Unauthorized"}), 403
        alert.status = "ACKNOWLEDGED"
        alert.acknowledged_at = datetime.now(UTC)
        db.session.commit()
        return jsonify({"success": True, "message": "SOS acknowledged"}), 200

    @app.route("/api/sos/resolve/<int:alert_id>", methods=["POST"])
    @role_required("admin")
    def admin_sos_resolve_api(alert_id: int):
        data = request.get_json(silent=True) or request.form.to_dict()
        alert = db.get_or_404(SOSAlert, alert_id)
        alert.status = "RESOLVED"
        alert.resolved_at = datetime.now(UTC)
        if data.get("resolution_notes"):
            alert.admin_notes = str(data.get("resolution_notes"))[:1000]
        db.session.commit()
        return jsonify({"success": True, "message": "SOS resolved"}), 200

    @app.route("/api/command-center/stats", methods=["GET"])
    @role_required("admin")
    def command_center_stats_api():
        fleet = _live_fleet_snapshot()
        delayed = sum(1 for b in fleet if b.get("service_status") == "delayed")
        etas = [b.get("eta_minutes", 0) for b in fleet if b.get("geometry_available", True)]
        avg_eta = int(sum(etas) / len(etas)) if etas else 0
        return jsonify({
            "active_buses": Bus.query.filter_by(is_active=True).count(),
            "active_routes": Route.query.filter_by(is_operational=True).count(),
            "active_drivers": Bus.query.filter(Bus.assigned_driver_code.isnot(None)).count(),
            "passengers_served": User.query.filter_by(role="passenger").count(),
            "delayed_vehicles": delayed,
            "average_eta": avg_eta
        })

    @app.route("/heatmap", methods=["GET"])
    @role_required("admin")
    def heatmap_page():
        city_names = set()
        for origin, destination in db.session.query(Route.origin, Route.destination).all():
            for value in (origin, destination):
                clean = (value or "").strip()
                if clean:
                    city_names.add(clean.lower())
        if not city_names:
            city_names = {
                (name or "").strip().lower()
                for (name,) in db.session.query(Stop.stop_name).distinct().all()
                if (name or "").strip()
            }
        heatmap_stats = {
            "total_routes": Route.query.count(),
            "total_stops": Stop.query.count(),
            "total_cities": len(city_names),
            "total_trips": Trip.query.count(),
        }
        return render_template("heatmap.html", heatmap_stats=heatmap_stats)

    @app.get("/heatmap/data")
    @role_required("admin", "passenger", "driver")
    def heatmap_data_api():
        stops = db.session.query(Stop.stop_name, Stop.stop_lat, Stop.stop_lon, func.count(Stop.id).label('intensity')).filter(Stop.stop_lat.isnot(None)).group_by(Stop.stop_name, Stop.stop_lat, Stop.stop_lon).limit(200).all()
        return jsonify({"cities": [{"name": s[0], "lat": s[1], "lng": s[2], "intensity": min(1.0, s[3] * 0.15)} for s in stops]})

    @app.route("/dashboard/analytics", methods=["GET"])
    @role_required("admin")
    def analytics_dashboard():
        role_counts = {"passengers": User.query.filter_by(role="passenger").count(), "drivers": Bus.query.filter(Bus.assigned_driver_code.isnot(None)).count(), "admins": User.query.filter_by(role="admin").count()}
        totals = {"total_trips": Trip.query.count(), "active_trips": Trip.query.filter(Trip.status.in_(ACTIVE_TRIP_STATUSES)).count(), "bus_count": Bus.query.count(), "user_count": sum(role_counts.values())}
        top_routes = db.session.query(Route.route_code, func.count(Trip.id).label('trips')).join(Trip).group_by(Route.route_code).order_by(db.text('trips DESC')).limit(5).all()
        return render_template("analytics_dashboard.html", role_counts=role_counts, trip_status_counts={"scheduled": 0, "in_progress": totals["active_trips"], "completed": 0, "cancelled": 0}, route_labels=[r[0] for r in top_routes], trips_per_route=[r[1] for r in top_routes], totals=totals)

    @app.route("/lost-and-found", methods=["GET", "POST"])
    @login_required
    def lost_and_found_page(): return render_template("lost_and_found.html")

def _backfill_transpulse_ids() -> None:
    """Backfill missing transpulse_id values from database records only."""
    changed = False
    for user in User.query.all():
        if user.role == "admin" and not user.transpulse_id:
            user.transpulse_id = _admin_transpulse_id_for_user(user.id)
            changed = True
    for bus in Bus.query.filter(Bus.assigned_driver_code.isnot(None)).all():
        normalized = _normalize_driver_code(bus.assigned_driver_code or "")
        if normalized and bus.assigned_driver_code != normalized:
            bus.assigned_driver_code = normalized
            bus.assigned_driver_name = normalized
            changed = True
    if changed:
        db.session.commit()


def initialize_database() -> None:
    db.create_all()
    _ensure_lost_found_columns()
    _ensure_default_admin()
    _ensure_shared_driver_account()
    _backfill_transpulse_ids()


app = create_app()

MAIL_SERVER = "smtp.gmail.com"
MAIL_PORT = 587
MAIL_USE_TLS = True

MAIL_USERNAME = os.getenv("MAIL_USERNAME")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")

if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 5000))
    app.run(host=host, port=port, debug=False)
