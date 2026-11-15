"""
polling_controller.py: decide how often each sensor reads, from the weather forecast
-----------------------------------------------------------------------------------
Every 15 minutes (or once, for a demo) this script:
  1. fetches the hourly rain forecast (Environment Canada GEM / HRDPS 2.5 km, through Open-Meteo, no key);
  2. reads each monitored basin's latest water level and rise rate;
  3. picks a MODE per sensor with the state machine below;
  4. writes it to data/sensor_settings.json, where lora_bridge.py turns it into the tiny downlink
     ("M,<node>,<mode>") that the receiver puts in its next ACK to that node.
     (sensor_bridge.py, the USB bridge, reads the same file's interval_s.)

STATE MACHINE (first matching rule wins)
  STORM  every 60 s   water rising >= 0.3 cm/min, OR water > 10 cm above the outlet, OR raining >= 2 mm/h now
                      ... and it stays in STORM until 30 min after the last of those (to catch the drawdown curve)
  WATCH  every 5 min  >= 10 mm forecast in the next 12 h (pre-storm watch, BEFORE the rain starts),
                      OR any rain >= 2 mm in the next 24 h starting within 3 h, OR light rain now (>= 0.5 mm/h)
                      ... and it stays in WATCH until 2 h after the last of those
  DRY    every 30 min otherwise (< 2 mm in 24 h): also the daily dry baseline for self-calibration

WHY the backend decides and not the sensor alone: the sensor can't see the sky. Switching to 5-minute
readings 12 h ahead costs about 6 mAh/day for that day and guarantees the start of the hydrograph.
WHY the sensor ALSO switches itself to storm mode (firmware): a LoRaWAN downlink can only reach a sensor right
after it transmits, i.e. up to 30 min later in DRY mode. A storm the forecast missed must not wait for that.

Usage:
    python polling_controller.py                       # once, real forecast
    python polling_controller.py --every 900           # keep running, every 15 min
    python polling_controller.py --demo-forecast 25    # pitch: "pretend 25 mm are forecast tonight"
"""

import argparse
import json
import os
import time
import urllib.request

import pandas as pd

import maintenance
import processing as proc

DATA = "data"
MONITORED_FILE = os.path.join(DATA, "monitored_basins.csv")
LIVE_FILE = os.path.join(DATA, "live_readings.csv")
SETTINGS_FILE = os.path.join(DATA, "sensor_settings.json")
STATE_FILE = os.path.join(DATA, "polling_state.json")
OPEN_METEO = ("https://api.open-meteo.com/v1/gem?latitude={lat}&longitude={lon}"
              "&hourly=precipitation&forecast_days=2&timezone=America%2FToronto")

MODES = ["DRY", "WATCH", "STORM"]
INTERVAL_S = {"DRY": 1800, "WATCH": 300, "STORM": 60}          # field timing (matches the firmware)
DEMO_INTERVAL_S = {"DRY": 60, "WATCH": 20, "STORM": 5}           # firmware DEMO_TIMING 1

DRY_24H_MM = 2.0
WATCH_12H_MM = 10.0
WATCH_SOON_H = 3
RAIN_NOW_WATCH_MM_H = 0.5
RAIN_NOW_STORM_MM_H = 2.0
STORM_RISE_CM_MIN = 0.3
STORM_LEVEL_CM = proc.NORMAL_BAND_CM
HOLD_MIN = {"STORM": 30, "WATCH": 120}


