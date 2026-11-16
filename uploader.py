"""
uploader.py: send readings from the bridges to the DrainShield website
---------------------------------------------------------------------
Used by lora_bridge.py and sensor_bridge.py when they are started with
    --upload https://your-site.ample.run --key dsk_...
(an administrator makes the key on the website, under "Sensor upload keys").

* Readings are still written to data/live_readings.csv as before; uploading is extra.
* If the internet or the website is down, readings wait in data/upload_queue.jsonl and are sent when it's
  back (retried every 30 s, and kept across a restart of the bridge). The website keeps each reading once,
  so sending one twice is harmless.
"""

import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime

import net

QUEUE_FILE = os.path.join("data", "upload_queue.jsonl")
CHUNK = 500                 # readings per request
RETRY_S = 30                # after a failure, wait this long before trying again
TIMEOUT_S = 8


def reading(basin_id, timestamp, distance_cm, battery_v=None, temp_c=None, flags=0, mode=None, rssi=None,
            snr=None, node=None, index=None):
    """One reading in the shape the website expects (timestamp = local time, like the CSV)."""
    if isinstance(timestamp, datetime):
        timestamp = timestamp.isoformat(timespec="seconds")
    return {"basin_id": basin_id, "timestamp": timestamp, "distance_cm": distance_cm, "battery_v": battery_v,
            "temp_c": temp_c, "flags": int(flags or 0), "mode": mode, "rssi": rssi, "snr": snr, "node": node,
            "index": index}


class Uploader:
    def __init__(self, site, key, queue_file=QUEUE_FILE, opener=None):
        self.url = site.rstrip("/") + "/api/ingest"
        self.key = key
        self.queue_file = queue_file
        self.opener = opener or net.urlopen
        self.pending = self._load()
        self.next_try = 0.0
        self.last_error = None
        if self.pending:
            print(f"   upload: {len(self.pending)} readings waiting from last time, sending them first")

    # ------------------------------------------------------------------ public
    def send(self, rows):
        """Queue these readings and try to send everything waiting. Returns the website's answer or None."""
        self.pending.extend(rows)
        return self.flush()

    def flush(self, force=False):
        """Try to send what's waiting (call this regularly; it waits RETRY_S after a failure)."""
        if not self.pending:
            return None
        if not force and time.monotonic() < self.next_try:
            self._save()
            return None
        answer = None
        while self.pending:
            chunk = self.pending[:CHUNK]
            try:
                answer = self._post(chunk)
            except urllib.error.HTTPError as e:
                if e.code in (400, 413, 422):            # the website will never accept these: set them aside
                    self._reject(chunk, e)
                    self.pending = self.pending[CHUNK:]
                    continue
                self._failed(e)
                self._save()
                return None
            except Exception as e:                       # offline, website down...
                self._failed(e)
                self._save()
                return None
            self.pending = self.pending[CHUNK:]
        if self.last_error:
            print("   upload: connection back, everything sent")
        self.last_error = None
        self._save()
        return answer

    # ------------------------------------------------------------------ inside
    def _post(self, rows):
        req = urllib.request.Request(self.url, data=json.dumps({"readings": rows}).encode(), method="POST",
                                     headers={"Content-Type": "application/json",
                                              "Authorization": f"Bearer {self.key}"})
        with self.opener(req, timeout=TIMEOUT_S) as resp:
            return json.loads(resp.read().decode() or "{}")

    def _failed(self, e):
        self.next_try = time.monotonic() + RETRY_S
        if isinstance(e, urllib.error.HTTPError) and e.code == 401:
            text = "the website refused the upload key (check --key, or make a new key)"
        else:
            text = f"can't reach the website ({getattr(e, 'reason', e)})"
        if text != self.last_error:
            print(f"   upload: {text}. {len(self.pending)} readings waiting; retrying every {RETRY_S} s")
        self.last_error = text

    def _reject(self, chunk, e):
        path = os.path.join(os.path.dirname(self.queue_file) or ".", "upload_rejected.jsonl")
        with open(path, "a", encoding="utf-8") as f:
            for r in chunk:
                f.write(json.dumps(r) + "\n")
        print(f"   upload: the website refused {len(chunk)} readings (HTTP {e.code}); saved in {path}")

    def _load(self):
        try:
            with open(self.queue_file, encoding="utf-8") as f:
                return [json.loads(line) for line in f if line.strip()]
        except (OSError, ValueError):
            return []

    def _save(self):
        if not self.pending:
            if os.path.exists(self.queue_file):
                os.remove(self.queue_file)
            return
        os.makedirs(os.path.dirname(self.queue_file) or ".", exist_ok=True)
        tmp = self.queue_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            for r in self.pending:
                f.write(json.dumps(r) + "\n")
        os.replace(tmp, self.queue_file)


def add_arguments(parser):
    parser.add_argument("--upload", metavar="SITE", help="also send readings to the website, e.g. https://xyz.ample.run")
    parser.add_argument("--key", help="sensor upload key from the website (dsk_...)")


def from_args(args):
    if not args.upload:
        return None
    if not args.key:
        raise SystemExit("--upload needs --key (make one on the website: Sensor upload keys)")
    print(f"   upload: sending readings to {args.upload}")
    return Uploader(args.upload, args.key)
