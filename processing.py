"""
processing.py
-------------
Turns raw sensor readings into things a person can act on.

    raw distance -> water level -> storms -> how the basin responded -> status

It does NOT care whether the data is simulated or real: as long as the readings
follow the data contract (basin_id, timestamp, distance_cm, battery_v), it works.

TWO SEPARATE QUESTIONS
  1. LIVE STATE: what is the water doing right now? (normal, rising, backing up...)
  2. MAINTENANCE: does a crew need to go there? This comes from how the basin
     behaved during past storms, plus the estimated sediment in the sump.

HOW WE DIAGNOSE A STORM
After each storm we compare the rise with what this basin did when it was clean
(learned from the first storms after installation):
  * rose MUCH MORE than when clean, drained slowly -> outlet or trap restricted
        (sediment reaching the trap's bottom lip, or debris jammed in it)
  * rose MUCH LESS than when clean in a big rain   -> grate probably covered
        (leaves): the water is staying on the street instead of coming in
  * about the same                                -> normal
Because a clean basin rises in proportion to (inflow / outlet capacity), the
ratio also gives a rough ESTIMATE of the outlet capacity left (1 / ratio).

SEDIMENT: the ultrasonic sensor can't see it (it's under the water). We ESTIMATE it
from the rain since installation x the catchment area x a sediment yield, and
correct it each time a crew measures the sump during a cleaning.

All decision rules are the THRESHOLDS below: first guesses, to tune with pilot data.
"""

import os

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# THRESHOLDS
# ---------------------------------------------------------------------------
NORMAL_BAND_CM = 10          # water up to 10 cm above the outlet invert = normal
HIGH_WATER_CM = 40           # more than 40 cm above the invert = backing up
DRAINED_WITHIN_CM = 3        # "drained" = back within 3 cm of the invert
MIN_RISE_TO_JUDGE_CM = 3     # rose less than this: storm too small to judge the outlet

RISE_OK_MAX = 2              # rise vs clean basin: up to 2x -> OK
RISE_WATCH_MAX = 4           # 2x to 4x -> Watch
RISE_CLEAN_SOON_MAX = 8      # 4x to 8x -> Clean soon, above -> Urgent

GRATE_CHECK_MIN_EXPECTED_CM = 6   # only check the grate when a clean basin would rise 6+ cm
GRATE_WATCH_RATIO = 0.4           # rose less than 40% of the clean rise -> Watch
GRATE_CLEAN_SOON_RATIO = 0.2      # less than 20% -> Clean soon

DRAIN_OK_MAX_MIN = 30
DRAIN_WATCH_MAX_MIN = 90
DRAIN_CLEAN_SOON_MAX_MIN = 180

SEDIMENT_WATCH_PCT = 60      # estimated sump fill
SEDIMENT_CLEAN_SOON_PCT = 80
SEDIMENT_DENSITY = 1600      # kg/m3
ANNUAL_RAIN_MM = 1000

DEFAULT_RISE_CM_PER_MM_H = 0.3
LEARNING_STORMS = 3
MIN_INTENSITY_MM_H = 5
RAIN_EVENT_GAP_H = 6
PEAK_SEARCH_AFTER_RAIN_H = 6
NO_DATA_AFTER_MIN = 60
BATTERY_FULL_V = 3.60        # used to show the battery as a rough percentage
BATTERY_EMPTY_V = 3.20       # (depends on the battery chemistry: recalibrate with the real cells)
BATTERY_LOW_V = 3.35
BATTERY_CRITICAL_V = 3.25

