import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-insecure-key")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'instance' / 'licensure.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    WARNING_DAYS = int(os.environ.get("WARNING_DAYS", 90))
    CRITICAL_DAYS = int(os.environ.get("CRITICAL_DAYS", 30))

    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 MB, generous for a CSV upload
