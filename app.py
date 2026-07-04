from datetime import datetime, timedelta, timezone, UTC
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
from types import SimpleNamespace
from urllib.error import URLError
from urllib.request import Request, urlopen

from flask import Flask, current_app, flash, jsonify, redirect, render_template, request, url_for, session
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import or_, func, case
from sqlalchemy.exc import IntegrityError
from flask_migrate import Migrate
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from config import Config
from models import db, login_manager
from models.bus import Bus
from models.feedback import Feedback
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
TRIP_STATUS_OPTIONS = {"ready", "active", "completed", "return_ready", "offline", "scheduled", "in_progress", "cancelled"}
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
BUS_DELAY_DATA = {}
BUS_SIMULATION_STATE = {}
PASSENGER_TRACKING_SESSIONS = {}
_MAP_DEFAULT_CENTER = None

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

migrate = Migrate()


def _normalize_driver_code(raw: str) -> str:
    """Normalize driver codes DRV-1 through DRV-10000."""
    if not raw:
        return ""
    clean = re.sub(r"^(DRV|DVR)-", "", str(raw).upper().strip())
    try:
        num = int(clean)
        if 1 <= num <= 10000:
            return f"DRV-{num:03d}" if num < 1000 else f"DRV-{num}"
    except ValueError:
        pass
    return f"DRV-{clean}" if clean else ""


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


def _resolve_transpulse_id(raw: str, role: str) -> str:
    if role == "driver":
        return _normalize_driver_code(raw)
    if role == "admin":
        return _normalize_admin_transpulse_id(raw)
    return (raw or "").strip()


SHARED_DRIVER_EMAIL = "driver@transpulse.com"


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
    if not _shared_driver_user():
        driver = User(
            full_name="TransPulse Driver",
            email=SHARED_DRIVER_EMAIL,
            role="driver",
            auth_provider="local",
        )
        driver.set_password("Driver@123")
        db.session.add(driver)
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
    if pct >= 91:
        return "Full"
    if pct >= 71:
        return "High"
    if pct >= 31:
        return "Medium"
    return "Low"


def _simulated_occupancy_percentage(bus: Optional[Bus]) -> int:
    if not bus:
        return 43
    seed = f"{bus.id}:{bus.bus_number}:{bus.registration_number}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return 15 + (int(digest[:8], 16) % 71)


def _display_occupancy_for_bus(bus: Optional[Bus]) -> tuple[int, str]:
    pct = _simulated_occupancy_percentage(bus)
    try:
        if bus:
            occ = BusOccupancy.query.filter_by(bus_id=bus.id).order_by(BusOccupancy.recorded_at.desc()).first()
            if occ:
                pct = int(round(float(occ.occupancy_percentage or 0)))
                if pct <= 0 and occ.total_seats:
                    pct = int(round((float(occ.occupied_seats or 0) / float(occ.total_seats)) * 100))
                if pct <= 0:
                    pct = _simulated_occupancy_percentage(bus)
    except Exception:
        pass
    pct = max(0, min(100, pct))
    return pct, _occupancy_level_for_percentage(pct)


def _latest_recorded_occupancy_for_bus(bus: Optional[Bus]) -> tuple[Optional[int], Optional[str]]:
    if not bus:
        return None, None
    occ = BusOccupancy.query.filter_by(bus_id=bus.id).order_by(BusOccupancy.recorded_at.desc()).first()
    if not occ:
        return None, None
    try:
        pct = int(round(float(occ.occupancy_percentage or 0)))
    except (TypeError, ValueError):
        pct = 0
    if pct <= 0 and occ.total_seats:
        pct = int(round((float(occ.occupied_seats or 0) / float(occ.total_seats)) * 100))
    pct = max(0, min(100, pct))
    level = (occ.occupancy_level or _occupancy_level_for_percentage(pct)).strip() or _occupancy_level_for_percentage(pct)
    return pct, level


def _display_occupancy_for_bus_at(bus: Optional[Bus], occupancy_offset: int = 0) -> tuple[int, str]:
    pct, _ = _display_occupancy_for_bus(bus)
    pct = max(5, min(100, pct + int(occupancy_offset or 0)))
    return pct, _occupancy_level_for_percentage(pct)


def _validate_driver_code_input(raw: str) -> tuple:
    """Return (normalized_code, error_message)."""
    code = _normalize_driver_code(raw)
    if not code:
        return "", "Invalid Driver ID format."
    try:
        num = int(code.replace("DRV-", ""))
        if num < 1 or num > 10000:
            return "", "Driver ID must be between DRV-001 and DRV-10000."
    except ValueError:
        return "", "Invalid Driver ID format."
    return code, ""


PASSWORD_RESET_MAX_AGE_SECONDS = 15 * 60
PASSWORD_RESET_SALT = "transpulse-passenger-password-reset"
PASSWORD_MIN_LENGTH = 8


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
    value = current_app.config.get(name)
    if value:
        return value
    return globals().get(name, default)


def _send_password_reset_email(recipient_email: str, reset_link: str) -> None:
    username = _mail_config_value("MAIL_USERNAME", "transpulse.official@gmail.com")
    password = (
        current_app.config.get("MAIL_PASSWORD")
        or os.getenv("TRANSPULSE_GMAIL_APP_PASSWORD")
        or os.getenv("MAIL_PASSWORD")
        or globals().get("MAIL_PASSWORD")
    )
    if not password:
        raise RuntimeError("Gmail SMTP password is not configured.")

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
    use_tls = bool(_mail_config_value("MAIL_USE_TLS", True))
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
    return (
        Trip.query
        .filter_by(route_id=route.id)
        .filter(Trip.shape_id.isnot(None))
        .order_by(Trip.id.asc())
        .first()
        or Trip.query.filter_by(route_id=route.id).order_by(Trip.id.asc()).first()
    )


def _route_stop_template_trip(route_id: int, shape_id: Optional[str] = None):
    query = (
        Trip.query
        .join(StopTime, StopTime.trip_id == Trip.id)
        .filter(Trip.route_id == route_id)
    )
    if shape_id:
        query = query.filter(Trip.shape_id == shape_id)
    return (
        query
        .group_by(Trip.id)
        .order_by(func.count(StopTime.id).desc(), Trip.id.asc())
        .first()
    )


def _stop_name_key(value: Optional[str]) -> str:
    return re.sub(r"[^A-Z0-9]+", "", (value or "").upper())


def _route_endpoint_validation_error(route: Optional[Route], trip, points: list) -> Optional[str]:
    if not route or not trip or len(points) < 2:
        return None

    direction = "backward" if getattr(trip, "direction_id", 0) == 1 else "forward"
    expected_first = route.destination if direction == "backward" else route.origin
    expected_last = route.origin if direction == "backward" else route.destination
    actual_first = points[0].get("name")
    actual_last = points[-1].get("name")

    if (
        _stop_name_key(expected_first)
        and _stop_name_key(actual_first)
        and _stop_name_key(expected_first) != _stop_name_key(actual_first)
    ):
        return (
            f"Validation error: assigned trip {trip.id} starts at {actual_first}, "
            f"but route {route.id} expects {expected_first}."
        )
    if (
        _stop_name_key(expected_last)
        and _stop_name_key(actual_last)
        and _stop_name_key(expected_last) != _stop_name_key(actual_last)
    ):
        return (
            f"Validation error: assigned trip {trip.id} ends at {actual_last}, "
            f"but route {route.id} expects {expected_last}."
        )
    return None


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