# ---------------------------------------------------------------------------
# STATUS LEVELS (maintenance) and LIVE STATES
# ---------------------------------------------------------------------------
STATUS = {
    "ok":         {"rank": 0, "label": "OK", "icon": "✔",
                   "color": "#0ca30c", "text": "#0a7a0a", "tint": "#e9f6e9"},
    "watch":      {"rank": 1, "label": "Watch", "icon": "!",
                   "color": "#fab219", "text": "#8a5d00", "tint": "#fdf4dc"},
    "clean_soon": {"rank": 2, "label": "Clean soon", "icon": "!!",
                   "color": "#ec835a", "text": "#b4471c", "tint": "#fcebe3"},
    "urgent":     {"rank": 3, "label": "Urgent", "icon": "✖",
                   "color": "#d03b3b", "text": "#b52a2a", "tint": "#f9e3e3"},
    "no_data":    {"rank": -1, "label": "No data", "icon": "?",
                   "color": "#8a8984", "text": "#52514e", "tint": "#efefec"},
}
LIVE = {
    "normal":     {"label": "Normal level", "icon": "✔", "status": "ok"},
    "rising":     {"label": "Rising with the rain", "icon": "↑", "status": "watch"},
    "high":       {"label": "Not draining", "icon": "!", "status": "clean_soon"},
    "backing_up": {"label": "Backing up", "icon": "✖", "status": "urgent"},
    "no_data":    {"label": "No live data", "icon": "?", "status": "no_data"},
}
DIAGNOSIS = {
    "normal": "Normal",
    "small": "Too small to judge",
    "outlet": "Outlet / trap restricted",
    "grate": "Grate may be covered",
    "raining": "Raining now",
    "no_data": "No data",
}


def worst(*keys):
    return max(keys, key=lambda k: STATUS[k]["rank"])


def grade(value, ok_max, watch_max, clean_soon_max):
    if value <= ok_max:
        return "ok"
    if value <= watch_max:
        return "watch"
    if value <= clean_soon_max:
        return "clean_soon"
    return "urgent"


def nice_duration(minutes):
    minutes = int(round(minutes))
    if minutes < 60:
        return f"{minutes} min"
    if minutes < 48 * 60:
        h, m = divmod(minutes, 60)
        return f"{h} h {m:02d} min" if m else f"{h} h"
    return f"{minutes / (24 * 60):.0f} days"


def format_level(level_cm):
    """+12 cm, -2 cm or 0 cm (never '-0 cm')."""
    v = int(round(level_cm))
    return "0 cm" if v == 0 else f"{v:+d} cm"


# ---------------------------------------------------------------------------
# 1. LOADING
# ---------------------------------------------------------------------------
def load_network(network, folder="."):
    basins = pd.read_csv(os.path.join(folder, "data", f"basins_{network}.csv"))
    readings = pd.read_csv(os.path.join(folder, "output", f"readings_{network}.csv"),
                           parse_dates=["timestamp"])
    rain = pd.read_csv(os.path.join(folder, "output", f"rain_{network}.csv"), parse_dates=["timestamp"])
    return basins, readings, rain


# ---------------------------------------------------------------------------
# 2. CLEANING: raw distance -> water level above the outlet invert
# ---------------------------------------------------------------------------
def basin_max_measurable_cm(basin):
    return (basin["sensor_height_cm"] - basin["sensor_blind_zone_cm"]) - basin["outlet_invert_cm"]


def subdrain_above_invert_cm(basin):
    """Height of the subdrains above the invert, or None if the basin has none."""
    if int(basin.get("subdrains", 0)) == 0:
        return None
    return basin["subdrain_height_cm"] - basin["outlet_invert_cm"]


def water_levels(readings, basin):
    r = readings[readings["basin_id"] == basin["basin_id"]].sort_values("timestamp").copy()
    level = (basin["sensor_height_cm"] - r["distance_cm"]) - basin["outlet_invert_cm"]
    r["level_cm"] = level.rolling(3, center=True, min_periods=1).median().round(1)  # remove spikes
    r["at_sensor_limit"] = r["level_cm"] >= basin_max_measurable_cm(basin) - 0.5
    return r[["timestamp", "level_cm", "at_sensor_limit", "battery_v"]].reset_index(drop=True)


