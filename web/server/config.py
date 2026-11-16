"""
config.py: settings, all read from environment variables (nothing here is specific to one host)

DATABASE_URL     PostgreSQL connection string (Ample, Supabase, Render... all give one).
                 Not set: a local SQLite file, web/drainshield_dev.db, for running on your laptop.
SETUP_TOKEN      One-time code that lets the first administrator account be created at /setup.
                 Ignored once any account exists.
COOKIE_SECURE    "auto" (default: secure cookies when the site is served over https), "1" or "0".
APP_TZ           Time zone for readings sent without one (the bridges send local time). Default America/Toronto.
"""

import os
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent.parent

_url = os.environ.get("DATABASE_URL", "").strip()
if not _url:
    _url = f"sqlite:///{WEB_DIR / 'drainshield_dev.db'}"
elif _url.startswith("postgres://"):                 # SQLAlchemy wants the newer spelling + the psycopg 3 driver
    _url = "postgresql+psycopg://" + _url[len("postgres://"):]
elif _url.startswith("postgresql://"):
    _url = "postgresql+psycopg://" + _url[len("postgresql://"):]
DATABASE_URL = _url

SETUP_TOKEN = os.environ.get("SETUP_TOKEN", "").strip()
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "auto").strip().lower()
APP_TZ = os.environ.get("APP_TZ", "America/Toronto")

SESSION_COOKIE = "ds_session"
SESSION_HOURS = 12                    # "Remember me" off: the session ends after 12 h (or when the browser closes)
REMEMBER_DAYS = 30                    # "Remember me" on
MIN_PASSWORD_LEN = 10
LOGIN_MAX_FAILS = 8                   # per email and per IP address ...
LOGIN_WINDOW_MIN = 15                 # ... within this many minutes, then sign-in is paused for that window
MAX_READINGS_PER_UPLOAD = 5000

STATIC_DIR = Path(__file__).resolve().parent / "static"     # the built React site (npm run build writes it here)
