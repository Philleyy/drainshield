"""
demo_scenario.py: the 24-hour pitch demo
----------------------------------------
One scripted day (Tuesday Nov 17, 2026) at 4 Dorval pilot sites, 12 basins, with 3 weeks of history before it,
so every DrainShield feature shows up in one replay: adaptive reading modes, a surprise thunderstorm, a forecast
storm, pre-storm cleaning, the truck route, a crew fixing things, a flood, frost, a dead link, a low battery.

The dashboard's "Pitch demo" mode reads these files instead of the real ones (data/demo/, rebuilt on demand)
and a clock slider replaces "now": every page shows the network as it was at that minute. Readings appear when
they were RECEIVED (a radio outage delivers them late, with their real times), and the rain forecast is the one
Environment Canada had issued by then (the 09:30 thunderstorm is in no forecast).

Basins (site 4 = the 3 sensors on the demo table, nodes DS-01..03):
    S4-A   DS-01  clogged since last week (slow drainage)   -> flagged, routed, cleaned 12:45, fine tonight
    S4-N1  DS-02  normal; radio outage 13:20-14:40          -> grey, then all readings arrive late, none lost
    S4-N2  DS-03  normal (control)
    S7-A   DS-04  starting to slow                           -> flagged before the storm, cleaned 13:40
    S7-N1  DS-05  clean, but the main sewer surcharges 20:10 -> water backs up to street level: flood alert
    S7-N2  DS-06  normal
    S8-A   DS-07  frost on the sensor face 05:10-07:40       -> "sensor iced", never "flooding"
    S8-N1  DS-08  battery at 14%                             -> sensor-health warning
    S8-N2  DS-09  normal
    S9-A   DS-10  battery connector loose 07:50-12:10        -> offline, fixed by the crew on its route
    S9-N1  DS-11  normal
    S9-N2  DS-12  normal

    python demo_scenario.py        (re)builds data/demo/
"""

import json
import os

import numpy as np
import pandas as pd

import basin_model as bm

VERSION = 4
DEMO_DIR = os.path.join("data", "demo")
DAY = pd.Timestamp("2026-11-17")                 # a Tuesday
START = DAY - pd.Timedelta(days=21)
END = DAY + pd.Timedelta(days=1)
INSTALLED = START + pd.Timedelta(hours=8)

FILES = {k: os.path.join(DEMO_DIR, v) for k, v in {
    "monitored": "monitored_basins.csv", "live": "live_readings.csv", "log": "maintenance_log.csv",
    "scripted_log": "scripted_log.csv", "rain": "rain_actual.csv", "forecasts": "forecasts.json",
    "settings": "sensor_settings.json", "status": "sensor_status.json", "meta": "meta.json"}.items()}

MODES = ["DRY", "WATCH", "STORM"]
SAMPLE_S = {"DRY": 1800, "WATCH": 300, "STORM": 60}
TX_EVERY_S = {"DRY": 1800, "WATCH": 300, "STORM": 120}
STORM_HOLD_MIN = 30
REC_NO_ECHO, REC_AT_BLIND, REC_ICED, REC_ON_USB = 0x01, 0x02, 0x08, 0x20

# id, municipal id (Dorval pilot site), sensor id, role in the story
BASINS = [
    ("S4-A", "7082692", "DS-01", "clogged"), ("S4-N1", "7082693", "DS-02", "outage"),
    ("S4-N2", "10018421", "DS-03", "normal"),
    ("S7-A", "20008271", "DS-04", "slowing"), ("S7-N1", "20008270", "DS-05", "surcharge"),
    ("S7-N2", "20008272", "DS-06", "normal"),
    ("S8-A", "7033665", "DS-07", "iced"), ("S8-N1", "7033667", "DS-08", "low_battery"),
    ("S8-N2", "7033662", "DS-09", "normal"),
    ("S9-A", "7031071", "DS-10", "offline"), ("S9-N1", "7030873", "DS-11", "normal"),
    ("S9-N2", "7031070", "DS-12", "normal"),
]
TABLE = {"S4-A", "S4-N1", "S4-N2"}


