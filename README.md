<img src="assets/drainshield_logo.png" alt="DrainShield" width="320">

# DrainShield: catch basin monitoring and decision support

Software side of DrainShield's low-cost catch basin sensor: from raw sensor readings
to decisions a public works team can act on. It covers two needs:

1. **Predictive maintenance**: find basins that drain slowly (sediment, blocked trap, covered grate),
   and flag the ones to clean **before** a forecast storm.
2. **Emergency dispatch**: see which basin is backing up during a storm, without waiting for 311 calls.

**Status:** early development. All sensor data is **simulated** until the prototype is ready.
The catch basin **locations are real** (Ville de Montréal open data, Dorval).
New here? Start with **[SETUP_GUIDE.md](SETUP_GUIDE.md)**.

## Quick start

```
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Three pages, plus a **Crew / Engineering** view switch in the sidebar (Crew is simpler; Engineering adds
sensor health, hydrographs and history):

- **Network**: weather readiness banner (rain in the next 12 h, and which basins to clean before it),
  filter counters (🔴 Urgent · 🟠 Inspect · 🟢 Normal · ⚪ Offline), a map with the monitored basins and the
  city's unmonitored ones (grey), a search box, and the dispatch list.
- **Basin**: what to do (observed → possible explanation with a confidence level → next step), the to-scale
  cross-section, live water depth, drainage performance, and a **Log maintenance** button for crews.
- **Add basin**: from the as-built plan (or by picking one of the city's catch basins), with a live drawing.

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

**What the sensor can't see:** it measures the distance to the water surface only. The sump contents are
**estimated** (rain × drainage area × sediment yield), and water closer than its blind zone
(~0.65 m below the street with the pod at 0.40 m) shows as "≤ 0.65 m".

## Files

| File | What it does |
|---|---|
| `app.py` | Starts the dashboard, logo, view switch, shared replay controls |
| `network.py` · `dashboard.py` · `basin_setup.py` | The three pages |
| `processing.py` | Readings → water level, storms, diagnosis, estimates, status. **All thresholds at the top** |
| `weather.py` | Rain forecast (simulated in the demo; live Environment Canada GEM via Open-Meteo) and the ECCC radar layer |
| `maintenance.py` | Crew maintenance log and issue life cycle (`data/maintenance_log.csv`) |
| `basin_model.py` | As-built values (depths from the grate) → the numbers the model uses |
| `basin_drawing.py` | The to-scale cross-section |
| `import_municipal.py` | Makes `data/municipal_basins.csv` from the Ville de Montréal `ego_puisard_p.csv` |
| `simulate.py` · `make_basins.py` | Fake rain, water, sediment and sensor readings; demo basin lists |
| `basin_catalog.py` | Reference: Lécuyer precast models and TP-3/4/5 traps |
| `data_store.py` · `ui.py` | Data loading and page building blocks |

## Using another municipality

Download `ego_puisard_p.csv` ("Puisards d'égout") from donnees.montreal.ca, then:

```
python import_municipal.py path/to/ego_puisard_p.csv --owner "POINTE-CLAIRE"
```

Don't commit the full 78 MB file to GitHub: the slice in `data/` is all the dashboard needs.

## Data contract (one sensor reading)

| Field | Example | Meaning |
|---|---|---|
| `basin_id` | `DEMO-02` | Which basin |
| `timestamp` | `2026-10-15 14:05:00` | When it was measured |
| `distance_cm` | `81.4` | Distance from the sensor down to the surface it sees |
| `battery_v` | `3.512` | Battery voltage |

## Assumptions to check

- Trap bottom lip = sump top = outlet invert. If the real invert sits higher (a water seal), the model needs
  a separate lip height.
- Sensor pod 400 mm below the grate, 250 mm blind zone.
- Battery % is a straight line between 3.20 V (empty) and 3.60 V (full): recalibrate for the real cells.
- Heavy rain = 15 mm in 12 h; the sediment yield and all thresholds are first guesses to calibrate with pilot data.
- Wall thickness of 915 and 1220 mm basins are placeholders (`VERIFY` in `basin_model.py`).

## Roadmap

- [x] Simulated data, diagnosis, network map, basin inspector, add basin from as-built values
- [x] Forecast-based "inspect before the storm", crew maintenance log and issue life cycle
- [x] Real catch basin locations (Ville de Montréal open data)
- [ ] Detect irregular sensor data (flat lines, too many false echoes)
- [ ] Connect the real sensor prototype (then: live mode, signal strength), deploy online
