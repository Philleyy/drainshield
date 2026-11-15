"""
predictive.py: which catch basins will back up in TOMORROW's storm?
-------------------------------------------------------------------
processing.py tells us how each basin behaved in PAST storms (how high the water rose for a given rain
intensity, and how long it took to drain). This module projects that behaviour onto the FORECAST
(Environment Canada GEM/HRDPS, hourly, via Open-Meteo) to flag basins BEFORE the rain starts.

THE RULE, in three numbers per basin
  k_now   [cm per mm/h]  how high the water rose per mm/h of rain in the latest storm since the last cleaning
                         (k_clean = the same for the first storms after installation, when it was clean)
  h_start [cm]           water still in the basin when tomorrow's rain starts:
                         today's level minus (drawdown rate x minutes until the rain)
  i_fc    [mm/h]         the forecast's wettest hour in the next 24 h

  predicted peak  h_pred = h_start + k_now * i_obs * (i_fc / i_obs) ** p
        p = 1 when tomorrow is lighter than the storm we observed (scale down linearly)
        p = 2 when tomorrow is heavier (WHY: a restricted outlet behaves like an orifice, Q = Cd a sqrt(2 g h),
              so the head h grows with the SQUARE of the flow: the conservative choice for storms we haven't seen)

  Flag:  🔴 Inspect before storm   h_pred >= HIGH_WATER_CM (processing.py: backing up) or reaches the street zone
         🟠 Clean this week        h_pred >= half of that, or recovery index >= 3 (drains 3x slower than when clean)

  Recovery index RI = drain time now / drain time when clean. It catches a restriction even when the
  storms were too small to make the water rise much.

WHY CALIBRATE ON THE BASIN ITSELF instead of a textbook model: k is learned from the SAME hourly model rain
that the forecast uses, so the model's own bias (hourly averages hide 5-minute bursts) cancels out. A
rational-method + orifice check is kept for the engineering view (engineering_check), as a sanity bound.

DRY BASELINE: in dry weather the water rests at the outlet invert. If the dry reading creeps UP over days,
debris or sediment is sitting above the water line (trap blocked). If it drops, the sump water is
evaporating in a dry spell (normal, but the sensor reads below the invert).
"""

import math

import numpy as np
import pandas as pd

import processing as proc

HORIZON_H = 24                 # look this far ahead in the forecast
MIN_FORECAST_MM_H = 1.0        # below this, no prediction (nothing to predict)
MAX_EXPONENT = 2.0             # orifice law for storms heavier than the one observed
RI_INSPECT = 3.0               # recovery index that alone flags a basin
STREET_FREEBOARD_CM = 30       # "reaches the street zone" = within 30 cm of the grate
DRY_DRIFT_UP_CM = 3            # dry level this much above the invert for 3 days -> debris above water
DRY_DRIFT_DOWN_CM = 5          # this much below -> sump evaporating
DRY_DAYS = 3


def forecast_window(rain, now, hours=HORIZON_H):
    """Wettest forecast hour, total and start time in the next `hours` (None if no forecast)."""
    if rain is None or rain.empty or rain["timestamp"].max() <= now:
        return None
    w = rain[(rain["timestamp"] > now) & (rain["timestamp"] <= now + pd.Timedelta(hours=hours))]
    wet = w[w["rain_mm"] > 0]
    return {"max_mm_h": float(w["rain_mm"].max()) if not w.empty else 0.0,
            "total_mm": float(w["rain_mm"].sum()),
            "starts": wet["timestamp"].iloc[0] if not wet.empty else None}


