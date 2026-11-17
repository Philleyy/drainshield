"""
state.py: what the pages show, computed by the SAME analysis code as the Streamlit dashboard
---------------------------------------------------------------------------------------------
Nothing is re-implemented here: processing.py (drain times, status), data_store.py (triage), predictive.py,
route_optimizer.py, weather.py and demo_scenario.py are imported as they are. Two things make that possible:

* shim/streamlit.py stands in for Streamlit (those modules only use its cache and session state);
* data_store.py reads CSV files, so in live mode the database is copied to data/web/*.csv when it changes.
  In demo mode it reads data/demo/ at a demo clock, exactly like the dashboard's "Pitch demo".

Those modules keep their state in module globals (which files, what time), so every computation runs
under one lock, one request at a time. shortcut: fine for a pilot; give each request its own state before
serving many users at once.
"""

import functools
import json
import os
import re
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import pandas as pd
from sqlalchemy import delete, func, insert, select

from . import config
from .db import basins as basins_t, maintenance as maint_t, readings as readings_t, utcnow

HERE = Path(__file__).resolve().parent
ENGINE = config.WEB_DIR if (config.WEB_DIR / "processing.py").exists() else config.WEB_DIR.parent
sys.path[:0] = [str(HERE / "shim"), str(ENGINE)]
os.chdir(ENGINE)                         # the analysis modules use relative "data/..." paths
os.environ["TZ"] = config.APP_TZ         # ...and local time
if hasattr(time, "tzset"):
    time.tzset()

import streamlit as st                   # noqa: E402  (the shim)
import basin_model as bm                 # noqa: E402
import data_store                        # noqa: E402
import demo_scenario                     # noqa: E402
import maintenance                       # noqa: E402
import predictive                        # noqa: E402
import processing as proc                # noqa: E402
import route_optimizer as ro             # noqa: E402
import weather                           # noqa: E402

LOCK = threading.RLock()
# never data/ itself: on a laptop that holds the Streamlit app's real files. One folder per running server.
WEB_DATA = os.environ.get("WEB_DATA_DIR") or os.path.join("data", "web")
data_store.MONITORED_FILE = os.path.join(WEB_DATA, "monitored_basins.csv")
data_store.LIVE_FILE = os.path.join(WEB_DATA, "live_readings.csv")
data_store.LIVE_LOG_FILE = os.path.join(WEB_DATA, "maintenance_log.csv")
data_store.STATUS_FILE = os.path.join(WEB_DATA, "sensor_status.json")
data_store.SETTINGS_FILE = os.path.join(WEB_DATA, "sensor_settings.json")
data_store.OLD_USER_FILE = os.path.join(WEB_DATA, "none.csv")

EMPTIED_CM = -10          # water this far BELOW the outlet = the sump was pumped out (evaporation takes weeks)
FLAGGED = ["watch", "clean_soon", "urgent"]
RUN_NOTE = re.compile(r"Pre-storm run · stop (\d+) of (\d+) · arrive (\d\d:\d\d)(?: · (.*))?")

# data_store.status_for is not cached (the log can change): cache it per (data, log, basin, time)
_raw_status = data_store.status_for
_status = functools.lru_cache(maxsize=512)(lambda key, lkey, basin_id, when: _raw_status(key, basin_id, when))
data_store.status_for = lambda key, basin_id, when: _status(key, data_store.log_key(), basin_id, when)


def iso(t):
    return None if t is None or pd.isna(t) else pd.Timestamp(t).isoformat(timespec="minutes")


def local(series):
    """Database times (UTC) -> the local, zone-less times the analysis code works in."""
    return pd.to_datetime(series, utc=True).dt.tz_convert(config.APP_TZ).dt.tz_localize(None)


def sector(address):
    """'338 avenue Mimosa' -> 'avenue Mimosa': basins on one street are cleaned in one stop."""
    return re.sub(r"^[\d\s\-–]+", "", address or "") or "No address"


