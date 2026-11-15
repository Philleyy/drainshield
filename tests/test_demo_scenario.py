import os

import pandas as pd

import demo_scenario as dsc

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def build(tmp_path, monkeypatch):
    registry = pd.read_csv(os.path.join(REPO, "data", "municipal_basins.csv"), dtype={"municipal_id": str})
    monkeypatch.chdir(tmp_path)
    return dsc.build(registry)


def test_story_in_the_readings(tmp_path, monkeypatch):
    r = build(tmp_path, monkeypatch)
    assert dsc.ready() and r["basin_id"].nunique() == 12
    day = r[r["timestamp"] >= dsc.DAY]
    # adaptive modes: dry at night, storm during the evening storm
    night = day[day["timestamp"] < dsc.at("05:00")]
    assert set(night["mode"]) == {"DRY"}
    assert (day[(day["timestamp"] > dsc.at("19:00")) & (day["timestamp"] < dsc.at("22:00"))]["mode"] == "STORM").all()
    # surprise thunderstorm: sensors switch themselves before the 11:00 forecast
    assert (day[(day["timestamp"] > dsc.at("09:30")) & (day["timestamp"] < dsc.at("10:30"))]["mode"] == "STORM").any()
    # radio outage: readings kept and delivered late, none lost
    out = day[(day["basin_id"] == "S4-N1") & (day["timestamp"] >= dsc.at("13:20")) & (day["timestamp"] < dsc.at("14:40"))]
    assert len(out) >= 15 and (out["received"] >= dsc.at("14:40")).all()
    # loose connector: nothing at all from S9-A between 07:50 and 12:10
    k = day[day["basin_id"] == "S9-A"]
    assert k[(k["timestamp"] >= dsc.at("07:50")) & (k["timestamp"] < dsc.at("12:10"))].empty
    # frost: no-echo readings flagged iced, no distance
    ice = day[(day["basin_id"] == "S8-A") & (day["flags"] & dsc.REC_ICED > 0)]
    assert len(ice) >= 4 and ice["distance_cm"].isna().all()
    # flood: S7-N1 reaches the top of the sensor range
    f = day[day["basin_id"] == "S7-N1"]
    assert (f["flags"] & dsc.REC_AT_BLIND > 0).any()


def test_forecast_as_of():
    actual = dsc.hourly(dsc.minute_rain())
    before = dsc.rain_as_of(dsc.at("09:00"), actual)
    evening = before[(before["timestamp"] >= dsc.at("18:00")) & (before["timestamp"] < dsc.at("23:00"))]
    assert evening["rain_mm"].sum() == 0                              # not forecast yet
    after = dsc.rain_as_of(dsc.at("11:05"), actual)
    evening = after[(after["timestamp"] >= dsc.at("18:00")) & (after["timestamp"] < dsc.at("23:00"))]
    assert evening["rain_mm"].sum() == 29                             # the 11:00 forecast
    thunder = dsc.rain_as_of(dsc.at("09:00"), actual)
    assert thunder[thunder["timestamp"] == dsc.at("09:00")]["rain_mm"].iloc[0] == 0   # surprise: not forecast


def test_event_lookup():
    assert dsc.event_now(dsc.at("20:30"))["title"].startswith("Water backing up")
    assert dsc.event_now(dsc.DAY - pd.Timedelta(minutes=1)) is None