def at(hhmm, day=DAY):
    h, m = map(int, hhmm.split(":"))
    return day + pd.Timedelta(hours=h, minutes=m)


# ---------------------------------------------------------------------------
# The story, minute by minute (also the "jump to" chapters and the narration banner)
# ---------------------------------------------------------------------------
EVENTS = [
    ("00:00", "A dry night", "network",
     "All 12 sensors read every 30 min (DRY mode) to save battery. Two basins are already 🟠 from last week's "
     "storms: S4-A drains slowly, S7-A is starting to slow. S8-N1's battery is at 14%."),
    ("05:05", "Frost on a sensor", "network",
     "At −3 °C, frost covers S8-A's sensor face: no echo. DrainShield shows ⚪ sensor iced (unknown condition), "
     "never 'flooding'."),
    ("07:35", "Frost clears", "network", "S8-A reads normally again as the air warms up. Nobody had to drive there."),
    ("07:50", "A sensor goes silent", "network",
     "S9-A stops reporting (its battery connector came loose). After 60 min without a reading (08:34) it turns "
     "⚫ Offline: 'Inspect the sensor'."),
    ("09:30", "Surprise thunderstorm", "demo",
     "15 mm/h for 35 min, in no forecast. Each sensor sees the water rise at its next 30-min reading and switches "
     "ITSELF to STORM mode (every 60 s), without waiting for the server."),
    ("10:10", "Slow drainage confirmed", "basin:S4-A",
     "S4-A's water is stuck 20+ cm high after the rain; its clean neighbours drained in minutes."),
    ("11:00", "Environment Canada forecasts 29 mm tonight", "network",
     "The backend switches every sensor to WATCH (every 5 min) at its next transmission, 7 h before the first "
     "drop. S4-A and S7-A turn 🔴 Inspect before storm."),
    ("11:25", "Vacuum route sent to the crew", "route",
     "The dispatcher generates the route (S4-A, S7-A, and the silent S9-A on the way) and sends it. "
     "The three issues move to 'Verified / crew dispatched'."),
    ("12:10", "Sensor fixed on the way", "basin:S9-A",
     "The crew re-seats S9-A's battery connector: back online. One trip, two jobs."),
    ("12:45", "S4-A cleaned", "basin:S4-A",
     "190 mm of sediment vacuumed out. The crew logs it on the tablet: issue resolved, back to 🟢."),
    ("13:20", "Radio outage", "basin:S4-N1",
     "S4-N1's radio link drops. The sensor keeps measuring every 5 min and stores every reading in its flash."),
    ("13:40", "S7-A cleaned", "basin:S7-A", "Second basin cleaned before the storm. Issue resolved."),
    ("14:21", "No reading for 60 min", "network", "S4-N1 turns ⚫ Offline."),
    ("14:40", "Back online, nothing lost", "basin:S4-N1",
     "16 readings arrive at once with their original times: the gap in the graph fills in."),
    ("17:00", "Forecast updated: 37 mm", "network", "Environment Canada raises tonight's total. Sensors stay in WATCH."),
    ("18:00", "The storm starts", "demo",
     "Raining ≥ 2 mm/h: every sensor in STORM mode (reads every 60 s, sends every 2 min)."),
    ("19:30", "The cleaned basins keep up", "basin:S4-A",
     "S4-A and S7-A rise a few cm and drain in minutes: this morning's cleaning worked."),
    ("20:25", "Water backing up at S7-N1", "basin:S7-N1",
     "The main sewer is full downstream: water comes back up through the outlet. 🔴 Flooding / backing up now."),
    ("20:35", "Street level: dispatch + slow-down signs", "network",
     "S7-N1's water is above the sensor's range (≤ 0.43 m below the street) and rising. Passing cars push waves "
     "toward doors and basement windows: close or slow the street."),
    ("20:45", "Emergency crew on site", "basin:S7-N1", "Crew dispatched; slow-down signs placed."),
    ("22:00", "Water going down", "basin:S7-N1", "The sewer empties; S7-N1 drains back to normal."),
    ("23:00", "Rain ends", "demo",
     "Sensors hold STORM 30 min to record the drawdown, then WATCH 2 h, then back to DRY. S7-N1 filled to the top "
     "of the sensor range, so it is flagged for an inspection."),
    ("23:20", "S7-N1 inspected: no issue", "basin:S7-N1",
     "The basin was clean: the cause was downstream. Issue closed and reported to network engineering."),
]


