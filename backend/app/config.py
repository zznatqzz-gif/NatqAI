"""Environment-backed application settings."""
import os

APP_NAME = os.getenv("NATQAI_APP_NAME", "NatqAI API")
DATABASE_PATH = os.getenv("NATQAI_DATABASE", "./natqai.db")
SECRET_KEY = os.getenv("NATQAI_SECRET_KEY", "development-only-change-me")
TOKEN_TTL_SECONDS = int(os.getenv("NATQAI_TOKEN_TTL", "86400"))
DAILY_MESSAGE_LIMIT = int(os.getenv("NATQAI_DAILY_MESSAGE_LIMIT", "100"))
ENVIRONMENT = os.getenv("NATQAI_ENV", "development").strip().lower()
CORS_ORIGINS = tuple(
    origin.strip()
    for origin in os.getenv(
        "NATQAI_CORS_ORIGINS", "http://localhost:3000,http://localhost:5173"
    ).split(",")
    if origin.strip()
)


def validate_settings() -> None:
    """Reject unsafe production configuration before serving requests."""
    if DAILY_MESSAGE_LIMIT < 1 or DAILY_MESSAGE_LIMIT > 1_000_000:
        raise RuntimeError("NATQAI_DAILY_MESSAGE_LIMIT must be between 1 and 1000000")
    if TOKEN_TTL_SECONDS < 60 or TOKEN_TTL_SECONDS > 60 * 60 * 24 * 30:
        raise RuntimeError("NATQAI_TOKEN_TTL must be between 60 seconds and 30 days")
    if ENVIRONMENT == "production":
        if SECRET_KEY == "development-only-change-me" or len(SECRET_KEY) < 32:
            raise RuntimeError("Set a unique NATQAI_SECRET_KEY of at least 32 characters in production")
        if not CORS_ORIGINS:
            raise RuntimeError("Configure at least one NATQAI_CORS_ORIGINS entry in production")
        if "*" in CORS_ORIGINS:
            raise RuntimeError("Wildcard CORS origins are not allowed in production")
