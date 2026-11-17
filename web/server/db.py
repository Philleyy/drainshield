"""
db.py: the database tables (SQLAlchemy Core: the same code runs on PostgreSQL and SQLite)

Tables are created on start-up if they don't exist (fine for a prototype; a real product would add
migrations with Alembic).
"""

from datetime import datetime, timezone

from sqlalchemy import (Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, MetaData, String, Table,
                        Text, UniqueConstraint, create_engine)

from . import config

metadata = MetaData()

users = Table(
    "users", metadata,
    Column("id", Integer, primary_key=True),
    Column("email", String(254), nullable=False, unique=True),          # stored lower-case
    Column("name", String(120), nullable=False, default=""),
    Column("role", String(20), nullable=False),                         # admin | engineering | crew | demo
    Column("password_hash", String(255), nullable=False),               # argon2id, never the password itself
    Column("active", Boolean, nullable=False, default=True),
    Column("must_change_password", Boolean, nullable=False, default=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("last_login_at", DateTime(timezone=True)),
)

sessions = Table(
    "sessions", metadata,
    Column("token_hash", String(64), primary_key=True),                 # sha256 of the cookie value
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("last_seen_at", DateTime(timezone=True), nullable=False),
    Column("user_agent", String(255), nullable=False, default=""),
)

ingest_keys = Table(
    "ingest_keys", metadata,
    Column("id", String(16), primary_key=True),                         # public part of the key
    Column("name", String(120), nullable=False),
    Column("secret_hash", String(64), nullable=False),                  # sha256 of the secret part
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("created_by", Integer, ForeignKey("users.id", ondelete="SET NULL")),
    Column("last_used_at", DateTime(timezone=True)),
    Column("revoked", Boolean, nullable=False, default=False),
)

readings = Table(
    "readings", metadata,
    Column("id", Integer, primary_key=True),
    Column("basin_id", String(40), nullable=False),
    Column("ts", DateTime(timezone=True), nullable=False),              # when the sensor measured (UTC)
    Column("received_at", DateTime(timezone=True), nullable=False),     # when the website got it (UTC)
    Column("distance_cm", Float),                                       # sensor to water; empty = no echo
    Column("battery_v", Float),
    Column("temp_c", Float),
    Column("flags", Integer, nullable=False, default=0),
    Column("mode", String(10)),                                         # DRY | WATCH | STORM
    Column("rssi", Float),
    Column("snr", Float),
    Column("node", Integer),
    Column("seq", Integer),                                             # the sensor's own reading number
    UniqueConstraint("basin_id", "ts", name="uq_reading_basin_ts"),     # the same reading sent twice is kept once
)
Index("ix_readings_basin_ts", readings.c.basin_id, readings.c.ts)

sensors = Table(
    "sensors", metadata,
    Column("basin_id", String(40), primary_key=True),
    Column("last_reading_at", DateTime(timezone=True)),
    Column("last_received_at", DateTime(timezone=True)),
    Column("distance_cm", Float),
    Column("battery_v", Float),
    Column("temp_c", Float),
    Column("mode", String(10)),
    Column("rssi", Float),
    Column("flags", Integer),
    Column("readings_total", Integer, nullable=False, default=0),
)

basins = Table(
    "basins", metadata,
    Column("basin_id", String(40), primary_key=True),
    Column("row", Text, nullable=False),                # the as-built geometry, as basin_model.build_row() makes it (JSON)
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

maintenance = Table(
    "maintenance", metadata,
    Column("id", Integer, primary_key=True),
    Column("basin_id", String(40), nullable=False, index=True),
    Column("at", DateTime(timezone=True), nullable=False),
    Column("action", String(60), nullable=False),
    Column("sediment_mm", Float),
    Column("note", Text, nullable=False, default=""),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="SET NULL")),
)

engine = create_engine(config.DATABASE_URL, pool_pre_ping=True, future=True,
                       connect_args={"check_same_thread": False} if config.DATABASE_URL.startswith("sqlite") else {})


def create_tables():
    metadata.create_all(engine)


def utcnow():
    return datetime.now(timezone.utc)


def as_utc(dt):
    """SQLite gives times back without a zone: they were stored as UTC."""
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