def events():
    return [{"time": at(t), "title": title, "where": where, "text": text} for t, title, where, text in EVENTS]


def event_now(t):
    """The latest story event at or before t (or None)."""
    ev = [e for e in events() if e["time"] <= t]
    return ev[-1] if ev else None


# ---------------------------------------------------------------------------
# Rain: what actually fell (per minute) and what each forecast said
# ---------------------------------------------------------------------------
HISTORY_STORMS = [(-20, 14, [4, 8, 3]), (-16, 9, [4, 8, 3]), (-12, 16, [5, 9, 4]),
                  (-7, 13, [6, 10, 5]), (-3, 15, [5, 10, 6])]
EVENING_ACTUAL = {18: 3, 19: 8, 20: 20, 21: 9, 22: 4}             # mm in each hour (44 mm)
FORECASTS = [                                                      # (issued, {hour of DAY: mm})
    (at("23:00", DAY - pd.Timedelta(days=1)), {}),
    (at("05:00"), {}),
    (at("11:00"), {18: 2, 19: 5, 20: 12, 21: 7, 22: 3}),               # 29 mm
    (at("17:00"), {18: 3, 19: 7, 20: 14, 21: 9, 22: 4}),               # 37 mm
    (at("23:00"), {}),
]
THUNDER = (at("09:30"), at("10:05"), 15.0)                          # start, end, mm/h


def minute_rain():
    """Rain intensity (mm/h) at every minute from START to END."""
    t = pd.date_range(START, END, freq="min", inclusive="left")
    i = pd.Series(0.0, index=t)
    for day, hour, mm in HISTORY_STORMS:
        for k, v in enumerate(mm):
            s = DAY + pd.Timedelta(days=day, hours=hour + k)
            i[s:s + pd.Timedelta(minutes=59)] = v
    i[THUNDER[0]:THUNDER[1] - pd.Timedelta(minutes=1)] = THUNDER[2]
    for hour, mm in EVENING_ACTUAL.items():
        s = DAY + pd.Timedelta(hours=hour)
        i[s:s + pd.Timedelta(minutes=59)] = mm
    return i


def hourly(i):
    return (i.resample("h").sum() / 60).rename("rain_mm")


def rain_as_of(t, actual_hourly, forecasts=FORECASTS, minute=None):
    """Hourly rain the way the dashboard would see it at time t: measured up to now, then the latest forecast
    issued by t. The current hour counts as measured as soon as rain has started in it."""
    t = pd.Timestamp(t)
    hours = pd.date_range(START, END + pd.Timedelta(days=1), freq="h", inclusive="left")
    out = pd.Series(0.0, index=hours)
    now_h = t.floor("h")
    past = actual_hourly[actual_hourly.index < now_h]
    out.loc[past.index] = past.values
    issued = [f for when, f in forecasts if when <= t]
    fc = issued[-1] if issued else {}
    for h in hours[hours >= now_h]:
        if h.normalize() == DAY and h.hour in fc:
            out[h] = fc[h.hour]
    if minute is not None and now_h in actual_hourly.index:
        fallen = minute[now_h:t]
        if (fallen > 0).any():
            out[now_h] = actual_hourly[now_h]
    return pd.DataFrame({"timestamp": out.index, "rain_mm": out.values})


