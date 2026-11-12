"""
data_store.py
-------------
Loads everything the dashboard needs and keeps the selected basin shared between pages.

    data/municipal_basins.csv   every catch basin of the municipality (Ville de Montréal open data)
    data/monitored_basins.csv   the basins that have a DrainShield sensor, with their as-built geometry
    data/live_readings.csv      what the sensors sent (written by sensor_bridge.py)
    data/sensor_settings.json   reading interval chosen in the dashboard (read by sensor_bridge.py)
    data/sensor_status.json     what the bridge last heard from each sensor
    data/maintenance_log.csv    the crews' maintenance log

Rain comes from the real Environment Canada GEM model (past 7 days + forecast) through
Open-Meteo. Without internet, the rain-based features simply switch off.
"""

import json
import os

import pandas as pd
import streamlit as st

import maintenance
import processing as proc
import weather

DATA = "data"
REGISTRY_FILE = os.path.join(DATA, "municipal_basins.csv")
MONITORED_FILE = os.path.join(DATA, "monitored_basins.csv")
OLD_USER_FILE = os.path.join(DATA, "basins_user.csv")          # name used by earlier versions
LIVE_FILE = os.path.join(DATA, "live_readings.csv")
SETTINGS_FILE = os.path.join(DATA, "sensor_settings.json")
STATUS_FILE = os.path.join(DATA, "sensor_status.json")
READING_COLUMNS = ["basin_id", "timestamp", "distance_cm", "battery_v"]
DEFAULT_INTERVAL_S = 5


def _mtime(path):
    return os.path.getmtime(path) if os.path.exists(path) else 0


def now():
    """The current local time (the dashboard is live: no more replay)."""
    return pd.Timestamp.now().floor("s")


def data_key():
    """Changes whenever a basin file or the readings change (used to refresh caches)."""
    return (_mtime(MONITORED_FILE), _mtime(LIVE_FILE), _mtime(REGISTRY_FILE), _mtime(maintenance.LOG_FILE))


@st.cache_data(show_spinner=False)
def _load(key):
    if not os.path.exists(MONITORED_FILE) and os.path.exists(OLD_USER_FILE):
        os.replace(OLD_USER_FILE, MONITORED_FILE)                     # carry over basins added before
    basins = pd.read_csv(MONITORED_FILE, dtype={"municipal_id": str}) if os.path.exists(MONITORED_FILE) \
        else pd.DataFrame(columns=["basin_id", "municipal_id", "latitude", "longitude"])
    readings = (pd.read_csv(LIVE_FILE, parse_dates=["timestamp"]) if os.path.exists(LIVE_FILE)
                else pd.DataFrame(columns=READING_COLUMNS))
    readings["timestamp"] = pd.to_datetime(readings["timestamp"])
    readings["distance_cm"] = pd.to_numeric(readings["distance_cm"], errors="coerce")
    readings["battery_v"] = pd.to_numeric(readings["battery_v"], errors="coerce")
    if not basins.empty and "sensor_height_cm" in basins:      # learn each sensor's height from the water
        log = maintenance.load()
        basins = pd.DataFrame([proc.calibrate(b, readings, maintenance.last_install(log, b["basin_id"]))
                               for _, b in basins.iterrows()]).reset_index(drop=True)
    return basins, readings


def load_all():
    """(monitored basins, sensor readings, rain, rain events, truth) — truth is always empty now."""
    basins, readings = _load(data_key())
    lat, lon = center()
    rain = weather.rain_series(round(lat, 3), round(lon, 3))
    return basins, readings, rain, proc.rain_events(rain), pd.DataFrame()


# Pilot prioritization (import_priorities.py): load x low point, see README. Three levels on the map.
PRIORITY_FILE = os.path.join(DATA, "basin_priorities.csv")
PRIORITY = {   # level: (tiers, colour, dot size, legend)
    "High": ("A", "#4b2bb3", 11, "A: big catchment + confirmed low point"),
    "Moderate": ("BCD", "#8b72e8", 8, "B–D: one of the two (or elevation unknown)"),
    "Low": ("EF", "#a9a8a2", 6, "E–F: neither"),
    "Not compatible": ("–", "#d9d7d0", 5, "not a round basin, or type unknown"),
}


