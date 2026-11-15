import pandas as pd

import predictive as pr
import processing as proc


def history(rows):
    base = {"informative": True, "learning": False, "drawdown_cm_min": None}
    return pd.DataFrame([{**base, **r} for r in rows])


def test_coefficients_and_recovery_index():
    h = history([
        {"start": pd.Timestamp("2026-09-01"), "peak_cm": 3.0, "peak_mm_h": 10, "drain_min": 8, "learning": True},
        {"start": pd.Timestamp("2026-09-10"), "peak_cm": 4.0, "peak_mm_h": 10, "drain_min": 9, "learning": True},
        {"start": pd.Timestamp("2026-10-20"), "peak_cm": 18.0, "peak_mm_h": 9, "drain_min": 45,
         "drawdown_cm_min": 0.3}])
    c = pr.coefficients(h)
    assert abs(c["k_clean"] - 0.35) < 1e-9 and abs(c["k_now"] - 2.0) < 1e-9
    assert pr.recovery_index(c["t_now"], c["t_clean"]) == 4.5


def test_prediction_linear_down_quadratic_up():
    assert pr.predicted_peak_cm(2.0, 10, 5) == 10.0          # half the rain -> half the rise
    assert pr.predicted_peak_cm(2.0, 10, 20) == 80.0         # double the rain -> 4x (orifice law)
    assert pr.predicted_peak_cm(2.0, 10, 0.2) is None        # dry forecast


def test_water_at_rain_start():
    assert pr.water_at_rain_start(20, 0.5, 30) == 5
    assert pr.water_at_rain_start(20, 0.5, 120) == 0
    assert pr.water_at_rain_start(1, None, None) == 0


def basin():
    return {"basin_id": "T1", "grate_height_cm": 170.0, "outlet_invert_cm": 30.0, "catchment_area_m2": 600,
            "runoff_coeff": 0.9, "outlet_diameter_cm": 25}


def rain(now, mm_h, start_h=6, hours=3):
    ts = pd.date_range(now.floor("h") - pd.Timedelta(hours=3), periods=40, freq="h")
    r = pd.Series(0.0, index=ts)
    s = now.floor("h") + pd.Timedelta(hours=start_h)
    r[(ts >= s) & (ts < s + pd.Timedelta(hours=hours))] = mm_h
    return pd.DataFrame({"timestamp": ts, "rain_mm": r.values})


def test_overflow_flags():
    now = pd.Timestamp("2026-11-14 18:00")
    h = history([
        {"start": now - pd.Timedelta(days=40), "peak_cm": 3.0, "peak_mm_h": 10, "drain_min": 8, "learning": True},
        {"start": now - pd.Timedelta(days=2), "peak_cm": 24.0, "peak_mm_h": 8, "drain_min": 60}])
    S = {"history": h, "level_cm": 0.0}
    heavy = pr.overflow_risk(basin(), S, rain(now, 12), now)
    assert heavy["flag"] == "Urgent" and heavy["predicted_peak_cm"] >= proc.HIGH_WATER_CM
    light = pr.overflow_risk(basin(), S, rain(now, 2), now)
    assert light["flag"] == "Inspect"                         # small rise, but drains 6x slower than clean
    clean = {"history": history([{"start": now - pd.Timedelta(days=2), "peak_cm": 3.0, "peak_mm_h": 10,
                                  "drain_min": 8, "learning": True}]), "level_cm": 0.0}
    assert pr.overflow_risk(basin(), clean, rain(now, 12), now)["flag"] is None
    assert pr.overflow_risk(basin(), S, None, now)["sentence"].startswith("No forecast")


def test_dry_baseline_drift():
    now = pd.Timestamp("2026-11-14 18:00")
    ts = pd.date_range(now - pd.Timedelta(days=3), now, freq="30min")
    lv = pd.DataFrame({"timestamp": ts, "level_cm": 4.0})
    dry = pd.DataFrame({"timestamp": pd.date_range(now - pd.Timedelta(days=10), now, freq="h"), "rain_mm": 0.0})
    m, verdict = pr.dry_baseline_drift(lv, dry, now)
    assert m == 4.0 and verdict.startswith("debris")
    m, verdict = pr.dry_baseline_drift(lv.assign(level_cm=-7.0), dry, now)
    assert verdict.startswith("sump water evaporating")


def test_engineering_check_numbers():
    e = pr.engineering_check(basin(), 20, 1.0)
    assert abs(e["inflow_l_s"] - 3.0) < 0.01                  # 0.9 x 20 mm/h x 600 m2 = 3 L/s
    assert e["head_cm"] <= 0.1                                 # a clean 250 mm outlet barely notices it
    assert 15 < pr.engineering_check(basin(), 20, 0.05)["head_cm"] < 30   # 5% open -> ~21 cm of water