# ---------------------------------------------------------------------------
# 3. STORMS and SEDIMENT ESTIMATE
# ---------------------------------------------------------------------------
def rain_events(rain):
    wet = rain[rain["rain_mm"] > 0]
    if wet.empty:
        return pd.DataFrame(columns=["start", "end", "total_mm", "peak_mm_h"])
    step = rain["timestamp"].diff().median()
    event_id = (wet["timestamp"].diff() > pd.Timedelta(hours=RAIN_EVENT_GAP_H)).cumsum()
    ev = wet.groupby(event_id).agg(start=("timestamp", "min"), end=("timestamp", "max"),
                                   total_mm=("rain_mm", "sum"), peak_step_mm=("rain_mm", "max"))
    ev["end"] = ev["end"] + step
    ev["peak_mm_h"] = ev["peak_step_mm"] * (pd.Timedelta(hours=1) / step)
    return ev.drop(columns="peak_step_mm").reset_index(drop=True)


def sediment_estimate(basin, rain, since=None, start_cm=None):
    """Estimated sediment depth (cm above the sump floor) at every rain-gauge time step.

    sediment = measured at installation (or at the last cleaning) + rain since then x catchment x yield
    """
    per_mm_m = (basin["sediment_yield_kg_m2_yr"] / ANNUAL_RAIN_MM * basin["catchment_area_m2"]
                / (SEDIMENT_DENSITY * basin["basin_area_m2"]))
    base = basin["sediment_at_install_cm"] if start_cm is None else start_cm
    rain_since = rain["rain_mm"].where(rain["timestamp"] > since, 0) if since is not None else rain["rain_mm"]
    est = base + rain_since.cumsum() * per_mm_m * 100
    if since is not None:   # before the cleaning, keep the old estimate
        before = basin["sediment_at_install_cm"] + rain["rain_mm"].cumsum() * per_mm_m * 100
        est = est.where(rain["timestamp"] >= since, before)
    return pd.DataFrame({"timestamp": rain["timestamp"],
                         "sediment_cm": np.minimum(est, basin["sump_depth_cm"])})