def coefficients(history, reset=None):
    """k_clean, k_now (cm per mm/h), drain times clean/now (min), observed intensity and drawdown rate
    of the latest informative storm. history = processing.analyze_events() output."""
    out = {"k_clean": None, "k_now": None, "i_obs": None, "t_clean": None, "t_now": None,
           "drawdown_cm_min": None, "storms": 0}
    if history is None or history.empty:
        return out
    inf = history[history["informative"] & history["peak_cm"].notna()]
    if reset is not None:
        inf = inf[inf["start"] >= reset]
    if inf.empty:
        return out
    intensity = inf["peak_mm_h"].clip(lower=proc.MIN_INTENSITY_MM_H)
    k = inf["peak_cm"] / intensity
    learning = inf[inf["learning"]]
    out["storms"] = len(inf)
    out["k_clean"] = float(k[inf["learning"]].mean()) if not learning.empty else None
    last = inf.iloc[-1]
    out["k_now"] = float(k.iloc[-1])
    out["i_obs"] = float(intensity.iloc[-1])
    clean_drain = learning["drain_min"].dropna()
    out["t_clean"] = float(clean_drain.median()) if not clean_drain.empty else None
    out["t_now"] = None if pd.isna(last["drain_min"]) else float(last["drain_min"])
    out["drawdown_cm_min"] = None if pd.isna(last.get("drawdown_cm_min")) else float(last["drawdown_cm_min"])
    return out


def recovery_index(t_now, t_clean, floor_min=10):
    """Drain time now / drain time when clean (both floored at 10 min: "drained right away" = 1)."""
    if t_now is None or t_clean is None:
        return None
    return round(max(t_now, floor_min) / max(t_clean, floor_min), 1)


def predicted_peak_cm(k_now, i_obs, i_fc, h_start=0.0):
    """Peak level above the invert for a forecast intensity, scaled from the observed storm."""
    if k_now is None or i_obs is None or i_fc is None or i_fc < MIN_FORECAST_MM_H:
        return None
    ratio = i_fc / max(i_obs, 1e-6)
    p = 1.0 if ratio <= 1 else MAX_EXPONENT
    return round(h_start + k_now * i_obs * ratio ** p, 1)


def water_at_rain_start(level_cm, drawdown_cm_min, minutes_until_rain):
    """Level left when the rain starts, if the basin keeps draining at its observed rate."""
    if level_cm is None or level_cm <= proc.DRAINED_WITHIN_CM:
        return 0.0
    if drawdown_cm_min is None or minutes_until_rain is None:
        return float(level_cm)                      # don't know how fast it drains: assume it stays
    return max(0.0, level_cm - drawdown_cm_min * minutes_until_rain)


def street_zone_cm(basin):
    """Level above the invert at which water is within STREET_FREEBOARD_CM of the grate."""
    return basin["grate_height_cm"] - basin["outlet_invert_cm"] - STREET_FREEBOARD_CM


def overflow_risk(basin, S, rain, now, reset=None):
    """Prediction for one monitored basin. S = data_store.status_for() / processing.basin_status() result."""
    fc = forecast_window(rain, now)
    c = coefficients(S.get("history"), reset)
    ri = recovery_index(c["t_now"], c["t_clean"])
    out = {"basin_id": basin["basin_id"], "forecast_max_mm_h": None if fc is None else fc["max_mm_h"],
           "forecast_total_mm": None if fc is None else fc["total_mm"],
           "rain_starts": None if fc is None else fc["starts"], "k_clean": c["k_clean"], "k_now": c["k_now"],
           "recovery_index": ri, "h_start_cm": None, "predicted_peak_cm": None,
           "backing_up_cm": proc.HIGH_WATER_CM, "street_zone_cm": round(street_zone_cm(basin), 1),
           "flag": None, "sentence": ""}
    if fc is None:
        out["sentence"] = "No forecast (offline)."
        return out
    minutes = None if fc["starts"] is None else max((fc["starts"] - now).total_seconds() / 60, 0)
    h0 = water_at_rain_start(S.get("level_cm"), c["drawdown_cm_min"], minutes)
    pred = predicted_peak_cm(c["k_now"], c["i_obs"], fc["max_mm_h"], h0)
    out.update(h_start_cm=round(h0, 1), predicted_peak_cm=pred)

    red_at = min(proc.HIGH_WATER_CM, out["street_zone_cm"])
    if pred is not None and pred >= red_at:
        out["flag"] = "Urgent"
    elif (pred is not None and pred >= red_at / 2) or (ri is not None and ri >= RI_INSPECT):
        out["flag"] = "Inspect"

    if pred is None:
        out["sentence"] = ("No storm since installation or cleaning to learn from yet." if c["k_now"] is None
                           else f"Dry forecast (wettest hour {fc['max_mm_h']:.1f} mm/h).")
    else:
        when = f" ({fc['starts']:%a %H:%M})" if fc["starts"] is not None else ""
        out["sentence"] = (f"Forecast {fc['max_mm_h']:.0f} mm/h{when}: water expected to rise to about "
                           f"{pred:.0f} cm above the outlet (backing up at {proc.HIGH_WATER_CM} cm)"
                           + (f", drains {ri:g}x slower than when clean." if ri and ri >= 1.5 else "."))
    return out


