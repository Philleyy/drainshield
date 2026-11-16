# DrainShield website (web app)

The website people sign into: https://x9unyy6jkf5h.ample.run (hosted on Ample, free plan).
Standard FastAPI + PostgreSQL + React, nothing specific to Ample, so it can move to any host.

| Folder | What it is |
|---|---|
| `server/` | The Python web server (FastAPI). `main.py` = all the web addresses, `db.py` = database tables, `security.py` = passwords, sessions and upload keys, `ingest.py` = storing sensor readings. |
| `frontend/` | The React website (what you see). `src/pages/` = one file per screen, `src/styles.css` = the look (design "D"). |
| `tests/` | Server tests: `python -m pytest -q` from this folder. |
| `build_frontend.sh` | Builds the React site into `server/static` (the host runs it on every deploy). |

## Run it on your laptop

```
cd web
python -m pip install -r requirements.txt
python -m uvicorn server.main:app --reload
```
Without `DATABASE_URL` it uses a local file, `web/drainshield_dev.db`. To see the React pages you also need
Node.js once: `cd frontend`, `npm install`, `npm run build`, then reload http://localhost:8000.
To create the first account locally, start the server with a setup code, e.g. in PowerShell
`$env:SETUP_TOKEN="pick-anything"` before the uvicorn command, then open http://localhost:8000/setup?token=pick-anything.

## Settings (environment variables)

`DATABASE_URL` (PostgreSQL; the host sets it), `SETUP_TOKEN` (one-time code for the first administrator),
`COOKIE_SECURE` (`1` online), `APP_TZ` (default America/Toronto).

## Sending sensor readings to the website

Make a key on the website (Administration, Sensor upload keys), then on the laptop next to the receiver:
```
python lora_bridge.py COM5 --upload https://x9unyy6jkf5h.ample.run --key dsk_...
python sensor_bridge.py COM3 --basin TEST-01 --upload https://x9unyy6jkf5h.ample.run --key dsk_...
```
Readings are still saved in `data/live_readings.csv`. If the internet drops they wait in
`data/upload_queue.jsonl` and are sent when it's back (`uploader.py`).