# ---------------------------------------------------------------------------
# 4. HOW DID THE BASIN RESPOND TO EACH STORM?
# ---------------------------------------------------------------------------
def analyze_events(levels, events, now, basin=None):
    rows, learned = [], []
    sub = subdrain_above_invert_cm(basin) if basin is not None else None
    prev_capacity, prev_sudden = None, False
    for i, ev in events.iterrows():
        if ev["start"] > now:
            break
        next_start = events["start"].iloc[i + 1] if i + 1 < len(events) else pd.Timestamp.max
        window_end = min(next_start, now, ev["end"] + pd.Timedelta(hours=PEAK_SEARCH_AFTER_RAIN_H))
        during = levels[(levels["timestamp"] >= ev["start"]) & (levels["timestamp"] <= window_end)]

        default_rise = DEFAULT_RISE_CM_PER_MM_H * (basin["catchment_area_m2"] / 600 if basin is not None else 1)
        rise_per_mm_h = np.mean(learned) if len(learned) >= LEARNING_STORMS else default_rise
        intensity = max(ev["peak_mm_h"], MIN_INTENSITY_MM_H)
        row = {"start": ev["start"], "end": ev["end"], "total_mm": round(ev["total_mm"], 1),
               "peak_mm_h": round(ev["peak_mm_h"], 1), "peak_cm": np.nan,
               "expected_cm": round(rise_per_mm_h * intensity, 1), "rise_ratio": np.nan,
               "capacity_pct": np.nan, "grate_pct": np.nan, "drain_min": np.nan,
               "drawdown_cm_min": np.nan, "reached_limit": False, "reached_subdrain": False,
               "informative": False, "learning": len(learned) < LEARNING_STORMS, "sudden": False,
               "diagnosis": "no_data", "verdict": "No data", "status": "no_data"}
        if during.empty:
            rows.append(row)
            continue

        peak = during["level_cm"].max()
        row.update(peak_cm=peak, reached_limit=bool(during["at_sensor_limit"].any()),
                   reached_subdrain=sub is not None and peak >= sub)
        if now < ev["end"]:
            row.update(diagnosis="raining", verdict="Raining now", status=None)
            rows.append(row)
            continue

        ratio = peak / row["expected_cm"]
        row["rise_ratio"] = round(ratio, 2)

        # Drain time and drawdown rate after the rain stopped
        after = during[during["timestamp"] >= ev["end"]]
        drained = after[after["level_cm"] <= DRAINED_WITHIN_CM]
        if not drained.empty:
            minutes = max((drained["timestamp"].iloc[0] - ev["end"]).total_seconds() / 60, 0)
            drain_text = "drained right away" if minutes < 10 else f"drained in {nice_duration(minutes)}"
        else:
            minutes = (window_end - ev["end"]).total_seconds() / 60
            drain_text = f"still not drained after {nice_duration(minutes)}"
        row["drain_min"] = minutes
        start_level = after["level_cm"].max() if not after.empty else peak
        if minutes >= 10 and start_level > DRAINED_WITHIN_CM:
            row["drawdown_cm_min"] = round((start_level - DRAINED_WITHIN_CM) / minutes, 2)

        if (not row["learning"] and row["expected_cm"] >= GRATE_CHECK_MIN_EXPECTED_CM
                and ratio < GRATE_WATCH_RATIO):
            # Big rain, but the water hardly came in: the grate is probably covered
            status = "clean_soon" if ratio < GRATE_CLEAN_SOON_RATIO else "watch"
            row.update(diagnosis="grate", status=status, informative=True,
                       grate_pct=round(100 * ratio), capacity_pct=np.nan,
                       verdict=f"Rose only {peak:.0f} cm in a big rain (clean: ~{row['expected_cm']:.0f} cm)")
        elif peak < MIN_RISE_TO_JUDGE_CM:
            row.update(diagnosis="small", status="ok", verdict="Barely rose (normal)")
        else:
            row["informative"] = True
            if row["reached_limit"]:
                rise_status = "urgent"
            elif row["learning"]:
                rise_status = "ok"      # still learning this basin's normal rise: only extreme cases count
            else:
                rise_status = grade(ratio, RISE_OK_MAX, RISE_WATCH_MAX, RISE_CLEAN_SOON_MAX)
            drain_status = grade(minutes, DRAIN_OK_MAX_MIN, DRAIN_WATCH_MAX_MIN, DRAIN_CLEAN_SOON_MAX_MIN)
            status = worst(rise_status, drain_status)
            # rough estimate (storm-to-storm noise is about ±30%, so near-normal shows as ~100%)
            capacity = 100 if ratio <= 1.3 else 100 / ratio
            row["capacity_pct"] = round(capacity)
            row["sudden"] = capacity <= 25 and (
                (prev_capacity is not None and prev_capacity >= 70) or prev_sudden)
            prev_capacity, prev_sudden = capacity, row["sudden"]
            top = "Reached the top of the sensor range" if row["reached_limit"] else f"Rose {peak:.0f} cm"
            row.update(status=status, diagnosis="normal" if status == "ok" else "outlet",
                       verdict=f"{top}, {drain_text}")
            if len(learned) < LEARNING_STORMS:
                learned.append(peak / intensity)
        rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 5. LIVE STATE and MAINTENANCE STATUS AT TIME 'now'
