"""
app.py: start the DrainShield dashboard
---------------------------------------
From the project folder:
    python -m streamlit run app.py
Your browser opens the dashboard. Stop it with Ctrl+C in the terminal.

To feed it real readings from a sensor plugged into this computer, run
sensor_bridge.py in a SECOND terminal (see the "Live sensor" page).

This file sets up the pages, the logo, the Crew / Engineering view switch and
the auto-refresh, which are shared by every page:
    network.py      -> every catch basin of the city + the dispatch list
    dashboard.py    -> one monitored catch basin in detail
    sensor_live.py  -> raw readings from a sensor, and its reading interval
    basin_setup.py  -> attach a sensor to a catch basin (as-built geometry)
"""

import time

import streamlit as st

import data_store

st.set_page_config(page_title="DrainShield", page_icon="assets/drainshield_icon.png", layout="wide")
st.logo("assets/drainshield_logo.png", icon_image="assets/drainshield_icon.png", size="large")

page = st.navigation([
    st.Page("network.py", title="Network", icon=":material/map:", default=True),
    st.Page("dashboard.py", title="Basin", icon=":material/water_drop:"),
    st.Page("sensor_live.py", title="Live sensor", icon=":material/sensors:"),
    st.Page("basin_setup.py", title="Add basin", icon=":material/add_circle:"),
])

basins, *_ = data_store.load_all()
params = st.query_params
if "basin_id" not in st.session_state and not basins.empty:
    wanted = params.get("basin")
    st.session_state["basin_id"] = wanted if wanted in set(basins["basin_id"]) else basins["basin_id"].iloc[0]
if "role" not in st.session_state:
    st.session_state["role"] = params.get("view", "Crew")

with st.sidebar:
    st.segmented_control("View", ["Crew", "Engineering"], key="role", width="stretch",
                         help="Crew: just what to do. Engineering: sensor health, hydrographs and history.")
    refresh = st.toggle("Auto-refresh every 10 s", value=params.get("refresh", "1") == "1", key="auto_refresh",
                        help="Re-reads the sensor data. Turn it off while you fill in a form.")
    st.caption(f"Live data · {data_store.now():%b %d, %H:%M:%S}")

page.run()

if refresh and page.title != "Add basin":       # never refresh in the middle of filling a form
    time.sleep(10)
    st.rerun()
