# DrainShield: handoff to Raph

*Written Nov 26, 2026, from the code at commit `2dc9452` (Nov 23). Phil (Philippe Bordeleau) is handing the software side to Raph.*

## 1. The short version

- **You own the website.** You decide the stack, the structure, and what to rewrite. Phil handles the hardware, the municipalities, and the competition.
- **A rewrite is allowed, but read the code first.** It's already a standard stack: FastAPI + PostgreSQL + React/TypeScript. The valuable part is the decision logic (section 4), not the framework. If you rewrite, treat `processing.py`, `predictive.py` and the tests as the spec.
- **Hosting and domain are your call, with no rush.** The current site is free and works for demos. Hold off on buying a domain: the name "DrainShield" isn't final yet.
- **Everything passes today:** 27 engine tests (`tests/`) and 16 server tests (`web/tests/`).

## 2. What DrainShield is

A sensor pod is mounted on the wall of a street catch basin (puisard), about 400 mm below the grate. It measures the distance down to the water. The software turns those readings into decisions for a city's public works team:

1. **Before and after storms (predictive maintenance):** spot basins that drain slowly (sediment, a blocked trap, a covered grate). Cross that with Environment Canada's rain forecast so crews clean the risky basins *before* the storm.
2. **During storms (real-time):** show which basin is backing up right now, so crews respond faster and limit flood damage. This speeds up response; it isn't meant to replace residents calling 311.