# ---------------------------------------------------------------------------
# Pure decision logic (tested in tests/test_polling.py)
# ---------------------------------------------------------------------------
def forecast_summary(rain, now):
    """{'next12_mm', 'next24_mm', 'now_mm_h', 'starts_in_h'} from an hourly rain table, or None."""
    if rain is None or rain.empty:
        return None
    r = rain.sort_values("timestamp")
    hour = now.floor("h")
    cur = r[r["timestamp"] == hour]["rain_mm"]
    ahead = r[r["timestamp"] > hour]
    n12 = ahead[ahead["timestamp"] <= hour + pd.Timedelta(hours=12)]["rain_mm"].sum()
    w24 = ahead[ahead["timestamp"] <= hour + pd.Timedelta(hours=24)]
    wet = w24[w24["rain_mm"] > 0]
    return {"next12_mm": float(n12), "next24_mm": float(w24["rain_mm"].sum()),
            "now_mm_h": float(cur.iloc[0]) if not cur.empty else 0.0,
            "starts_in_h": None if wet.empty else (wet["timestamp"].iloc[0] - now).total_seconds() / 3600}


def triggers(fc, level_cm, rise_cm_min):
    """Which modes are wanted right now (before the hold rules), with the reason."""
    out = {}
    if rise_cm_min is not None and rise_cm_min >= STORM_RISE_CM_MIN:
        out["STORM"] = f"water rising {rise_cm_min:.1f} cm/min"
    elif level_cm is not None and level_cm > STORM_LEVEL_CM:
        out["STORM"] = f"water {level_cm:.0f} cm above the outlet"
    elif fc and fc["now_mm_h"] >= RAIN_NOW_STORM_MM_H:
        out["STORM"] = f"raining {fc['now_mm_h']:.1f} mm/h now"
    if fc:
        if fc["next12_mm"] >= WATCH_12H_MM:
            out["WATCH"] = f"pre-storm watch: {fc['next12_mm']:.0f} mm forecast in 12 h"
        elif fc["next24_mm"] >= DRY_24H_MM and fc["starts_in_h"] is not None and fc["starts_in_h"] <= WATCH_SOON_H:
            out["WATCH"] = f"{fc['next24_mm']:.0f} mm forecast, starting in {fc['starts_in_h']:.0f} h"
        elif fc["now_mm_h"] >= RAIN_NOW_WATCH_MM_H:
            out["WATCH"] = f"light rain now ({fc['now_mm_h']:.1f} mm/h)"
    return out


def decide(fc, level_cm, rise_cm_min, state, now):
    """state = {'last': {'STORM': iso, 'WATCH': iso}} for one basin (updated in place).
    Returns (mode, reason)."""
    last = state.setdefault("last", {})
    wanted = triggers(fc, level_cm, rise_cm_min)
    for m in wanted:
        last[m] = now.isoformat()
    for m in ("STORM", "WATCH"):
        if m in wanted:
            return m, wanted[m]
        if m in last and now - pd.Timestamp(last[m]) < pd.Timedelta(minutes=HOLD_MIN[m]):
            mins = HOLD_MIN[m] - (now - pd.Timestamp(last[m])).total_seconds() / 60
            return m, f"holding {m.lower()} mode {mins:.0f} more min"
    if fc is None:
        return "DRY", "no forecast (offline): dry timing, the sensor's own storm trigger still works"
    return "DRY", f"dry: {fc['next24_mm']:.1f} mm forecast in 24 h"


# ---------------------------------------------------------------------------
# Inputs and outputs
# ---------------------------------------------------------------------------
def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)                                            # never leave a half-written file


def fetch_forecast(lat, lon):
    try:
        with urllib.request.urlopen(OPEN_METEO.format(lat=round(lat, 3), lon=round(lon, 3)), timeout=8) as r:
            h = json.load(r)["hourly"]
        return pd.DataFrame({"timestamp": pd.to_datetime(h["time"]),
                             "rain_mm": pd.to_numeric(pd.Series(h["precipitation"]), errors="coerce").fillna(0)})
    except Exception:
        return None


def demo_forecast(now, total_mm, start_in_h=6, hours=6):
    """A made-up storm for the pitch: total_mm spread over `hours`, starting in `start_in_h`."""
    ts = pd.date_range(now.floor("h") - pd.Timedelta(hours=2), periods=50, freq="h")
    rain = pd.Series(0.0, index=ts)
    start = now.floor("h") + pd.Timedelta(hours=start_in_h)
    rain[(ts >= start) & (ts < start + pd.Timedelta(hours=hours))] = total_mm / hours
    return pd.DataFrame({"timestamp": ts, "rain_mm": rain.values})


