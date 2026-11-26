"""Tests for the web server: sign-in, accounts, upload keys, sensor uploads. Run from web/: python -m pytest -q"""

import os
import sys
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WEB))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("SETUP_TOKEN", "test-setup-token")
    monkeypatch.setenv("COOKIE_SECURE", "0")
    monkeypatch.setenv("WEB_DATA_DIR", str(tmp_path / "web"))        # live data copies: not the repo's data/ folder
    for m in [m for m in sys.modules if m.startswith("server")]:
        del sys.modules[m]
    import server.config as config
    config.DATABASE_URL = f"sqlite:///{tmp_path / 'test.db'}"
    from sqlalchemy import create_engine
    import server.db as db
    db.engine = create_engine(config.DATABASE_URL, connect_args={"check_same_thread": False})
    import server.main as main
    main.engine = db.engine
    main.security.limiter.fails.clear()
    from fastapi.testclient import TestClient
    with TestClient(main.app) as c:
        send = c.request

        def english(method, url, *args, **kwargs):          # the site answers in French by default; these checks read English
            url = str(url)
            return send(method, url + ("&" if "?" in url else "?") + "lang=en", *args, **kwargs)
        c.request = english
        yield c


def setup_admin(c, password="correct horse battery"):
    r = c.post("/api/setup", json={"token": "test-setup-token", "email": "Phil@Example.com", "name": "Phil",
                                   "password": password})
    assert r.status_code == 200, r.text
    return r


def test_setup_once_and_needs_token(client):
    assert client.get("/api/setup").json() == {"needed": True}
    assert client.post("/api/setup", json={"token": "wrong", "email": "a@b.ca", "name": "A",
                                           "password": "long enough pw"}).status_code == 403
    setup_admin(client)
    assert client.get("/api/auth/me").json()["user"]["email"] == "phil@example.com"
    assert client.get("/api/setup").json() == {"needed": False}
    assert client.post("/api/setup", json={"token": "test-setup-token", "email": "x@y.ca", "name": "X",
                                           "password": "long enough pw"}).status_code == 409


def test_login_logout_and_wrong_password(client):
    setup_admin(client)
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/login", json={"email": "phil@example.com", "password": "nope"}).status_code == 401
    r = client.post("/api/auth/login", json={"email": " PHIL@example.com", "password": "correct horse battery"})
    assert r.status_code == 200
    assert "httponly" in r.headers["set-cookie"].lower()
    assert client.get("/api/auth/me").status_code == 200


def test_rate_limit(client):
    setup_admin(client)
    for _ in range(8):
        client.post("/api/auth/login", json={"email": "phil@example.com", "password": "bad"})
    r = client.post("/api/auth/login", json={"email": "phil@example.com", "password": "correct horse battery"})
    assert r.status_code == 429


def test_new_user_must_change_temporary_password(client):
    setup_admin(client)
    r = client.post("/api/users", json={"email": "crew@dorval.ca", "name": "Crew 1", "role": "crew"})
    assert r.status_code == 200
    temp = r.json()["temporary_password"]
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"email": "crew@dorval.ca", "password": temp}).status_code == 200
    assert client.get("/api/sensors").json()["detail"] == "password_change_required"
    assert client.get("/api/sensors?allow_pending_password=true").status_code == 403
    assert client.post("/api/auth/password", json={"current": temp, "new": "short"}).status_code == 422
    assert client.post("/api/auth/password", json={"current": temp, "new": "a much better one"}).status_code == 200
    assert client.get("/api/sensors").status_code == 200
    assert client.get("/api/users").status_code == 403                     # crew is not an administrator


def test_cannot_remove_last_admin(client):
    setup_admin(client)
    me = client.get("/api/auth/me").json()["user"]
    assert client.patch(f"/api/users/{me['id']}", json={"role": "crew"}).status_code == 409
    assert client.patch(f"/api/users/{me['id']}", json={"active": False}).status_code == 409


def test_ingest_with_key_and_duplicates(client):
    setup_admin(client)
    key = client.post("/api/keys", json={"name": "Bench laptop"}).json()["key"]
    rows = [{"basin_id": "TEST-01", "timestamp": "2026-11-15 14:00:00", "distance_cm": 100.2, "battery_v": 3.9,
             "mode": "DRY"},
            {"basin_id": "TEST-01", "timestamp": "2026-11-15 14:01:00", "distance_cm": 99.8}]
    assert client.post("/api/ingest", json={"readings": rows}).status_code == 401
    assert client.post("/api/ingest", json={"readings": rows},
                       headers={"Authorization": "Bearer dsk_bad_key"}).status_code == 401
    r = client.post("/api/ingest", json={"readings": rows}, headers={"Authorization": f"Bearer {key}"})
    body = r.json()
    assert body["season"]["dry_every_s"] in (900, 1800, 3600)       # the reading interval for this season
    assert {k: body[k] for k in ("accepted", "duplicates", "modes")} == {"accepted": 2, "duplicates": 0, "modes": {}}
    r = client.post("/api/ingest", json={"readings": rows + rows[:1]}, headers={"Authorization": f"Bearer {key}"})
    assert r.json()["accepted"] == 0 and r.json()["duplicates"] == 3
    s = client.get("/api/sensors").json()["sensors"][0]
    assert s["basin_id"] == "TEST-01" and s["readings_total"] == 2 and s["distance_cm"] == 99.8
    assert s["battery_v"] == 3.9                                     # kept from the reading that had one
    assert s["last_reading_at"].startswith("2026-11-15T19:01")       # 14:01 Montréal = 19:01 UTC
    assert len(client.get("/api/sensors/TEST-01/readings").json()["readings"]) == 2
    kid = key.split("_")[1]
    client.delete(f"/api/keys/{kid}")
    assert client.post("/api/ingest", json={"readings": rows},
                       headers={"Authorization": f"Bearer {key}"}).status_code == 401