# ---------------------------------------------------------------------------- which data, what time
@contextmanager
def use(conn, demo, minute=0):
    """Point the analysis code at the demo (at a demo clock) or at the live data. Yields the time 'now'."""
    with LOCK:
        st.session_state.update(data_mode=data_store.DEMO_LABEL if demo else "Live", demo_t=int(minute))
        if demo:
            if not demo_scenario.ready():
                demo_scenario.build(pd.read_csv(HERE / "demo_registry.csv", dtype={"municipal_id": str}))
                st.cache_data.clear()
        else:
            export_live(conn)
            auto_close(conn)
        yield data_store.now().floor("min")


_exported = None


def export_live(conn):
    """Copy the database into the CSV files data_store.py reads, when something changed.
    shortcut: full re-export, fine up to ~100k readings; make it incremental beyond that."""
    global _exported
    key = tuple(tuple(conn.execute(select(func.count(), func.max(col)).select_from(t)).one())
                for t, col in ((basins_t, basins_t.c.updated_at), (readings_t, readings_t.c.received_at),
                               (maint_t, maint_t.c.id)))
    if key == _exported:
        return
    os.makedirs(WEB_DATA, exist_ok=True)
    rows = [json.loads(r) for (r,) in conn.execute(select(basins_t.c.row).order_by(basins_t.c.basin_id))]
    if rows:
        pd.DataFrame(rows).to_csv(data_store.MONITORED_FILE, index=False)
    elif os.path.exists(data_store.MONITORED_FILE):
        os.remove(data_store.MONITORED_FILE)
    c = readings_t.c
    r = pd.DataFrame(conn.execute(
        select(c.basin_id, c.ts, c.distance_cm, c.battery_v, c.flags, c.mode, c.temp_c)
        .where(c.ts >= utcnow() - pd.Timedelta(days=45)).order_by(c.ts)).all(),
        columns=["basin_id", "timestamp", "distance_cm", "battery_v", "flags", "mode", "temp_c"])
    r["timestamp"] = local(r["timestamp"])
    r.to_csv(data_store.LIVE_FILE, index=False)
    m = maint_t.c
    log = pd.DataFrame(conn.execute(select(m.basin_id, m.at, m.action, m.sediment_mm, m.note).order_by(m.at)).all(),
                       columns=maintenance.COLUMNS)
    log["time"] = local(log["time"]).dt.floor("min")        # so an entry made this minute already counts
    log.to_csv(data_store.LIVE_LOG_FILE, index=False)
    _exported = key


def add_log(conn, demo, when, basin_id, action, sediment_mm=None, note="", user_id=None):
    if demo:                                 # the demo's own log file, at the demo clock (shared by all viewers)
        data_store.files()
        maintenance.add(basin_id, when, action, sediment_mm, note)
    else:
        conn.execute(insert(maint_t).values(basin_id=basin_id, at=utcnow(), action=action,
                                            sediment_mm=sediment_mm, note=note, user_id=user_id))
        export_live(conn)


# ---------------------------------------------------------------------------- issue progress + automatic close-out
def emptied_at(levels, start, end):
    """When the sensor first saw the sump pumped out between start and end (2 readings in a row), or None."""
    w = levels[(levels["timestamp"] >= start) & (levels["timestamp"] <= end)]
    low = (w["level_cm"] <= EMPTIED_CM) & (w["level_cm"].shift(-1) <= EMPTIED_CM)
    return w["timestamp"][low].iloc[0] if low.any() else None


def auto_close(conn):
    """Live: a flagged basin whose sump the sensor saw emptied is logged as cleaned, with nobody tapping anything.
    (The next rain then has to drain fast for it to count as verified: see progress().)"""
    key, when = data_store.data_key(), data_store.now().floor("min")
    basins, *_ = data_store.load_all()
    for bid in list(basins["basin_id"]):
        S = data_store.status_for(key, bid, when)
        if S.get("issue_since") is None or S["status"] in ("ok", "no_data"):
            continue
        t = emptied_at(data_store.levels_for(key, bid), S["issue_since"], when)
        if t is None:
            continue
        at = t.tz_localize(config.APP_TZ, ambiguous=True, nonexistent="shift_forward").tz_convert("UTC")
        already = conn.execute(select(func.count()).select_from(maint_t).where(      # log one emptied sump once
            maint_t.c.basin_id == bid, maint_t.c.action == "Cleaned / vacuumed", maint_t.c.at >= at.to_pydatetime())).scalar()
        if not already:
            conn.execute(insert(maint_t).values(
                basin_id=bid, at=at.to_pydatetime(), action="Cleaned / vacuumed", sediment_mm=0,
                note="Detected by the sensor: the sump was emptied (water dropped below the outlet)"))
    export_live(conn)