# ---------------------------------------------------------------------------
# Water in each basin: a simple reservoir, minute by minute
#   dL/dt = (R * r * i - L) / tau     r: cm per mm/h when clean, R: rise multiplier, tau: drain time constant
# ---------------------------------------------------------------------------
def clog(role, t):
    """(rise multiplier R, time constant tau in min) at time t."""
    if role == "clogged" and DAY - pd.Timedelta(days=10) <= t < at("12:45"):
        return 7.0, 45.0
    if role == "slowing" and DAY - pd.Timedelta(days=5) <= t < at("13:40"):
        return 2.6, 12.0
    return 1.0, 4.0


def surcharge(t):
    """Water forced up from the main sewer at S7-N1 (cm above the invert)."""
    pts = [(at("20:10"), 0), (at("20:40"), 125), (at("21:15"), 125), (at("22:05"), 0)]
    for (t0, v0), (t1, v1) in zip(pts, pts[1:]):
        if t0 <= t <= t1:
            return v0 + (v1 - v0) * (t - t0).total_seconds() / (t1 - t0).total_seconds()
    return 0.0


def simulate_level(role, r, intensity):
    idx = intensity.index
    i = intensity.to_numpy()
    R = np.ones(len(idx))
    tau = np.full(len(idx), 4.0)
    for k, (a, b) in enumerate([clog(role, t) for t in idx[::30]]):        # clog state changes slowly
        R[k * 30:(k + 1) * 30], tau[k * 30:(k + 1) * 30] = a, b
    L = np.zeros(len(idx))
    for k in range(1, len(idx)):
        L[k] = L[k - 1] + (R[k] * r * i[k] - L[k - 1]) / tau[k]
    level = pd.Series(L, index=idx)
    if role == "surcharge":
        s = pd.Series([surcharge(t) for t in idx[(idx >= at("20:10")) & (idx <= at("22:05"))]],
                      index=idx[(idx >= at("20:10")) & (idx <= at("22:05"))])
        level.loc[s.index] = np.maximum(level.loc[s.index], s)
    return level


def temperature(t):
    """Air temperature in the basin (°C): cold night before the demo day, mild otherwise."""
    if t.normalize() == DAY:
        h = t.hour + t.minute / 60
        return float(np.interp(h, [0, 5, 7.5, 10, 14, 18, 24], [-1, -3, -1, 2, 4, 3, 2]))
    return 5.0


# ---------------------------------------------------------------------------
# When each sensor reads: the firmware's state machine, replayed
# ---------------------------------------------------------------------------
def server_mode(t, events_hist):
    """Mode the backend wants at t (polling_controller.py rules on this day's forecasts)."""
    if t >= DAY:
        if at("18:00") <= t < at("23:30"):
            return "STORM"
        if at("11:00") <= t < at("18:00") or t >= at("23:30"):
            return "WATCH"
        return "DRY"
    for s, e in events_hist:                     # history: watch 6 h before each storm, storm during it
        if s <= t < e + pd.Timedelta(minutes=STORM_HOLD_MIN):
            return "STORM"
        if s - pd.Timedelta(hours=6) <= t < s:
            return "WATCH"
    return "DRY"


def reading_times(level, offset_min, events_hist, silent=None):
    """[(time, mode)] for one node: wakes every SAMPLE_S[mode]; the mode is the more careful of the backend's
    (learned at each transmission) and its own (water moving > 0.3 cm/min, or > 3 cm above its dry baseline)."""
    out, t = [], START + pd.Timedelta(minutes=offset_min)
    known, storm_until, last_tx, prev = "DRY", START, START - pd.Timedelta(days=1), None
    while t < END:
        lv = float(level.asof(t))
        if prev is not None:
            dt = max((t - prev[0]).total_seconds() / 60, 1)
            if abs(lv - prev[1]) / dt >= 0.3 or lv > 3:            # moving fast, or 3 cm above its dry baseline
                storm_until = t + pd.Timedelta(minutes=STORM_HOLD_MIN)
        mode = "STORM" if t < storm_until else "DRY"
        mode = max(mode, known, key=MODES.index)
        dead = silent is not None and silent[0] <= t < silent[1]
        if not dead:
            out.append((t, mode))
            if (t - last_tx).total_seconds() >= TX_EVERY_S[mode] - 1:      # transmission: the ACK brings the mode
                known, last_tx = server_mode(t, events_hist), t
        prev = (t, lv)
        mode = max(mode, known, key=MODES.index)
        t = t + pd.Timedelta(seconds=SAMPLE_S[mode])
        if t.second:                                                       # keep readings on whole minutes
            t = t.ceil("min")
    return out


