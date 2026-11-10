"""
data_store.py
-------------
Loads all the data the dashboard needs (demo basins, the simulated town, and the
basins you added), re-runs the simulator automatically when a basin file changes,
and keeps the "current moment" and the selected basin shared between pages.
"""

import os

import pandas as pd
import streamlit as st

import maintenance
import processing as proc
import simulate
import weather

DATA, OUT = "data", "output"
USER_FILE = os.path.join(DATA, "basins_user.csv")
NETWORKS = ["demo", "town", "user"]
NETWORK_NAMES = {"demo": "Demo", "town": "Simulated town", "user": "Yours"}


def _mtime(path):
    return os.path.getmtime(path) if os.path.exists(path) else 0


def _needs_simulation(network):
    basins_file = os.path.join(DATA, f"basins_{network}.csv")
    readings_file = os.path.join(OUT, f"readings_{network}.csv")
    truth_file = os.path.join(OUT, f"truth_{network}.csv")
    if not os.path.exists(basins_file):
        return False
    if not os.path.exists(readings_file) or not os.path.exists(truth_file):
        return True
    if _mtime(readings_file) < _mtime(basins_file):
        return True
    basins = pd.read_csv(basins_file)
    if "sensor_id" not in basins.columns:                # file from an older version
        return True
    ids = set(basins["basin_id"])
    return not ids <= set(pd.read_csv(readings_file, usecols=["basin_id"])["basin_id"])


def ensure_data():
    demo = os.path.join(DATA, "basins_demo.csv")
    muni_file = os.path.join(DATA, "municipal_basins.csv")
    stale = not os.path.exists(demo) or "sensor_id" not in pd.read_csv(demo, nrows=1).columns
    if not stale and os.path.exists(muni_file):     # demo basins must sit on the current city's basins
        demo_ids = set(pd.read_csv(demo, dtype={"municipal_id": str})["municipal_id"].dropna())
        stale = not demo_ids <= set(pd.read_csv(muni_file, dtype={"municipal_id": str})["municipal_id"])
    if stale:
        import random
        import make_basins
        os.makedirs(DATA, exist_ok=True)
        rng = random.Random(make_basins.SEED)
        make_basins.save(make_basins.make_demo(), "demo")
        make_basins.save(make_basins.make_pilot(rng), "pilot")
        make_basins.save(make_basins.make_town(rng), "town")
    for network in NETWORKS:
        if _needs_simulation(network):
            simulate.run_network(network, verbose=False)


def data_key():
    """Changes whenever a basin file or a readings file changes (used to refresh caches)."""
    return tuple(_mtime(os.path.join(folder, f"{kind}_{n}.csv"))
                 for n in NETWORKS for folder, kind in [(DATA, "basins"), (OUT, "readings")])


@st.cache_data(show_spinner="Loading data...")
def _load(key):
    basins, readings, truth = [], [], []
    for network in NETWORKS:
        bf = os.path.join(DATA, f"basins_{network}.csv")
        if not os.path.exists(bf):
            continue
        b = pd.read_csv(bf)
        if b.empty:
            continue
        b["network"] = network
        basins.append(b)
        readings.append(pd.read_csv(os.path.join(OUT, f"readings_{network}.csv"), parse_dates=["timestamp"]))
        tf = os.path.join(OUT, f"truth_{network}.csv")
        if os.path.exists(tf) and os.path.getsize(tf) > 5:
            truth.append(pd.read_csv(tf, parse_dates=["date"]))
    rain = pd.read_csv(os.path.join(OUT, "rain_demo.csv"), parse_dates=["timestamp"])
    return (pd.concat(basins, ignore_index=True), pd.concat(readings, ignore_index=True), rain,
            proc.rain_events(rain), pd.concat(truth, ignore_index=True) if truth else pd.DataFrame())


def load_all():
    ensure_data()
    return _load(data_key())


def basin_row(basins, basin_id):
    return basins[basins["basin_id"] == basin_id].iloc[0]


@st.cache_data
def levels_for(key, basin_id):
    basins, readings, *_ = load_all()
    return proc.water_levels(readings, basin_row(basins, basin_id))


def log_key():
    return _mtime(maintenance.LOG_FILE)


@st.cache_data(show_spinner=False)
def _log(key):
    return maintenance.load()


def entries_for(basin_id, now):
    return maintenance.for_basin(_log(log_key()), basin_id, now)


def status_for(key, basin_id, now):
    """Status of one basin at `now`, taking the crew's maintenance log into account."""
    basins, _, rain, events, _ = load_all()
    basin = basin_row(basins, basin_id)
    entries = entries_for(basin_id, now)
    S = proc.basin_status(basin, levels_for(key, basin_id), events, rain, now,
                          reset=maintenance.last_reset(entries))
    S["lifecycle"] = maintenance.lifecycle(S, entries)
    S["entries"] = entries
    return S