# ---------------------------------------------------------------------------
def basin_status(basin, levels, events, rain, now, reset=None):
    """reset = (time, measured sediment in cm or None) of the last cleaning / "no issue found" visit.
    Storms before it no longer count for the maintenance status."""
    past = levels[levels["timestamp"] <= now]
    history = analyze_events(levels, events, now, basin)
    reset_time = reset[0] if reset else None
    sed = sediment_estimate(basin, rain[rain["timestamp"] <= now], since=reset_time,
                            start_cm=reset[1] if reset and reset[1] is not None else
                            (0.0 if reset else None))
    sed_cm = float(sed["sediment_cm"].iloc[-1]) if not sed.empty else basin["sediment_at_install_cm"]
    sed_pct = 100 * sed_cm / basin["sump_depth_cm"]
    raining = not events[(events["start"] <= now) & (events["end"] >= now)].empty
    sub = subdrain_above_invert_cm(basin)

    r = {"history": history, "sediment_cm": sed_cm, "sediment_pct": sed_pct,
         "sediment_status": grade(sed_pct, SEDIMENT_WATCH_PCT, SEDIMENT_CLEAN_SOON_PCT, 1000),
         "raining_now": raining, "max_measurable_cm": basin_max_measurable_cm(basin),
         "level_cm": None, "at_sensor_limit": False, "last_reading": None,
         "minutes_since_reading": None, "battery_v": None, "battery_status": "no_data",
         "worst_event": None, "last_event": None,
         "live": "no_data", "live_text": "The sensor has not sent any data yet.",
         "status": "no_data", "headline": "Sensor not reporting: check the sensor", "reasons": [],
         "trend": "", "issue_since": None, "confidence": None}
    if past.empty:
        return r

    last = past.iloc[-1]
    minutes_since = (now - last["timestamp"]).total_seconds() / 60
    recent = past[past["timestamp"] >= last["timestamp"] - pd.Timedelta(minutes=30)]
    change = recent["level_cm"].iloc[-1] - recent["level_cm"].iloc[0] if len(recent) > 1 else 0
    r["trend"] = "↑ Rising" if change > 2 else "↓ Draining" if change < -2 else "→ Stable"
    r.update(level_cm=float(last["level_cm"]), at_sensor_limit=bool(last["at_sensor_limit"]),
             last_reading=last["timestamp"], minutes_since_reading=minutes_since,
             battery_v=float(last["battery_v"]),
             battery_status=("urgent" if last["battery_v"] < BATTERY_CRITICAL_V else
                             "watch" if last["battery_v"] < BATTERY_LOW_V else "ok"))

    # ---- 1. LIVE STATE ----
    level = r["level_cm"]
    if minutes_since > NO_DATA_AFTER_MIN:
        r.update(live="no_data", live_text=f"Last reading {nice_duration(minutes_since)} ago "
                                           f"({format_level(level)} at the time).")
    elif r["at_sensor_limit"] or level > HIGH_WATER_CM or (sub is not None and level >= sub):
        txt = f"{'At least ' if r['at_sensor_limit'] else ''}{format_level(level)} above normal."
        if sub is not None and level >= sub:
            txt += " Water is above the subdrains and flowing back into the road base."
        r.update(live="backing_up", live_text=txt)
    elif level > NORMAL_BAND_CM:
        if raining:
            r.update(live="rising", live_text=f"{format_level(level)} with the rain. Fine if it goes "
                                              "back down quickly.")
        else:
            r.update(live="high", live_text=f"{format_level(level)} above normal although it isn't raining.")
    else:
        if raining:
            txt = "Raining, but the water is draining as fast as it comes in."
        elif level > DRAINED_WITHIN_CM:
            txt = f"Almost back to normal ({format_level(level)}), still draining."
        else:
            txt = "Currently drained: water at its normal level."
        r.update(live="normal", live_text=txt)

    # ---- 2. MAINTENANCE ----
    reasons = []
    if minutes_since > NO_DATA_AFTER_MIN:
        r.update(status="no_data", headline="Sensor not reporting: check the sensor")
        reasons.append(("no_data", f"No reading for {nice_duration(minutes_since)}. The sensor may be "
                                   "broken, covered or out of battery."))
        r["reasons"] = reasons
        return r

    informative = history[history["informative"]] if not history.empty else history
    if reset_time is not None and not informative.empty:
        informative = informative[informative["start"] >= reset_time]
    flagged = informative[informative["status"].isin(["watch", "clean_soon", "urgent"])] \
        if not informative.empty else informative
    r["issue_since"] = flagged["end"].iloc[0] if not flagged.empty else None
    r["confidence"] = (None if flagged.empty else "Low" if len(flagged) == 1 else
                       "Medium" if len(flagged) == 2 else "High")
    storm_status, diag = "ok", "normal"
    if informative.empty:
        reasons.append(("ok", "No real storm yet to test the basin."))
    else:
        # Clogging doesn't fix itself: the worst storm since the last cleaning sets the status
        ranks = informative["status"].map(lambda k: STATUS[k]["rank"])
        w = informative[ranks == ranks.max()].iloc[-1]
        last_ev = informative.iloc[-1]
        r.update(worst_event=w.to_dict(), last_event=last_ev.to_dict())
        storm_status, diag = w["status"], w["diagnosis"]
        reasons.append((w["status"], storm_sentence(w, basin, last=w.name == last_ev.name)))
        if w.name != last_ev.name:
            reasons.append((last_ev["status"], storm_sentence(last_ev, basin, last=True)))

    sed_status = r["sediment_status"]
    reasons.append((sed_status, f"Estimated sediment: {sed_cm:.0f} cm, {sed_pct:.0f}% of the "
                                f"{basin['sump_depth_cm']:.0f} cm sump (up to the trap's bottom lip)."))
    status = worst(storm_status, sed_status)

    if r["battery_status"] != "ok":
        word = "critical, replace it now" if r["battery_status"] == "urgent" else "low, replace it soon"
        reasons.append((r["battery_status"], f"Sensor battery is {word} ({r['battery_v']:.2f} V)."))

    r.update(status=status, reasons=reasons,
             headline=maintenance_headline(status, diag if storm_status == status else "sediment",
                                           r["live"], r["battery_status"], w if not informative.empty else None))
    return r


