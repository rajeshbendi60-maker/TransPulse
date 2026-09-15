from flask import Blueprint, jsonify, request
from flask_login import login_user, logout_user, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from models.user import User
from models import db
import logging
from .gtfs import success_response, error_response

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth_bp", __name__, url_prefix="/api/v1/auth")

@auth_bp.route("/passenger/register", methods=["POST"])
def register_passenger():
    data = request.json
    if not data:
        return error_response("Invalid request", 400)
    
    email = data.get("email")
    password = data.get("password")
    full_name = data.get("full_name")
    
    if User.query.filter_by(email=email).first():
        return error_response("Email already registered", 400)
        
    user = User(email=email, full_name=full_name, role="passenger")
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    
    login_user(user)
    
    return success_response({
        "token": "dummy-jwt-token-for-mobile",
        "user": user.to_dict()
    })

@auth_bp.route("/passenger/login", methods=["POST"])
def login_passenger():
    data = request.json
    email = data.get("email")
    password = data.get("password")
    
    user = User.query.filter_by(email=email, role="passenger").first()
    if user and user.check_password(password):
        login_user(user)
        return success_response({
            "token": "dummy-jwt-token-for-mobile",
            "user": user.to_dict()
        })
    return error_response("Invalid credentials", 401)

@auth_bp.route("/driver/login", methods=["POST"])
def login_driver():
    data = request.json
    email = data.get("email")
    password = data.get("password")
    
    user = User.query.filter_by(email=email, role="driver").first()
    if user and user.check_password(password):
        login_user(user)
        return success_response({
            "token": "dummy-jwt-token-for-mobile",
            "user": user.to_dict()
        })
    return error_response("Invalid credentials", 401)

@auth_bp.route("/admin/login", methods=["POST"])
def login_admin():
    data = request.json
    email = data.get("email")
    password = data.get("password")
    
    user = User.query.filter_by(email=email, role="district_admin").first()
    if user and user.check_password(password):
        login_user(user)
        return success_response({
            "token": "dummy-jwt-token-for-mobile",
            "user": user.to_dict()
        })
    return error_response("Invalid credentials", 401)

@auth_bp.route("/verify-firebase", methods=["POST"])
def verify_firebase():
    data = request.json
    firebase_token = data.get("token")
    phone_number = data.get("phoneNumber")
    # In a real scenario, we verify with Firebase Admin SDK.
    # For now, accept and return a JWT.
    
    # We find or create user based on phone (if phone exists) or email.
    return success_response({
        "token": "jwt-after-firebase-verification",
        "user": {
            "id": 1,
            "role": "passenger",
            "email": "phone-user@transpulse.com"
        }
    })

profile_bp = Blueprint("profile_bp", __name__, url_prefix="/api/v1")

@profile_bp.route("/profile", methods=["GET"])
def get_profile():
    if current_user.is_authenticated:
        return success_response(current_user.to_dict())
    return error_response("Unauthorized", 401)

@profile_bp.route("/districts", methods=["GET"])
def get_districts():
    # Return dummy districts for now
    return success_response([
        {"id": 1, "name": "District 1"},
        {"id": 2, "name": "District 2"}
    ])
# TP-v2.0-Release