def priority_level(tier):
    return next((lvl for lvl, (tiers, *_) in PRIORITY.items() if isinstance(tier, str) and tier in tiers),
                "Not compatible")


def municipal_basins():
    """Every catch basin of the municipality (Ville de Montréal open data) + its pilot priority."""
    return _municipal(_mtime(REGISTRY_FILE), _mtime(PRIORITY_FILE))


@st.cache_data(show_spinner=False)
def _municipal(*key):
    if not os.path.exists(REGISTRY_FILE):
        return pd.DataFrame(columns=["municipal_id", "address", "latitude", "longitude", "basin_type", "tier",
                                     "priority_level"])
    reg = pd.read_csv(REGISTRY_FILE, dtype={"municipal_id": str})
    if os.path.exists(PRIORITY_FILE):
        pri = pd.read_csv(PRIORITY_FILE, dtype={"municipal_id": str})
        reg = reg.merge(pri, on="municipal_id", how="left")
        missing = reg["tier_label"].isna()
        reg.loc[missing, "tier_label"] = "Not analysed (not in the prioritization file)"
        reg.loc[missing, "compatibility"] = "Not analysed"
    else:
        reg["tier"] = None
    reg["priority_level"] = reg["tier"].map(priority_level)
    return reg


def center():
    reg = municipal_basins()
    if reg.empty:
        return 45.4440, -73.7520
    return float(reg["latitude"].median()), float(reg["longitude"].median())


def basin_row(basins, basin_id):
    return basins[basins["basin_id"] == basin_id].iloc[0]


@st.cache_data(show_spinner=False)
def levels_for(key, basin_id):
    basins, readings = _load(key)
    return proc.water_levels(readings.dropna(subset=["distance_cm"]), basin_row(basins, basin_id))


# ---------------------------------------------------------------------------
# Maintenance log and status
# ---------------------------------------------------------------------------
def log_key():
    return _mtime(maintenance.LOG_FILE)


@st.cache_data(show_spinner=False)
def _log(key):
    return maintenance.load()


def entries_for(basin_id, when):
    return maintenance.for_basin(_log(log_key()), basin_id, when)


def status_for(key, basin_id, when):
    """Status of one monitored basin at `when`, taking the maintenance log into account."""
    basins, _, rain, events, _ = load_all()
    basin = basin_row(basins, basin_id)
    entries = entries_for(basin_id, when)
    S = proc.basin_status(basin, levels_for(key, basin_id), events, rain, when,
                          reset=maintenance.last_reset(entries))
    S["lifecycle"] = maintenance.lifecycle(S, entries)
    S["entries"] = entries
    return S


# Map / dispatch-list categories, most urgent first.
# Infrastructure state (red/orange/green) is kept separate from sensor state (grey).
CATEGORIES = {
    "Urgent": {"color": "#d03b3b", "size": 22, "rank": 0, "emoji": "🔴", "tint": "#f9e3e3", "text": "#b52a2a"},
    "Inspect": {"color": "#ec835a", "size": 16, "rank": 1, "emoji": "🟠", "tint": "#fcebe3", "text": "#b4471c"},
    "Normal": {"color": "#0ca30c", "size": 13, "rank": 2, "emoji": "🟢", "tint": "#e9f6e9", "text": "#0a7a0a"},
    "Offline": {"color": "#55534e", "size": 13, "rank": 3, "emoji": "⚫", "tint": "#efefec", "text": "#52514e"},
}


def triage(b, S, forecast):
    """(category, priority label, recommended action) for one monitored basin."""
    live = proc.live_summary(b, S)
    _, _, _, action = proc.drainage_health(b, S)
    if S["live"] == "no_data" or S["status"] == "no_data":
        return "Offline", "Sensor offline", "Inspect the sensor"
    if S["live"] in ("backing_up", "high"):
        return "Urgent", "Flooding / backing up now", live["action"]
    if S["status"] in ("urgent", "clean_soon", "watch") and weather.is_heavy(forecast):
        return "Urgent", "Inspect before storm", "Clean it before the rain starts"
    if S["status"] in ("urgent", "clean_soon", "watch"):
        return "Inspect", {"urgent": "Very slow drainage", "clean_soon": "Slow drainage",
                           "watch": "Starting to slow"}[S["status"]], action
    return "Normal", "Normal", "No action"


