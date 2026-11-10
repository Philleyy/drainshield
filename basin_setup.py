"""
basin_setup.py: add a catch basin from its as-built plan
--------------------------------------------------------
Only asks for what a municipality actually has on its as-built plans (plans tel que
construit): inside diameter, outlet invert depth and pipe size, sump, other pipes
coming in, and where our sensor pod was mounted. Saving adds it to
data/basins_user.csv and generates simulated data for it.
"""

import re

import pandas as pd
import streamlit as st

import basin_model as bm
import data_store
import simulate
import ui
from basin_catalog import TRAPS, trap_for_pipe
from basin_drawing import basin_svg

ui.inject_css()
basins, *_ = data_store.load_all()
other_ids = set(basins.loc[basins["network"] != "user", "basin_id"])
user_ids = set(basins.loc[basins["network"] == "user", "basin_id"])
cfg = bm.default_config()

# Municipal catch basins (Ville de Montréal open data) that don't have a sensor yet
muni = data_store.municipal_basins()
attached = set(basins["municipal_id"].dropna().astype(str)) if "municipal_id" in basins else set()
muni = muni[~muni["municipal_id"].isin(attached)]
muni_label = dict(zip(muni["municipal_id"], muni["address"]))


def use_municipal():
    """Copy the chosen municipal basin's position into the form."""
    mid = st.session_state.get("muni_pick")
    if mid:
        row = muni[muni["municipal_id"] == mid].iloc[0]
        st.session_state["lat"], st.session_state["lon"] = float(row["latitude"]), float(row["longitude"])


# Coming from "+ Attach a DrainShield sensor" on the map: pre-fill the form
if "prefill" in st.session_state:
    p = st.session_state.pop("prefill")
    st.session_state["muni_pick"] = p["municipal_id"]
    st.session_state["lat"], st.session_state["lon"] = p["latitude"], p["longitude"]

st.title("Add a basin")
st.caption("From the as-built plan (plan tel que construit). Depths are measured down from the street grate. "
           "The drawing on the right updates as you type (press Enter).")

form, preview = st.columns([1, 1.15], gap="large")

with form:
    st.markdown("**Identification**")
    mid = st.selectbox("Municipal catch basin (optional)", list(muni["municipal_id"]), index=None, key="muni_pick",
                       on_change=use_municipal, placeholder="🔍 Search the city's catch basins by number or street",
                       format_func=lambda m: f"#{m} · {muni_label.get(m, '')}",
                       help="From the Ville de Montréal open data. Picking one fills in the position.")
    c1, c2 = st.columns(2)
    cfg["basin_id"] = c1.text_input("Basin ID", placeholder="e.g. DOR-101", key="bid",
                                    on_change=lambda: st.session_state.pop("just_saved", None)).strip()
    cfg["sensor_id"] = c2.text_input("Sensor device ID", placeholder="e.g. DS-0042", key="sid",
                                     help="The sensor is tracked separately: it can be swapped without losing "
                                          "the basin's dimensions or history.").strip()
    c1, c2 = st.columns(2)
    cfg["latitude"] = c1.number_input("Latitude", 44.0, 47.0, 45.4440, 0.0001, format="%.6f", key="lat")
    cfg["longitude"] = c2.number_input("Longitude", -80.0, -60.0, -73.7520, 0.0001, format="%.6f", key="lon")
    if mid:
        cfg["municipal_id"], cfg["address"] = mid, muni_label.get(mid, "")

    st.markdown("**As-built geometry**")
    options = list(bm.DIAMETERS) + ["custom"]
    dia = st.selectbox("Inside diameter", options, key="dia", format_func=lambda d: bm.DIAMETERS.get(d, "Custom"))
    cfg["diameter_mm"] = (st.number_input("Custom inside diameter (mm)", 300, 2500, 760, 5, key="dia_custom")
                          if dia == "custom" else dia)
    c1, c2 = st.columns(2)
    cfg["invert_depth_mm"] = c1.number_input("Outlet invert depth (mm)", 500, 6000, 1400, 10, key="inv",
                                             help="Profondeur du radier: from the top of the grate down to the "
                                                  "bottom of the outlet pipe.")
    cfg["outlet_mm"] = c2.selectbox("Outlet pipe ø (mm)", bm.PIPE_SIZES_MM, index=2, key="pipe")
    sump = st.segmented_control("Sump depth below invert", list(bm.SUMPS), default=300, key="sump",
                                format_func=lambda s: bm.SUMPS[s])
    cfg["sump_mm"] = 300 if sump is None else sump      # (0 mm is a valid choice, so don't use "or")
    cfg["sensor_depth_mm"] = st.number_input("Sensor depth from grate (mm)", 100, 3000, bm.DEFAULT_SENSOR_DEPTH_MM,
                                             10, key="sdepth", help="Standard mount: 400 mm. Change it if the "
                                                                    "installer had to avoid an obstacle.")

    more = st.expander("More options: trap, incoming pipes / subdrains, sensor blind zone")