def maintenance_headline(status, diag, live, battery_status, worst_event):
    if status == "ok":
        head = "No maintenance needed"
        if battery_status != "ok":
            head += ", but the sensor battery needs replacing"
        return head
    if diag == "grate":
        head = ("Check the grate: it may be partly covered" if status == "watch"
                else "Maintenance required: grate blocked, water is staying on the street")
    elif diag == "sediment":
        head = ("Sump filling up with sediment (estimated): plan a cleaning" if status == "watch"
                else "Sump almost full of sediment (estimated): schedule a cleaning")
    else:
        sudden = worst_event is not None and bool(worst_event.get("sudden"))
        cause = "sudden blockage detected (debris in the trap or pipe?)" if sudden else \
                "clogging detected in recent storms"
        head = {"watch": "Outlet starting to restrict: keep an eye on it",
                "clean_soon": f"Schedule a cleaning: {cause}",
                "urgent": f"Maintenance required: {cause}"}[status]
    suffix = {"normal": " (water back to normal)", "backing_up": " (backing up right now)",
              "rising": " (raining now)", "high": " (water still high)"}.get(live, "")
    return head + suffix


def storm_sentence(ev, basin, last):
    label = "During the last storm" if last else "During the storm"
    when = f"{ev['start']:%b %d}, {ev['total_mm']:.0f} mm"
    if ev["diagnosis"] == "grate":
        return (f"{label} ({when}) the water rose only {ev['peak_cm']:.0f} cm, while this basin "
                f"normally rises about {ev['expected_cm']:.0f} cm in a rain like that. Only about "
                f"{ev['grate_pct']:.0f}% of the runoff seems to get in: the rest is staying on the street.")
    rose = ("the water rose to the top of the sensor range" if ev["reached_limit"]
            else f"the water rose {ev['peak_cm']:.0f} cm")
    text = (f"{label} ({when}) {rose}, while a clean basin rises about {ev['expected_cm']:.0f} cm. "
            f"Afterwards it {ev['verdict'].split(', ', 1)[1]}.")
    if ev["diagnosis"] == "outlet":
        bound = "at most " if ev["reached_limit"] else "about "
        text += f" Estimated outlet capacity left: {bound}{ev['capacity_pct']:.0f}%."
    if ev["reached_subdrain"]:
        text += " The water reached the subdrains (road base saturation, frost heave risk in winter)."
    return text


# ---------------------------------------------------------------------------
# 6. DISPATCHER VIEW: short answers for someone deciding in 3 seconds
# ---------------------------------------------------------------------------
def battery_pct(volts):
    if volts is None:
        return None
    return int(round(100 * np.clip((volts - BATTERY_EMPTY_V) / (BATTERY_FULL_V - BATTERY_EMPTY_V), 0, 1)))


