import os
import secrets
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()


class Config:
    GO_API_URL = os.getenv("GO_API_URL", "http://localhost:8080").rstrip("/")
    GO_API_TIMEOUT = float(os.getenv("GO_API_TIMEOUT", "10"))

    SECRET_KEY = os.getenv("SECRET_KEY") or secrets.token_hex(32)
    SECRET_KEY_IS_EPHEMERAL = not os.getenv("SECRET_KEY")

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("COOKIE_SECURE", "0") == "1"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=int(os.getenv("SESSION_HOURS", "24")))

    # The web app only serves these two Go roles.
    ALLOWED_ROLES = ("customer", "seller")