def network_status(key, lkey, when):
    """One row per MONITORED basin: what the map and the dispatch list need."""
    basins, _, rain, *_ = load_all()
    forecast = weather.forecast_from_series(rain, when)
    rows = []
    for _, b in basins.iterrows():
        S = status_for(key, b["basin_id"], when)
        cat, priority, action = triage(b, S, forecast)
        health, detail, *_ = proc.drainage_health(b, S)
        depth = (None if S["level_cm"] is None or S["live"] == "no_data"
                 else proc.depth_below_street_m(b, S["level_cm"]))
        w = S.get("worst_event")
        recovery = ("" if not w or pd.isna(w.get("drain_min")) else
                    "< 10 min" if w["drain_min"] < 10 else f"{proc.nice_duration(w['drain_min'])} (normal < 10 min)")
        rows.append({
            "basin_id": b["basin_id"], "municipal_id": b.get("municipal_id"),
            "address": b.get("address", "") if isinstance(b.get("address", ""), str) else "",
            "latitude": b["latitude"], "longitude": b["longitude"], "category": cat, "priority": priority,
            "rank": CATEGORIES[cat]["rank"] * 10 + (0 if priority == "Flooding / backing up now" else 1)
                    + {"urgent": 0, "clean_soon": 1, "watch": 2}.get(S["status"], 3) / 10,
            "live": live_title(b, S),
            "water": ("—" if depth is None else
                      f"≤ {proc.closest_readable_m(b):.2f} m" if S["at_sensor_limit"] else f"{depth:.2f} m"),
            "trend": S.get("trend", ""), "recovery": recovery,
            "drainage": f"{health} ({detail})", "action": action, "issue": S.get("lifecycle") or "",
            "updated": ago(S["minutes_since_reading"]),
            "online": S["live"] != "no_data",
            "battery_pct": proc.battery_pct(S["battery_v"]),
        })
    cols = ["basin_id", "municipal_id", "address", "latitude", "longitude", "category", "priority", "rank",
            "live", "water", "trend", "recovery", "drainage", "action", "issue", "updated", "online", "battery_pct"]
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(rows).sort_values(["rank", "basin_id"]).reset_index(drop=True)


def live_title(b, S):
    return proc.live_summary(b, S)["title"]


def ago(minutes):
    if minutes is None or pd.isna(minutes):
        return "—"
    if minutes < 1:
        return f"{max(int(minutes * 60), 0)} s ago"
    return f"{proc.nice_duration(minutes)} ago"


def engineering():
    """True when the Engineering view is selected (Crew is the default)."""
    return st.session_state.get("role") == "Engineering"


def select_basin(basin_id):
    st.session_state["basin_id"] = basin_id


# ---------------------------------------------------------------------------
# Monitored basins
# ---------------------------------------------------------------------------
def save_monitored_basin(row, replace=False):
    """Add (or replace) one basin in data/monitored_basins.csv."""
    os.makedirs(DATA, exist_ok=True)
    df = pd.read_csv(MONITORED_FILE, dtype={"municipal_id": str}) if os.path.exists(MONITORED_FILE) \
        else pd.DataFrame()
    if not df.empty and row["basin_id"] in set(df["basin_id"]):
        if not replace:
            raise ValueError("exists")
        df = df[df["basin_id"] != row["basin_id"]]
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    df.to_csv(MONITORED_FILE, index=False)
    st.cache_data.clear()


def delete_monitored_basin(basin_id):
    df = pd.read_csv(MONITORED_FILE, dtype={"municipal_id": str})
    df[df["basin_id"] != basin_id].to_csv(MONITORED_FILE, index=False)
    st.cache_data.clear()


# ---------------------------------------------------------------------------
# Sensor settings (written here, read by sensor_bridge.py) and status (the other way round)
# ---------------------------------------------------------------------------
def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def sensor_settings():
    return _read_json(SETTINGS_FILE)


def set_interval(sensor_key, seconds):
    settings = sensor_settings()
    settings.setdefault(sensor_key, {})["interval_s"] = seconds
    os.makedirs(DATA, exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)


def interval_for(sensor_key):
    return sensor_settings().get(sensor_key, {}).get("interval_s", DEFAULT_INTERVAL_S)


def sensor_status():
    return _read_json(STATUS_FILE)
