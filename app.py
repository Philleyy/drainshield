"""
app.py: start the DrainShield dashboard
---------------------------------------
From the project folder:
    python -m streamlit run app.py
Your browser opens the dashboard. Stop it with Ctrl+C in the terminal.

To feed it real readings from a sensor plugged into this computer, run
sensor_bridge.py (USB) or lora_bridge.py (LoRa receiver) in a SECOND terminal.

This file sets up the pages, the logo, the Crew / Engineering view switch, the
Live / Pitch demo switch and the auto-refresh, which are shared by every page:
    demo_page.py    -> (Pitch demo only) the demo day, hour by hour
    network.py      -> every catch basin of the city + the dispatch list
    dashboard.py    -> one monitored catch basin in detail
    sensor_live.py  -> raw readings from a sensor, and its reading interval
    basin_setup.py  -> attach a sensor to a catch basin (as-built geometry)
    route_page.py   -> the vacuum truck's route through the basins to clean

PITCH DEMO: one scripted 24-hour day (demo_scenario.py) replayed on every page. The sidebar clock moves
through the day (slider, play button, or "jump to" a moment of the story).
"""

import time

import streamlit as st

import data_store
import demo_scenario

st.set_page_config(page_title="DrainShield", page_icon="assets/drainshield_icon.png", layout="wide")
st.logo("assets/drainshield_logo.png", icon_image="assets/drainshield_icon.png", size="large")
params = st.query_params

# ---------------------------------------------------------------------------
# Live / Pitch demo switch (before anything is loaded: it decides which files are read)
# ---------------------------------------------------------------------------
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


keep("data_mode", data_store.DEMO_LABEL if params.get("demo") == "1" else "Live")
st.session_state.setdefault("demo_t", 0)
st.session_state.setdefault("playing", False)


def leave_or_enter_demo():
    remember("data_mode")
    st.session_state["playing"] = False
    st.session_state.pop("basin_id", None)
    st.session_state.pop("picked", None)
    st.session_state.pop("route_plan", None)


with st.sidebar:
    st.segmented_control("Data", ["Live", data_store.DEMO_LABEL], key="data_mode", width="stretch",
                         on_change=leave_or_enter_demo,
                         help="Live: your sensors. Pitch demo: one scripted 24-hour day at 4 Dorval pilot sites.")
demo = data_store.demo_on()
if demo and not demo_scenario.ready():
    with st.spinner("Building the 24-hour demo day..."):
        demo_scenario.build()
    st.cache_data.clear()

pages = [st.Page("demo_page.py", title="Demo day", icon=":material/play_circle:")] if demo else []
pages += [
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
keep("scripted", True)
keep("demo_speed", 15)


# ---------------------------------------------------------------------------
# Demo clock controls
# ---------------------------------------------------------------------------
def hhmm(minute):
    return "24:00" if minute >= 1440 else f"{minute // 60:02d}:{minute % 60:02d}"


def slider_moved():
    st.session_state["demo_t"] = st.session_state["demo_slider"]
    st.session_state["playing"] = False


def chapter_picked():
    pick = st.session_state.get("demo_chapter")
    if pick is not None:
        st.session_state["demo_t"] = pick
        st.session_state["playing"] = False
    st.session_state["demo_chapter"] = None


def scripted_changed():
    remember("scripted")
    demo_scenario.reset_log(scripted=st.session_state["scripted"])
    st.cache_data.clear()


def reset_demo():
    demo_scenario.reset_log(scripted=st.session_state["scripted"])
    st.session_state.update(demo_t=0, playing=False)
    st.session_state.pop("route_plan", None)
    st.cache_data.clear()


with st.sidebar:
    st.segmented_control("View", ["Crew", "Engineering"], key="role", width="stretch", on_change=remember, args=("role",),
                         help="Crew: just what to do. Engineering: sensor health, hydrographs and history.")
    if demo:
        st.markdown(f"**Demo clock · {demo_scenario.DAY:%a %b %d}**")
        st.session_state["demo_slider"] = st.session_state["demo_t"]
        st.select_slider("Time of day", options=list(range(0, 1441, 5)), key="demo_slider",
                         format_func=hhmm, on_change=slider_moved, label_visibility="collapsed")
        c1, c2 = st.columns([1, 1])
        if c1.button("⏸ Pause" if st.session_state["playing"] else "▶ Play", width="stretch", type="primary"):
            st.session_state["playing"] = not st.session_state["playing"]
            if st.session_state["demo_t"] >= 1440:
                st.session_state["demo_t"] = 0
            st.rerun()
        c2.selectbox("Speed", [5, 15, 30, 60], key="demo_speed", label_visibility="collapsed",
                     on_change=remember, args=("demo_speed",),
                     format_func=lambda m: f"{m} min / step")
        chapters = {int((demo_scenario.at(hm) - demo_scenario.DAY).total_seconds() // 60): f"{hm} · {title}"
                    for hm, title, *_ in demo_scenario.EVENTS}
        st.selectbox("Jump to", list(chapters), index=None, key="demo_chapter", on_change=chapter_picked,
                     placeholder="Jump to a moment...", format_func=chapters.get, label_visibility="collapsed")
        st.toggle("Scripted crew actions", key="scripted", on_change=scripted_changed,
                  help="On: the crews act as in the story (dispatch, cleaning...). Off: only what you click "
                       "(Send route, Log maintenance) happens.")
        st.button("↺ Reset demo", on_click=reset_demo, width="stretch",
                  help="Back to 00:00 and forget what was clicked during the demo.")
        refresh = False
    else:
        refresh = st.toggle("Auto-refresh every 10 s", value=params.get("refresh", "1") == "1", key="auto_refresh",
                            help="Re-reads the sensor data. Turn it off while you fill in a form.")
        st.caption(f"Live data · {data_store.now():%b %d, %H:%M:%S}")

# ---------------------------------------------------------------------------
# Narration banner (demo): what is happening at this minute of the story
# ---------------------------------------------------------------------------
if demo:
    t = data_store.now()
    ev = demo_scenario.event_now(t)
    st.html(f"""<div style="border-left:5px solid #2a78d6;background:#e5effb;border-radius:8px;padding:10px 14px;
        margin-bottom:6px;color:#14365e"><div style="font-size:0.8rem;letter-spacing:.04em;text-transform:uppercase">
        ▶ Pitch demo · {t:%a %b %d} · <b style="font-size:1.05rem">{hhmm(data_store.demo_minute())}</b></div>
        <div style="font-weight:600;margin-top:2px">{ev['time']:%H:%M} · {ev['title']}</div>
        <div style="font-size:0.92rem">{ev['text']}</div></div>""" if ev else "")

page.run()

if demo and st.session_state["playing"]:
    time.sleep(0.4)
    st.session_state["demo_t"] = min(1440, st.session_state["demo_t"] + st.session_state.get("demo_speed", 15))
    if st.session_state["demo_t"] >= 1440:
        st.session_state["playing"] = False
    st.rerun()
elif refresh and page.title != "Add basin":       # never refresh in the middle of filling a form
    time.sleep(10)
    st.rerun()