def depth_below_street_m(basin, level_cm):
    """Water level above the invert (cm) -> depth of the water surface below the street (m)."""
    return (basin["grate_height_cm"] - (basin["outlet_invert_cm"] + level_cm)) / 100


def closest_readable_m(basin):
    """The closest the water can get to the street and still be measured (sensor + blind zone)."""
    return (basin["grate_height_cm"] - (basin["sensor_height_cm"] - basin["sensor_blind_zone_cm"])) / 100


def live_summary(basin, S):
    """Title, one-line value and action for the LIVE card."""
    key = S["live"]
    title = LIVE[key]["label"]
    if key == "no_data":
        last = (f"Last reading {nice_duration(S['minutes_since_reading'])} ago"
                if S["minutes_since_reading"] is not None else "Never reported")
        return {"title": title, "value": last, "action": "Inspect the sensor"}
    depth = depth_below_street_m(basin, S["level_cm"])
    if S["at_sensor_limit"]:
        value = f"Water ≤ {closest_readable_m(basin):.2f} m below street (above the sensor's range)"
    else:
        value = f"Water {depth:.2f} m below street"
    if key == "normal":
        title = ("Normal (keeping up with the rain)" if S["raining_now"] else
                 "Normal (drained)" if S["level_cm"] <= DRAINED_WITHIN_CM else "Normal (draining)")
        action = "No action"
    elif key == "rising":
        action = "Monitor: fine if it drains right after the rain"
    elif key == "high":
        action = "Water stuck high in dry weather: check within 24 h"
    else:
        action = "Dispatch a crew now: street flooding risk"
        sub = subdrain_above_invert_cm(basin)
        if sub is not None and S["level_cm"] >= sub:
            action += ". Backfilling into the subdrains / road base"
    return {"title": title, "value": value, "action": action}


def drainage_health(basin, S):
    """One combined 'drainage health' answer: (label, detail, status key, action)."""
    w = S.get("worst_event")
    if S["status"] == "no_data":
        return "Unknown", "No recent data", "no_data", "Inspect the sensor"
    if not w:
        return "Not tested yet", "No storm big enough yet", "ok", "No action"
    if w["diagnosis"] == "grate":
        return ("Grate blocked", f"Only ~{w['grate_pct']:.0f}% of the runoff gets in", w["status"],
                "Clear the grate")
    cap = f"{'≤' if w['reached_limit'] else '~'}{w['capacity_pct']:.0f}% capacity"
    label = {"ok": "Normal", "watch": "Slightly slow", "clean_soon": "Slow",
             "urgent": "Very slow"}[w["status"]]
    action = {"ok": "No action", "watch": "Inspect on the next route",
              "clean_soon": "Vacuum / jetting needed (schedule)",
              "urgent": "Vacuum / jetting needed (priority)"}[w["status"]]
    if w["status"] == "ok" and S["sediment_status"] != "ok":
        return "Normal", f"{cap} · sump filling (est. {S['sediment_pct']:.0f}%)", S["sediment_status"], \
               "Add to the next vacuum route"
    return label, cap, w["status"], action


