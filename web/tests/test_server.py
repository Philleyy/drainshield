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
    assert r.json() == {"accepted": 2, "duplicates": 0, "modes": {}}
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
def minute(hhmm):
    return int(hhmm[:2]) * 60 + int(hhmm[3:])


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


def test_demo_story_on_the_website(client, monkeypatch):
    from server import state
    monkeypatch.setattr(state.ro, "osrm_matrix", lambda *a, **k: (_ for _ in ()).throw(OSError("offline")))
    setup_admin(client)
    client.post("/api/demo/reset")
    o = client.get(f"/api/overview?demo=1&t={minute('11:00')}").json()
    assert o["counts"] == {"Urgent": 2, "Inspect": 0, "Offline": 1, "Normal": 9}
    assert o["forecast"]["heavy"] and o["forecast"]["starts"].endswith("18:00")
    run = o["run"]["suggested"]
    assert [s["id"] for s in run["stops"]] == ["S4-A", "S7-A", "S9-A"] and run["spare_min"] > 0
    o = client.get(f"/api/overview?demo=1&t={minute('13:45')}").json()        # scripted run sent at 11:25
    sent = o["run"]["sent"]
    assert sent["done"] == 3 and "sump emptied" in sent["stops"][0]["done_text"] and o["run"]["suggested"] is None
    d = client.get(f"/api/basins/S4-A?demo=1&t={minute('23:30')}").json()
    assert [s["done"] for s in d["steps"]] == [True] * 4 and d["steps"][3]["label"].startswith("Verified")
    assert d["dims"]["invert_depth_cm"] == 140 and len(d["levels"]) > 50
    assert client.get("/api/basins/NOPE?demo=1").status_code == 404
    # sending the run from the page logs one dispatch per stop, and it shows as sent
    client.post("/api/demo/reset")
    r = client.post(f"/api/run/send?demo=1&t={minute('09:50')}", json={"exclude": ["S9-A"]})
    assert r.json() == {"stops": 2}
    o = client.get(f"/api/overview?demo=1&t={minute('09:55')}").json()
    assert [s["id"] for s in o["run"]["sent"]["stops"]] == ["S4-A", "S7-A"]
    client.post("/api/demo/reset")


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
        with db.engine.begin() as conn, state.use(conn, False):
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
