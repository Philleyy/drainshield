"""
demo_page.py: the pitch demo day, hour by hour (Pitch demo mode only)
--------------------------------------------------------------------
One picture of the whole day up to the demo clock:
  1. rain: what fell (solid) and what Environment Canada was forecasting at that minute (outlined)
  2. water level in the four basins of the story
  3. every reading every sensor sent, coloured by its mode (DRY every 30 min, WATCH 5 min, STORM 60 s):
     the gaps are the frost, the dead connector and the radio outage; ◆ = delivered late from the sensor's flash
Then the story so far, with a button to open the page that shows each moment.
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import data_store
import demo_scenario as dsc
import ui

ui.inject_css()
basins, readings, rain, events, _ = data_store.load_all()
now = data_store.now()
key = data_store.data_key()
day0, day1 = dsc.DAY, dsc.DAY + pd.Timedelta(days=1)

st.title("The demo day")
st.caption(f"{dsc.DAY:%A %B %d} at 4 Dorval pilot sites, 12 sensors (site 4 = the 3 sensors on the table). "
           "Move the clock in the sidebar, press ▶ Play, or jump to a moment of the story.")

# ---------------------------------------------------------------------------
# Headline numbers
# ---------------------------------------------------------------------------
today = readings[readings["timestamp"] >= day0]
minutes = max((now - day0).total_seconds() / 60, 1)
every_minute = len(basins) * minutes
late = today[(today["received"] - today["timestamp"]) > pd.Timedelta(minutes=10)] if "received" in today else today.iloc[0:0]
log = data_store._log(data_store.log_key())
crew = log[(log["time"] >= day0) & (log["time"] <= now)] if not log.empty else log
c = st.columns(4)
c[0].html(ui.tile("Readings today", f"{len(today):,}",
                  f"{100 * (1 - len(today) / every_minute):.0f}% fewer than reading every minute", "neutral"))
c[1].html(ui.tile("Delivered late", f"{len(late)}", "stored in the sensor's flash during an outage, 0 lost", "neutral"))
c[2].html(ui.tile("Crew actions logged", f"{len(crew)}", "dispatched, cleaned, inspected", "neutral"))
mode_now = readings.sort_values("timestamp").groupby("basin_id")["mode"].last() if "mode" in readings else pd.Series()
c[3].html(ui.tile("Sensors in STORM mode", f"{int((mode_now == 'STORM').sum())}", f"of {len(basins)} now", "neutral"))

# ---------------------------------------------------------------------------
# The day in one figure
# ---------------------------------------------------------------------------
MODE_COLOR = {"DRY": "#86b6ef", "WATCH": "#2a78d6", "STORM": "#104281"}    # one hue, light -> dark
LINE_COLOR = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
STORY = [("S4-A", "S4-A (clogged, cleaned 12:45)"), ("S7-A", "S7-A (slowing, cleaned 13:40)"),
         ("S7-N1", "S7-N1 (sewer backs up 20:10)"), ("S4-N2", "S4-N2 (normal control)")]

fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.06, row_heights=[0.22, 0.33, 0.45],
                    subplot_titles=("Rain (mm in each hour)", "Water above the outlet (cm)",
                                    "Every reading received, by mode"))
hourly = rain[(rain["timestamp"] >= day0) & (rain["timestamp"] < day1)]
past = hourly[hourly["timestamp"] + pd.Timedelta(hours=1) <= now.ceil("h")]
future = hourly[hourly["timestamp"] + pd.Timedelta(hours=1) > now.ceil("h")]
fig.add_trace(go.Bar(x=past["timestamp"] + pd.Timedelta(minutes=30), y=past["rain_mm"], name="Rain measured",
                     marker=dict(color="#55534e", cornerradius=3), width=3.2e6,
                     hovertemplate="%{x|%H:00}: %{y:.1f} mm<extra>measured</extra>"), row=1, col=1)
fig.add_trace(go.Bar(x=future["timestamp"] + pd.Timedelta(minutes=30), y=future["rain_mm"],
                     name="Rain forecast (as of now)", width=3.2e6,
                     marker=dict(color="rgba(0,0,0,0)", line=dict(color="#55534e", width=1.5), cornerradius=3),
                     hovertemplate="%{x|%H:00}: %{y:.1f} mm<extra>forecast</extra>"), row=1, col=1)

for (bid, label), color in zip(STORY, LINE_COLOR):
    if bid not in set(basins["basin_id"]):
        continue
    lv = data_store.levels_for(key, bid)
    lv = lv[(lv["timestamp"] >= day0) & (lv["timestamp"] <= now)]
    fig.add_trace(go.Scatter(x=lv["timestamp"], y=lv["level_cm"], mode="lines", name=label,
                             line=dict(color=color, width=2), connectgaps=False,
                             hovertemplate="%{x|%H:%M}: %{y:.0f} cm<extra>" + bid + "</extra>"), row=2, col=1)
b0 = basins.iloc[0]
top = b0["sensor_height_cm"] - b0["sensor_blind_zone_cm"] - b0["outlet_invert_cm"]
fig.add_hline(y=40, line=dict(color="#a9a8a2", dash="dot", width=1), row=2, col=1,
              annotation_text="backing up (40 cm)", annotation_position="top left")
fig.add_hline(y=top, line=dict(color="#a9a8a2", dash="dot", width=1), row=2, col=1,
              annotation_text="top of the sensor range (0.43 m below street)", annotation_position="top left")

order = [b for b in basins["basin_id"]][::-1]
for mode, color in MODE_COLOR.items():
    m = today[(today["mode"] == mode) & (today["distance_cm"].notna())] if "mode" in today else today.iloc[0:0]
    fig.add_trace(go.Scatter(x=m["timestamp"], y=m["basin_id"], mode="markers", name=f"{mode} reading",
                             marker=dict(color=color, size=8, symbol="line-ns", line=dict(width=2, color=color)),
                             hovertemplate="%{y} %{x|%H:%M}<extra>" + mode + "</extra>"), row=3, col=1)
iced = today[today["distance_cm"].isna()]
fig.add_trace(go.Scatter(x=iced["timestamp"], y=iced["basin_id"], mode="markers", name="No echo (iced)",
                         marker=dict(color="#8a8984", size=8, symbol="x-thin", line=dict(width=2, color="#8a8984")),
                         hovertemplate="%{y} %{x|%H:%M}<extra>no echo</extra>"), row=3, col=1)
if not late.empty:
    fig.add_trace(go.Scatter(x=late["timestamp"], y=late["basin_id"], mode="markers", name="Delivered late",
                             marker=dict(color="#eb6834", size=9, symbol="diamond-open", line=dict(width=1.5)),
                             customdata=late["received"].dt.strftime("%H:%M"),
                             hovertemplate="%{y} read %{x|%H:%M}, arrived %{customdata}<extra>late</extra>"),
                  row=3, col=1)

for e in dsc.events():
    if e["time"] <= now:
        fig.add_vline(x=e["time"], line=dict(color="#d9d7d0", width=1), row="all", col=1)
fig.add_vline(x=now, line=dict(color="#d03b3b", width=2), row="all", col=1)
fig.update_xaxes(range=[day0, day1], dtick=3 * 3600 * 1000, tickformat="%H:%M", showgrid=False)
fig.update_yaxes(gridcolor="#efefec", zeroline=False)
fig.update_yaxes(categoryorder="array", categoryarray=order, row=3, col=1, showgrid=False)
fig.update_layout(height=720, margin=dict(l=10, r=10, t=40, b=10), barmode="overlay", hovermode="closest",
                  legend=dict(orientation="h", y=-0.08), plot_bgcolor="white")
st.plotly_chart(fig, width="stretch")
st.caption("Red line = the demo clock. Thin grey lines = moments of the story. Gaps in the bottom panel: frost "
           "(✕, no echo), the loose connector at S9-A, and S4-N1's radio outage, whose readings arrive at 14:40 (◆).")

# ---------------------------------------------------------------------------
# The story so far
# ---------------------------------------------------------------------------
st.subheader("What happened, and what DrainShield did")
past_events = [e for e in dsc.events() if e["time"] <= now][::-1]
if not past_events:
    st.info("Press ▶ Play in the sidebar to start the day.")
for i, e in enumerate(past_events[:8]):
    c1, c2 = st.columns([5, 1])
    c1.markdown(f"**{e['time']:%H:%M} · {e['title']}**  \n{e['text']}")
    where = e["where"]
    if where != "demo" and c2.button("Show →", key=f"ev{i}", width="stretch"):
        if where.startswith("basin:"):
            data_store.select_basin(where.split(":", 1)[1])
            st.switch_page("dashboard.py")
        st.switch_page({"network": "network.py", "route": "route_page.py"}[where])
if len(past_events) > 8:
    with st.expander(f"Earlier ({len(past_events) - 8})"):
        for e in past_events[8:]:
            st.markdown(f"**{e['time']:%H:%M} · {e['title']}**  \n{e['text']}")
