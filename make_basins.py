"""
make_basins.py
--------------
Creates the lists of FAKE catch basins used by the simulator and the dashboard,
described the way a municipality knows them (as-built depths, see basin_model.py).

It writes in the data/ folder:
    data/basins_demo.csv   -> 6 basins on a few streets, each in a different simulated situation
    data/basins_pilot.csv  -> 5 basins on neighbouring streets (pilot project)
    data/basins_town.csv   -> 30 basins spread over a small town

Basins you add in the dashboard ("Basin setup" page) go in data/basins_user.csv,
which this script never touches.

Run it from the project folder with:
    python make_basins.py

The sensors are fake, but they sit on REAL Dorval catch basins (Ville de Montréal open data).
"""

import os
import random

import pandas as pd

import basin_model as bm

# Real catch basin locations from the Ville de Montréal open data (see import_municipal.py).
# Our demo sensors are "attached" to real basins so the map shows real streets.
MUNICIPAL_FILE = os.path.join("data", "municipal_basins.csv")
_used = set()


def real_spot(near=None, rng=None):
    """Pick an unused real catch basin: the closest one to `near`, or a random one."""
    if not os.path.exists(MUNICIPAL_FILE):
        return None
    m = pd.read_csv(MUNICIPAL_FILE, dtype={"municipal_id": str})
    m = m[~m["municipal_id"].isin(_used)]
    if near is not None:
        d = (m["latitude"] - near[0]) ** 2 + (m["longitude"] - near[1]) ** 2
        spot = m.loc[d.idxmin()]
    else:   # a random basin inside the town area
        m = m[m["latitude"].between(TOWN_BOX["lat_min"], TOWN_BOX["lat_max"])
              & m["longitude"].between(TOWN_BOX["lon_min"], TOWN_BOX["lon_max"])]
        spot = m.iloc[rng.randrange(len(m))]
    _used.add(spot["municipal_id"])
    return spot

SEED = 42
# Dorval: the residential area south of the highway (avenues Dawson, Lilas, Roy, Saint-Louis...)
TOWN_BOX = {"lat_min": 45.438, "lat_max": 45.452, "lon_min": -73.780, "lon_max": -73.728}
PILOT_CENTER = (45.4440, -73.7520)


def basin(basin_id, scenario, lat, lon, rng=None, **changes):
    cfg = bm.default_config()
    spot = real_spot(near=(lat, lon)) if rng is None else real_spot(rng=rng)
    if spot is not None:      # snap to a real catch basin
        lat, lon = spot["latitude"], spot["longitude"]
        cfg.update(municipal_id=spot["municipal_id"], address=spot["address"])
    cfg.update(basin_id=basin_id, sensor_id=f"DS-{basin_id}", latitude=round(lat, 6), longitude=round(lon, 6),
               sim_scenario=scenario)
    cfg.update(changes)
    return bm.build_row(cfg)


def make_demo():
    lat, lon = PILOT_CENTER
    subdrain = [{"kind": "Subdrain", "depth_mm": 950, "diameter_mm": 150}]
    return [
        basin("DEMO-01", "healthy", lat + 0.0018, lon - 0.0030),
        basin("DEMO-02", "sediment_fill", lat + 0.0006, lon - 0.0004, sediment_at_install_mm=160),
        basin("DEMO-03", "trap_block", lat - 0.0003, lon + 0.0022, invert_depth_mm=1550, inlets=subdrain),
        basin("DEMO-04", "grate_block", lat - 0.0016, lon - 0.0024),
        basin("DEMO-05", "low_battery", lat - 0.0028, lon + 0.0004, sump_mm=500, invert_depth_mm=1400),
        basin("DEMO-06", "offline", lat + 0.0010, lon + 0.0036),
    ]


def random_basin(rng, basin_id, scenario, lat, lon, anywhere=False):
    inlets = ([{"kind": "Subdrain", "depth_mm": rng.choice([900, 950, 1000]), "diameter_mm": 150}]
              if rng.random() < 0.3 else [])
    return basin(basin_id, scenario, lat, lon, rng=rng if anywhere else None,
                 invert_depth_mm=rng.choice([1200, 1300, 1400, 1400, 1500, 1700]),
                 sump_mm=500 if rng.random() < 0.2 else 300, inlets=inlets,
                 catchment_m2=rng.randint(250, 900),
                 sediment_at_install_mm=160 if scenario == "sediment_fill" else rng.randint(20, 120))


def make_pilot(rng):
    scenarios = ["healthy", "healthy", "sediment_fill", "grate_block", "trap_block"]
    return [random_basin(rng, f"PILOT-{i:02d}", s,
                         PILOT_CENTER[0] + rng.uniform(-0.0009, 0.0009),
                         PILOT_CENTER[1] + rng.uniform(-0.0012, 0.0012))
            for i, s in enumerate(scenarios, start=1)]


def make_town(rng):
    scenarios = (["healthy"] * 21 + ["sediment_fill"] * 4 +
                 ["trap_block", "grate_block", "grate_block", "offline", "low_battery"])
    rng.shuffle(scenarios)
    return [random_basin(rng, f"DOR-{i:03d}", s,
                         rng.uniform(TOWN_BOX["lat_min"], TOWN_BOX["lat_max"]),
                         rng.uniform(TOWN_BOX["lon_min"], TOWN_BOX["lon_max"]), anywhere=True)
            for i, s in enumerate(scenarios, start=1)]


def save(rows, name):
    path = os.path.join("data", f"basins_{name}.csv")
    pd.DataFrame(rows).to_csv(path, index=False)
    print(f"Saved {len(rows)} basins to {path}")


if __name__ == "__main__":
    rng = random.Random(SEED)
    os.makedirs("data", exist_ok=True)
    save(make_demo(), "demo")
    save(make_pilot(rng), "pilot")
    save(make_town(rng), "town")
