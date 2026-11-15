<img src="assets/drainshield_logo.png" alt="DrainShield" width="320">

# DrainShield: catch basin monitoring and decision support

Software side of DrainShield's low-cost catch basin sensor: from raw sensor readings
to decisions a public works team can act on. It covers two needs:

1. **Predictive maintenance**: find basins that drain slowly (sediment, blocked trap, covered grate),
   and flag the ones to clean **before** a forecast storm.
2. **Emergency dispatch**: see which basin is backing up during a storm, without waiting for 311 calls.

**Status:** early development, **live data only**. The map shows **all 5,035 Dorval catch basins** from the
Ville de Montréal open data; a basin gets a status once a DrainShield sensor is attached to it.
Readings come from a sensor plugged into the laptop by USB (`sensor_bridge.py`) or from the wireless
Heltec LoRa sensors through a USB receiver (`lora_bridge.py`, see **Wireless prototype** below).
New here? Start with **[SETUP_GUIDE.md](SETUP_GUIDE.md)**.

## Quick start

```
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

In a **second terminal**, with the Arduino plugged in (see the **Live sensor** page):

```
python sensor_bridge.py                        (lists the ports, e.g. COM3)
python sensor_bridge.py COM3 --basin TEST-01
```

Five pages, plus a **Crew / Engineering** view switch in the sidebar (Crew is simpler; Engineering adds
sensor health, hydrographs and history):

- **Network**: weather readiness banner (rain in the next 12 h, and which basins to clean before it),
  filter counters (🔴 Urgent · 🟠 Inspect · 🟢 Normal · ⚪ Offline), a map with the monitored basins and the
  city's unmonitored ones (grey), a search box, and the dispatch list.
- **Basin**: what to do (observed → possible explanation with a confidence level → next step), the to-scale
  cross-section, live water depth, drainage performance, and a **Log maintenance** button for crews.
- **Live sensor**: raw readings of any sensor (bench test: does it match the tape measure?), noise, and the
  **data collection frequency** (1 s to 15 min), which is sent to the Arduino.
- **Add basin**: attach a sensor to one of the city's catch basins and enter the as-built plan (diameter,
  invert, outlet pipe, sump, **cast-iron trap installed or not**), with a live drawing.
- **Truck route**: the basins to clean (🔴 urgent first, including those predicted to back up in the next 24 h of
  forecast rain), ordered into one route from the public works yard: map, total time, crew sheet (CSV) and
  Google Maps links. A demo set (the 10 pilot sites) shows it before any sensor is installed.

## Pitch demo: a whole day in 3 minutes

Sidebar **Data → Pitch demo** replays one scripted day (Tue Nov 17) at 4 Dorval pilot sites, 12 sensors (site 4 =
the 3 sensors on the table), on every page. A clock in the sidebar replaces "now": drag it, press **▶ Play**, or
**Jump to** a moment. A banner tells the story at each minute, and the **Demo day** page shows the whole day: rain
(measured and forecast), water levels, and every reading coloured by its mode.

| Time | What happens | What it shows |
| --- | --- | --- |
| 00:00 | Dry night, 2 basins already 🟠, 1 battery at 14% | DRY mode (30 min), drainage history, sensor health |
| 05:05 | Frost on S8-A's sensor | ⚪ sensor iced, never "flooding" |
| 07:50 | S9-A goes silent (loose connector) | ⚫ offline after 60 min |
| 09:30 | Surprise thunderstorm (no forecast) | sensors switch themselves to STORM (60 s) |
| 11:00 | Forecast: 29 mm tonight | backend → WATCH (5 min); S4-A, S7-A 🔴 Inspect before storm |
| 11:25 | Vacuum route sent | **Truck route** page, issues → "crew dispatched" |
| 12:10–13:40 | Sensor fixed, S4-A and S7-A cleaned | crew taps on the route page, basins back to 🟢 |
| 13:20–14:40 | S4-N1 radio outage | ⚫ offline, then every reading arrives late with its real time |
| 18:00 | The storm starts | STORM mode everywhere; the cleaned basins keep up |
| 20:25 | S7-N1: main sewer backs up | 🔴 Flooding: dispatch + slow-down signs (car wakes push water at homes) |
| 23:20 | S7-N1 inspected, no issue | issue closed, cause reported downstream |

**Scripted crew actions** (sidebar) plays the crews as in the story; turn it off to do it yourself live: on
**Truck route**, *Generate*, *Send route to the crew*, then *✅ Cleaned* per stop (or **Log maintenance** on a
basin's page). **↺ Reset demo** forgets the clicks. The demo files live in `data/demo/` (not in Git) and rebuild
with `python demo_scenario.py`; they never touch your real sensor data. Start straight in demo mode with
`http://localhost:8501/?demo=1`.

