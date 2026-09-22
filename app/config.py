import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _normalize_database_url(url):
    # Some hosted Postgres providers hand out "postgres://" connection
    # strings, but SQLAlchemy 2.x only recognizes the "postgresql://" scheme.
    if url and url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://"):]
    return url


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-insecure-key")
    SQLALCHEMY_DATABASE_URI = _normalize_database_url(
        os.environ.get("DATABASE_URL")
    ) or f"sqlite:///{BASE_DIR / 'instance' / 'licensure.db'}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Render (and most hosted platforms) give a web service's local disk no
    # persistence guarantee across deploys/restarts. RENDER is an env var
    # Render sets automatically on every service it runs; if we're on
    # Render and still pointed at a local SQLite file (DATABASE_URL wasn't
    # set to a real database), every redeploy silently wipes all data.
    # Surface that loudly instead of letting it happen quietly again.
    EPHEMERAL_STORAGE_WARNING = bool(
        os.environ.get("RENDER")
    ) and SQLALCHEMY_DATABASE_URI.startswith("sqlite:")

    WARNING_DAYS = int(os.environ.get("WARNING_DAYS", 90))
    CRITICAL_DAYS = int(os.environ.get("CRITICAL_DAYS", 30))

    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 MB, generous for a CSV upload