# ---------------------------------------------------------------------------
# Dry-weather baseline drift (self-check of the sediment / evaporation state)
# ---------------------------------------------------------------------------
def dry_baseline_drift(levels, rain, now, days=DRY_DAYS):
    """Median level (cm above invert) in hours with no rain in the previous 24 h, over the last `days`.
    Returns (median_cm or None, verdict)."""
    if levels is None or levels.empty:
        return None, "no data"
    since = now - pd.Timedelta(days=days)
    lv = levels[(levels["timestamp"] >= since) & (levels["timestamp"] <= now)]
    if rain is not None and not rain.empty:
        wet = rain[rain["rain_mm"] > 0]["timestamp"]
        if not wet.empty:
            last_wet = wet.searchsorted(lv["timestamp"], side="right") - 1
            prev = np.where(last_wet >= 0, wet.to_numpy()[np.clip(last_wet, 0, None)], np.datetime64("NaT"))
            dry = pd.isna(prev) | ((lv["timestamp"].to_numpy() - prev) > np.timedelta64(24, "h"))
            lv = lv[dry]
    if len(lv) < 6:
        return None, "not enough dry readings"
    m = float(lv["level_cm"].median())
    if m >= DRY_DRIFT_UP_CM:
        return m, "debris or sediment above the water line (dry level above the outlet)"
    if m <= -DRY_DRIFT_DOWN_CM:
        return m, "sump water evaporating in the dry spell (reads below the outlet)"
    return m, "normal"


# ---------------------------------------------------------------------------
# Engineering cross-check: rational method + orifice (for the Engineering view and the pitch)
# ---------------------------------------------------------------------------
def rational_inflow_l_s(runoff_coeff, intensity_mm_h, catchment_m2):
    """Q = C i A. i in mm/h, A in m2 -> L/s."""
    return runoff_coeff * intensity_mm_h / 3.6e6 * catchment_m2 * 1000


def orifice_head_cm(flow_l_s, outlet_diameter_cm, open_fraction, cd=0.6):
    """Head above the outlet needed to pass `flow_l_s` through an outlet whose effective opening is
    `open_fraction` of the pipe area: h = (Q / (Cd a))^2 / 2g."""
    a = math.pi * (outlet_diameter_cm / 200) ** 2 * max(open_fraction, 1e-4)
    v = flow_l_s / 1000 / (cd * a)
    return v * v / (2 * 9.81) * 100


def engineering_check(basin, intensity_mm_h, open_fraction):
    q = rational_inflow_l_s(basin.get("runoff_coeff", 0.9), intensity_mm_h, basin.get("catchment_area_m2", 600))
    return {"inflow_l_s": round(q, 2),
            "head_cm": round(orifice_head_cm(q, basin.get("outlet_diameter_cm", 25), open_fraction), 1)}
