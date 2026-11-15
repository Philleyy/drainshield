import pandas as pd

import polling_controller as pc

NOW = pd.Timestamp("2026-11-14 18:00")


def fc(total_mm, start_in_h=6, hours=6, now_mm_h=0.0):
    rain = pc.demo_forecast(NOW, total_mm, start_in_h, hours)
    if now_mm_h:
        rain.loc[rain["timestamp"] == NOW.floor("h"), "rain_mm"] = now_mm_h
    return pc.forecast_summary(rain, NOW)


def test_dry_watch_storm():
    assert pc.decide(fc(0), 0, 0, {}, NOW)[0] == "DRY"
    assert pc.decide(fc(1), 0, 0, {}, NOW)[0] == "DRY"                       # < 2 mm in 24 h
    assert pc.decide(fc(25), 0, 0, {}, NOW)[0] == "WATCH"                    # pre-storm watch, 6 h ahead
    assert pc.decide(fc(5, start_in_h=8), 0, 0, {}, NOW)[0] == "DRY"         # light rain, still far off
    assert pc.decide(fc(5, start_in_h=2), 0, 0, {}, NOW)[0] == "WATCH"       # light rain about to start
    assert pc.decide(fc(0), 0, 0.5, {}, NOW)[0] == "STORM"                   # water rising
    assert pc.decide(fc(0), 15, 0, {}, NOW)[0] == "STORM"                    # water high
    assert pc.decide(fc(0, now_mm_h=4), 0, 0, {}, NOW)[0] == "STORM"         # raining hard now
    assert pc.decide(None, 0, 0, {}, NOW)[0] == "DRY"                        # offline


def test_hold_times():
    state = {}
    assert pc.decide(fc(0), 0, 1.0, state, NOW)[0] == "STORM"
    assert pc.decide(fc(0), 0, 0, state, NOW + pd.Timedelta(minutes=20))[0] == "STORM"   # catch the drawdown
    assert pc.decide(fc(0), 0, 0, state, NOW + pd.Timedelta(minutes=31))[0] == "DRY"
    state = {}
    assert pc.decide(fc(25), 0, 0, state, NOW)[0] == "WATCH"
    assert pc.decide(fc(0), 0, 0, state, NOW + pd.Timedelta(minutes=90))[0] == "WATCH"
    assert pc.decide(fc(0), 0, 0, state, NOW + pd.Timedelta(minutes=121))[0] == "DRY"