with more:
    trap_name = trap_for_pipe(cfg["outlet_mm"])
    can_trap = trap_name is not None and cfg["sump_mm"] > 0
    cfg["has_trap"] = st.checkbox(f"Cast-iron trap (cloche) installed{f' · {trap_name}' if can_trap else ''}",
                                  value=can_trap, disabled=not can_trap, key=f"trap_{can_trap}",
                                  help="Sized automatically from the outlet pipe (TP-3 ø200, TP-4 ø250, TP-5 ø300). "
                                       "Needs a sump for its water seal.")

    st.markdown("**Incoming pipes / subdrains**")
    inlets_df = st.data_editor(
        pd.DataFrame(columns=["Type", "Depth from grate (mm)", "Diameter (mm)"]).astype(
            {"Type": "str", "Depth from grate (mm)": "float", "Diameter (mm)": "float"}),
        num_rows="dynamic", hide_index=True, width="stretch", key="inlets",
        column_config={
            "Type": st.column_config.SelectboxColumn("Type", options=bm.INLET_KINDS, default="Subdrain", required=True),
            "Depth from grate (mm)": st.column_config.NumberColumn(min_value=0, max_value=6000, step=10, required=True),
            "Diameter (mm)": st.column_config.SelectboxColumn(options=[100, 150, 200, 250, 300], default=150,
                                                              required=True),
        })
    st.caption("Click **+** under the table to add a pipe, e.g. a subdrain at 950 mm, ø150. "
               "Water rising above an incoming pipe backs up into it (into the road base for a subdrain).")
    cfg["inlets"] = [{"kind": r["Type"] or "Subdrain", "depth_mm": float(r["Depth from grate (mm)"]),
                      "diameter_mm": float(r["Diameter (mm)"])}
                     for _, r in inlets_df.iterrows()
                     if pd.notna(r["Depth from grate (mm)"]) and pd.notna(r["Diameter (mm)"])]

    cfg["blind_zone_mm"] = st.number_input("Sensor blind zone (mm)", 20, 600, bm.DEFAULT_BLIND_ZONE_MM, 10,
                                           key="blind", help="The sensor can't measure anything closer. ~250 mm "
                                                             "for JSN-SR04T-type waterproof ultrasonic sensors.")

with form:
    with st.expander("Simulator settings (for demo data generation only)"):
        scen = list(simulate.SCENARIOS)
        cfg["sim_scenario"] = st.selectbox("Situation to simulate", scen, key="scen",
                                           format_func=lambda s: f"{simulate.SCENARIO_SHORT[s]}: {simulate.SCENARIOS[s]}")
        c1, c2 = st.columns(2)
        cfg["catchment_m2"] = c1.number_input("Area draining to it (m²)", 20, 20000, 600, 10, key="area")
        cfg["runoff_coeff"] = c2.number_input("Runoff coefficient C", 0.1, 1.0, 0.9, 0.05, key="c")
        cfg["sediment_yield"] = c1.number_input("Sediment yield (kg/m²/year)", 0.0, 5.0, 0.15, 0.05, key="yield")
        cfg["sediment_at_install_mm"] = c2.number_input("Sediment in the sump at installation (mm)", 0, 1000, 50, 10,
                                                        key="sed0")

