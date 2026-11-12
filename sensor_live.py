"""
sensor_live.py: the raw readings of a sensor, and its reading interval
---------------------------------------------------------------------
Use this page to test a sensor on the bench: is it talking, does the distance match
the tape measure, how often does it read? It works for any sensor ID that the
bridge records, even if no catch basin has been set up for it yet.
"""

from datetime import timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import data_store
import processing as proc
import ui

ui.inject_css()
basins, readings, *_ = data_store.load_all()
now = data_store.now()
status = data_store.sensor_status()

st.title("Live sensor")
ids = sorted(set(readings["basin_id"].dropna()) | set(basins["basin_id"]) | set(status))

with st.expander("How to connect a sensor to this dashboard", expanded=not ids):
    st.markdown("""
1. Upload **`arduino/drainshield_sensor/drainshield_sensor.ino`** to the Arduino with the Arduino IDE
   (your first test sketch also works). Then **close the IDE's Serial Monitor**: only one program can use the port.
2. Plug the Arduino into this computer with USB.
3. Open a **second terminal** in VS Code (the **+** in the terminal panel) and run:
   ```
   python -m pip install pyserial
   python sensor_bridge.py
   ```
   It lists the ports, e.g. `COM3`. Then start recording (pick any ID for a bench test):
   ```
   python sensor_bridge.py COM3 --basin TEST-01
   ```
4. Readings appear below within a few seconds. Leave both terminals running.

To watch on a phone or a teammate's laptop **on the same Wi-Fi**, open the *Network URL*
that Streamlit printed when it started (e.g. `http://192.168.1.23:8501`).
""")

if not ids:
    st.info("No sensor has sent anything yet.")
    st.stop()

default = st.session_state.get("live_sensor", ids[0])
sensor = st.selectbox("Sensor / basin ID", ids, index=ids.index(default) if default in ids else 0,
                      key="live_sensor_select",
                      on_change=lambda: st.session_state.update(live_sensor=st.session_state["live_sensor_select"]))
r = readings[readings["basin_id"] == sensor].sort_values("timestamp")
info = status.get(sensor, {})

# ---------------------------------------------------------------------------
# Latest reading
# ---------------------------------------------------------------------------
c1, c2, c3, c4 = st.columns(4)
if r.empty:
    c1.html(ui.tile("Latest distance", "—", "nothing recorded yet", "no_data"))
else:
    last = r.iloc[-1]
    age_s = (now - last["timestamp"]).total_seconds()
    key = "ok" if age_s < 3 * data_store.interval_for(sensor) + 10 else "urgent"
    value = "no echo" if pd.isna(last["distance_cm"]) else f"{last['distance_cm']:.1f} cm"
    c1.html(ui.tile("Latest distance", value, f"{data_store.ago(age_s / 60)} · {last['timestamp']:%H:%M:%S}", key))
    recent = r[r["timestamp"] >= now - timedelta(minutes=10)]
    rate = len(recent) / 10
    c2.html(ui.tile("Readings, last 10 min", f"{len(recent)}", f"{rate:.1f} per minute", "neutral"))
    valid = recent["distance_cm"].dropna()
    spread = f"± {valid.std():.1f} cm" if len(valid) > 2 else "—"
    c3.html(ui.tile("Noise (last 10 min)", spread, "standard deviation; < 1 cm is good for a still target",
                    "neutral"))
fw = info.get("firmware", "unknown")
dev = info.get("device_interval_ms")
c4.html(ui.tile("Firmware", fw, f"device confirms {dev / 1000:g} s interval" if dev else
                "interval not confirmed by the device", "neutral"))

# ---------------------------------------------------------------------------
# Reading interval (sent to the Arduino by sensor_bridge.py)
# ---------------------------------------------------------------------------
st.subheader("Data collection frequency")
options = {1: "Every 1 s (bench test)", 5: "Every 5 s", 10: "Every 10 s", 30: "Every 30 s", 60: "Every minute",
           300: "Every 5 min", 900: "Every 15 min (field, saves battery)"}