def progress(S, levels, when):
    """The 4 steps of an issue, [(label, time or None)], or None if the basin has no recent issue."""
    hist, entries = S["history"], S["entries"]
    resets = entries[entries["action"].isin(maintenance.RESOLVES)] if not entries.empty else entries
    sent = entries[entries["action"] == "Crew dispatched"] if not entries.empty else entries
    flagged = hist[hist["informative"] & hist["status"].isin(FLAGGED)] if not hist.empty else hist
    if S.get("issue_since") is not None and S["status"] not in ("ok", "no_data"):          # open issue
        run = sent[sent["time"] >= S["issue_since"]]
        return [("Flagged by the sensor", S["issue_since"]), ("On a run", run["time"].iloc[0] if len(run) else None),
                ("Sensor sees the sump emptied", None), ("Next rain drains fast", None)]
    if resets.empty or when - resets["time"].iloc[-1] > pd.Timedelta(days=7):
        return None
    done = resets.iloc[-1]
    t = done["time"]
    since = resets["time"].iloc[-2] if len(resets) > 1 else pd.Timestamp.min
    before = flagged[(flagged["end"] <= t) & (flagged["end"] > since)] if not flagged.empty else flagged
    run = sent[(sent["time"] <= t) & (sent["time"] > since)]
    seen = emptied_at(levels, t - pd.Timedelta(hours=2), min(t + pd.Timedelta(hours=2), when))
    step3 = (("Sensor saw the sump emptied", seen) if seen is not None else
             ("Cleaned (logged by the crew)", t) if done["action"] == "Cleaned / vacuumed" else
             ("Inspected: no issue found", t))
    ok = hist[hist["informative"] & (hist["start"] >= t) & (hist["status"] == "ok") & (hist["end"] <= when)] \
        if not hist.empty else hist
    return [("Flagged by the sensor", before["end"].iloc[0] if len(before) else None),
            ("On a run", run["time"].iloc[-1] if len(run) else None), step3,
            ("Verified: the next rain drained fast", ok["end"].iloc[0]) if len(ok) else ("Next rain drains fast", None)]


def steps_json(steps):
    return None if steps is None else [{"label": label, "at": iso(t), "done": t is not None} for label, t in steps]


# ---------------------------------------------------------------------------- overview
def forecast_json(rain, when):
    fc = weather.forecast_from_series(rain, when)
    start = when.floor("h")
    w = rain[(rain["timestamp"] >= start) & (rain["timestamp"] < start + pd.Timedelta(hours=36))]
    hours = [{"t": iso(t), "mm": round(float(mm), 1)} for t, mm in zip(w["timestamp"], w["rain_mm"])]
    if fc is None:
        return {"available": False, "hours": hours}
    return {"available": True, "total_mm": round(fc["total_mm"], 1), "max_mm_h": round(fc["max_mm_h"], 1),
            "starts": iso(fc["starts"]), "heavy": weather.is_heavy(fc), "hours": hours}


def network(when):
    """One dict per monitored basin (most urgent first), with the pre-storm prediction folded in."""
    key = data_store.data_key()
    net = data_store.network_status(key, data_store.log_key(), when)
    basins, _, rain, *_ = data_store.load_all()
    out = []
    for _, r in net.iterrows():
        bid = r["basin_id"]
        b, S = data_store.basin_row(basins, bid), data_store.status_for(key, bid, when)
        last = maintenance.last_reset(S["entries"])
        p = predictive.overflow_risk(b, S, rain, when, reset=last[0] if last else None)
        cat, priority, reason = r["category"], r["priority"], r["action"]
        # as route_page.py, but only BEFORE the rain: once it rains, the measured level speaks for itself
        if not S["raining_now"] and ((cat == "Normal" and p["flag"]) or (cat == "Inspect" and p["flag"] == "Urgent")):
            cat, priority, reason = p["flag"], "Predicted to back up", p["sentence"]
        out.append({"id": bid, "address": r["address"], "sector": sector(r["address"]),
                    "lat": float(r["latitude"]), "lon": float(r["longitude"]), "category": cat,
                    "priority": priority, "action": reason, "water": r["water"], "recovery": r["recovery"],
                    "updated": r["updated"], "battery_pct": r["battery_pct"], "reading": r["reading"],
                    "dispatched": r["issue"] == "Verified / crew dispatched",
                    "steps": steps_json(progress(S, data_store.levels_for(key, bid), when))})
    order = {"Urgent": 0, "Inspect": 1, "Offline": 2, "Normal": 3}
    return sorted(out, key=lambda x: order[x["category"]])


