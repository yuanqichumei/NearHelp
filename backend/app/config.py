import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND = Path(__file__).resolve().parents[1]


def demo_enabled() -> bool:
    return os.getenv("NEARHELP_DEMO_GUESTS", "").strip().lower() in {"true", "1"}


def database_path() -> Path:
    load_dotenv(BACKEND.parent / ".env")
    return BACKEND / os.environ.get("NEARTALK_DB_PATH", "data/neartalk.sqlite3")
