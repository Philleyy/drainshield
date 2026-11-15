import json
from datetime import datetime

import lora_bridge as lb

RECV = datetime(2026, 11, 14, 18, 0, 0)


def line(node=1, first=10, records=None, **kw):
    msg = {"type": "pkt", "node": node, "first": first, "mode": 1, "backlog": 0, "rssi": -40.0, "snr": 9.5,
           "records": records or [[120, 812, 810, -3, 6, 196, 0], [60, 808, 809, 2, 6, 196, 0]]}
    msg.update(kw)
    return json.dumps(msg)


def test_decode_times_and_values():
    seen = {}
    _, rows = lb.decode(line(), RECV, {1: "TEST-01"}, seen)
    assert [r["timestamp"].strftime("%H:%M:%S") for r in rows] == ["17:58:00", "17:59:00"]
    assert rows[0]["basin_id"] == "TEST-01" and rows[0]["distance_cm"] == 81.0 and rows[0]["battery_v"] == 3.92
    assert rows[1]["rise_mm_min"] == 0.2 and seen == {"1": 11}


def test_duplicates_dropped_and_restart():
    seen = {}
    lb.decode(line(), RECV, {}, seen)
    _, rows = lb.decode(line(), RECV, {}, seen)                       # same packet again (ACK was lost)
    assert rows == []
    _, rows = lb.decode(line(first=11, records=[[60, 1, 1, 0, 0, 0, 0], [0, 900, 900, 0, 6, 196, 0]]), RECV, {}, seen)
    assert [r["index"] for r in rows] == [12]                         # overlap: only the new one
    _, rows = lb.decode(line(first=0, records=[[0, 900, 900, 0, 6, 196, 0]]), RECV, {}, seen)
    assert len(rows) == 1                                             # counter restarted: accepted


def test_flags_map_to_dashboard_contract():
    seen = {}
    recs = [[0, 35, 35, 0, 6, 196, lb.REC_AT_BLIND], [0, 0, 800, 0, -4, 196, lb.REC_NO_ECHO | lb.REC_ICED],
            [0, 700, 700, 0, 20, 0, lb.REC_ON_USB]]
    _, rows = lb.decode(line(records=recs), RECV, {}, seen)
    assert rows[0]["distance_cm"] == lb.BLIND_ZONE_CM                 # water at the sensor = HIGH, kept
    assert rows[1]["distance_cm"] is None and "sensor iced" in lb.flag_text(rows[1]["flags"])
    assert rows[2]["battery_v"] is None and rows[0]["basin_id"] == "NODE-01"


def test_node_map_and_modes(tmp_path):
    f = tmp_path / "monitored.csv"
    f.write_text("basin_id,sensor_id\nPILOT-A,DS-01\nPILOT-B,2\nOTHER,\n")
    m = lb.node_map("3=PILOT-C", str(f))
    assert m == {1: "PILOT-A", 2: "PILOT-B", 3: "PILOT-C"}
    modes = lb.wanted_modes(m, {"PILOT-A": {"mode": "STORM"}, "PILOT-B": {"interval_s": 300},
                                "PILOT-C": {"interval_s": 1800}})
    assert modes == {1: 2, 2: 1, 3: 0}


def test_write_files(tmp_path):
    seen = {}
    _, rows = lb.decode(line(), RECV, {1: "TEST-01"}, seen)
    live, tele, status = tmp_path / "live.csv", tmp_path / "tele.csv", tmp_path / "status.json"
    lb.append_rows(rows, RECV, str(live), str(tele))
    lb.update_status(rows, str(status))
    assert live.read_text().splitlines()[0] == "basin_id,timestamp,distance_cm,battery_v"
    assert live.read_text().splitlines()[1] == "TEST-01,2026-11-14T17:58:00,81.0,3.92"
    assert json.loads(status.read_text())["TEST-01"]["mode"] == "WATCH"