@st.cache_data(show_spinner=False)
def municipal_basins():
    """Unmonitored municipal catch basins (Ville de Montréal open data slice), or an empty table."""
    path = os.path.join(DATA, "municipal_basins.csv")
    if not os.path.exists(path):
        return pd.DataFrame(columns=["municipal_id", "address", "latitude", "longitude", "basin_type"])
    return pd.read_csv(path, dtype={"municipal_id": str})


# Map / dispatch-list categories, most urgent first.
# Infrastructure state (red/orange/green) is kept separate from sensor state (grey).
CATEGORIES = {
    "Urgent": {"color": "#d03b3b", "size": 22, "rank": 0, "emoji": "🔴", "tint": "#f9e3e3", "text": "#b52a2a"},
    "Inspect": {"color": "#ec835a", "size": 15, "rank": 1, "emoji": "🟠", "tint": "#fcebe3", "text": "#b4471c"},
    "Normal": {"color": "#0ca30c", "size": 10, "rank": 2, "emoji": "🟢", "tint": "#e9f6e9", "text": "#0a7a0a"},
    "Offline": {"color": "#8a8984", "size": 12, "rank": 3, "emoji": "⚪", "tint": "#efefec", "text": "#52514e"},
}


def triage(b, S, forecast):
    """(category, priority label, recommended action) for one basin."""
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


@st.cache_data(show_spinner="Checking every basin...")
def network_status(key, lkey, now):
    """One row per basin: what the map and the dispatch list need."""
    basins, _, rain, *_ = load_all()
    forecast = weather.simulated_forecast(rain, now)
    rows = []
    for _, b in basins.iterrows():
        S = status_for(key, b["basin_id"], now)
        cat, priority, action = triage(b, S, forecast)
        health, detail, *_ = proc.drainage_health(b, S)
        depth = (None if S["level_cm"] is None or S["live"] == "no_data"
                 else proc.depth_below_street_m(b, S["level_cm"]))
        w = S.get("worst_event")
        recovery = ("" if not w or pd.isna(w.get("drain_min")) else
                    "< 10 min" if w["drain_min"] < 10 else f"{proc.nice_duration(w['drain_min'])} (normal < 10 min)")
        rows.append({
            "basin_id": b["basin_id"], "network": NETWORK_NAMES[b["network"]],
            "address": b.get("address", "") if isinstance(b.get("address", ""), str) else "",
            "latitude": b["latitude"], "longitude": b["longitude"], "category": cat, "priority": priority,
            "rank": CATEGORIES[cat]["rank"] * 10 + (0 if priority == "Flooding / backing up now" else 1)
                    + {"urgent": 0, "clean_soon": 1, "watch": 2}.get(S["status"], 3) / 10,
            "live": proc.live_summary(b, S)["title"],
            "water": ("—" if depth is None else
                      f"≤ {proc.closest_readable_m(b):.2f} m" if S["at_sensor_limit"] else f"{depth:.2f} m"),
            "trend": S.get("trend", ""), "recovery": recovery,
            "drainage": f"{health} ({detail})", "action": action, "issue": S.get("lifecycle") or "",
            "updated": ("—" if S["minutes_since_reading"] is None else
                        "just now" if S["minutes_since_reading"] < 1 else
                        f"{proc.nice_duration(S['minutes_since_reading'])} ago"),
            "online": S["live"] != "no_data",
            "battery_pct": proc.battery_pct(S["battery_v"]),
        })
    return pd.DataFrame(rows).sort_values(["rank", "basin_id"]).reset_index(drop=True)


def engineering():
    """True when the Engineering view is selected (Crew is the default)."""
    return st.session_state.get("role") == "Engineering"


def select_basin(basin_id):
    st.session_state["basin_id"] = basin_id


def save_user_basin(row, replace=False):
    """Add (or replace) one basin in data/basins_user.csv, then re-simulate the user network."""
    os.makedirs(DATA, exist_ok=True)
    df = pd.read_csv(USER_FILE) if os.path.exists(USER_FILE) else pd.DataFrame()
    if not df.empty and row["basin_id"] in set(df["basin_id"]):
        if not replace:
            raise ValueError("exists")
        df = df[df["basin_id"] != row["basin_id"]]
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    df.to_csv(USER_FILE, index=False)
    simulate.run_network("user", verbose=False)
    st.cache_data.clear()


def delete_user_basin(basin_id):
    df = pd.read_csv(USER_FILE)
    df = df[df["basin_id"] != basin_id]
    df.to_csv(USER_FILE, index=False)
    simulate.run_network("user", verbose=False)
    st.cache_data.clear()
