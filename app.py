"""
app.py: start the DrainShield dashboard
---------------------------------------
From the project folder:
    streamlit run app.py
Your browser opens the dashboard. Stop it with Ctrl+C in the terminal.

This file sets up the pages, the logo, the Crew / Engineering view switch and the
"replay time" control shared by all of them:
    network.py      -> map of every basin + dispatch list
    dashboard.py    -> one catch basin in detail
    basin_setup.py  -> add a catch basin from its as-built plan
"""

from datetime import timedelta

import pandas as pd
import streamlit as st

import data_store

st.set_page_config(page_title="DrainShield", page_icon="assets/drainshield_icon.png", layout="wide")
st.logo("assets/drainshield_logo.png", icon_image="assets/drainshield_icon.png", size="large")

page = st.navigation([
    st.Page("network.py", title="Network", icon=":material/map:", default=True),
    st.Page("dashboard.py", title="Basin", icon=":material/water_drop:"),
    st.Page("basin_setup.py", title="Add basin", icon=":material/add_circle:"),
])

# ---- shared state: which moment we look at, and which basin is selected ----
basins, readings, rain, events, truth = data_store.load_all()
t_min, t_max = rain["timestamp"].min(), rain["timestamp"].max()
params = st.query_params
if "now" not in st.session_state:
    start = pd.Timestamp(params.get("t", str(t_max)))
    st.session_state["now"] = min(max(start, t_min), t_max).to_pydatetime()
if "basin_id" not in st.session_state:
    wanted = params.get("basin", "DEMO-02")
    st.session_state["basin_id"] = wanted if wanted in set(basins["basin_id"]) else basins["basin_id"].iloc[0]

if "role" not in st.session_state:
    st.session_state["role"] = params.get("view", "Crew")

with st.sidebar:
    st.segmented_control("View", ["Crew", "Engineering"], key="role", width="stretch",
                         help="Crew: just what to do. Engineering: sensor health, hydrographs and history.")
    st.markdown("**Demo replay**")
    st.caption("All data is simulated. Move through time to see what we would have known.")
    st.slider("Time", min_value=t_min.to_pydatetime(), max_value=t_max.to_pydatetime(),
              step=timedelta(minutes=15), format="MMM D, HH:mm", key="now", label_visibility="collapsed")
    moments = {"Start": t_min + timedelta(hours=12),
               "Before storm": pd.Timestamp("2026-10-15 06:00"),
               "Storm (Oct 15)": pd.Timestamp("2026-10-15 14:30"),
               "Storm +1 h": pd.Timestamp("2026-10-15 16:00"),
               "End": t_max}
    cols = st.columns(2)
    for i, (label, moment) in enumerate(moments.items()):
        cols[i % 2].button(label, width="stretch", key=f"jump_{i}",
                           on_click=lambda m=moment: st.session_state.update(now=m.to_pydatetime()))

page.run()
