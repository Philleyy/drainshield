"""
simulate.py
-----------
Generates FAKE rain and FAKE ultrasonic sensor readings for a network of catch
basins, so we can build the dashboard before the real sensors exist.

Run it from the project folder with ONE of:
    python simulate.py demo      (one basin in several situations, for the dashboard)
    python simulate.py user      (the basins you added in the dashboard's "Basin setup" page)
    python simulate.py pilot     (the 5-basin pilot neighbourhood)
    python simulate.py town      (the 30-basin town network)

It reads   data/basins_<network>.csv
It writes  output/rain_<network>.csv      -> what a rain gauge would record
           output/readings_<network>.csv  -> what our sensors would send
           output/truth_<network>.csv     -> the hidden truth (sediment, outlet state),
                                             so we can check how good our estimates are

-------------------------------------------------------------------------------
HOW THE PHYSICS WORKS (simplified on purpose)
-------------------------------------------------------------------------------
Each catch basin is a small reservoir, like the reservoirs in HMETS:

    change in stored water = inflow - outflow

 * Inflow  = rational method, Q_in = C * i * A, times how open the GRATE is.
             A leaf mat on the grate keeps water on the street: less inflow.
 * Outflow = only when the water is above the outlet invert:
             Q_out = K * (water level - invert)          ("linear reservoir")
             K = how easily water leaves. CLOGGING = K getting smaller.
 * SEDIMENT settles in the sump with every storm (more catchment = more sediment).
   The ultrasonic sensor can't see it (it's under the water), but when it reaches
   the bottom lip of the cast-iron TRAP (cloche), water has to squeeze through a
   thin gap under the lip, so the outlet chokes from the bottom even if the pipe
   is clear. The gap gets critical when (gap x trap perimeter) < pipe area.
 * If the basin fills past the grate, water ponds on the street.

-------------------------------------------------------------------------------
WHAT THE SENSOR SENDS (our "data contract")
-------------------------------------------------------------------------------
    basin_id, timestamp, distance_cm, battery_v
distance_cm = distance from the sensor DOWN to the surface it sees (water, or
sediment if the sump has dried out below the sediment top).
Includes noise, false echoes, a blind zone, battery drain, and adaptive
reporting (every 15 min when dry, every 5 min when the water is high or moving).
"""

import os
import sys

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# SETTINGS - change these freely
# ---------------------------------------------------------------------------
START_DATE = "2026-09-01 00:00"
N_DAYS = 60
STEP_MIN = 5                 # model time step = how often the sensor wakes up (min)
DRY_REPORT_EVERY_MIN = 15    # in dry weather, send a reading this often
WET_MARGIN_CM = 3            # "wet mode" if water is this far above the invert...
CHANGE_TRIGGER_CM = 2        # ...or if the level moved this much since the last reading

RAIN_SEED = 7                # same seed -> same weather for every network
BASIN_SEED = 123

POND_AREA_M2 = 25            # street area that floods around a full basin
POND_MAX_DEPTH_M = 0.10      # deeper than this, water runs off down the street
EVAPORATION_CM_PER_DAY = 0.3
MIN_SUMP_LEVEL_CM = 5

K_CLEAN_250MM = 0.04         # m2/s, outlet coefficient of a clean ø250 outlet (scales with pipe area)
SEDIMENT_DENSITY = 1600      # kg/m3 of settled sediment (bulk)
ANNUAL_RAIN_MM = 1000        # to convert a yearly sediment yield into "per mm of rain"

NOISE_CM = 0.3
SPIKE_PROBABILITY = 0.002

BATTERY_START_V = 3.60
BATTERY_DROP_PER_READING_V = 0.000015
LOW_BATTERY_DROP_PER_READING_V = 0.00009
BATTERY_DEAD_V = 3.20

FORCED_STORM_DAY = 44        # Oct 15: a 30 mm/h thunderstorm, so every demo has one big storm
FORCED_STORM_START_HOUR = 14
FORCED_STORM_DURATION_H = 1.0
FORCED_STORM_INTENSITY_MM_H = 30