def latest_state(basin, readings, log):
    """(level_cm above the outlet, rise cm/min over the last 10 min) or (None, None)."""
    b = proc.calibrate(basin, readings, maintenance.last_install(log, basin["basin_id"]))
    lv = proc.water_levels(readings.dropna(subset=["distance_cm"]), b)
    if lv.empty:
        return None, None
    last = lv.iloc[-1]
    recent = lv[lv["timestamp"] >= last["timestamp"] - pd.Timedelta(minutes=10)]
    rise = None
    if len(recent) >= 2:
        dt = (recent["timestamp"].iloc[-1] - recent["timestamp"].iloc[0]).total_seconds() / 60
        if dt > 0:
            rise = (recent["level_cm"].iloc[-1] - recent["level_cm"].iloc[0]) / dt
    return float(last["level_cm"]), rise


def run_once(now=None, demo_mm=None, demo_timing=False, verbose=True):
    now = pd.Timestamp(now) if now is not None else pd.Timestamp.now().floor("s")
    if not os.path.exists(MONITORED_FILE):
        if verbose:
            print("No monitored basin yet (add one in the dashboard).")
        return {}
    basins = pd.read_csv(MONITORED_FILE, dtype={"municipal_id": str})
    readings = (pd.read_csv(LIVE_FILE, parse_dates=["timestamp"]) if os.path.exists(LIVE_FILE)
                else pd.DataFrame(columns=["basin_id", "timestamp", "distance_cm", "battery_v"]))
    readings["distance_cm"] = pd.to_numeric(readings["distance_cm"], errors="coerce")
    readings["battery_v"] = pd.to_numeric(readings["battery_v"], errors="coerce")
    log = maintenance.load()

    lat, lon = float(basins["latitude"].median()), float(basins["longitude"].median())
    rain = demo_forecast(now, demo_mm) if demo_mm is not None else fetch_forecast(lat, lon)
    fc = forecast_summary(rain, now)
    settings, state = read_json(SETTINGS_FILE), read_json(STATE_FILE)
    intervals = DEMO_INTERVAL_S if demo_timing else INTERVAL_S
    decisions = {}
    for _, b in basins.iterrows():
        bid = b["basin_id"]
        if settings.get(bid, {}).get("manual"):
            continue                                                 # someone is bench testing: leave it
        level, rise = latest_state(b, readings, log)
        mode, reason = decide(fc, level, rise, state.setdefault(bid, {}), now)
        entry = settings.setdefault(bid, {})
        changed = entry.get("mode") != mode
        entry.update(mode=mode, interval_s=intervals[mode], reason=reason, updated=now.isoformat())
        decisions[bid] = (mode, reason, changed)
        if verbose:
            print(f"{now:%H:%M}  {bid:12s} {mode:5s} every {intervals[mode]:>4d} s  {'(changed) ' if changed else ''}{reason}")
    write_json(SETTINGS_FILE, settings)
    write_json(STATE_FILE, state)
    return decisions


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Set each DrainShield sensor's reading mode from the forecast.")
    ap.add_argument("--every", type=int, default=0, help="repeat every N seconds (0 = run once)")
    ap.add_argument("--demo-forecast", type=float, default=None, metavar="MM",
                    help="pretend MM of rain is forecast, starting in 6 h (for the pitch)")
    ap.add_argument("--demo-timing", action="store_true", help="intervals of the firmware's DEMO_TIMING (60/20/5 s)")
    a = ap.parse_args()
    while True:
        run_once(demo_mm=a.demo_forecast, demo_timing=a.demo_timing)
        if not a.every:
            break
        time.sleep(a.every)