**Customer:** smaller Québec municipalities (Dorval is the reference data set; Chambly, Stoneham, L'Assomption and Vaudreuil-Dorion have been contacted or interviewed). The town or city is the customer, not the cleaning contractors.

**Business model (decided Nov 25):** cities don't want to install, repair or swap batteries. DrainShield owns the pods and does all field work; the city just gets a reliable product and software. **Hard constraint: DrainShield must not add to the city's workload or budget.**

## 3. Where things stand (Nov 26, 2026)

| Done | Not done / open |
|---|---|
| Streamlit dashboard (original prototype, all pages working) | Final sensor not chosen in hardware: **60 GHz radar (Acconeer A121/XM125)** is the current assumption, but the code is still written around ultrasonic sensors |
| Web app live on Ample, with sign-in, roles, upload keys | Cellular (LTE) data link not solved |
| All 5,035 Dorval catch basins on the map (Ville de Montréal open data) | Battery life not bench-tested (deliverable assumes 5–10 years) |
| Pitch demo: a scripted 24-hour storm day at 4 pilot sites, 12 sensors | Web app hasn't passed a full dry run yet, so the Streamlit dashboard stays until it does |
| Wireless prototype: Heltec LoRa nodes → USB receiver → laptop → website | Name not final; no domain |
| ESP8266 Wi-Fi sketch posting straight to the website (being tested) | Sensor in every basin vs. only critical ones: undecided |
| Pre-storm predictions, vacuum-truck route, crew view, FR/EN | Thresholds are first guesses, not yet tuned with real pilot data |

## 4. How data becomes a decision

This is the heart of the project. All of it lives in the repo root and is shared by both apps.

### 4.1 One reading (the data contract)
`basin_id, timestamp, distance_cm, battery_v`. That's all the engine needs. Any sensor or radio works as long as it produces this. A different sensor (radar instead of ultrasonic) mostly changes the blind zone and noise, not the pipeline.

### 4.2 Distance → water level (`processing.py`)
- Level = height above the **outlet invert** (radier). In dry weather the sump water rests exactly at the invert, so that's the "0 cm" line.
- **Self-calibration:** the first dry, steady hours after install (≥ 6 steady hours, within the first 48) teach the sensor where the invert is, so nobody has to measure the sensor height. If the resting level is more than 15 cm off what the as-built plans say, it warns (sump not refilled since a cleaning, or bracket at a different height). The invert depth can also be left empty, in which case the sensor learns it.
- A 3-point rolling median removes spikes. Readings stuck at the sensor's closest measurable distance (the blind zone) mean "water at or above the sensor", which is flooding, not a bad echo.

### 4.3 Storms → diagnosis
Rain events come from Environment Canada GEM/HRDPS hourly data via Open-Meteo (free, no key). A gap of 6 h or more splits two storms. For each storm, the engine compares the rise with what this same basin did when clean (learned from its first 3 storms):

| Observation | Diagnosis |
|---|---|
| Rose much more than when clean, drained slowly | Outlet / trap restricted (sediment at the trap lip, or debris) |
| Rose much less than expected in a big rain | Grate probably covered (leaves): water staying on the street |
| About the same | Normal |

Grades (tunable constants at the top of `processing.py`):
- **Rise ratio vs. clean:** ≤ 2× OK · ≤ 4× Watch · ≤ 8× Clean soon · above that, Urgent
- **Drain time after the rain stops:** ≤ 30 min OK · ≤ 90 Watch · ≤ 180 Clean soon · above that, Urgent
- **Estimated outlet capacity left** ≈ 1 / rise ratio
- **Sediment is estimated, not measured** (rain × catchment area × sediment yield). It resets when a crew logs a cleaning, using the depth they measured. Fill ≥ 60% → Watch, ≥ 80% → Clean soon.
- The **worst storm since the last cleaning** sets the maintenance status (clogging doesn't fix itself). Confidence goes from Low to Medium to High as 1, 2, then 3+ storms flag it.

### 4.4 Two separate answers per basin
1. **Live state** (right now): Normal · Rising with the rain · Not draining (high in dry weather) · Backing up (> 40 cm above the invert, at the sensor limit, or above the subdrains) · No data (> 60 min silent) · Learning.
2. **Maintenance status** (does a crew need to go?): OK · Watch · Clean soon · Urgent · No data.

**Rule from the brief: a sensor problem must never look like a basin problem.** Offline, low battery and iced are sensor states (grey/black), never infrastructure alarms.

### 4.5 Triage: what the map and dispatch list show (`data_store.triage`)
First matching rule wins:
1. Sensor iced or offline → **⚫ Offline** (inspect the sensor)
2. Backing up, or not draining → **🔴 Urgent**
3. Any maintenance flag **and** heavy rain forecast → **🔴 Inspect before storm**. Heavy rain = ≥ 15 mm in the next 12 h, or ≥ 10 mm in spring (Mar 15–May 31) and fall (Sep 15–Nov 30) on the website (`web/server/season.py`).
4. Any maintenance flag → **🟠 Inspect**
5. Otherwise → **🟢 Normal**

### 4.6 Pre-storm prediction (`predictive.py`)
For each basin: predicted peak = water left when the rain starts + (rise per mm/h learned from its latest storm) × forecast intensity. The intensity is scaled linearly for lighter storms and with the **square** for heavier ones, because a restricted outlet behaves like an orifice, so it errs on the safe side. Predicted peak ≥ 40 cm or within 30 cm of the grate → 🔴. At least half of that, or draining 3× slower than when clean → 🟠. The docstring explains why it's calibrated on each basin instead of a textbook model.

### 4.7 From flag to closed issue (no extra work for the city)
- **Pre-storm run:** the website proposes the flagged basins as one truck route (`route_optimizer.py`): nearest-neighbour + 2-opt, urgent stops first, real road times from the free public OSRM server, with a straight-line fallback so the demo never breaks. The run starts from the Dorval public works yard.
- "Send to crew" writes one *Crew dispatched* log entry per stop, and the crew view on the tablet reads them back.
- **Nobody taps "cleaned":** when the water drops ≥ 10 cm below the invert (the vacuum truck emptied the sump), the server logs the cleaning itself. The next rain draining normally marks it **verified**.
- Issue lifecycle: Detected (unverified) → Verified / crew dispatched → Resolved.

### 4.8 How often sensors read (`polling_controller.py` + firmware)
- **STORM** every 60 s (rising ≥ 0.3 cm/min, > 10 cm above the invert, or ≥ 2 mm/h rain now)
- **WATCH** every 5 min (≥ 10 mm forecast in 12 h, rain starting within 3 h, or light rain now)
- **DRY** every 30 min otherwise

The server knows the forecast, so it tells the sensor when to speed up *before* the rain. The firmware also switches itself to STORM, because a downlink can only reach a sensor right after it transmits. The website also sends a seasonal dry interval (`dry_every_s`), but the firmware doesn't read it yet.

## 5. The two apps in the repo

| | Streamlit dashboard (repo root) | Web app (`web/`) |
|---|---|---|
| Run | `streamlit run app.py` | `cd web && uvicorn server.main:app --reload` (+ `npm run build` in `web/frontend` once) |
| Data | CSV files in `data/` | PostgreSQL online, SQLite file locally |
| Status | Original prototype, kept as a fallback | The product going forward |

The web server **re-uses the same engine files** through `web/server/state.py`. It fakes Streamlit's cache (`web/server/shim/streamlit.py`) and copies the database to CSV so `data_store.py` can read it. That's clever but hacky; see section 8.

Key folders: `arduino/` (3 sketches), `hardware/enclosure/` (pod CAD, STEP/STL), `data/` (Dorval basins + pilot priorities), `tests/`, `web/tests/`. `Claude outputs/` holds a duplicate of the USB sketch and can be deleted.

## 6. Users: who can do what

Accounts are invite-only: an admin creates them, and nobody can sign up. Roles live in `web/server/main.py`:

| Role | Can |
|---|---|
| **admin** | Everything, plus create/disable accounts, reset passwords, make and revoke sensor upload keys |
| **engineering** | Add/edit/remove basins and sensors, change settings, everything crew can do |
| **crew** | See the network, open basins, follow runs, log maintenance |
| **demo** | Judges' account: always in the pitch demo; can try the actions on demo data (resettable), never touches live data |

**What users can modify:**
- **Basins (as-built plans, not catalogue models):** ID, city ID, address, GPS, inside diameter (405/610/915/1220 mm), outlet invert depth (optional, the sensor can learn it), outlet pipe (150–450 mm), sump (0/300/500 mm), sensor depth (default 400 mm), cast-iron trap yes/no. They can also pick a basin from the city map to pre-fill it.
- **Maintenance log:** Crew dispatched, Inspected, Obstruction found, Requires further investigation, Cleaned / vacuumed (+ measured sediment), No issue found, Sensor installed / re-installed.
- **Pre-storm run:** remove stops, set the departure time.
- **Settings:** on-call name and phone.
- **Live / Pitch demo switch,** FR/EN language, and in the Streamlit version, the sensor reading interval.

Things users should *not* have to see by default: raw telemetry, battery voltages and hydrology parameters. Crew view first; engineering detail behind progressive disclosure.

## 7. Hardware context (it keeps changing)

- **In the code now:** Arduino Uno + HC-SR04 over USB (`sensor_bridge.py`); Heltec WiFi LoRa 32 V3 + A02YYUW ultrasonic nodes with a receiver over USB (`lora_bridge.py`, flash ring buffer, ACK carries the mode); ESP8266 + HC-SR04 posting over Wi-Fi to `/api/ingest`.
- **Decided since:** 60 GHz radar (Acconeer A121/XM125 assumed), battery-powered, 5–10 year battery target, pod slides onto a wall bracket and can be placed and removed from street level, waterproof.
- **Heads-up:** the claude.ai project brief still describes an Arduino MKR WAN 1310 + DYP-A02YY ultrasonic. That's out of date. Trust Phil and the latest decisions over that text.
- Readings reach the website with an upload key (`dsk_...`). Duplicates are ignored (matched on basin + timestamp), so retries are safe. The bridges queue readings offline and resend.

## 8. Known shortcuts and tech debt (flagged in the code as `shortcut:`)

- **One request at a time:** the engine keeps state in module globals, so `state.py` runs every computation under one lock. Fine for a pilot, not for many users.
- **Full DB → CSV re-export** whenever data changes. Fine up to about 100k readings.
- **No migrations:** tables are created on start-up. Add Alembic before real data matters.
- The firmware ignores the seasonal `dry_every_s` from the server.
- The public OSRM server is a free demo service. A real deployment would host its own.
- "Grate covered" detection while it rains (a basin stays flat while neighbours within 400 m rise) still needs validating in the pilot.
- **All thresholds are first guesses.** The 915/1220 mm wall thicknesses are placeholders (`VERIFY` in `basin_model.py`), and battery % is a straight line from 3.20 to 3.60 V.
- Roadmap items still open: bench-test the real sensor, detect irregular sensor data (flat lines, false echoes), LoRaWAN/cellular for the pilot.

## 9. Hosting today, and the choices ahead

- **Now:** Ample free plan at `https://x9unyy6jkf5h.ample.run`. It deploys from GitHub, since the repo is public. McGill's network blocks `*.ample.run`, so `web/cloudflare-relay/worker.js` (a free Cloudflare Worker) serves the same site from a workers.dev address on campus.
- The site URL is **hard-coded** in a few places (the ESP8266 sketch, bridge commands, the relay). Changing hosts means updating those.
- Settings are environment variables only (`DATABASE_URL`, `SETUP_TOKEN`, `COOKIE_SECURE`, `APP_TZ`), so the code isn't tied to Ample.

**Constraint for now: free, with no credit card.** Options to weigh:
1. **Stay on Ample + relay:** costs nothing and works for demos. Awkward, though, and depends on a small host.
2. **Run locally only** until going public: fine for development and bench tests (sensor and laptop on the same Wi-Fi). Demos need Phil's laptop, and nobody can sign in from elsewhere.
3. **Move to a mainstream host + custom domain later** (Phil wanted something like Supabase + Render to stay possible). Most need a card, even on free tiers. Decide once the name is final.

## 10. Constraints to keep, whatever you rebuild

- Free / no credit card for now; portable, standard code.
- Never add work or cost for the city. Sensor-confirmed cleanings over manual "mark cleaned".
- A crew member answers "where, what, what do I do" in under 10 seconds on a tablet.
- Keep sensor state and infrastructure state visually separate (🔴 🟠 🟢 vs ⚫).
- French and English (Québec municipalities).
- Be honest in the UI: sediment and capacity are **estimates**, so label them that way.
- The pitch demo must always work, even with no rain and no internet (fallbacks for weather and routing).
- Invite-only accounts, including a judges' demo account.
- The project brief also has UI rules: progressive disclosure, a to-scale basin cross-section on the basin page, only 2 main KPI cards (water level now, drainage performance), and no generic "AI-looking" design.

## 11. Suggested first week

1. Get access (Phil): GitHub collaborator, an admin account on the live site, and Ample + Cloudflare access if you take over hosting.
2. Run both test suites: `python -m pytest -q tests` (root) and `cd web && python -m pytest -q`.
3. Run the web app locally, switch to **Pitch demo**, and play the day. It's the fastest way to see every feature.
4. Read the docstrings of `processing.py`, `predictive.py` and `web/server/state.py`. They explain the *why*.
5. Then decide: keep and refactor, or rebuild. Either way, carry over the thresholds and the tests.

**Ask Phil about:** sensor-per-basin strategy, which city the next demo targets (L'Assomption asked for one), and anything in section 3's "open" column.