with preview:
    row = bm.build_row(cfg)
    st.subheader("Preview")
    ui.svg_image(basin_svg(pd.Series(row), 0), max_width=600)
    depth = bm.depth_mm(cfg)
    c1, c2, c3 = st.columns(3)
    c1.html(ui.tile("Outlet invert depth", f"{cfg['invert_depth_mm']:.0f} mm", "below the grate", "neutral"))
    c2.html(ui.tile("Total depth (to floor)", f"{depth:.0f} mm", f"invert + {cfg['sump_mm']} mm sump", "neutral"))
    c3.html(ui.tile("Flood buffer", f"{cfg['invert_depth_mm'] - cfg['sensor_depth_mm']:.0f} mm",
                    "invert to sensor", "neutral"))
    st.caption(f"The sensor sees water up to {cfg['sensor_depth_mm'] + cfg['blind_zone_mm']:.0f} mm below the "
               f"grate (its {cfg['blind_zone_mm']:.0f} mm blind zone hides anything closer).")

    checks = bm.check(cfg)
    for level, msg in checks:
        {"error": st.error, "warning": st.warning, "info": st.info}[level](msg)

    bid = cfg["basin_id"]
    id_ok = bool(re.fullmatch(r"[A-Za-z0-9_-]{1,30}", bid))
    if bid and not id_ok:
        st.error("Basin ID: letters, numbers, - or _ only (max 30 characters).")
    if bid in other_ids:
        st.error(f"{bid} is already used by a demo or simulated basin.")
    replace = st.checkbox(f"Replace my existing basin {bid}", key="replace") if bid in user_ids else False
    errors = [m for lvl, m in checks if lvl == "error"]
    can_save = id_ok and not errors and bid not in other_ids and (bid not in user_ids or replace)
    if st.button("Save basin", type="primary", disabled=not can_save, width="stretch"):
        with st.spinner("Generating simulated data..."):
            data_store.save_user_basin(row, replace=replace)
        data_store.select_basin(bid)
        st.session_state["just_saved"] = bid
        st.rerun()
    if st.session_state.get("just_saved"):
        st.success(f"Saved {st.session_state['just_saved']}.")
        st.page_link("dashboard.py", label=f"Open {st.session_state['just_saved']} →")
    if not bid:
        st.caption("Enter a basin ID to save.")

# ---------------- Your basins ----------------
st.divider()
st.subheader("Your basins")
if not user_ids:
    st.write("None yet. They're saved in `data/basins_user.csv`, so you can commit them to GitHub.")
else:
    mine = basins[basins["network"] == "user"]
    st.dataframe(pd.DataFrame({
        "ID": mine["basin_id"], "Sensor": mine.get("sensor_id"), "Address": mine.get("address"),
        "Diameter (mm)": (mine["inner_width_cm"] * 10).round(),
        "Invert depth (mm)": (mine["invert_depth_cm"] * 10).round(),
        "Outlet ø (mm)": (mine["outlet_diameter_cm"] * 10).round(),
        "Sump (mm)": (mine["sump_depth_cm"] * 10).round(), "Trap": mine["trap_model"],
        "Incoming pipes": mine["subdrains"],
    }), hide_index=True, width="stretch")
    c1, c2 = st.columns([2, 1])
    to_delete = c1.selectbox("Delete a basin", sorted(user_ids), key="del")
    if c2.button("Delete", width="stretch"):
        data_store.delete_user_basin(to_delete)
        st.rerun()