## Wireless prototype (Heltec LoRa, 3 basins)

Three Heltec WiFi LoRa 32 V3 boards, each with an A02YYUW sensor. Two are battery **nodes**; the third is the
**receiver** plugged into the laptop, and it also measures its own basin. All three run
`arduino/drainshield_lora/drainshield_lora.ino`: set `ROLE` and `NODE_ID` at the top before flashing each one
(Arduino IDE: board "Heltec WiFi LoRa 32(V3)", library "RadioLib"; wiring and options are in the sketch header).

1. **Add basin** for each sensor, with Sensor ID `DS-01`, `DS-02`, `DS-03` (= `NODE_ID` 1, 2, 3).
2. Terminal 1: `python -m streamlit run app.py`
3. Terminal 2: `python lora_bridge.py COM5` (the receiver's port; no argument lists the ports)
4. Terminal 3 (optional): `python polling_controller.py --every 900`, or for the pitch
   `python polling_controller.py --demo-forecast 25 --demo-timing` ("25 mm forecast tonight": every sensor
   switches to 5-minute readings at its next transmission).

Each node keeps every reading in its own flash until the receiver acknowledges it: unplug the receiver for an
hour and the readings arrive late, with their original times. `DEMO_TIMING 1` in the sketch shortens the
intervals (60 s / 20 s / 5 s instead of 30 min / 5 min / 60 s) so the table demo moves; `BENCH_MODE 1` keeps the
board awake with the OLED on and adds serial commands (`DUMP` prints the stored readings as CSV).

## Pilot priority (which basins to equip first)

The **Network** map colours every basin without a sensor by pilot priority, from the prioritization file
(`import_priorities.py` → `data/basin_priorities.csv`):

| Map colour | Tiers | Meaning |
|---|---|---|
| Dark purple | A | Big catchment **and** confirmed local low point: water arrives in quantity and has nowhere to go |
| Purple | B–D | One of the two (or big catchment with unknown elevation) |
| Grey | E–F | Neither |
| Light grey | – | Not a round basin, type unknown in the inventory, or not analysed |

Ringed dots are the **10 proposed pilot sites**: one anchor + two neighbours each, so a clog can be told apart
from a whole street being overloaded. The basin card shows the tier, score, estimated catchment, low point and
whether our bracket fits; **Add basin** fills in the catchment area for the sediment estimate.
It's a ranking to choose pilot sites (prioritization, not prediction): it uses inventory points, not real terrain,
and only about a third of the basins have an elevation. Update it with:

```
python import_priorities.py path/to/puisards_dorval_prioritized.csv
```

## How a problem is detected

After every storm we compare how high the water rose with what the same basin did when it was clean:

| What we see | Likely cause |
|---|---|
| Rose about the same as when clean | Normal |
| Rose **much more** and drained slowly | Outlet or trap restricted: sediment at the trap's bottom lip, or debris |
| Rose **much less** in a big rain | Grate covered (leaves): water is staying on the street |

The ratio gives a rough **outlet capacity estimate**. If **15 mm or more** of rain is forecast in the next
12 h, any basin already flagged for slow drainage becomes **🔴 Urgent: inspect before the storm**.

**Issue life cycle:** Detected (unverified) → Verified / crew dispatched → Resolved. Logging
"Cleaned / vacuumed" (or "No issue found") closes the issue: older storms stop counting and the
sediment estimate restarts from what the crew measured.

**Self-calibration (no sensor height to measure):** in dry weather the water rests at the outlet invert, so
the distance the sensor sees on a dry, steady day is the distance to the invert. The dashboard learns it from
the first 6–48 steady hours after installation (logged automatically when a basin is added, or with
"Sensor installed / re-installed" in the maintenance log) and measures everything from there. The bracket's
standard depth (400 mm) is only used until then, and as a sanity check (±15 cm).

**On the sensor (Arduino):** median of 5 pings, then a tracking loop with a PID structure that smooths the
level, estimates how fast it moves and ignores sudden jumps (false echoes) unless 3 readings in a row agree.
It switches itself to a reading every 30 s while the water moves (storm mode), and back to the slow
dry-weather interval after 30 still minutes.

**What the sensor can't see:** it measures the distance to the water surface only. The sump contents are
**estimated** (rain × drainage area × sediment yield), and water closer than its blind zone
(3 cm for the A02YYUW: ~0.43 m below the street with the pod at 0.40 m) shows as "≤ 0.43 m".

## Files

| File | What it does |
|---|---|
| `app.py` | Starts the dashboard, logo, view switch, auto-refresh |
| `network.py` · `dashboard.py` · `sensor_live.py` · `basin_setup.py` | The four pages |
| `sensor_bridge.py` | USB serial → `data/live_readings.csv`; sends the chosen interval back to the Arduino |
| `arduino/drainshield_sensor/drainshield_sensor.ino` | Arduino sketch: median of 5 pings, tracking loop, storm mode, temperature correction, adjustable interval |
| `processing.py` | Readings → water level, storms, diagnosis, estimates, status. **All thresholds at the top** |
| `weather.py` | Past and forecast rain (Environment Canada GEM model via Open-Meteo) and the ECCC radar layer |
| `maintenance.py` | Crew maintenance log and issue life cycle (`data/maintenance_log.csv`) |
| `basin_model.py` | As-built values (depths from the grate) → the numbers the model uses |
| `basin_drawing.py` | The to-scale cross-section |
| `import_municipal.py` | Makes `data/municipal_basins.csv` from the Ville de Montréal `ego_puisard_p.csv` |
| `import_priorities.py` | Makes `data/basin_priorities.csv` (tiers, score, catchment, low points, pilot sites) |
| `basin_catalog.py` | Reference: Lécuyer precast models and TP-3/4/5 traps |
| `data_store.py` · `ui.py` | Data loading and page building blocks |
| `arduino/drainshield_lora/drainshield_lora.ino` | Heltec V3 sketch, two roles: battery **node** (median of 5 readings, tracking loop, flash ring buffer, LoRa with ACK, deep sleep, 3 reading modes) or USB **receiver** |
| `arduino/drainshield_lora/drainshield_packet.h` | The radio packet format (12-byte header + 13 bytes per reading) |
| `lora_bridge.py` | Receiver USB → `data/live_readings.csv` + `data/node_telemetry.csv`; passes each sensor's mode back |
| `polling_controller.py` | Forecast + water level → DRY / WATCH / STORM mode per sensor (`data/sensor_settings.json`) |
| `predictive.py` | Past storms + forecast → predicted peak level in the next 24 h, recovery index, dry-baseline drift |
| `route_optimizer.py` · `route_page.py` | Vacuum truck route: OSRM road times, nearest neighbour + 2-opt, crew sheet, Google Maps links |
| `demo_scenario.py` · `demo_page.py` | The 24 h pitch demo: the scripted day (readings, forecasts, crew actions) and its overview page |
| `tests/` | `python -m pytest tests`: routing, prediction, polling modes, LoRa decoding, demo day |

**Data files:** `data/municipal_basins.csv` (the city's basins), `data/basin_priorities.csv` (pilot priority), `data/monitored_basins.csv` (basins with a
sensor, made by **Add basin**), `data/live_readings.csv` (written by the bridge), `data/maintenance_log.csv`,
`data/sensor_settings.json` (reading interval per sensor).

## Using another municipality

Download `ego_puisard_p.csv` ("Puisards d'égout") from donnees.montreal.ca, then:

```
python import_municipal.py path/to/ego_puisard_p.csv --owner "POINTE-CLAIRE"
```

Don't commit the full 78 MB file to GitHub: the slice in `data/` is all the dashboard needs.

## Data contract (one sensor reading)

| Field | Example | Meaning |
|---|---|---|
| `basin_id` | `TEST-01` | Which basin |
| `timestamp` | `2026-10-15 14:05:00` | When it was measured |
| `distance_cm` | `81.4` | Distance from the sensor down to the surface it sees |
| `battery_v` | `3.512` | Battery voltage (empty when powered by USB) |

## Assumptions to check

- Trap bottom lip = sump top = outlet invert. If the real invert sits higher (a water seal), the model needs
  a separate lip height.
- Sensor pod 400 mm below the grate, 30 mm blind zone (A02YYUW datasheet; check it on the bench). Basins added
  before this change keep the 250 mm they were saved with: re-save them on **Add basin**.
- Battery % is a straight line between 3.20 V (empty) and 3.60 V (full): recalibrate for the real cells.
- Heavy rain = 15 mm in 12 h; the sediment yield and all thresholds are first guesses to calibrate with pilot data.
- Wall thickness of 915 and 1220 mm basins are placeholders (`VERIFY` in `basin_model.py`).

## Roadmap

- [x] Diagnosis, network map, basin inspector, add basin from as-built values
- [x] Forecast-based "inspect before the storm", crew maintenance log and issue life cycle
- [x] All Dorval catch basins (Ville de Montréal open data)
- [x] Live USB sensor feed, adjustable reading interval
- [ ] Bench-test the real sensor; calibrate blind zone and noise
- [ ] Detect irregular sensor data (flat lines, too many false echoes)
- [x] Wireless prototype: Heltec V3 LoRa nodes, flash ring buffer, weather-driven reading modes
- [x] Predicted overflow in the next 24 h, vacuum truck route
- [ ] LoRaWAN gateway and network server for the Dorval pilot; deploy online