# What each simulated situation does (the dashboard never sees this, only the readings)
SCENARIOS = {
    "healthy":       "Stays in good condition (normal, slow sediment build-up)",
    "sediment_fill": "Sump fills with sediment until it chokes the trap (e.g. construction site upstream)",
    "trap_block":    "Debris suddenly jams the trap/outlet partway through",
    "grate_block":   "Leaf mat covers the grate partway through: water stays on the street",
    "low_battery":   "Healthy basin, but the sensor battery drains fast and dies",
    "offline":       "Healthy basin, but the sensor stops sending data partway through",
}
SCENARIO_SHORT = {"healthy": "Healthy", "sediment_fill": "Sediment filling", "trap_block": "Trap blocked",
                  "grate_block": "Grate covered", "low_battery": "Battery dying", "offline": "Sensor offline"}
LEGACY_NAMES = {"slow_clog": "sediment_fill", "sudden_block": "trap_block"}
SEDIMENT_MULTIPLIER = {"sediment_fill": 4.0}       # times the normal sediment yield


# ---------------------------------------------------------------------------
# 1. RAIN
# ---------------------------------------------------------------------------
def make_rain(n_steps, rng):
    """Return an array of rain intensity (mm/h), one value per time step."""
    steps_per_hour = 60 // STEP_MIN
    steps_per_day = 24 * steps_per_hour
    rain = np.zeros(n_steps)
    t = 0
    while True:
        t += int(rng.exponential(4.0) * steps_per_day)        # ~4 days between storms
        if t >= n_steps:
            break
        if rng.random() < 0.10:                                # short, intense thunderstorm
            duration = int(rng.uniform(0.5, 1.5) * steps_per_hour)
            mean_intensity = rng.uniform(12, 30)
        else:                                                  # ordinary light-to-moderate rain
            duration = int(rng.uniform(1, 8) * steps_per_hour)
            mean_intensity = min(rng.exponential(1.5) + 0.3, 5.0)
        for k in range(duration):
            if t + k < n_steps:
                rain[t + k] = mean_intensity * rng.lognormal(0, 0.4)
        t += duration
    start = FORCED_STORM_DAY * steps_per_day + FORCED_STORM_START_HOUR * steps_per_hour
    rain[start:start + int(FORCED_STORM_DURATION_H * steps_per_hour)] = FORCED_STORM_INTENSITY_MM_H
    return rain


# ---------------------------------------------------------------------------
# 2. WATER + SEDIMENT BALANCE
# ---------------------------------------------------------------------------
def outlet_opening(sed, basins):
    """How open the outlet still is (0 to 1) given the sediment depth (m), per basin.

    With a trap: water enters under the trap's bottom lip. When sediment comes
    within a few cm of the lip, the gap under it becomes the bottleneck.
    Without a trap: sediment above the invert covers the bottom of the pipe.
    """
    lip = basins["sump_depth_cm"].to_numpy() / 100
    inv = basins["outlet_invert_cm"].to_numpy() / 100
    d = basins["outlet_diameter_cm"].to_numpy() / 100
    width = basins["trap_width_cm"].to_numpy() / 100
    proj = basins["trap_projection_cm"].to_numpy() / 100
    has_trap = width > 0
    pipe_area = np.pi * d ** 2 / 4
    gap = np.maximum(lip - sed, 0)
    perimeter = width + 2 * proj                       # the three open sides of the hood
    with_trap = gap * perimeter / pipe_area
    without_trap = 1 - (sed - inv) / d
    return np.clip(np.where(has_trap, with_trap, without_trap), 0.01, 1.0)


