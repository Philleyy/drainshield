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
