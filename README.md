<img src="assets/drainshield_logo.png" alt="DrainShield" width="320">

# DrainShield: catch basin monitoring and decision support

Software side of DrainShield's low-cost catch basin sensor: from raw sensor readings
to decisions a public works team can act on. It covers two needs:

1. **Predictive maintenance**: find basins that drain slowly (sediment, blocked trap, covered grate),
   and flag the ones to clean **before** a forecast storm.
2. **Emergency dispatch**: see which basin is backing up during a storm, without waiting for 311 calls.

**Status:** early development, **live data only**. The map shows **all 5,035 Dorval catch basins** from the
Ville de Montréal open data; a basin gets a status once a DrainShield sensor is attached to it.
Readings come from a sensor plugged into the laptop by USB (`sensor_bridge.py`), later from LoRaWAN.
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

Four pages, plus a **Crew / Engineering** view switch in the sidebar (Crew is simpler; Engineering adds
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
(~0.65 m below the street with the pod at 0.40 m) shows as "≤ 0.65 m".

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
- Sensor pod 400 mm below the grate, 250 mm blind zone.
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
- [ ] Wireless (LoRaWAN) sensor, battery reporting, deploy online