def received_time(t, mode, role):
    if role == "outage" and at("13:20") <= t < at("14:40"):
        return at("14:40") + pd.Timedelta(seconds=30)
    if mode == "STORM":                                                    # sent every 2 min, 2 readings each
        return t.ceil("2min") + pd.Timedelta(seconds=5) if t.minute % 2 else t + pd.Timedelta(seconds=5)
    return t + pd.Timedelta(seconds=5)


# ---------------------------------------------------------------------------
# Build the files
# ---------------------------------------------------------------------------
def build_basins(registry):
    rows = []
    for bid, muni, sid, role in BASINS:
        m = registry[registry["municipal_id"] == muni]
        cfg = bm.default_config()
        cfg.update(basin_id=bid, sensor_id=sid, municipal_id=muni,
                   address=m["address"].iloc[0] if not m.empty else bid,
                   latitude=float(m["latitude"].iloc[0]) if not m.empty else 45.444,
                   longitude=float(m["longitude"].iloc[0]) if not m.empty else -73.752,
                   catchment_m2=700, sim_scenario=f"demo:{role}")
        rows.append(bm.build_row(cfg))
    return pd.DataFrame(rows)


def scripted_log():
    rows = [(bid, INSTALLED, "Sensor installed / re-installed", None, "Pilot installation") for bid, *_ in BASINS]
    rows += [
        ("S4-A", at("11:25"), "Crew dispatched", None, "Vacuum route sent from the dashboard"),
        ("S7-A", at("11:25"), "Crew dispatched", None, "Vacuum route sent from the dashboard"),
        ("S9-A", at("11:25"), "Crew dispatched", None, "Sensor check added to the route"),
        ("S9-A", at("12:10"), "Inspected", None, "Battery connector had come loose: re-seated, sensor reporting"),
        ("S4-A", at("12:45"), "Cleaned / vacuumed", 10, "190 mm of sediment removed; leaves at the trap lip"),
        ("S7-A", at("13:40"), "Cleaned / vacuumed", 10, "120 mm of sediment removed"),
        ("S7-N1", at("20:45"), "Crew dispatched", None,
         "Emergency: street flooding. Slow-down signs placed (car wakes were pushing water at doorways)"),
        ("S7-N1", at("23:20"), "No issue found", None,
         "Basin clean. Water came back from the main sewer (surcharged downstream): reported to engineering"),
    ]
    return pd.DataFrame(rows, columns=["basin_id", "time", "action", "sediment_mm", "note"])