def simulate(basins, rain_mm_h, rng):
    """Return true surface level (cm above floor) [step, basin] and a daily truth table."""
    n_steps, n = len(rain_mm_h), len(basins)
    dt = STEP_MIN * 60.0
    days = np.arange(n_steps) * STEP_MIN / (60 * 24)
    scen = [LEGACY_NAMES.get(s, s) for s in basins["sim_scenario"]]

    inv = basins["outlet_invert_cm"].to_numpy() / 100
    grate = basins["grate_height_cm"].to_numpy() / 100
    lip = basins["sump_depth_cm"].to_numpy() / 100
    d = basins["outlet_diameter_cm"].to_numpy() / 100
    a_basin = basins["basin_area_m2"].to_numpy()
    a_catch = basins["catchment_area_m2"].to_numpy()
    c = basins["runoff_coeff"].to_numpy()
    k_clean = K_CLEAN_250MM * (d / 0.25) ** 2 * rng.uniform(0.8, 1.2, size=n)

    # Sediment: metres of sump fill per mm of rain
    mult = np.array([SEDIMENT_MULTIPLIER.get(s, 1.0) for s in scen])
    yield_per_mm = basins["sediment_yield_kg_m2_yr"].to_numpy() * mult / ANNUAL_RAIN_MM
    sed_per_mm = yield_per_mm * a_catch / (SEDIMENT_DENSITY * a_basin)
    sed = basins["sediment_at_install_cm"].to_numpy() / 100
    sed_cap = np.where(basins["trap_width_cm"].to_numpy() > 0, lip, inv + d)

    # Sudden events (blocked trap, blocked grate) happen on a random day
    event_day = rng.uniform(25, 40, size=n)
    trap_factor = np.ones((n_steps, n))
    grate_factor = np.ones((n_steps, n))
    for j, s in enumerate(scen):
        if s == "trap_block":
            trap_factor[days >= event_day[j], j] = 0.02
        if s == "grate_block":
            grate_factor[days >= event_day[j], j] = 0.12

    v_invert, v_grate = a_basin * inv, a_basin * grate
    v_max = v_grate + POND_AREA_M2 * POND_MAX_DEPTH_M
    evap = EVAPORATION_CM_PER_DAY / 100 / 86400 * a_basin * dt
    v = v_invert.copy()
    levels = np.zeros((n_steps, n))
    truth = []
    steps_per_day = 24 * 60 // STEP_MIN

    for t in range(n_steps):
        rain_mm_step = rain_mm_h[t] * STEP_MIN / 60
        sed = np.minimum(sed + sed_per_mm * rain_mm_step, sed_cap)
        opening = outlet_opening(sed, basins) * trap_factor[t]
        k = k_clean * opening
        q_in = c * (rain_mm_h[t] / 1000 / 3600) * a_catch * grate_factor[t]

        v_no_out = v + q_in * dt - np.where(q_in == 0, evap, 0)                 # below the invert
        v_basin = np.maximum((v + q_in * dt + k * dt * inv) / (1 + k * dt / a_basin), v_invert)
        v_pond = ((v + q_in * dt - k * dt * (grate - inv) + k * dt * v_grate / POND_AREA_M2)
                  / (1 + k * dt / POND_AREA_M2))
        v_pond = np.clip(v_pond, v_grate, v_max)
        v = np.where(v_no_out <= v_invert, v_no_out, np.where(v_basin <= v_grate, v_basin, v_pond))
        v = np.maximum(v, a_basin * MIN_SUMP_LEVEL_CM / 100)
        h = np.where(v <= v_grate, v / a_basin, grate + (v - v_grate) / POND_AREA_M2)
        levels[t] = np.maximum(h, sed) * 100           # the sensor sees whichever is on top

        if t % steps_per_day == 0:
            for j in range(n):
                truth.append({"basin_id": basins["basin_id"].iloc[j], "date": days[t],
                              "sediment_cm": round(sed[j] * 100, 1),
                              "outlet_open_pct": round(opening[j] * 100, 1),
                              "grate_open_pct": round(grate_factor[t, j] * 100, 1)})
    return levels, pd.DataFrame(truth)