def dispatch_summary(basin, S):
    """Structured maintenance summary: list of (field, text)."""
    rows = []
    status, w = S["status"], S.get("worst_event")
    if status == "no_data":
        silent = nice_duration(S["minutes_since_reading"]) if S["minutes_since_reading"] else "a while"
        rows = [("Problem", f"Sensor silent for {silent}"),
                ("Likely cause", "Dead battery, damaged or covered sensor"),
                ("Recommended action", "Inspect the sensor")]
    elif status == "ok":
        rows = [("Problem", "None"), ("Recommended action", "No action needed")]
    elif w is not None and w["status"] == status and w["diagnosis"] == "grate":
        rows = [("Problem", f"Water barely got in during the {w['start']:%b %d} rain "
                            f"(rose {w['peak_cm']:.0f} cm, ≈{w['expected_cm']:.0f} cm normally)"),
                ("Likely cause", "Grate covered (leaves, debris): water stays on the street"),
                ("Recommended action", "Clear the grate (quick street-crew job)")]
    elif w is not None and w["status"] == status:
        drained = w["drain_min"]
        if w["reached_limit"]:
            problem = f"Filled to the top of the sensor range in the {w['start']:%b %d} rain ({w['total_mm']:.0f} mm)"
        else:
            problem = (f"Rose {w['peak_cm']:.0f} cm in the {w['start']:%b %d} rain "
                       f"(≈{w['expected_cm']:.0f} cm when clean)")
        if drained >= 10:
            problem += f", took {nice_duration(drained)} to drain (< 10 min when clean)"
        if w["sudden"]:
            cause = "Sudden blockage: debris jammed in the trap or outlet pipe"
        elif S["sediment_pct"] < SEDIMENT_WATCH_PCT:
            cause = (f"Debris in the trap or a partial pipe restriction (sump only ~{S['sediment_pct']:.0f}% "
                     "full, estimated)")
        elif basin["trap_height_cm"] > 0:
            cause = (f"Sediment likely reaching the trap lip (sump ~{S['sediment_pct']:.0f}% full, estimated) "
                     "or a partial pipe restriction")
        else:
            cause = "Sediment covering the outlet or a partial pipe restriction"
        action = {"watch": "Inspect on the next route", "clean_soon": "Schedule a vacuum truck (non-emergency)",
                  "urgent": "Send a vacuum / jetting crew (priority)"}[status]
        rows = [("Problem", problem), ("Likely cause", cause), ("Recommended action", action)]
    else:
        rows = [("Problem", f"Sump filling up: ~{S['sediment_pct']:.0f}% full (estimated)"),
                ("Likely cause", "Normal sediment build-up"),
                ("Recommended action", "Add to the next vacuum route" if status == "watch"
                 else "Schedule a vacuum truck (non-emergency)")]
    if S["battery_status"] in ("watch", "urgent") and status != "no_data":
        when = "replace it now" if S["battery_status"] == "urgent" else "replace it on the next visit"
        rows.append(("Device", f"Battery low (~{battery_pct(S['battery_v'])}%): {when}"))
    return rows


def maintenance_title(S):
    return {"ok": "No maintenance needed", "watch": "Keep an eye on it", "clean_soon": "Maintenance needed",
            "urgent": "Maintenance required", "no_data": "Check the sensor"}[S["status"]]


def action_banner(basin, S):
    """The ONE thing to do about this basin: (colour key, icon, headline, detail)."""
    live = live_summary(basin, S)
    if S["live"] == "backing_up":
        where = (f"≤ {closest_readable_m(basin):.2f} m" if S["at_sensor_limit"]
                 else f"{depth_below_street_m(basin, S['level_cm']):.2f} m")
        return "urgent", "✖", f"Flooding: water backing up, {where} below the street", live["action"]
    if S["live"] == "no_data":
        return "no_data", "?", "Sensor offline: inspect the sensor", live["value"]
    if S["live"] == "high":
        return "clean_soon", "!", "Not draining after the rain", live["action"]
    status, w = S["status"], S.get("worst_event")
    if status == "ok":
        head = "Normal: draining well" if not S["raining_now"] else "Normal: keeping up with the rain"
        detail = "No action needed"
        if S["battery_status"] != "ok":
            detail += f" · sensor battery low (~{battery_pct(S['battery_v'])}%), replace it on the next visit"
        return "ok", "✔", head, detail
    rows = dict(dispatch_summary(basin, S))
    if w is not None and w["status"] == status and w["diagnosis"] == "grate":
        what, do = "Grate blocked", "clear the grate"
    elif w is not None and w["status"] == status:
        what = {"watch": "Starting to drain slowly", "clean_soon": "Draining slowly",
                "urgent": "Draining very slowly"}[status]
        do = {"watch": "inspect on the next route", "clean_soon": "schedule vacuum",
              "urgent": "vacuum / jetting, priority"}[status]
    else:
        what, do = "Sump filling up", "plan a vacuum"
    return ("clean_soon" if status != "urgent" else "urgent"), "!", \
        f"Maintenance needed: {what} ({do})", rows.get("Likely cause", "")
