"""weather.py: the forecast falls back to Open-Meteo's second server, and a failure isn't retried on every page."""
import io
import json

import weather

REPLY = json.dumps({"hourly": {"time": ["2026-11-16T00:00", "2026-11-16T01:00"], "precipitation": [1.5, None]}})


def test_backup_server_then_short_pause_after_a_failure(monkeypatch):
    calls = []

    def fake(url, timeout=10):
        calls.append(url)
        if "//api.open-meteo.com" in url:               # the first server can't be reached
            raise OSError("timed out")
        return io.StringIO(REPLY)

    monkeypatch.setattr(weather.net, "urlopen", fake)
    monkeypatch.setattr(weather, "_sources", [weather.OPEN_METEO, weather.OPEN_METEO_BACKUP])
    monkeypatch.setattr(weather, "_failed_at", 0.0)
    rain = weather.rain_series(1.0, 2.0)
    assert list(rain["rain_mm"]) == [1.5, 0.0] and len(calls) == 2
    weather.rain_series(1.0, 3.0)                       # the server that answered is now asked first
    assert len(calls) == 3 and "historical-forecast-api" in calls[-1]

    monkeypatch.setattr(weather.net, "urlopen", lambda url, timeout=10: (_ for _ in ()).throw(OSError("offline")))
    assert weather.rain_series(1.0, 4.0).empty
    monkeypatch.setattr(weather.net, "urlopen", fake)
    assert weather.rain_series(1.0, 5.0).empty and len(calls) == 3      # within 2 min: no new attempt
