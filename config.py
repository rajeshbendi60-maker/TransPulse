from pathlib import Path
import os
import secrets


BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
INSTANCE_DIR.mkdir(exist_ok=True)
DATABASE_PATH = INSTANCE_DIR / "transpulse.db"

class Config:
    SECRET_KEY = os.environ.get(
        "SECRET_KEY",
        secrets.token_hex(32)
    )

    SQLALCHEMY_DATABASE_URI = f"sqlite:///{DATABASE_PATH.as_posix()}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False