"""
ingest.py: store readings uploaded by the bridges (lora_bridge.py / sensor_bridge.py)

A bridge POSTs {"readings": [{basin_id, timestamp, distance_cm, battery_v, ...}, ...]} with its upload key.
The same reading can arrive twice (a retry after a dropped connection): it is stored once, matched on
(basin_id, timestamp). Timestamps without a time zone are local time (APP_TZ), as the bridges write them.
"""

import math
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, insert, select, update

from . import config, season
from .db import as_utc, readings, sensors, utcnow

LOCAL = ZoneInfo(config.APP_TZ)
BASIN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,39}$")
MODES = {"DRY", "WATCH", "STORM", "USB", ""}


class Reading(BaseModel):
    basin_id: str
    timestamp: datetime
    distance_cm: float | None = Field(default=None, ge=0, le=2000)
    battery_v: float | None = Field(default=None, ge=0, le=20)
    temp_c: float | None = Field(default=None, ge=-60, le=90)
    flags: int = Field(default=0, ge=0, le=255)
    mode: str | None = None
    rssi: float | None = None
    snr: float | None = None
    node: int | None = None
    index: int | None = None

    @field_validator("distance_cm", "battery_v", "temp_c", "rssi", "snr", mode="before")
    @classmethod
    def _finite(cls, v):
        return None if isinstance(v, float) and not math.isfinite(v) else v   # inf / nan = no value

    @field_validator("basin_id")
    @classmethod
    def _basin(cls, v):
        if not BASIN_RE.match(v):
            raise ValueError("basin_id: letters, digits, - _ . only (max 40)")
        return v

    @field_validator("mode")
    @classmethod
    def _mode(cls, v):
        v = (v or "").strip().upper()
        return v if v in MODES and v else None          # unknown mode: keep the reading, drop the label

    def ts_utc(self):
        t = self.timestamp if self.timestamp.tzinfo else self.timestamp.replace(tzinfo=LOCAL)
        return t.astimezone(timezone.utc)


class Upload(BaseModel):
    readings: list[Reading] = Field(max_length=config.MAX_READINGS_PER_UPLOAD)


def store(conn, upload: Upload) -> dict:
    """Insert new readings, skip ones already stored, refresh each sensor's latest status."""
    now = utcnow()
    by_basin: dict[str, list[Reading]] = {}
    for r in upload.readings:
        by_basin.setdefault(r.basin_id, []).append(r)

    added = duplicates = 0
    for basin, rows in by_basin.items():
        times = [r.ts_utc() for r in rows]
        known = {as_utc(t) for (t,) in conn.execute(
            select(readings.c.ts).where(readings.c.basin_id == basin, readings.c.ts >= min(times),
                                        readings.c.ts <= max(times)))}
        fresh, seen = [], set()
        for r, t in zip(rows, times):
            if t in known or t in seen:
                duplicates += 1
                continue
            seen.add(t)
            fresh.append({"basin_id": basin, "ts": t, "received_at": now, "distance_cm": r.distance_cm,
                          "battery_v": r.battery_v, "temp_c": r.temp_c, "flags": r.flags, "mode": r.mode,
                          "rssi": r.rssi, "snr": r.snr, "node": r.node, "seq": r.index})
        if fresh:
            conn.execute(insert(readings), fresh)
            added += len(fresh)
            with_batt = [x for x in fresh if x["battery_v"] is not None]
            _update_sensor(conn, basin, max(fresh, key=lambda x: x["ts"]), len(fresh), now,
                           max(with_batt, key=lambda x: x["ts"])["battery_v"] if with_batt else None)
    s = season.info(datetime.now(LOCAL))
    return {"accepted": added, "duplicates": duplicates, "modes": {},
            "season": {"key": s["key"], "dry_every_s": s["dry_every_min"] * 60}}


def _update_sensor(conn, basin, latest, n_new, now, battery_v):
    row = conn.execute(select(sensors).where(sensors.c.basin_id == basin)).mappings().first()
    values = {"last_received_at": now}
    if row is None or row["last_reading_at"] is None or as_utc(row["last_reading_at"]) <= latest["ts"]:
        values.update(last_reading_at=latest["ts"], distance_cm=latest["distance_cm"], temp_c=latest["temp_c"],
                      mode=latest["mode"], rssi=latest["rssi"], flags=latest["flags"])
        if battery_v is not None:                     # USB readings carry no battery: keep the last known
            values["battery_v"] = battery_v
    if row is None:
        conn.execute(insert(sensors).values(basin_id=basin, readings_total=n_new, **values))
    else:
        conn.execute(update(sensors).where(sensors.c.basin_id == basin)
                     .values(readings_total=row["readings_total"] + n_new, **values))


def latest(conn):
    out = []
    for r in conn.execute(select(sensors).order_by(sensors.c.basin_id)).mappings():
        out.append({**dict(r), "last_reading_at": _iso(r["last_reading_at"]),
                    "last_received_at": _iso(r["last_received_at"])})
    return out


def remove(conn, basin):
    """Forget a sensor and every reading it sent. Returns False if there was none."""
    gone = conn.execute(delete(sensors).where(sensors.c.basin_id == basin)).rowcount
    gone += conn.execute(delete(readings).where(readings.c.basin_id == basin)).rowcount
    return gone > 0


def recent(conn, basin, limit=200):
    rows = conn.execute(select(readings).where(readings.c.basin_id == basin)
                        .order_by(readings.c.ts.desc()).limit(limit)).mappings()
    return [{"timestamp": _iso(r["ts"]), "received_at": _iso(r["received_at"]), "distance_cm": r["distance_cm"],
             "battery_v": r["battery_v"], "temp_c": r["temp_c"], "flags": r["flags"], "mode": r["mode"]}
            for r in rows]


def _iso(t):
    return as_utc(t).isoformat() if t is not None else None