def overview(when):
    net = network(when)
    _, _, rain, *_ = data_store.load_all()
    counts = {c: sum(b["category"] == c for b in net) for c in ("Urgent", "Inspect", "Offline", "Normal")}
    return {"now": iso(when), "forecast": forecast_json(rain, when), "counts": counts, "basins": net,
            "run": run_state(net, rain, when)}


# ---------------------------------------------------------------------------- pre-storm run
@functools.lru_cache(maxsize=64)
def _plan(stops, start):
    df = pd.DataFrame(list(stops), columns=["basin_id", "address", "latitude", "longitude", "category", "priority",
                                            "reason"])
    return ro.plan_route(df, start_time=pd.Timestamp(start))


@functools.lru_cache(maxsize=64)
def _road_line(points):
    try:
        return ro.osrm_geometry(list(points))
    except Exception:                       # offline: straight segments
        return list(points)


def thin(line, n=400):
    step = max(len(line) // n, 1)
    return [[round(float(a), 5), round(float(b), 5)] for a, b in line[::step]]


def suggested_run(net, rain, when, exclude=(), leave=None):
    """The run DrainShield proposes: every flagged basin no crew has been sent to yet, urgent first."""
    todo = [b for b in net if b["category"] != "Normal" and not b["dispatched"] and b["id"] not in exclude]
    if not todo:
        return None
    start = pd.Timestamp.combine(when.date(), pd.Timestamp(leave).time()) if leave \
        else (when + pd.Timedelta(minutes=10)).ceil("15min")
    plan = _plan(tuple((b["id"], b["address"], b["lat"], b["lon"], b["category"], b["priority"], b["action"])
                       for b in todo), start.isoformat())
    fc = weather.forecast_from_series(rain, when)
    back = pd.Timestamp.combine(start.date(), pd.Timestamp(plan.back_at_depot).time())
    if back < start:
        back += pd.Timedelta(days=1)
    rain_starts = fc["starts"] if fc and fc["total_mm"] >= 0.5 else None
    stops = [{"stop": int(s["stop"]), "id": s["basin_id"], "address": s["address"], "sector": sector(s["address"]),
              "category": s["category"], "priority": s["priority"], "task": s["reason"], "arrive": s["arrive"],
              "depart": s["depart"], "service_min": int(s["service_min"]), "lat": float(s["latitude"]),
              "lon": float(s["longitude"])} for _, s in plan.stops.iterrows()]
    return {"stops": stops, "leave": start.strftime("%H:%M"), "back": plan.back_at_depot,
            "drive_min": round(plan.drive_s / 60), "service_min": round(plan.service_min),
            "km": round(plan.drive_m / 1000, 1), "source": plan.source, "note": plan.note,
            "line": thin(plan.geometry), "google": plan.google_links,
            "depot": [ro.DORVAL_DEPOT["latitude"], ro.DORVAL_DEPOT["longitude"]],
            "rain_starts": iso(rain_starts),
            "spare_min": None if rain_starts is None else round((rain_starts - back).total_seconds() / 60)}


def sent_run(net, when):
    """The run sent today, read back from the maintenance log (each stop's dispatch note carries its number,
    arrival time and task), with what has been done since."""
    log = data_store._log(data_store.log_key())
    if log.empty:
        return None
    today = log[(log["action"] == "Crew dispatched") & (log["time"] >= when.normalize()) & (log["time"] <= when)]
    found = [(e, RUN_NOTE.search(str(e["note"]))) for _, e in today.iterrows()]
    found = [(e, m) for e, m in found if m]
    if not found:
        return None
    sent = max(e["time"] for e, _ in found)                              # a later run replaces an earlier one
    by_id = {b["id"]: b for b in net}
    stops = []
    for e, m in sorted(((e, m) for e, m in found if e["time"] == sent), key=lambda x: int(x[1][1])):
        b = by_id.get(e["basin_id"])
        if b is None:
            continue
        done = b["category"] == "Normal"
        step3 = (b["steps"] or [None] * 3)[2]
        stops.append({"stop": int(m[1]), "id": b["id"], "address": b["address"], "sector": b["sector"],
                      "category": b["category"], "task": m[4] or b["action"], "arrive": m[3], "done": done,
                      "done_text": ("" if not done else f"{step3['label']} at {step3['at'][11:]}"
                                    if step3 and step3["at"] else "Sensor reporting again"),
                      "lat": b["lat"], "lon": b["lon"]})
    depot = (ro.DORVAL_DEPOT["latitude"], ro.DORVAL_DEPOT["longitude"])
    line = _road_line((depot, *((s["lat"], s["lon"]) for s in stops), depot))
    return {"sent": iso(sent), "stops": stops, "done": sum(s["done"] for s in stops), "line": thin(line),
            "depot": list(depot)}


def run_state(net, rain, when, exclude=(), leave=None):
    return {"suggested": suggested_run(net, rain, when, tuple(exclude), leave), "sent": sent_run(net, when)}


def send_run(conn, demo, when, exclude, leave, user_id):
    _, _, rain, *_ = data_store.load_all()
    plan = suggested_run(network(when), rain, when, tuple(exclude), leave)
    if plan is None:
        raise ValueError("No basin to send a crew to.")
    n = len(plan["stops"])
    for s in plan["stops"]:
        add_log(conn, demo, when, s["id"], "Crew dispatched",
                note=f"Pre-storm run · stop {s['stop']} of {n} · arrive {s['arrive']} · {s['task']}", user_id=user_id)
    return n


# ---------------------------------------------------------------------------- one basin
def basin_detail(basin_id, when):
    key = data_store.data_key()
    basins, _, rain, *_ = data_store.load_all()
    if basin_id not in set(basins["basin_id"]):
        return None
    b, S = data_store.basin_row(basins, basin_id), data_store.status_for(key, basin_id, when)
    levels = data_store.levels_for(key, basin_id)
    fc = weather.forecast_from_series(rain, when)
    cat, priority, _ = data_store.triage(b, S, fc)

    kind, _, head, _ = proc.action_banner(b, S)                          # same wording as dashboard.py
    parts = dict(proc.dispatch_summary(b, S))
    before_storm = priority == "Inspect before storm"
    if before_storm:
        kind, head = "urgent", f"Clean before the storm: {weather.describe(fc)[2:]}"
    rows = []
    if S["status"] != "ok" or S["live"] == "no_data":
        rows = [(k, parts[v]) for k, v in (("What we saw", "Problem"), ("Likely cause", "Likely cause")) if v in parts]
        step = parts.get("Recommended action", "")
        rows.append(("Next step", "Before the rain starts: " + step.lower() if before_storm else step))
    if "Device" in parts:
        rows.append(("Sensor", parts["Device"]))

    level = S["level_cm"]
    if level is None or S["live"] == "no_data":
        water = {"key": "no_data", "title": "Unknown", "text": proc.live_summary(b, S)["value"]}
    else:
        where = (f"≤ {proc.closest_readable_m(b):.2f} m below the street (above the sensor's range)"
                 if S["at_sensor_limit"] else f"{proc.depth_below_street_m(b, level):.2f} m below the street")
        height = ("sump emptied" if level <= EMPTIED_CM else "at the outlet (resting level)"
                  if level <= proc.DRAINED_WITHIN_CM else f"{level:.0f} cm above the outlet")
        water = {"key": S["live"], "title": proc.LIVE[S["live"]]["label"], "text": f"Water surface {where} · {height}"}
    health, detail, health_key, health_action = proc.drainage_health(b, S)

    w = S.get("worst_event")
    lv = levels[(levels["timestamp"] >= when.normalize()) & (levels["timestamp"] <= when)]
    lv = lv.iloc[::max(len(lv) // 500, 1)]
    rn = rain[(rain["timestamp"] >= when.normalize()) & (rain["timestamp"] < when.normalize() + pd.Timedelta(days=1))]
    hist, entries = S["history"], S["entries"]
    online = S["minutes_since_reading"] is not None and S["minutes_since_reading"] <= proc.NO_DATA_AFTER_MIN
    return {
        "now": iso(when), "id": basin_id, "address": b.get("address") if isinstance(b.get("address"), str) else "",
        "sector": sector(b.get("address") if isinstance(b.get("address"), str) else ""),
        "facts": f"ø{b['inner_width_cm'] * 10:.0f} mm · outlet {b['invert_depth_cm'] / 100:.2f} m below the street",
        "calibrating": b.get("cal_note") if b.get("cal_status") == "learning" else None,
        "sensor": {"online": online and not S.get("iced"), "iced": bool(S.get("iced")),
                   "battery_pct": proc.battery_pct(S["battery_v"]), "updated": data_store.ago(S["minutes_since_reading"]),
                   "mode": S.get("reading_mode") if isinstance(S.get("reading_mode"), str) else None},
        "category": cat, "banner": {"kind": kind, "head": head, "rows": rows, "confidence": S.get("confidence")},
        "steps": steps_json(progress(S, levels, when)),
        "water": water, "drainage": {"key": health_key, "title": health, "text": detail, "action": health_action},
        "levels": [{"t": iso(t), "cm": float(v)} for t, v in zip(lv["timestamp"], lv["level_cm"])],
        "rain": [{"t": iso(t), "mm": round(float(mm), 1)} for t, mm in zip(rn["timestamp"], rn["rain_mm"])],
        "dims": {k: float(b[k]) for k in ("inner_width_cm", "invert_depth_cm", "sump_depth_cm", "outlet_diameter_cm",
                                           "sensor_depth_cm")},
        "level_cm": None if level is None or S["live"] == "no_data" else float(level),
        "sediment_pct": round(float(S["sediment_pct"])),
        "storms": [] if hist.empty else [
            {"start": iso(e["start"]), "mm": e["total_mm"], "verdict": e.get("verdict", ""), "status": e["status"]}
            for _, e in hist.iloc[::-1].head(8).iterrows()],
        "log": [] if entries.empty else [{"at": iso(e["time"]), "action": e["action"],
                                          "note": e["note"] if isinstance(e["note"], str) else ""}
                                         for _, e in entries.iloc[::-1].head(10).iterrows()],
        "restriction": (f"Inferred restriction: {'≤' if w['reached_limit'] else '~'}{w['capacity_pct']:.0f}% capacity"
                        if w and w["diagnosis"] == "outlet" and w["status"] != "ok" else None),
    }


# ---------------------------------------------------------------------------- add a basin (live)
def save_basin(conn, fields):
    """fields: the as-built form (mm from the grate). Returns the warnings; raises ValueError on an error."""
    cfg = bm.default_config()
    cfg.update(fields)
    msgs = bm.check(cfg)
    errors = [text for level, text in msgs if level == "error"]
    if errors:
        raise ValueError(" ".join(errors))
    new = conn.execute(select(basins_t.c.basin_id).where(basins_t.c.basin_id == cfg["basin_id"])).first() is None
    conn.execute(delete(basins_t).where(basins_t.c.basin_id == cfg["basin_id"]))
    conn.execute(insert(basins_t).values(basin_id=cfg["basin_id"], row=json.dumps(bm.build_row(cfg), default=str),
                                         updated_at=utcnow()))
    if new:                                  # the sensor learns its resting water level from this moment
        conn.execute(insert(maint_t).values(basin_id=cfg["basin_id"], at=utcnow(), action=maintenance.INSTALL,
                                            note="Added on the website"))
    return [text for level, text in msgs if level != "error"]


def demo_story():
    return {"day": demo_scenario.DAY.strftime("%a %b %d"),
            "events": [{"minute": int(t[:2]) * 60 + int(t[3:]), "time": t, "title": title, "text": text}
                       for t, title, _, text in demo_scenario.EVENTS]}