def test_ingest_rejects_bad_values(client):
    setup_admin(client)
    key = client.post("/api/keys", json={"name": "k"}).json()["key"]
    bad = [{"basin_id": "x y", "timestamp": "2026-11-15T14:00:00"}]
    assert client.post("/api/ingest", json={"readings": bad}, headers={"Authorization": f"Bearer {key}"}).status_code == 422


def test_cross_site_post_refused_and_headers(client):
    r = client.post("/api/auth/login", json={"email": "a@b.ca", "password": "x"}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    r = client.get("/api/health")
    assert r.headers["x-frame-options"] == "DENY" and "default-src 'self'" in r.headers["content-security-policy"]
    assert client.get("/api/nothing-here").status_code == 404


# ---------------------------------------------------------------------------- pages (state.py)
def test_run_note_and_emptied_sump():
    import pandas as pd
    from server import state
    m = state.RUN_NOTE.search("Pre-storm run · stop 2 of 3 · arrive 12:09 · Inspect the sensor")
    assert (m[1], m[2], m[3], m[4]) == ("2", "3", "12:09", "Inspect the sensor")
    assert state.RUN_NOTE.search("Emergency: street flooding") is None
    t = pd.date_range("2026-11-17 12:00", periods=6, freq="5min")
    levels = pd.DataFrame({"timestamp": t, "level_cm": [1, 0, -28, -28, -28, 0]})
    assert state.emptied_at(levels, t[0], t[-1]) == t[2]
    levels["level_cm"] = [1, 0, -28, 0, 1, 0]                      # one stray reading is not a cleaning
    assert state.emptied_at(levels, t[0], t[-1]) is None
    assert state.sector("9405-9475 chemin de la Côte-de-Liesse") == "chemin de la Côte-de-Liesse"


def test_live_basin_from_setup_to_cleaning(client):
    setup_admin(client)
    body = {"basin_id": "TEST-01", "latitude": 45.44, "longitude": -73.75, "invert_depth_mm": 1400}
    assert client.post("/api/basins", json={**body, "sensor_depth_mm": 1350}).status_code == 422   # can't see the water
    assert client.post("/api/basins", json=body).status_code == 200
    o = client.get("/api/overview").json()
    assert [b["id"] for b in o["basins"]] == ["TEST-01"] and o["basins"][0]["category"] == "Offline"
    assert client.post("/api/basins/TEST-01/log", json={"action": "Inspected", "note": "ok"}).status_code == 200
    d = client.get("/api/basins/TEST-01").json()
    assert d["log"][0]["action"] == "Inspected" and d["id"] == "TEST-01"
    assert client.post("/api/basins/TEST-01/log", json={"action": "Painted it"}).status_code == 422


def test_emptied_sump_is_logged_once(client, monkeypatch):
    import pandas as pd
    from sqlalchemy import func, select
    from server import db, state
    setup_admin(client)
    client.post("/api/basins", json={"basin_id": "TEST-01", "latitude": 45.44, "longitude": -73.75, "invert_depth_mm": 1400})
    t0 = pd.Timestamp.now().floor("min") - pd.Timedelta(hours=3)
    levels = pd.DataFrame({"timestamp": [t0 + pd.Timedelta(minutes=30 * i) for i in range(4)], "level_cm": [8, 6, -27, -28]})
    monkeypatch.setattr(state.data_store, "status_for", lambda key, bid, when: {"issue_since": t0, "status": "clean_soon"})
    monkeypatch.setattr(state.data_store, "levels_for", lambda key, bid: levels)
    for _ in range(2):                                   # every page load runs it: the second must not log again
        with db.engine.begin() as conn, state.use(conn):
            pass
    with db.engine.begin() as conn:
        rows = conn.execute(select(state.maint_t.c.note).where(state.maint_t.c.action == "Cleaned / vacuumed")).all()
    assert len(rows) == 1 and "Detected by the sensor" in rows[0][0]


def test_basin_without_outlet_depth_and_city_list(client):
    setup_admin(client)
    r = client.post("/api/basins", json={"basin_id": "NEW-1", "municipal_id": "7082692", "latitude": 45.44,
                                          "longitude": -73.75})
    assert r.status_code == 200, r.text
    d = client.get("/api/basins/NEW-1").json()
    assert "learning" in d["facts"] and d["dims"]["invert_depth_cm"] == 140      # 0.40 m sensor + 1.00 m placeholder
    city = client.get("/api/city-basins").json()
    assert city["columns"][:4] == ["municipal_id", "address", "latitude", "longitude"]


def test_esp8266_bench_demo(client):
    """Tonight's demo: the ESP8266 sketch's exact message (UTC 'Z' times, null = no echo), then the basin pages."""
    from datetime import datetime, timedelta, timezone
    setup_admin(client)
    key = client.post("/api/keys", json={"name": "ESP8266 bench"}).json()["key"]
    now = datetime.now(timezone.utc).replace(microsecond=0)
    dist = [42.7] * 10 + [15.0, 12.5, None, 30.2] + [42.6] * 6       # steady, hand over it, no echo, back
    rows = [{"basin_id": "TEST-ESP", "timestamp": (now - timedelta(seconds=120 + 30 * (len(dist) - i))).strftime(
        "%Y-%m-%dT%H:%M:%SZ"), "distance_cm": d} for i, d in enumerate(dist)]
    for r in rows:                                                   # one request per reading, like the ESP
        a = client.post("/api/ingest", json={"readings": [r]}, headers={"Authorization": f"Bearer {key}"})
        assert a.status_code == 200 and a.json()["accepted"] == 1, a.text
    s = [x for x in client.get("/api/sensors").json()["sensors"] if x["basin_id"] == "TEST-ESP"][0]
    assert s["distance_cm"] == 42.6 and s["readings_total"] == len(dist)
    assert client.get("/api/overview").status_code == 200            # sensor not yet a basin: no crash
    assert client.post("/api/basins", json={"basin_id": "TEST-ESP", "latitude": 45.448,
                                            "longitude": -73.744}).status_code == 200
    for path in ["/api/overview", "/api/basins/TEST-ESP", "/api/run", "/api/sensors/TEST-ESP/readings"]:
        assert client.get(path).status_code == 200, path
    # outlet depth left empty: the placeholder must not raise a flood alert while the sensor learns it
    b = client.get("/api/overview").json()["basins"][0]
    assert b["category"] == "Normal" and "Learning" in b["priority"], b
    assert "not learned" in client.get("/api/basins/TEST-ESP").json()["water"]["text"]
    # bench set-up: outlet depth = sensor depth + what it reads to the table -> normal; a hand at 15 cm -> urgent
    client.post("/api/basins", json={"basin_id": "TEST-ESP", "latitude": 45.448, "longitude": -73.744,
                                     "sensor_depth_mm": 400, "invert_depth_mm": 400 + 426})
    assert client.get("/api/overview").json()["basins"][0]["category"] == "Normal"
    hand = [{"basin_id": "TEST-ESP", "timestamp": (now - timedelta(seconds=120 - 20 * i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "distance_cm": 15.0} for i in range(3)]
    client.post("/api/ingest", json={"readings": hand}, headers={"Authorization": f"Bearer {key}"})
    b = client.get("/api/overview").json()["basins"][0]
    assert b["category"] == "Urgent" and b["water"] == "0.55 m", (b["category"], b["priority"], b["water"])


def test_ingest_infinity_is_no_echo_and_bad_body_does_not_crash(client):
    setup_admin(client)
    key = client.post("/api/keys", json={"name": "k"}).json()["key"]
    h = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    body = '{"readings":[{"basin_id":"T1","timestamp":"2026-11-17T18:54:10","distance_cm":Infinity},' \
           '{"basin_id":"T1","timestamp":"2026-11-17T18:54:15","distance_cm":183.7}]}'
    r = client.post("/api/ingest", content=body, headers=h)                 # what the bridge sent tonight
    assert r.status_code == 200 and r.json()["accepted"] == 2, r.text
    r = client.post("/api/ingest", content='{"readings":[{"basin_id":"T1","timestamp":"x","distance_cm":Infinity}]}',
                    headers=h)
    assert r.status_code == 422 and r.json()["detail"][0]["msg"]


def test_all_digit_basin_id_stays_text(client):
    setup_admin(client)
    base = {"latitude": 45.4543, "longitude": -73.7761, "sensor_depth_mm": 400, "invert_depth_mm": 1400,
            "diameter_mm": 610, "outlet_mm": 250, "sump_mm": 300, "has_trap": True}
    assert client.post("/api/basins", json={**base, "basin_id": "7081852"}).status_code == 200
    assert client.post("/api/basins", json={**base, "basin_id": "TEST-1"}).status_code == 200
    assert client.delete("/api/basins/TEST-1").status_code == 200
    ids = [b["id"] for b in client.get("/api/overview").json()["basins"]]
    assert ids == ["7081852"]                                         # text, not the number 7081852 (it blanked the map)
    assert client.post("/api/basins", json={**base, "basin_id": "FAR", "latitude": 0, "longitude": 0}).status_code == 422
