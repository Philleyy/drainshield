"""
plot_compare.py
---------------
Plots a CLEAN basin next to a CLOGGING basin so you can see how differently
they respond to the same rain.

Run it from the project folder (after simulate.py) with:
    python plot_compare.py pilot
or pick the two basins yourself:
    python plot_compare.py pilot PILOT-01 PILOT-05
    python plot_compare.py town DOR-003 DOR-010

It saves the figure in output/figures/ and also opens it in a window.
"""

import os
import sys

import matplotlib.pyplot as plt
import pandas as pd

# Colours (blue = clean, orange = clogging, grey = rain)
CLEAN_COLOR = "#2a78d6"
CLOG_COLOR = "#eb6834"
RAIN_COLOR = "#8a8984"
TEXT = "#0b0b0b"
TEXT_MUTED = "#52514e"
GRID = "#e4e3df"

# The window to zoom in on: the forced "design storm" in simulate.py (day 44, 14:00)
ZOOM_START = "2026-10-15 12:00"
ZOOM_END = "2026-10-16 00:00"

REMOVE_SPIKES = True   # clean out false-echo spikes before plotting
BLIND_ZONE_CM = 25     # must match simulate.py


def load(network):
    basins = pd.read_csv(os.path.join("data", f"basins_{network}.csv"))
    readings = pd.read_csv(os.path.join("output", f"readings_{network}.csv"), parse_dates=["timestamp"])
    rain = pd.read_csv(os.path.join("output", f"rain_{network}.csv"), parse_dates=["timestamp"])
    return basins, readings, rain


def water_above_outlet(readings, basins, basin_id):
    """Convert raw sensor distances into 'water height above the outlet pipe' (cm).

    0 cm   = normal dry-weather level (water sitting at the outlet pipe)
    > 0 cm = water backing up in the basin
    This conversion will later move into its own processing script.
    """
    b = basins.set_index("basin_id").loc[basin_id]
    r = readings[readings["basin_id"] == basin_id].copy()
    level_above_floor = b["sensor_height_cm"] - r["distance_cm"]
    r["above_outlet_cm"] = level_above_floor - b["outlet_invert_cm"]

    # First taste of DATA CLEANING: the sensor sometimes sends a false echo
    # (one crazy value between two normal ones). A "rolling median" of 3
    # readings replaces each value by the middle one of itself and its two
    # neighbours, which removes single spikes but keeps real rises.
    # Set REMOVE_SPIKES = False to see the raw data with the spikes.
    if REMOVE_SPIKES:
        r["above_outlet_cm"] = r["above_outlet_cm"].rolling(3, center=True, min_periods=1).median()

    # Highest level the sensor can measure (water inside the blind zone)
    r.attrs["max_measurable_cm"] = (b["sensor_height_cm"] - b["sensor_blind_zone_cm"]) - b["outlet_invert_cm"]
    return r


def style(ax):
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=TEXT_MUTED, labelsize=9)


if __name__ == "__main__":
    network = sys.argv[1] if len(sys.argv) > 1 else "pilot"
    basins, readings, rain = load(network)

    # Default choice: the first healthy basin and the first slowly clogging one.
    if len(sys.argv) >= 4:
        clean_id, clog_id = sys.argv[2], sys.argv[3]
    else:
        clean_id = basins.loc[basins["sim_scenario"] == "healthy", "basin_id"].iloc[0]
        clog_id = basins.loc[basins["sim_scenario"].isin(["sediment_fill", "trap_block", "slow_clog"]), "basin_id"].iloc[0]

    clean = water_above_outlet(readings, basins, clean_id)
    clog = water_above_outlet(readings, basins, clog_id)
    hourly_rain = rain.set_index("timestamp")["rain_mm"].resample("h").sum()

    fig, (ax_rain, ax_all, ax_zoom) = plt.subplots(
        3, 1, figsize=(11, 8.5), gridspec_kw={"height_ratios": [1, 2.2, 2.2]})
    fig.patch.set_facecolor("#fcfcfb")

    # --- Panel 1: rain (bars hanging down from the top, hydrology style) ---
    ax_rain.bar(hourly_rain.index, hourly_rain.values, width=1 / 24, color=RAIN_COLOR)
    ax_rain.invert_yaxis()
    ax_rain.set_ylabel("Rain (mm/h)", color=TEXT_MUTED, fontsize=9)
    ax_rain.set_title("Rainfall", loc="left", color=TEXT, fontsize=11)
    ax_rain.set_xticklabels([])

    # --- Panel 2: the whole period ---
    # The labels use the simulator's hidden "truth" (healthy, slow clog...).
    # With real sensors we won't know this; working it out is the dashboard's job.
    scenario = basins.set_index("basin_id")["sim_scenario"].str.replace("_", " ")
    for df, color, label in [(clean, CLEAN_COLOR, f"{clean_id} ({scenario[clean_id]})"),
                             (clog, CLOG_COLOR, f"{clog_id} ({scenario[clog_id]})")]:
        ax_all.plot(df["timestamp"], df["above_outlet_cm"], color=color, linewidth=1.2, label=label)
    ax_all.axvspan(pd.Timestamp(ZOOM_START), pd.Timestamp(ZOOM_END), color=GRID, alpha=0.6, lw=0)
    ax_all.set_ylabel("Water above outlet pipe (cm)", color=TEXT_MUTED, fontsize=9)
    ax_all.set_title("Same rain, very different response as the outlet clogs",
                     loc="left", color=TEXT, fontsize=11)
    ax_all.legend(frameon=False, fontsize=9, loc="upper left")

    # --- Panel 3: zoom on the big storm ---
    for df, color in [(clean, CLEAN_COLOR), (clog, CLOG_COLOR)]:
        z = df[(df["timestamp"] >= ZOOM_START) & (df["timestamp"] <= ZOOM_END)]
        ax_zoom.plot(z["timestamp"], z["above_outlet_cm"], color=color, linewidth=2,
                     marker="o", markersize=3)
    limit = clog.attrs["max_measurable_cm"]
    ax_zoom.axhline(limit, color=TEXT_MUTED, linewidth=1, linestyle="--")
    ax_zoom.text(pd.Timestamp(ZOOM_END), limit + 1.5, f"sensor limit for {clog_id}: water too close to measure",
                 ha="right", va="bottom", color=TEXT_MUTED, fontsize=8)
    ax_zoom.set_ylabel("Water above outlet pipe (cm)", color=TEXT_MUTED, fontsize=9)
    ax_zoom.set_title("Zoom on the Oct 15 thunderstorm (30 mm/h, grey band above): "
                      "the clean basin barely moves, the clogged one fills and drains slowly",
                      loc="left", color=TEXT, fontsize=11)
    ax_zoom.xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter("%H:%M"))

    for ax in (ax_rain, ax_all, ax_zoom):
        style(ax)
    ax_rain.set_xlim(ax_all.get_xlim())

    fig.tight_layout()
    os.makedirs(os.path.join("output", "figures"), exist_ok=True)
    out = os.path.join("output", "figures", f"compare_{network}_{clean_id}_vs_{clog_id}.png")
    fig.savefig(out, dpi=150, facecolor=fig.get_facecolor())
    print(f"Saved figure to {out}")
    plt.show()
