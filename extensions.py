from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_compress import Compress
from flask_migrate import Migrate
import os

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100000 per day", "10000 per hour"],
    storage_uri=os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
)
compress = Compress()
migrate = Migrate()
