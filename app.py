"""
app.py: start the DrainShield dashboard
---------------------------------------
From the project folder:
    python -m streamlit run app.py
Your browser opens the dashboard. Stop it with Ctrl+C in the terminal.

To feed it real readings from a sensor plugged into this computer, run
sensor_bridge.py (USB) or lora_bridge.py (LoRa receiver) in a SECOND terminal.

This file sets up the pages, the logo, the Crew / Engineering view switch and the
auto-refresh, which are shared by every page:
    network.py      -> every catch basin of the city + the dispatch list
    dashboard.py    -> one monitored catch basin in detail
    sensor_live.py  -> raw readings from a sensor, and its reading interval
    basin_setup.py  -> attach a sensor to a catch basin (as-built geometry)
    route_page.py   -> the vacuum truck's route through the basins to clean
"""

import time

import streamlit as st

import data_store

st.set_page_config(page_title="DrainShield", page_icon="assets/drainshield_icon.png", layout="wide")
st.logo("assets/drainshield_logo.png", icon_image="assets/drainshield_icon.png", size="large")
params = st.query_params

ss = st.session_state


def keep(key, default):
    """Streamlit forgets a sidebar switch's value when a page change interrupts a run (e.g. clicking a
    dispatch row) or resets it to the default. Keep a copy under "_<key>" and put it back every run, before
    the switch is drawn."""
    ss.setdefault("_" + key, default)
    ss[key] = ss["_" + key]


def remember(key):
    """on_change helper: store the new value (a segmented control can be clicked off: keep the old one)."""
    if ss.get(key) is None:
        ss[key] = ss["_" + key]
    ss["_" + key] = ss[key]


pages = [
    st.Page("network.py", title="Network", icon=":material/map:", default=True),
    st.Page("dashboard.py", title="Basin", icon=":material/water_drop:"),
    st.Page("route_page.py", title="Truck route", icon=":material/local_shipping:"),
    st.Page("sensor_live.py", title="Live sensor", icon=":material/sensors:"),
    st.Page("basin_setup.py", title="Add basin", icon=":material/add_circle:"),
]
page = st.navigation(pages)

basins, *_ = data_store.load_all()
if ("basin_id" not in st.session_state or st.session_state["basin_id"] not in set(basins["basin_id"])) \
        and not basins.empty:
    wanted = params.get("basin")
    st.session_state["basin_id"] = wanted if wanted in set(basins["basin_id"]) else basins["basin_id"].iloc[0]
keep("role", params.get("view", "Crew"))


with st.sidebar:
    st.segmented_control("View", ["Crew", "Engineering"], key="role", width="stretch", on_change=remember, args=("role",),
                         help="Crew: just what to do. Engineering: sensor health, hydrographs and history.")
    refresh = st.toggle("Auto-refresh every 10 s", value=params.get("refresh", "1") == "1", key="auto_refresh",
                        help="Re-reads the sensor data. Turn it off while you fill in a form.")
    st.caption(f"Live data · {data_store.now():%b %d, %H:%M:%S}")

page.run()

if refresh and page.title != "Add basin":       # never refresh in the middle of filling a form
    time.sleep(10)
    st.rerun()
