"""uploader.py: readings wait in a queue while offline and are sent once the website answers."""

import io
import json
import urllib.error

import uploader


class FakeSite:
    def __init__(self):
        self.online = False
        self.got = []
        self.code = None

    def __call__(self, req, timeout):
        if not self.online:
            raise urllib.error.URLError("offline")
        if self.code:
            raise urllib.error.HTTPError(req.full_url, self.code, "no", {}, io.BytesIO(b"{}"))
        assert req.headers["Authorization"] == "Bearer dsk_x_y"
        rows = json.loads(req.data)["readings"]
        self.got.extend(rows)
        return io.BytesIO(json.dumps({"accepted": len(rows), "duplicates": 0, "modes": {}}).encode())


def test_queue_survives_offline_and_restart(tmp_path, monkeypatch):
    site = FakeSite()
    q = tmp_path / "queue.jsonl"
    up = uploader.Uploader("https://x.example/", "dsk_x_y", queue_file=str(q), opener=site)
    r1 = uploader.reading("TEST-01", "2026-11-15T14:00:00", 100.0, mode="DRY")
    assert up.send([r1]) is None and q.exists()                     # offline: kept on disk
    site.online = True
    assert up.flush() is None                                       # waits 30 s before retrying
    up2 = uploader.Uploader("https://x.example", "dsk_x_y", queue_file=str(q), opener=site)   # bridge restarted
    assert len(up2.pending) == 1
    answer = up2.flush()                                            # a fresh start tries right away
    assert answer["accepted"] == 1 and site.got[0]["basin_id"] == "TEST-01" and not q.exists()


def test_refused_readings_are_set_aside(tmp_path):
    site = FakeSite()
    site.online, site.code = True, 422
    q = tmp_path / "queue.jsonl"
    up = uploader.Uploader("https://x.example", "dsk_x_y", queue_file=str(q), opener=site)
    up.send([uploader.reading("bad id", "2026-11-15T14:00:00", 1.0)])
    assert up.pending == [] and (tmp_path / "upload_rejected.jsonl").exists()