def _route_has_gtfs_stop_times(route_id: Optional[int]) -> bool:
    if not route_id:
        return False
    return (
        db.session.query(StopTime.id)
        .join(Trip, StopTime.trip_id == Trip.id)
        .join(Stop, StopTime.stop_id == Stop.id)
        .filter(Trip.route_id == route_id, Stop.stop_code.isnot(None))
        .first()
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


def _gtfs_backed_trip_for_route(route_id: Optional[int]) -> Optional[Trip]:
    if not route_id:
        return None
    candidates = (
        Trip.query
        .filter(
            Trip.route_id == route_id,
            Trip.bus_id.is_(None),
            Trip.shape_id.isnot(None),
        )
        .order_by(Trip.id.asc())
        .all()
    )
    for trip in candidates:
        stop_times_count = StopTime.query.filter_by(trip_id=trip.id).count()
        shape_points_count = Shape.query.filter_by(shape_id=trip.shape_id).count()
        if stop_times_count > 0 and shape_points_count > 0:
            return trip
    return None


def _first_gtfs_backed_trip() -> Optional[Trip]:
    candidates = (
        Trip.query
        .filter(Trip.bus_id.is_(None), Trip.shape_id.isnot(None))
        .order_by(Trip.id.asc())
        .all()
    )
    for trip in candidates:
        stop_times_count = StopTime.query.filter_by(trip_id=trip.id).count()
        shape_points_count = Shape.query.filter_by(shape_id=trip.shape_id).count()
        if stop_times_count > 0 and shape_points_count > 0:
            return trip
    return None


def _gtfs_backed_route_ids() -> set:
    shape_ids = {
        row[0]
        for row in Shape.query.with_entities(Shape.shape_id).distinct().all()
        if row[0]
    }
    if not shape_ids:
        return set()
    rows = (
        db.session.query(Trip.route_id)
        .join(StopTime, StopTime.trip_id == Trip.id)
        .filter(Trip.shape_id.in_(shape_ids))
        .group_by(Trip.route_id)
        .all()
    )
    return {row[0] for row in rows}


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


def _repair_active_bus_gtfs_links(allow_fallback: bool = False) -> list:
    repairs = []
    for bus in Bus.query.filter_by(is_active=True).all():
        before = _bus_chain_debug(bus)
        gtfs_trip = _gtfs_backed_trip_for_route(bus.route_id)
        repair_mode = "same_route"
        if not gtfs_trip:
            repairs.append({
                "bus_number": bus.bus_number,
                "repaired": False,
                "reason": "No GTFS-backed trip found for current route",
                "before": before,
            })
            continue

        bus.route_id = gtfs_trip.route_id
        route = db.session.get(Route, gtfs_trip.route_id)
        if route:
            route.is_operational = True

        active_trip = _active_trip_for_bus(bus)
        if not active_trip:
            active_trip = Trip(
                bus_id=bus.id,
                route_id=gtfs_trip.route_id,
                shape_id=gtfs_trip.shape_id,
                start_time=datetime.now(UTC),
                status="active",
            )
            db.session.add(active_trip)
        else:
            active_trip.route_id = gtfs_trip.route_id
            active_trip.shape_id = gtfs_trip.shape_id

        db.session.flush()
        StopTime.query.filter_by(trip_id=active_trip.id).delete(synchronize_session=False)
        _copy_stop_times_from_template(active_trip, gtfs_trip)
        db.session.flush()

        after = _bus_chain_debug(bus)
        repairs.append({
            "bus_number": bus.bus_number,
            "repaired": after["geometry_available"],
            "mode": repair_mode,
            "gtfs_trip_id": gtfs_trip.id,
            "before": before,
            "after": after,
        })
    return repairs


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
    trip = _active_trip_for_bus(bus)
    route = db.session.get(Route, trip.route_id if trip else bus.route_id)
    driver_name, driver_code = _driver_display_fields(bus)
    current_stop = None
    if route and trip:
        gps = _fresh_gps_packet(bus.id, time.time())
        points = _route_points_for_assigned_trip(route, trip) if gps else []
        if points:
            current_stop = points[_nearest_route_index(gps["lat"], gps["lon"], points)]["name"]
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

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = "login_page"

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
def load_user(user_id: str): return db.session.get(User, int(user_id))

@login_manager.unauthorized_handler
def unauthorized():
    flash("Please log in to continue.", "warning")
    return redirect(url_for("login_page"))

def role_required(*allowed_roles):
    def decorator(func):
        @wraps(func)
        @login_required
        def wrapper(*args, **kwargs):
            if current_user.role not in allowed_roles:
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
    default = {
        "path": shape_path,
        "leg_end_indexes": _path_indexes_for_stops(points, shape_path),
        "source": "gtfs",
        "generated_point_count": 0,
    }
    if _gtfs_shape_has_sufficient_detail(points, shape_path):
        return default
    if len(points) < 2:
        return default

    cache_key, stop_signature = _road_geometry_cache_identity(route, trip, points)
    cache_entry = RoadGeometryCache.query.filter_by(cache_key=cache_key).first()
    if cache_entry and cache_entry.status == "ready":
        cached_path, cached_leg_indexes = _decode_cached_road_geometry(cache_entry)
        if len(cached_path) >= 2 and len(cached_leg_indexes) == len(points):
            return {
                "path": cached_path,
                "leg_end_indexes": cached_leg_indexes,
                "source": "osrm",
                "generated_point_count": len(cached_path),
            }

    if cache_entry and cache_entry.status == "failed" and _road_geometry_failure_is_recent(cache_entry):
        default["source"] = "gtfs_fallback"
        return default

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
                    return {
                        "path": cached_path,
                        "leg_end_indexes": cached_leg_indexes,
                        "source": "osrm",
                        "generated_point_count": len(cached_path),
                    }
                default["source"] = "gtfs_fallback"
                return default
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
                    return {
                        "path": cached_path,
                        "leg_end_indexes": cached_leg_indexes,
                        "source": "osrm",
                        "generated_point_count": len(cached_path),
                    }
            default["source"] = "gtfs_fallback"
            return default
        logger.info(
            "[ROAD_GEOMETRY] cached route_id=%s shape_id=%s gtfs_points=%s generated_points=%s",
            route.id, getattr(trip, "shape_id", None), len(shape_path), len(generated_path),
        )
        return {
            "path": generated_path,
            "leg_end_indexes": leg_end_indexes,
            "source": "osrm",
            "generated_point_count": len(generated_path),
        }
    except (URLError, TimeoutError, ValueError, OSError, json.JSONDecodeError) as error:
        _cache_road_geometry_failure(
            cache_entry, cache_key, stop_signature, route, trip, error
        )
        default["source"] = "gtfs_fallback"
        return default

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
    return points if len(points) >= 2 else []


def _route_geometry_path_for_assigned_trip(trip) -> list:
    """Live tracking shape: assigned trip shape only, never stop or route fallback."""
    shape_path = _shape_path_for_trip(trip)
    return shape_path if len(shape_path) >= 2 else []


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
    endpoint_error = _route_endpoint_validation_error(route, trip, points)
    if endpoint_error:
        return endpoint_error
    if not getattr(trip, "shape_id", None):
        return f"Validation error: assigned trip {trip.id} has no shape_id."
    if len(route_path) < 2:
        return f"Validation error: assigned trip {trip.id} shape {trip.shape_id} has no usable shape points."
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

        fallback_trip = _route_stop_template_trip(
            route.id,
            getattr(trip, "shape_id", None)
        ) or _route_stop_template_trip(route.id)
        if fallback_trip and getattr(fallback_trip, "id", None) != getattr(trip, "id", None):
            return _route_points_for(route, fallback_trip)

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


def _bus_simulation_profile(bus: Bus, trip, route: Route, now_seconds: float) -> dict:
    bus_id = int(getattr(bus, "id", 0) or 0)
    seed = _simulation_seed(bus, trip, route)
    trip_id = getattr(trip, "id", None) if trip else None
    route_id = getattr(route, "id", None)
    persisted_started_at = _persistent_trip_started_at(trip)
    state = BUS_SIMULATION_STATE.get(bus_id)
    if (
        not state
        or state.get("route_id") != route_id
        or state.get("trip_id") != trip_id
    ):
        _reset_bus_simulation_state(bus_id, route_id, trip_id, persisted_started_at or now_seconds)
        state = BUS_SIMULATION_STATE[bus_id]

    if persisted_started_at:
        state["started_at"] = persisted_started_at
    state["timestamp"] = now_seconds
    elapsed = max(0.0, now_seconds - float(state.get("started_at") or now_seconds))
    base_speed = 30.0 + (seed % 29)
    cruise_speed = max(24.0, min(62.0, base_speed + (((seed >> 9) % 9) - 4) * 0.7))
    wave = math.sin((elapsed / (17.0 + (seed % 11))) + ((seed % 360) * math.pi / 180.0)) * 5.5
    step = (((int(elapsed // 7) + (seed % 13)) % 7) - 3) * 0.65
    live_speed = max(18.0, min(68.0, cruise_speed + wave + step))
    occupancy_wave = int(round(math.sin((elapsed / (45.0 + (seed % 17))) + seed) * 6))

    return {
        "seed": seed,
        "started_at": float(state.get("started_at") or now_seconds),
        "elapsed_seconds": elapsed,
        "cruise_speed": cruise_speed,
        "live_speed": live_speed,
        "occupancy_offset": occupancy_wave,
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


def _build_journey_legs(points: list, shape_path: list, avg_speed: float = 50.0) -> list:
    """Travel legs between consecutive GTFS stops along full shape geometry."""
    legs = []
    if len(points) < 2 or len(shape_path) < 2:
        return legs

    shape_stop_indices = _path_indexes_for_stops(points, shape_path)
    if len(shape_stop_indices) != len(points):
        return legs
    if len(shape_path) > len(points):
        for i in range(1, len(shape_stop_indices) - 1):
            min_index = shape_stop_indices[i - 1] + 1
            max_index = len(shape_path) - 1 - (len(shape_stop_indices) - 1 - i)
            shape_stop_indices[i] = max(min_index, min(shape_stop_indices[i], max_index))
        shape_stop_indices[-1] = len(shape_path) - 1

    for i in range(len(points) - 1):
        start_idx = shape_stop_indices[i]
        end_idx = shape_stop_indices[i + 1]
        segment = shape_path[start_idx:end_idx + 1]
        if len(segment) < 2 and start_idx < len(shape_path) - 1:
            segment = shape_path[start_idx:start_idx + 2]
        elif len(segment) < 2 and start_idx > 0:
            segment = shape_path[start_idx - 1:start_idx + 1]
        if len(segment) < 2:
            continue
        dist = _path_segment_distance(segment)
        duration = max(15, int((dist / avg_speed) * 3600))
        legs.append({
            "segment": segment,
            "duration": duration,
            "distance_km": dist,
            "from_idx": i,
            "to_idx": i + 1,
        })
    return legs


def _build_journey_phases(legs: list, stop_count: int) -> list:
    STOP_WAIT = 5
    TERMINAL_WAIT = 300
    phases = []
    route_distance_km = 0.0
    for leg in legs:
        leg_distance_km = leg.get("distance_km", 0.0)
        phases.append({
            "type": "travel",
            "segment": leg["segment"],
            "duration": leg["duration"],
            "distance_start_km": route_distance_km,
            "distance_km": leg_distance_km,
            "from_idx": leg["from_idx"],
            "to_idx": leg["to_idx"],
        })
        route_distance_km += leg_distance_km
        arrival_point = leg["segment"][-1]
        if leg["to_idx"] == stop_count - 1:
            phases.append({
                "type": "terminal",
                "stop_idx": leg["to_idx"],
                "duration": TERMINAL_WAIT,
                "route_distance_km": route_distance_km,
                "position": arrival_point,
            })
        else:
            phases.append({
                "type": "at_stop",
                "stop_idx": leg["to_idx"],
                "duration": STOP_WAIT,
                "route_distance_km": route_distance_km,
                "position": arrival_point,
            })
    return phases


def _resolve_phase_state(phases: list, display_points: list, cycle_offset: float) -> dict:
    elapsed = cycle_offset
    for phase in phases:
        if elapsed < phase["duration"]:
            if phase["type"] == "travel":
                progress = elapsed / phase["duration"] if phase["duration"] else 0.0
                lat, lng, bearing, path_idx = _position_on_path(phase["segment"], progress)
                shape_point = phase["segment"][path_idx]
                distance_start_km = phase.get("distance_start_km", 0.0)
                route_distance_km = distance_start_km + (phase.get("distance_km", 0.0) * progress)
                return {
                    "phase": "travel",
                    "lat": lat,
                    "lng": lng,
                    "bearing": bearing,
                    "shape_point_index": shape_point.get("shape_index"),
                    "current_stop_idx": phase["from_idx"],
                    "next_stop_idx": phase["to_idx"],
                    "progress": progress,
                    "route_distance_km": route_distance_km,
                    "phase_elapsed": elapsed,
                    "phase_duration": phase["duration"],
                    "status": "IN PROGRESS",
                }
            stop_idx = phase["stop_idx"]
            pt = phase["position"]
            status = "ARRIVED TERMINAL" if phase["type"] == "terminal" else "AT BUS STAND"
            next_idx = min(stop_idx + 1, len(display_points) - 1)
            prev_idx = max(stop_idx - 1, 0)
            if phase["type"] == "terminal":
                bearing = _bearing_between_points(display_points[prev_idx], display_points[stop_idx])
            elif next_idx > stop_idx:
                bearing = _bearing_between_points(display_points[stop_idx], display_points[next_idx])
            else:
                bearing = _bearing_between_points(display_points[prev_idx], display_points[stop_idx])
            return {
                "phase": phase["type"],
                "lat": pt["lat"],
                "lng": pt["lng"],
                "bearing": bearing,
                "shape_point_index": pt.get("shape_index"),
                "current_stop_idx": stop_idx,
                "next_stop_idx": next_idx,
                "progress": 1.0 if stop_idx == len(display_points) - 1 else stop_idx / max(1, len(display_points) - 1),
                "route_distance_km": phase.get("route_distance_km", 0.0),
                "phase_elapsed": elapsed,
                "phase_duration": phase["duration"],
                "status": status,
            }
        elapsed -= phase["duration"]

    last = display_points[-1]
    return {
        "phase": "terminal",
        "lat": phases[-1]["position"]["lat"],
        "lng": phases[-1]["position"]["lng"],
        "bearing": _bearing_between_points(display_points[-2], display_points[-1]) if len(display_points) >= 2 else 0.0,
        "shape_point_index": phases[-1]["position"].get("shape_index"),
        "current_stop_idx": len(display_points) - 1,
        "next_stop_idx": len(display_points) - 1,
        "progress": 1.0,
        "route_distance_km": phases[-1].get("route_distance_km", 0.0),
        "phase_elapsed": phases[-1].get("duration", 0),
        "phase_duration": phases[-1].get("duration", 0),
        "status": "ARRIVED TERMINAL",
    }


def _phase_list_duration(phases: list) -> int:
    return sum(p["duration"] for p in phases)


def _route_geometry_path(route, trip=None) -> list:
    trip = _resolve_trip_for_route(route, trip)
    shape_path = _shape_path_for_trip(trip) if trip else []
    if shape_path:
        return shape_path
    points = _route_points_for(route, trip)
    return [{"lat": p["lat"], "lng": p["lng"]} for p in points]


def _complete_active_trips(bus_id: int) -> None:
    Trip.query.filter(
        Trip.bus_id == bus_id,
        Trip.status.in_(ACTIVE_TRIP_STATUSES)
    ).update(
        {"status": "completed", "end_time": datetime.now(UTC)},
        synchronize_session=False
    )


def _create_trip_for_bus(bus: Bus, route_id: int) -> Trip:
    template_trip = _gtfs_backed_trip_for_route(route_id)
    new_trip = Trip(
        bus_id=bus.id,
        route_id=route_id,
        shape_id=template_trip.shape_id if template_trip else None,
        direction_id=getattr(template_trip, "direction_id", None) if template_trip else None,
        start_time=None,
        status="ready"
    )
    db.session.add(new_trip)
    db.session.flush()
    if template_trip:
        _copy_stop_times_from_template(new_trip, template_trip)
    else:
        route = db.session.get(Route, route_id)
        if route:
            _ensure_trip_stop_times_from_route(new_trip, route)
    logger.info(
        "[ROUTE_ASSIGN] bus_id=%s bus_number=%s bus.route_id=%s trip.route_id=%s shape_id=%s",
        bus.id, bus.bus_number, route_id, route_id,
        new_trip.shape_id
    )
    return new_trip


def _active_trip_for_bus(bus: Bus) -> Optional[Trip]:
    if not bus:
        return None
    return (
        Trip.query.filter(Trip.bus_id == bus.id, Trip.status.in_(ACTIVE_TRIP_STATUSES))
        .order_by(Trip.start_time.desc())
        .first()
    )


def _driver_dashboard_trip_for_bus(bus: Optional[Bus]) -> Optional[Trip]:
    if not bus:
        return None
    return (
        Trip.query.filter(
            Trip.bus_id == bus.id,
            Trip.status.in_(("active", "in_progress", "return_ready", "ready", "scheduled"))
        )
        .order_by(
            case(
                (Trip.status.in_(ACTIVE_TRIP_STATUSES), 0),
                (Trip.status == "return_ready", 1),
                (Trip.status.in_(("ready", "scheduled")), 2),
                else_=3,
            ),
            Trip.created_at.desc(),
            Trip.id.desc(),
        )
        .first()
    )


def _trip_state_label(trip: Optional[Trip], bus: Optional[Bus] = None) -> str:
    if not trip:
        return "OFFLINE"
    status = (trip.status or "").strip().lower()
    if status in ACTIVE_TRIP_STATUSES:
        return "ACTIVE"
    if status == "return_ready":
        return "RETURN_READY"
    if status in {"ready", "scheduled"}:
        return "NOT_STARTED"
    if status == "completed":
        return "COMPLETED"
    if bus and not bus.is_active:
        return "OFFLINE"
    return status.upper() or "OFFLINE"


def _prepare_return_trip(bus: Bus, completed_trip: Trip) -> Trip:
    existing = (
        Trip.query.filter_by(bus_id=bus.id, status="return_ready")
        .order_by(Trip.id.desc())
        .first()
    )
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
            _copy_reversed_stop_times_from_trip(existing, completed_trip)
        return existing

    return_trip = Trip(
        bus_id=bus.id,
        route_id=completed_trip.route_id,
        shape_id=completed_trip.shape_id,
        direction_id=0 if getattr(completed_trip, "direction_id", 0) == 1 else 1,
        start_time=None,
        end_time=None,
        status="return_ready",
    )
    db.session.add(return_trip)
    db.session.flush()
    _copy_reversed_stop_times_from_trip(return_trip, completed_trip)
    return return_trip


def _repair_live_trip_stop_times_from_gtfs() -> list:
    repairs = []
    repair_statuses = ("active", "in_progress", "ready", "scheduled")
    trips = (
        Trip.query
        .filter(Trip.bus_id.isnot(None), Trip.status.in_(repair_statuses))
        .order_by(Trip.id.asc())
        .all()
    )
    for trip in trips:
        if getattr(trip, "direction_id", 0) == 1:
            continue
        route = db.session.get(Route, trip.route_id)
        if not route:
            continue
        points = _route_points_for_assigned_trip(route, trip)
        if not _route_endpoint_validation_error(route, trip, points):
            continue

        template_trip = _gtfs_backed_trip_for_route(trip.route_id)
        if not template_trip:
            repairs.append({
                "trip_id": trip.id,
                "route_id": trip.route_id,
                "repaired": False,
                "reason": "No canonical GTFS trip for route",
            })
            continue
        if trip.shape_id and template_trip.shape_id != trip.shape_id:
            repairs.append({
                "trip_id": trip.id,
                "route_id": trip.route_id,
                "repaired": False,
                "reason": "Assigned trip shape differs from canonical GTFS shape",
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
        repairs.append({
            "trip_id": trip.id,
            "route_id": trip.route_id,
            "template_trip_id": template_trip.id,
            "repaired": not _route_endpoint_validation_error(route, trip, after_points),
            "before": before,
            "after": after,
        })

    if repairs:
        logger.warning("[GTFS_TRACKING_REPAIR] %s", repairs)
    return repairs


def _start_driver_trip(bus: Bus, requested_return: bool = False) -> Trip:
    if not bus.route_id:
        raise ValueError("Assigned bus has no route.")

    trip = None
    if requested_return:
        trip = (
            Trip.query.filter_by(bus_id=bus.id, status="return_ready")
            .order_by(Trip.id.desc())
            .first()
        )
    if not trip:
        trip = (
            Trip.query.filter(
                Trip.bus_id == bus.id,
                Trip.status.in_(("ready", "scheduled", "return_ready"))
            )
            .order_by(
                case((Trip.status == "return_ready", 0), else_=1),
                Trip.id.desc(),
            )
            .first()
        )
    if not trip:
        trip = _create_trip_for_bus(bus, bus.route_id)

    _complete_active_trips(bus.id)
    trip.status = "active"
    trip.start_time = datetime.now(UTC)
    trip.end_time = None
    route = db.session.get(Route, trip.route_id)
    points = _route_points_for_assigned_trip(route, trip) if route else []
    route_path = _route_geometry_path_for_assigned_trip(trip)
    validation_error = _assigned_trip_validation_error(route, trip, points, route_path)
    if validation_error:
        raise ValueError(validation_error)
    bus.is_active = True
    LIVE_GPS_DATA.pop(bus.id, None)
    BUS_DELAY_DATA.pop(bus.id, None)
    return trip


def _end_driver_trip(bus: Bus) -> tuple[Trip, Trip]:
    trip = _active_trip_for_bus(bus)
    if not trip:
        raise ValueError("No active trip to end.")
    trip.status = "completed"
    trip.end_time = datetime.now(UTC)
    bus.is_active = False
    LIVE_GPS_DATA.pop(bus.id, None)
    BUS_DELAY_DATA.pop(bus.id, None)
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

def _get_active_subscriptions_cache():
    cache = []
    try:
        subs = Subscription.query.filter_by(active=True).all()
        for sub in subs:
            stop = db.session.get(Stop, sub.stop_id)
            if stop: cache.append({'user_id': sub.user_id, 'route_id': stop.route_id, 'stop_name': stop.stop_name})
    except Exception: db.session.rollback()
    return cache


def _cleanup_tracking_sessions(now: Optional[float] = None) -> None:
    now = now or time.time()
    expired = [
        user_id for user_id, session_data in PASSENGER_TRACKING_SESSIONS.items()
        if now - float(session_data.get("timestamp") or 0) > TRACKING_SESSION_TTL_SECONDS
    ]
    for user_id in expired:
        PASSENGER_TRACKING_SESSIONS.pop(user_id, None)


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
            f"🚌 Bus Delay Alert\n\n"
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
    if now_seconds - timestamp >= 30:
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


def _live_tracking_validation_snapshot(bus: Bus, trip, route: Optional[Route], message: str,
                                       gps: Optional[dict] = None) -> dict:
    driver_name_out, driver_code_out = _driver_display_fields(bus)
    occ_pct, occ_level = _latest_recorded_occupancy_for_bus(bus)
    trip_id = getattr(trip, "id", None) if trip else None
    shape_id = getattr(trip, "shape_id", None) if trip else None
    route_id = getattr(route, "id", None) if route else getattr(trip, "route_id", None)
    route_code = getattr(route, "route_code", None) if route else None
    route_name = getattr(route, "name", None) if route else None
    now_iso = datetime.now(UTC).isoformat()
    return {
        "bus_id": bus.id,
        "bus_number": bus.bus_number,
        "registration_number": bus.registration_number,
        "driver_id": driver_code_out,
        "driver_name": driver_name_out,
        "assigned_driver_id": bus.assigned_driver_id,
        "assigned_driver_code": driver_code_out,
        "assigned_driver_name": driver_name_out,
        "sos_active": False,
        "route_id": route_id,
        "route_code": route_code or "BUS-RT",
        "route_name": route_name or "Tracking Validation Error",
        "status": "Validation Error",
        "service_status": "validation_error",
        "bus_status": "LIVE" if bus.is_active else "OFFLINE",
        "trip_status": _trip_state_label(trip, bus),
        "gps_status": "LIVE GPS" if gps else "Waiting for GPS",
        "speed": None,
        "occupancy_pct": occ_pct,
        "occupancy_level": occ_level,
        "direction": "backward" if getattr(trip, "direction_id", 0) == 1 else "forward",
        "current_stop_index": 0,
        "completed_stops": 0,
        "trip_progress": 0,
        "source_stop": getattr(route, "origin", None) or "Waiting for GPS",
        "destination_stop": getattr(route, "destination", None) or "Calculating...",
        "current_stop": "Waiting for GPS",
        "next_stop": "Calculating...",
        "distance_remaining_km": 0,
        "distance_covered_km": 0,
        "eta_minutes": None,
        "base_eta_minutes": None,
        "updated_eta_minutes": None,
        "next_stop_eta_minutes": None,
        "eta_label": "Waiting for GPS" if gps else "Offline",
        "bearing": None,
        "current_lat": gps.get("lat") if gps else None,
        "current_lon": gps.get("lon") if gps else None,
        "is_live_gps": bool(gps),
        "gps_timestamp": datetime.fromtimestamp(gps["timestamp"], UTC).isoformat() if gps else now_iso,
        "shape_id": shape_id,
        "shape_point_count": 0,
        "shape_points_db": _shape_point_count_db(shape_id),
        "shape_points_api": 0,
        "points_removed": _shape_point_count_db(shape_id),
        "shape_point_index": None,
        "movement_state": "validation_error",
        "path": [],
        "stops": [],
        "geometry_available": False,
        "geometry_message": message,
        "validation_error": message,
        "trip_id": trip_id,
        "schedule": _route_schedule_for_assigned_trip(route, trip),
        "departure_time": "Waiting for GPS",
        "arrival_time": "Calculating...",
        "updated_arrival_time": "Calculating...",
        "journey_duration": "Calculating...",
        "journey_duration_minutes": None,
        "schedule_status": "VALIDATION ERROR",
        "delay_status": "VALIDATION ERROR",
        "current_delay_minutes": 0,
        "current_delay_seconds": 0,
        "current_delay_label": "0 min",
        "current_delay_reason": message,
        "remaining_delay_minutes": 0,
        "current_stop_scheduled_time": "Waiting for GPS",
        "current_stop_actual_time": "Waiting for GPS",
        "next_stop_scheduled_time": "Calculating...",
        "next_stop_expected_time": "Calculating...",
        "display_schedule_stops": [],
    }


def _real_gps_bus_snapshot(bus: Bus, trip, route: Route, gps: dict) -> dict:
    points = _route_points_for_assigned_trip(route, trip)
    route_path = _route_geometry_path_for_assigned_trip(trip)
    validation_error = _assigned_trip_validation_error(route, trip, points, route_path)
    if validation_error:
        return _live_tracking_validation_snapshot(bus, trip, route, validation_error, gps)
    direction = "backward" if getattr(trip, "direction_id", 0) == 1 else "forward"
    if direction == "backward":
        route_path = list(reversed(route_path))
    lat = gps["lat"]
    lon = gps["lon"]
    current_stop_idx = _nearest_route_index(lat, lon, points)
    next_stop_idx = min(current_stop_idx + 1, len(points) - 1) if points else 0
    path_index = _nearest_route_index(lat, lon, route_path)
    path_distance_km = _path_segment_distance(route_path) if len(route_path) >= 2 else 0.0
    try:
        covered_km = float(gps.get("distance_covered_km") or 0.0)
    except (TypeError, ValueError):
        covered_km = 0.0
    covered_km = max(0.0, min(path_distance_km, covered_km)) if path_distance_km else max(0.0, covered_km)
    remaining_km = max(0.0, path_distance_km - covered_km)
    trip_progress = (covered_km / path_distance_km * 100.0) if path_distance_km else 0.0
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

    def _optional_float(*keys):
        for key in keys:
            value = gps.get(key)
            if value is None:
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return None

    shape_id = getattr(trip, "shape_id", None) if trip else None
    delay_minutes = int(schedule_payload.get("current_delay_minutes") or 0)
    live_speed = _optional_float("speed", "velocity")
    completed_stops = max(0, min(len(points), int(gps.get("completed_stops") or 0)))
    active_stop_index = min(completed_stops, max(0, len(points) - 1)) if points else 0
    eta_minutes = None
    if live_speed and live_speed > 1 and remaining_km > 0:
        eta_minutes = max(1, int(math.ceil((remaining_km / live_speed) * 60)))
    eta_label = f"{eta_minutes} min" if eta_minutes is not None else "--"
    return {
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
        "route_name": route.name or "Tracking Active",
        "status": "IN PROGRESS",
        "service_status": "delayed" if delay_minutes > 0 else "on_time",
        "bus_status": "LIVE",
        "trip_status": "ACTIVE",
        "gps_status": "LIVE GPS",
        "speed": live_speed,
        "occupancy_pct": occ_pct,
        "occupancy_level": occ_level,
        "direction": direction,
        "current_stop_index": current_stop_idx,
        "completed_stops": completed_stops,
        "active_stop_index": active_stop_index,
        "trip_progress": round(trip_progress, 3),
        "source_stop": points[0]["name"] if points else (route.origin or "--"),
        "destination_stop": points[-1]["name"] if points else (route.destination or "--"),
        "current_stop": points[current_stop_idx]["name"] if points else "--",
        "next_stop": points[next_stop_idx]["name"] if points else "--",
        "distance_remaining_km": round(remaining_km, 2),
        "distance_covered_km": round(covered_km, 2),
        "eta_minutes": eta_minutes,
        "base_eta_minutes": eta_minutes,
        "updated_eta_minutes": eta_minutes,
        "next_stop_eta_minutes": eta_minutes,
        "eta_label": eta_label,
        "bearing": _optional_float("bearing", "heading", "course"),
        "current_lat": lat,
        "current_lon": lon,
        "is_live_gps": True,
        "gps_timestamp": datetime.fromtimestamp(gps["timestamp"], UTC).isoformat(),
        "shape_id": shape_id,
        "shape_point_count": len(route_path),
        "shape_points_db": _shape_point_count_db(shape_id),
        "shape_points_api": len(route_path),
        "points_removed": max(0, _shape_point_count_db(shape_id) - len(route_path)),
        "shape_point_index": path_index if route_path else None,
        "movement_state": "live_gps",
        "path": route_path,
        "stops": stop_payload,
        "geometry_available": True,
        "geometry_message": None,
        "trip_id": trip.id if trip and getattr(trip, "id", None) else None,
        "actual_departure_time": trip.start_time.strftime("%H:%M") if trip and trip.start_time else "--",
        "actual_arrival_time": trip.end_time.strftime("%H:%M") if trip and trip.end_time else "--",
        **schedule_payload,
    }


def _completed_trip_snapshot(bus: Bus, trip: Trip, route: Route) -> dict:
    points = _route_points_for_assigned_trip(route, trip)
    route_path = _route_geometry_path_for_assigned_trip(trip)
    validation_error = _assigned_trip_validation_error(route, trip, points, route_path)
    if validation_error:
        completed_message = f"Trip Completed. {validation_error}"
        snapshot = _live_tracking_validation_snapshot(bus, trip, route, completed_message, None)
        snapshot.update({
            "status": "Trip Completed",
            "service_status": "completed",
            "bus_status": "OFFLINE",
            "trip_status": "COMPLETED",
            "gps_status": "Offline",
            "eta_label": "Offline",
            "geometry_message": completed_message,
            "validation_error": validation_error,
            "gps_timestamp": trip.end_time.isoformat() if trip.end_time else snapshot.get("gps_timestamp"),
            "completed_at": trip.end_time.isoformat() if trip.end_time else None,
        })
        return snapshot
    direction = "backward" if getattr(trip, "direction_id", 0) == 1 else "forward"
    if direction == "backward":
        route_path = list(reversed(route_path))

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

    final_point = points[final_idx] if points else None
    path_distance_km = _path_segment_distance(route_path) if len(route_path) >= 2 else 0.0
    shape_id = getattr(trip, "shape_id", None) if trip else None

    return {
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
        "route_name": route.name or "Tracking Completed",
        "status": "Trip Completed",
        "service_status": "completed",
        "bus_status": "OFFLINE",
        "trip_status": "COMPLETED",
        "gps_status": "Offline",
        "speed": 0,
        "occupancy_pct": occ_pct,
        "occupancy_level": occ_level,
        "direction": direction,
        "current_stop_index": final_idx,
        "completed_stops": len(points),
        "trip_progress": 100,
        "source_stop": points[0]["name"] if points else (route.origin or "--"),
        "destination_stop": points[-1]["name"] if points else (route.destination or "--"),
        "current_stop": final_point["name"] if final_point else "--",
        "next_stop": "--",
        "distance_remaining_km": 0,
        "distance_covered_km": round(path_distance_km, 2),
        "eta_minutes": 0,
        "base_eta_minutes": 0,
        "updated_eta_minutes": 0,
        "next_stop_eta_minutes": 0,
        "eta_label": "Offline",
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
        "stops": stop_payload,
        "geometry_available": True,
        "geometry_message": None,
        "trip_id": trip.id if trip and getattr(trip, "id", None) else None,
        **schedule_payload,
    }


def _live_fleet_snapshot() -> list:
    snapshot = []
    now_seconds = time.time()
    queued_delay_notifications = 0
    active_sos_bus_ids = {
        row[0]
        for row in db.session.query(SOSAlert.bus_id)
        .filter(SOSAlert.status.in_(ACTIVE_SOS_STATUSES))
        .all()
    }

    stale_buses = [
        b_id
        for b_id, data in LIVE_GPS_DATA.items()
        if now_seconds - data["timestamp"] >= 30
    ]

    for b_id in stale_buses:
        del LIVE_GPS_DATA[b_id]

    active_buses = Bus.query.filter_by(
        is_active=True
    ).all()

    for bus in active_buses:

        real_gps = _fresh_gps_packet(bus.id, now_seconds)
        if not real_gps:
            continue

        trip = _active_trip_for_bus(bus)

        if not trip:
            continue

        route = db.session.get(
            Route,
            trip.route_id
        )

        if route is None:
            continue

        try:
            bus_data = _real_gps_bus_snapshot(bus, trip, route, real_gps)
        except Exception as exc:
            logger.exception("[FLEET] real GPS snapshot failed for bus %s: %s", bus.bus_number, exc)
            continue

        if bus_data:
            bus_data["sos_active"] = bus.id in active_sos_bus_ids
            try:
                queued_delay_notifications += _queue_meaningful_delay_notifications(bus_data, route, trip)
            except Exception as exc:
                logger.warning("[DELAY_NOTIFY] skipped for bus %s: %s", bus.bus_number, exc)
            snapshot.append(bus_data)

    if queued_delay_notifications:
        try:
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            logger.warning("[DELAY_NOTIFY] commit failed: %s", exc)

    return snapshot

def _admin_shell_metrics(include_snapshot: bool = False) -> dict:
    """Return admin page metrics without forcing live telemetry simulation."""
    total_buses = Bus.query.count()
    snapshot = _live_fleet_snapshot() if include_snapshot else []
    running = delayed = maintenance = offline = 0
    for b in snapshot:
        st = b.get("service_status", "")
        if st == "offline":
            offline += 1
        elif st == "maintenance":
            maintenance += 1
        elif st == "delayed":
            delayed += 1
        else:
            running += 1

    return {
        "total_buses": total_buses,
        "active_buses": (running + delayed) if include_snapshot else Bus.query.filter_by(is_active=True).count(),
        "running": running,
        "delayed": delayed,
        "maintenance": maintenance,
        "offline": offline,
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
    def google_register():
        full_name = (request.form.get("full_name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        if not email or not full_name:
            flash("Invalid Google account profile data.", "danger")
            return redirect(url_for("register_page"))
        user = User.query.filter_by(email=email).first()
        if user:
            flash("Email already exists. Please log in.", "warning")
            return redirect(url_for("login_page"))

        random_password = secrets.token_urlsafe(32)
        new_user = User(full_name=full_name, email=email, role="passenger", auth_provider="google")
        new_user.set_password(random_password)
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        return redirect(url_for("passenger_dashboard"))

    @app.route("/forgot-password", methods=["GET", "POST"])
    def forgot_password():
        if current_user.is_authenticated:
            return redirect(url_for(_dashboard_route_for_role(current_user.role)))

        submitted_email = ""
        if request.method == "POST":
            wants_json = _request_wants_json()
            submitted_email = (request.form.get("email") or "").strip().lower()
            if not submitted_email:
                if wants_json:
                    return jsonify({
                        "success": False,
                        "message": "Registered passenger email is required.",
                    }), 400
                flash("Registered passenger email is required.", "danger")
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
            if len(password) < min_length:
                flash(f"Password must be at least {min_length} characters.", "danger")
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
    def login_page():
        if current_user.is_authenticated: return redirect(url_for(_dashboard_route_for_role(current_user.role)))
        if request.method == "POST":
            email = (request.form.get("email") or "").strip().lower()
            password = request.form.get("password") or ""
            login_type = request.form.get("login_type") or "passenger"
            driver_id = request.form.get("driver_id")
            admin_id = request.form.get("admin_id")

            if not email or not password:
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
                    flash("No bus assigned to this Driver ID.", "danger")
                    return render_template("login.html")
                session["driver_code"] = formatted_code
                session["assigned_bus_id"] = assigned_bus.id
            
            if login_type == "admin":
                if user.role != "admin":
                    flash("Account is not an admin profile.", "danger")
                    return render_template("login.html")
                formatted_admin = _resolve_transpulse_id(admin_id or "", "admin")
                user_tid = user.transpulse_id or _admin_transpulse_id_for_user(user.id)
                if not formatted_admin or user_tid != formatted_admin:
                    flash("Admin ID does not match this user account profile.", "danger")
                    return render_template("login.html")

            login_user(user)
            return redirect(url_for(_dashboard_route_for_role(current_user.role)))
        return render_template("login.html")

    @app.route("/google_login", methods=["POST"])
    def google_login():
        email = (request.form.get("email") or "").strip().lower()
        if not email:
            flash("Google authentication payload missing.", "danger")
            return redirect(url_for("login_page"))
        user = User.query.filter_by(email=email).first()
        if not user:
            flash("Google account not found. Please register first.", "danger")
            return redirect(url_for("register_page"))
        if getattr(user, 'auth_provider', 'local') != "google":
            flash("This account was created locally. Please sign in with your password.", "warning")
            return redirect(url_for("login_page"))
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
                    is_active=True
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
                bus.is_active = True

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
                db.session.commit()

                if route_id:
                    _complete_active_trips(bus.id)
                    _create_trip_for_bus(bus, route_id)
                    db.session.commit()

                flash(f"Bus {bus_number} saved successfully.", "success")
            except IntegrityError:
                db.session.rollback()
                if assigned_driver_code_raw and _driver_code_taken(_normalize_driver_code(assigned_driver_code_raw)):
                    flash("Driver ID Already Assigned To Another Bus", "danger")
                else:
                    flash("Registration Number Already Exists", "danger")

            return redirect(url_for("admin_buses"))

        buses = Bus.query.order_by(Bus.created_at.desc()).all()
        for b in buses:
            trip = _active_trip_for_bus(b)
            route_ref = b.route_id or (trip.route_id if trip else None)
            b.route = db.session.get(Route, route_ref) if route_ref else None
            if b.route and trip:
                stops_data = _route_points_for(b.route, trip)
                b.route.intermediate_stops = ", ".join([s["name"] for s in stops_data[1:-1]]) if len(stops_data) > 2 else None

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
            bus.capacity = int(request.form.get("capacity", bus.capacity))
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
                bus.route_id = new_route_id
                _complete_active_trips(bus.id)
                _create_trip_for_bus(bus, new_route_id)
                _mark_route_operational(new_route_id)

            existing_reg = Bus.query.filter_by(registration_number=bus.registration_number).first()
            if existing_reg and existing_reg.id != bus.id:
                flash("Registration Number Already Exists", "danger")
                return redirect(url_for("edit_bus", bus_id=bus.id))

            try:
                db.session.commit()
                flash(f"Bus {bus.bus_number} updated successfully.", "success")
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
            db.session.commit()
            flash(f"Route {route.route_code} updated successfully.", "success")
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
            if (
                assigned_trip
                and (assigned_trip.status or "").strip().lower() in ACTIVE_TRIP_STATUSES
                and not _fresh_gps_packet(assigned_bus.id, time.time())
            ):
                driver_trip_state = "NOT_STARTED"

            if assigned_route and assigned_trip:
                driver_route_points = _route_points_for_assigned_trip(assigned_route, assigned_trip)
                driver_schedule = _route_schedule_for_assigned_trip(assigned_route, assigned_trip)
            elif assigned_route:
                driver_route_points = _route_points_for(assigned_route, None)
                driver_schedule = _route_schedule_for(assigned_route, None)
            else:
                driver_schedule = {}

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
                "sourceStop": (
                    assigned_route.origin
                    if assigned_route and assigned_route.origin
                    else (driver_route_points[0]["name"] if driver_route_points else "--")
                ),
                "destinationStop": (
                    assigned_route.destination
                    if assigned_route and assigned_route.destination
                    else (driver_route_points[-1]["name"] if driver_route_points else "--")
                ),
                "currentStop": driver_route_points[0]["name"] if driver_route_points else "--",
                "nextStop": driver_route_points[1]["name"] if len(driver_route_points) > 1 else "--",
                "totalStops": len(driver_route_points),
                "scheduledDeparture": driver_schedule.get("departure_time", "--"),
                "scheduledArrival": driver_schedule.get("arrival_time", "--"),
            }

        if request.method == "POST":
            action = request.form.get("action")
            if not assigned_trip: return redirect(url_for("driver_dashboard"))
            
            if action == "start":
                _start_driver_trip(assigned_bus, requested_return=(assigned_trip.status == "return_ready"))
            elif action == "end":
                _end_driver_trip(assigned_bus)
            
            db.session.commit()
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
        try:
            trip = _start_driver_trip(
                assigned_bus,
                requested_return=bool(data.get("return_trip"))
            )
            db.session.commit()
            return jsonify({
                "success": True,
                "trip_id": trip.id,
                "trip_status": _trip_state_label(trip, assigned_bus),
                "bus_status": "LIVE",
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
        try:
            completed_trip, return_trip = _end_driver_trip(assigned_bus)
            db.session.commit()
            return jsonify({
                "success": True,
                "completed_trip_id": completed_trip.id,
                "return_trip_id": return_trip.id,
                "trip_status": "COMPLETED",
                "next_trip_status": "RETURN_READY",
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
            LIVE_GPS_DATA.pop(assigned_bus.id, None)
            return jsonify({"error": "Trip is not active"}), 409

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
        route_points = _route_points_for_assigned_trip(route, active_trip) if route else []
        current_stop_index = _nearest_route_index(lat, lng, route_points) if route_points else 0
        if route_points:
            completed_stops = max(0, min(completed_stops, len(route_points)))
            target_stop_index = completed_stops
            if same_trip and gps_delta_km > 0.01 and target_stop_index < len(route_points):
                target = route_points[target_stop_index]
                distance_to_target = _haversine_km(lat, lng, target["lat"], target["lng"])
                if distance_to_target <= DRIVER_STOP_COMPLETION_THRESHOLD_KM:
                    completed_stops = min(len(route_points), completed_stops + 1)

        bearing = None
        for key in ("bearing", "heading", "course"):
            try:
                raw_bearing = data.get(key)
                if raw_bearing is not None:
                    bearing = float(raw_bearing)
                    break
            except (TypeError, ValueError):
                bearing = None

        LIVE_GPS_DATA[assigned_bus.id] = {
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
        }

        return jsonify({"success": True})

   
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
                
        db.session.commit()
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

        stop_id = data.get("stop_id")
        if not stop_id:
            return jsonify({"error": "stop_id is required"}), 400

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

        db.session.commit()

        return jsonify({
            "success": True,
            "active": sub.active
        }), 200

    @app.route("/api/tracking/session", methods=["POST"])
    @login_required
    def api_tracking_session():
        if current_user.role != "passenger":
            return jsonify({"error": "Unauthorized"}), 403

        data = request.get_json(silent=True) or {}

        try:
            bus_id = int(data.get("bus_id"))
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid bus_id"}), 400

        if bus_id <= 0:
            return jsonify({"error": "Invalid bus_id"}), 400

        bus = db.session.get(Bus, bus_id)
        if not bus:
            return jsonify({"error": "Bus not found"}), 404

        try:
            route_id = int(data.get("route_id")) if data.get("route_id") is not None else None
        except (TypeError, ValueError):
            route_id = None

        try:
            trip_id = int(data.get("trip_id")) if data.get("trip_id") is not None else None
        except (TypeError, ValueError):
            trip_id = None

        _record_passenger_tracking_session(
            current_user.id,
            bus_id,
            route_id,
            trip_id
        )

        return jsonify({"success": True}), 200
    
    @app.route("/api/notifications/<int:notif_id>/read", methods=["POST"])
    @login_required
    def api_notifications_read(notif_id):
        notif = db.get_or_404(Notification, notif_id)
        if notif.recipient_id != current_user.id: return jsonify({"error": "Unauthorized"}), 403
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
            data = request.get_json() or request.form.to_dict()
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
            .order_by(Complaint.created_at.desc())
            .all()
        )
        payload = []
        for c in complaints:
            cd = c.to_dict()
            user = db.session.get(User, c.passenger_id)
            cd['author_name'] = user.full_name if user else "Passenger User"
            cd['author_role'] = user.role if user else "passenger"
            bus = db.session.get(Bus, c.bus_id) if c.bus_id else None
            route = db.session.get(Route, c.route_id) if c.route_id else None
            driver = db.session.get(User, c.driver_id) if c.driver_id else None
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
            data = request.get_json() or request.form.to_dict()
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
                    if data.get("lost_date"): item.incident_date = datetime.strptime(data.get("lost_date"), '%Y-%m-%d')
                    item.contact_phone = data.get("contact_number", item.contact_phone)
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

            if data.get("driver_id"):
                matched_driver_bus = _bus_for_driver_code(data.get("driver_id"))
                if matched_driver_bus and shared_driver and matched_bus is None:
                    assigned_driver_id = shared_driver.id
                    bus_id_val = matched_driver_bus.id
                    matched_bus = matched_driver_bus
                elif matched_bus and matched_bus.assigned_driver_code and shared_driver:
                    assigned_driver_id = shared_driver.id

            if route_id_val is None and matched_bus and matched_bus.route_id:
                route_id_val = matched_bus.route_id

            if bus_id_val is None or route_id_val is None:
                return jsonify({"error": "Valid bus number required. Bus must have an assigned route."}), 400

            item = LostAndFound(
                user_id=current_user.id,
                item_name=data.get("item_category", "Unknown"),
                description=desc,
                color=data.get("color", ""),
                brand=data.get("brand", ""),
                incident_date=datetime.strptime(data.get("lost_date"), '%Y-%m-%d') if data.get("lost_date") else datetime.now(UTC),
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
        items = items_query.order_by(LostAndFound.created_at.desc()).all()

        payload = []
        for i in items:
            bus = db.session.get(Bus, i.bus_id)
            route = db.session.get(Route, i.route_id)
            driver = db.session.get(User, i.assigned_driver_id) if i.assigned_driver_id else None
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
        data = request.get_json() or {}
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
            route_eta_values.setdefault(rid, []).append(b.get("eta_minutes", 0))

        active_route_ids = set(route_bus_count.keys())
        for bus in Bus.query.filter_by(is_active=True).filter(Bus.route_id.isnot(None)).all():
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
            active_bus = Bus.query.filter_by(route_id=route.id, is_active=True).order_by(Bus.id.asc()).first()
            trip = _active_trip_for_bus(active_bus) if active_bus else None
            if not trip:
                trip = (
                    Trip.query
                    .filter_by(route_id=route.id)
                    .filter(Trip.shape_id.isnot(None))
                    .order_by(Trip.id.asc())
                    .first()
                ) or Trip.query.filter_by(route_id=route.id).order_by(Trip.id.asc()).first()
            points = (
                _route_points_for_assigned_trip(route, trip)
                if active_bus and trip
                else _route_points_for(route, trip)
            )
            if not points:
                continue
            gtfs_path = (
                _route_geometry_path_for_assigned_trip(trip)
                if active_bus and trip
                else _route_geometry_path(route, trip)
            )
            direction = "backward" if getattr(trip, "direction_id", 0) == 1 else "forward"
            if active_bus and direction == "backward":
                gtfs_path = list(reversed(gtfs_path))
            display_geometry = _display_geometry_for_map(route, trip, points, gtfs_path)
            geom_path = display_geometry["path"] or gtfs_path
            etas = route_eta_values.get(route.id, [])
            avg_eta = int(sum(etas) / len(etas)) if etas else 0
            schedule = (
                _route_schedule_for_assigned_trip(route, trip)
                if active_bus and trip
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
                "display_geometry_source": display_geometry["source"],
                "generated_road_geometry_points": display_geometry["generated_point_count"],
                "active_bus_count": route_bus_count.get(route.id, 0),
                "eta_minutes": avg_eta,
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
            .filter_by(recipient_id=current_user.id)
            .order_by(Notification.created_at.desc())
            .limit(100)
            .all()
        )
        role = current_user.role
        payload = []
        for n in notifs:
            category = _notification_category_for_role(role, n.message)
            if not category:
                continue
            title = "Notification"
            if n.message.startswith("["):
                end = n.message.find("]")
                if end > 1:
                    title = n.message[1:end]
            payload.append({
                "id": n.id,
                "title": title,
                "message": n.message,
                "category": category,
                "is_read": n.is_read,
                "timestamp": n.created_at.strftime("%Y-%m-%d %H:%M") if n.created_at else "",
                "priority": _notification_priority(category, n.message),
            })
        return jsonify({"notifications": payload})

    @app.route("/api/notifications/unread", methods=["GET"])
    @login_required
    def get_unread_notifications():
        notifs = Notification.query.filter_by(recipient_id=current_user.id, is_read=False).all()
        role = current_user.role
        count = 0
        for n in notifs:
            if _notification_category_for_role(role, n.message):
                count += 1
        return jsonify({"unread_count": count})

    @app.route("/api/sos/trigger", methods=["POST"])
    @login_required
    @role_required("passenger")
    def sos_trigger_api():
        data = request.get_json() or request.form.to_dict()
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

        def _coordinate(raw_value):
            try:
                return float(raw_value) if raw_value not in (None, "") else None
            except (TypeError, ValueError):
                return None
        sos_msg = f"[SOS EMERGENCY] {bus_label}: {reason} — passenger {current_user.full_name} needs immediate assistance."

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
            payload.append({
                "id": alert.id,
                "passenger_name": passenger.full_name if passenger else "Unknown",
                "passenger_id": (passenger.transpulse_id or passenger.id) if passenger else alert.passenger_id,
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
    @role_required("admin", "passenger")
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

    if User.query.count() == 0:
        print("[TRANSPULSE SYSTEM ENGINE] Initializing core system accounts...")
        admin = User(
            full_name="TransPulse Admin",
            email="admin@transpulse.com",
            role="admin",
        )
        admin.set_password("Admin@123")
        db.session.add(admin)
        db.session.flush()
        admin.transpulse_id = _admin_transpulse_id_for_user(admin.id)

        passenger = User(full_name="AP Passenger", email="passenger@transpulse.com", role="passenger")
        passenger.set_password("Pass@123")
        db.session.add(passenger)

        db.session.commit()
        print("[TRANSPULSE SYSTEM ENGINE] Core accounts ready (admin + passenger only).")

    _ensure_shared_driver_account()
    _backfill_transpulse_ids()


app = create_app()

MAIL_SERVER = "smtp.gmail.com"
MAIL_PORT = 587
MAIL_USE_TLS = True

MAIL_USERNAME = "transpulse.official@gmail.com"
MAIL_PASSWORD = "iinc rcar lwow igor"

if __name__ == "__main__":
    app.run(debug=False)