# ---------------------------------------------------------------------------
# 3. SENSOR: true levels -> the readings a real sensor would send
# ---------------------------------------------------------------------------
def make_readings(basins, levels, timestamps, rng):
    n_steps, _ = levels.shape
    rows = []
    for j, basin in basins.reset_index(drop=True).iterrows():
        scenario = LEGACY_NAMES.get(basin["sim_scenario"], basin["sim_scenario"])
        sensor_h, blind = basin["sensor_height_cm"], basin["sensor_blind_zone_cm"]
        invert = basin["outlet_invert_cm"]
        drop = LOW_BATTERY_DROP_PER_READING_V if scenario == "low_battery" else BATTERY_DROP_PER_READING_V
        offline_step = int(rng.uniform(0.4, 0.7) * n_steps) if scenario == "offline" else n_steps
        battery, last_sent_step, last_sent_level = BATTERY_START_V, -999, None

        for t in range(min(n_steps, offline_step)):
            level = levels[t, j]
            minutes_since = (t - last_sent_step) * STEP_MIN
            wet = level > invert + WET_MARGIN_CM
            changed = last_sent_level is not None and abs(level - last_sent_level) > CHANGE_TRIGGER_CM
            if not (minutes_since >= DRY_REPORT_EVERY_MIN or wet or changed):
                continue                                           # stay asleep, save battery
            if battery < BATTERY_DEAD_V:
                break
            distance = sensor_h - level + rng.normal(0, NOISE_CM)
            distance = max(distance, blind)                        # too close: sensor saturates
            if rng.random() < SPIKE_PROBABILITY:
                distance = rng.uniform(blind, sensor_h)            # false echo
            rows.append({"basin_id": basin["basin_id"], "timestamp": timestamps[t],
                         "distance_cm": round(distance, 1),
                         "battery_v": round(battery + rng.normal(0, 0.005), 3)})
            battery -= drop
            last_sent_step, last_sent_level = t, level
    return pd.DataFrame(rows, columns=["basin_id", "timestamp", "distance_cm", "battery_v"])


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def run_network(network, folder=".", verbose=True):
    basin_file = os.path.join(folder, "data", f"basins_{network}.csv")
    if not os.path.exists(basin_file):
        raise FileNotFoundError(f"Can't find {basin_file}. Run 'python make_basins.py' first.")
    basins = pd.read_csv(basin_file)
    n_steps = N_DAYS * 24 * 60 // STEP_MIN
    timestamps = pd.date_range(START_DATE, periods=n_steps, freq=f"{STEP_MIN}min")
    rain = make_rain(n_steps, np.random.default_rng(RAIN_SEED))
    rain_df = pd.DataFrame({"timestamp": timestamps, "rain_mm": np.round(rain * STEP_MIN / 60, 2)})

    out = os.path.join(folder, "output")
    os.makedirs(out, exist_ok=True)
    rain_df.to_csv(os.path.join(out, f"rain_{network}.csv"), index=False)
    if basins.empty:
        readings, truth = make_readings(basins, np.zeros((n_steps, 0)), timestamps, None), pd.DataFrame()
    else:
        rng = np.random.default_rng(BASIN_SEED)
        levels, truth = simulate(basins, rain, rng)
        readings = make_readings(basins, levels, timestamps, rng)
        truth["date"] = pd.Timestamp(START_DATE) + pd.to_timedelta(truth["date"], unit="D")
    readings.to_csv(os.path.join(out, f"readings_{network}.csv"), index=False)
    truth.to_csv(os.path.join(out, f"truth_{network}.csv"), index=False)
    if verbose:
        print(f"Simulated {len(basins)} basins over {N_DAYS} days "
              f"({rain_df['rain_mm'].sum():.0f} mm of rain).")
        print(f"Saved {len(readings):,} sensor readings to output/readings_{network}.csv")
    return basins, readings, rain_df, truth


if __name__ == "__main__":
    try:
        run_network(sys.argv[1] if len(sys.argv) > 1 else "demo")
    except FileNotFoundError as e:
        sys.exit(str(e))