current = data_store.interval_for(sensor)
if current not in options:
    options[current] = f"Every {current} s"
choice = st.segmented_control("Interval", list(options), default=current, format_func=lambda s: options[s],
                              key=f"interval_{sensor}", label_visibility="collapsed")
if choice and choice != current:
    data_store.set_interval(sensor, choice)
    st.toast(f"Interval for {sensor} set to {options[choice].lower()}. The bridge applies it within ~2 s.")
st.caption("This is the **dry-weather** interval. When the water starts moving (more than 0.3 cm/min), the "
           "DrainShield sketch switches by itself to **every 30 s** (or this interval, if shorter) until it has been "
           "still for 30 min. The bridge sends your choice to the Arduino (command `I,<ms>`) and the sketch confirms "
           "it; with the first test sketch the bridge keeps one reading per interval instead. In the field, a "
           "cellular sensor would receive the new interval at its next transmission.")

# ---------------------------------------------------------------------------
# Chart
# ---------------------------------------------------------------------------
st.subheader("Raw distance")
span = st.segmented_control("Window", ["10 min", "1 h", "24 h", "All"], default="10 min", key="live_span")
t0 = {"10 min": now - timedelta(minutes=10), "1 h": now - timedelta(hours=1),
      "24 h": now - timedelta(days=1), "All": r["timestamp"].min() if not r.empty else now}[span or "10 min"]
w = r[r["timestamp"] >= t0]
fig = go.Figure()
fig.add_scatter(x=w["timestamp"], y=w["distance_cm"], mode="lines+markers", line=dict(color="#2a78d6", width=2),
                marker=dict(size=5), hovertemplate="%{x|%H:%M:%S}<br>%{y:.1f} cm<extra></extra>", name="distance")
missing = w[w["distance_cm"].isna()]
if not missing.empty:
    fig.add_scatter(x=missing["timestamp"], y=[0] * len(missing), mode="markers", name="no echo",
                    marker=dict(color="#d03b3b", size=8, symbol="x"), hovertemplate="%{x|%H:%M:%S} no echo<extra></extra>")
fig.update_yaxes(title_text="distance from the sensor (cm)", autorange="reversed", gridcolor="#eeede9")
fig.update_xaxes(gridcolor="#eeede9")
fig.update_layout(height=380, margin=dict(l=55, r=10, t=10, b=30), plot_bgcolor="#ffffff",
                  paper_bgcolor="rgba(0,0,0,0)", showlegend=False)
st.plotly_chart(fig, width="stretch", theme=None)
st.caption("Axis reversed: the line goes UP when the target gets closer to the sensor (like water rising).")

# If this sensor belongs to a configured basin, show what it means
if sensor in set(basins["basin_id"]) and not r.dropna(subset=["distance_cm"]).empty:
    b = data_store.basin_row(basins, sensor)
    d = r.dropna(subset=["distance_cm"]).iloc[-1]["distance_cm"]
    level = b["sensor_height_cm"] - d - b["outlet_invert_cm"]
    cal = (f"calibrated from {b['cal_hours']:.0f} h of resting water" if b.get("cal_status") == "learned"
           else f"still calibrating: {b.get('cal_note', '')}")
    st.info(f"Configured as a catch basin: water **{proc.depth_below_street_m(b, level):.2f} m below the street** "
            f"({proc.format_level(level)} vs. its normal resting level) · {cal}.")
    st.page_link("dashboard.py", label=f"Open {sensor} in the Basin page →")
elif sensor not in set(basins["basin_id"]):
    st.caption(f"{sensor} isn't attached to a catch basin yet: use **Add basin** with the same ID when it goes "
               "into a real basin.")

with st.expander("Download the readings"):
    st.download_button("Download CSV", r.to_csv(index=False), file_name=f"{sensor}_readings.csv", mime="text/csv")
