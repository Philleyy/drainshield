"""processing.calibrate: a basin with no as-built outlet depth learns it from its resting water level."""
import pandas as pd

import basin_model as bm
import processing as proc


def basin(known):
    cfg = bm.default_config()
    cfg.update(basin_id="B1", invert_known=known, sensor_depth_mm=400)
    return pd.Series(bm.build_row(cfg))


def steady(distance_cm, hours=8):
    t = pd.date_range("2026-11-10 00:00", periods=hours * 4, freq="15min")
    return pd.DataFrame({"basin_id": "B1", "timestamp": t, "distance_cm": distance_cm})


def test_unknown_outlet_depth_is_learned_from_the_water():
    b = proc.calibrate(basin(known=False), steady(85.0))     # water rests 85 cm under the sensor (not the guessed 100)
    assert b["cal_status"] == "learned"
    assert b["invert_depth_cm"] == 125 and b["sensor_depth_cm"] == 40      # 0.40 m taped + 0.85 m learned
    assert b["grate_height_cm"] - b["outlet_invert_cm"] == 125
    assert proc.depth_below_street_m(b, 0) == 1.25


def test_known_outlet_depth_still_refuses_a_far_off_resting_level():
    b = proc.calibrate(basin(known=True), steady(60.0))      # 40 cm off the plans: not trusted
    assert b["cal_status"] == "learning" and "higher than expected" in b["cal_note"]