def build(registry=None, seed=7):
    """Write every demo file into data/demo/. Returns the readings table."""
    if registry is None:
        registry = pd.read_csv(os.path.join("data", "municipal_basins.csv"), dtype={"municipal_id": str})
    os.makedirs(DEMO_DIR, exist_ok=True)
    rng = np.random.default_rng(seed)
    intensity = minute_rain()
    hourly_rain = hourly(intensity)
    wet = hourly_rain[hourly_rain > 0]
    gid = (wet.index.to_series().diff() > pd.Timedelta(hours=6)).cumsum()
    events_hist = [(g.index.min(), g.index.max() + pd.Timedelta(hours=1)) for _, g in wet.groupby(gid)
                   if g.index.min() < DAY]

    basins = build_basins(registry)
    rows = []
    for k, (bid, muni, sid, role) in enumerate(BASINS):
        b = basins.iloc[k]
        r = 0.35 + 0.1 * ((k * 7) % 5) / 4                               # cm of rise per mm/h when clean
        level = simulate_level(role, r, intensity)
        silent = (at("07:50"), at("12:10")) if role == "offline" else None
        rest = b["sensor_height_cm"] - b["outlet_invert_cm"]             # distance to the resting water
        top = rest - b["sensor_blind_zone_cm"]                           # highest level the sensor can see
        volts0 = 3.256 if role == "low_battery" else 3.56 + 0.01 * (k % 4)
        noise = 0.0005 if role == "low_battery" else 0.002
        for t, mode in reading_times(level, (k * 7) % 30, events_hist, silent):
            lv = float(level.asof(t))
            flags = 0
            if role == "iced" and at("04:55") <= t < at("07:30"):
                dist, flags = np.nan, REC_NO_ECHO | REC_ICED
            elif lv >= top:
                dist, flags = float(b["sensor_blind_zone_cm"]), REC_AT_BLIND
            else:
                dist = round(rest - lv + rng.normal(0, 0.25), 1)
            batt = round(volts0 - 0.001 * (t - START).days / 21 + rng.normal(0, noise), 3)
            rows.append((bid, t, dist, batt, received_time(t, mode, role), mode, flags, round(temperature(t), 1)))
    readings = pd.DataFrame(rows, columns=["basin_id", "timestamp", "distance_cm", "battery_v", "received", "mode",
                                           "flags", "temp_c"]).sort_values(["received", "basin_id"])

    basins.to_csv(FILES["monitored"], index=False)
    readings.to_csv(FILES["live"], index=False)
    pd.DataFrame({"timestamp": hourly_rain.index, "rain_mm": hourly_rain.values}).to_csv(FILES["rain"], index=False)
    intensity[intensity > 0].rename("mm_h").to_csv(os.path.join(DEMO_DIR, "rain_minutes.csv"))
    with open(FILES["forecasts"], "w", encoding="utf-8") as f:
        json.dump([{"issued": w.isoformat(), "hours": fc} for w, fc in FORECASTS], f)
    log = scripted_log()
    log.to_csv(FILES["scripted_log"], index=False)
    reset_log(scripted=True)
    for name in ("settings", "status"):
        with open(FILES[name], "w", encoding="utf-8") as f:
            json.dump({}, f)
    with open(FILES["meta"], "w", encoding="utf-8") as f:
        json.dump({"version": VERSION, "day": DAY.isoformat()}, f)
    return readings


def reset_log(scripted=True):
    """The demo's maintenance log = the scripted crew actions (or only the installations), and nothing the
    presenter clicked."""
    log = pd.read_csv(FILES["scripted_log"], parse_dates=["time"])
    if not scripted:
        log = log[log["action"] == "Sensor installed / re-installed"]
    log.to_csv(FILES["log"], index=False)


def ready():
    try:
        with open(FILES["meta"], encoding="utf-8") as f:
            return json.load(f).get("version") == VERSION and all(os.path.exists(p) for p in FILES.values())
    except (OSError, ValueError):
        return False


def load_rain():
    actual = pd.read_csv(FILES["rain"], parse_dates=["timestamp"]).set_index("timestamp")["rain_mm"]
    minute = pd.read_csv(os.path.join(DEMO_DIR, "rain_minutes.csv"), parse_dates=[0], index_col=0)["mm_h"]
    with open(FILES["forecasts"], encoding="utf-8") as f:
        fc = [(pd.Timestamp(x["issued"]), {int(h): v for h, v in x["hours"].items()}) for x in json.load(f)]
    return actual, minute, fc


if __name__ == "__main__":
    r = build()
    print(f"Demo built in {DEMO_DIR}: {len(r):,} readings, {r['basin_id'].nunique()} basins, "
          f"{(r['timestamp'] >= DAY).sum():,} on the demo day.")
