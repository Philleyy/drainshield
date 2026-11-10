"""
network.py: the overview (home screen)
--------------------------------------
* Weather readiness banner: rain expected in the next 12 h, and which basins must be
  cleaned BEFORE it starts.
* Four filter counters: 🔴 Urgent · 🟠 Inspect · 🟢 Normal · ⚪ Offline (sensor problem).
* Map of the monitored basins, plus the municipality's unmonitored catch basins (grey dots,
  from the Ville de Montréal open data). Click a pin or search a basin to see its card.
* Dispatch list, most urgent first. Click a row to open the basin.
"""

import math

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import data_store
import ui
import weather

ui.inject_css()
basins, readings, rain, events, truth = data_store.load_all()
now = pd.Timestamp(st.session_state["now"])
df = data_store.network_status(data_store.data_key(), data_store.log_key(), now)
forecast = weather.simulated_forecast(rain, now)
cats = data_store.CATEGORIES
eng = data_store.engineering()

muni = data_store.municipal_basins()
attached = set(basins["municipal_id"].dropna().astype(str)) if "municipal_id" in basins else set()
muni = muni[~muni["municipal_id"].isin(attached)]

with st.sidebar:
    st.divider()
    groups = st.multiselect("Basins to show", list(data_store.NETWORK_NAMES.values()),
                            default=[n for n in data_store.NETWORK_NAMES.values() if n in set(df["network"])])
    st.markdown("**Map layers**")
    street_map = st.toggle("Street map", value=True, help="Needs internet. Turn off if the map stays blank.")
    show_muni = st.toggle(f"Unmonitored municipal basins ({len(muni)})", value=True,
                          help="Ville de Montréal open data (Puisards d'égout). Click one to attach a sensor.")
    radar = st.toggle("Live ECCC weather radar", value=False,
                      help="Environment Canada 1 km radar, real weather right now (not the demo replay time).")
df = df[df["network"].isin(groups)]

st.title("Network overview")
st.caption(f"What every sensor tells us on **{now:%b %d, %Y at %H:%M}** (simulated sensor data).")

# ---------------------------------------------------------------------------
# WEATHER READINESS BANNER
# ---------------------------------------------------------------------------
before_storm = df[df["priority"] == "Inspect before storm"]
flooding = df[df["priority"] == "Flooding / backing up now"]
inspect = df[df["category"] == "Inspect"]
if not flooding.empty:
    key, call = "urgent", f"{len(flooding)} catch basin(s) backing up right now: dispatch crews."
elif not before_storm.empty:
    key, call = "urgent", (f"⚠️ {len(before_storm)} catch basin(s) with slow drainage need cleaning "
                           f"before the rain starts: {', '.join(before_storm['basin_id'])}.")
elif weather.is_heavy(forecast):
    key, call = "rising", "Heavy rain coming, and no basin is flagged for slow drainage."
elif not inspect.empty:
    key, call = "clean_soon", f"{len(inspect)} catch basin(s) to add to the next vacuum route (no heavy rain expected)."
else:
    key, call = "ok", "Network ready: no action needed."
st.html(ui.card(key, "🌧" if forecast["total_mm"] >= 0.5 else "☀", "Weather readiness",
                weather.describe(forecast), [(key, call)]))
with st.expander("Real forecast right now (Environment Canada GEM, via Open-Meteo)"):
    live = weather.live_forecast(round(basins["latitude"].mean(), 3), round(basins["longitude"].mean(), 3))
    st.write(weather.describe(live) if live else "Unavailable (no internet connection?).")
    st.caption("The demo banner above uses the simulated rain as its forecast. When real sensors are connected, "
               "this live forecast replaces it.")

# ---------------------------------------------------------------------------
# SENSOR HEALTH (engineering view)
# ---------------------------------------------------------------------------
if eng:
    low = df[(df["battery_pct"].notna()) & (df["battery_pct"] < 15) & df["online"]]
    c = st.columns(4)
    c[0].html(ui.tile("Sensors online", f"{int(df['online'].sum())}", f"of {len(df)}", "ok"))
    c[1].html(ui.tile("Offline", f"{int((~df['online']).sum())}", "no reading for 1 h+", "no_data"))
    c[2].html(ui.tile("Low battery (<15%)", f"{len(low)}", ", ".join(low["basin_id"]) or "none", "watch"))
    c[3].html(ui.tile("Data irregularities", "0", "not detected (rule not built yet)", "neutral"))

# ---------------------------------------------------------------------------
# FILTER COUNTERS
# ---------------------------------------------------------------------------
labels = {c: f"{s['emoji']} {int((df['category'] == c).sum())} {c}" for c, s in cats.items()}
chosen = st.pills("Filter", list(cats), selection_mode="multi", default=list(cats),
                  format_func=lambda c: labels[c], label_visibility="collapsed", key="filter")
shown = df[df["category"].isin(chosen or list(cats))].copy()

# ---------------------------------------------------------------------------
# SEARCH + MAP + SELECTED BASIN CARD
# ---------------------------------------------------------------------------
def pick_from_map():
    pts = st.session_state["map"].selection.points
    if pts:
        cd = pts[0]["customdata"]
        st.session_state["picked"] = (cd[1], cd[0])


def pick_from_search():
    if st.session_state.get("search"):
        st.session_state["picked"] = ("basin", st.session_state["search"])


addresses = dict(zip(df["basin_id"], df["address"]))
st.selectbox("Find a basin", list(df["basin_id"]), index=None, key="search", on_change=pick_from_search,
             placeholder="🔍 Search by basin ID or street...", label_visibility="collapsed",
             format_func=lambda b: f"{b} · {addresses.get(b, '')}")

map_col, card_col = st.columns([1.75, 1], gap="medium")
picked = st.session_state.get("picked")
with map_col:
    shown["size"] = shown["category"].map(lambda c: cats[c]["size"])
    shown["kind"] = "basin"
    pts = df            # fit the view on the monitored basins (the grey ones are all over the city)
    center = {"lat": (pts["latitude"].min() + pts["latitude"].max()) / 2,
              "lon": (pts["longitude"].min() + pts["longitude"].max()) / 2}
    span = max(pts["longitude"].max() - pts["longitude"].min(),
               (pts["latitude"].max() - pts["latitude"].min()) * 1.6, 0.002)
    zoom = min(16.0, math.log2(360 * 2.2 / span) - 0.3)        # fit every basin on screen
    if picked:
        src = df[df["basin_id"] == picked[1]] if picked[0] == "basin" else muni[muni["municipal_id"] == picked[1]]
        if not src.empty:
            center, zoom = {"lat": src["latitude"].iloc[0], "lon": src["longitude"].iloc[0]}, 16.5
    fig = px.scatter_map(
        shown, lat="latitude", lon="longitude", color="category", size="size", size_max=22,
        color_discrete_map={c: s["color"] for c, s in cats.items()},
        category_orders={"category": list(cats)[::-1]},
        hover_name="basin_id", custom_data=["basin_id", "kind"],
        hover_data={"address": True, "priority": True, "water": True, "size": False, "kind": False,
                    "latitude": False, "longitude": False, "category": False},
        labels={"address": "Address", "priority": "Status", "water": "Water below street"},
        zoom=zoom, center=center, map_style="carto-positron" if street_map else "white-bg", height=540)
    if show_muni and not muni.empty:
        fig.add_trace(go.Scattermap(
            lat=muni["latitude"], lon=muni["longitude"], mode="markers", name="Unmonitored",
            marker=dict(size=6, color="#a9a8a2", opacity=0.75),
            customdata=list(zip(muni["municipal_id"], ["muni"] * len(muni))),
            text=muni["address"], hovertemplate="Unmonitored catch basin %{customdata[0]}<br>%{text}<extra></extra>"))
        fig.data = (fig.data[-1],) + fig.data[:-1]          # grey dots underneath
    if picked:
        src = shown[shown["basin_id"] == picked[1]] if picked[0] == "basin" else muni[muni["municipal_id"] == picked[1]]
        if not src.empty:
            fig.add_trace(go.Scattermap(lat=src["latitude"], lon=src["longitude"], mode="markers", hoverinfo="skip",
                                        marker=dict(size=34, color="#0b2d5b", opacity=0.25), showlegend=False))
    layers = [{"sourcetype": "raster", "source": [weather.RADAR_TILES], "opacity": 0.55, "below": "traces"}] if radar else []
    fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), showlegend=False, map_layers=layers)
    st.plotly_chart(fig, width="stretch", on_select=pick_from_map, selection_mode="points", key="map")

with card_col:
    if not picked:
        st.markdown("**Click a pin, or search a basin.**")
        st.caption("Grey dots are the municipality's catch basins without a sensor yet.")
        top = df[df["category"].isin(["Urgent", "Inspect"])].head(6)
        if not top.empty:
            st.markdown("**Needs attention**")
            st.html('<table class="fs-table">' + "".join(
                f'<tr><td>{cats[r["category"]]["emoji"]} <b>{r["basin_id"]}</b><br>'
                f'<span class="fs-muted">{r["address"]}</span></td><td>{r["priority"]}</td></tr>'
                for _, r in top.iterrows()) + "</table>")
    elif picked[0] == "basin" and picked[1] in set(df["basin_id"]):
        r = df[df["basin_id"] == picked[1]].iloc[0]
        ck = {"Urgent": "urgent", "Inspect": "clean_soon", "Normal": "ok", "Offline": "no_data"}[r["category"]]
        st.html(ui.dispatch_card(ck, {"Urgent": "!", "Inspect": "!", "Normal": "✔", "Offline": "?"}[r["category"]],
                                 r["address"] or "Monitored basin",
                                 f"{r['basin_id']} · {r['priority']}",
                                 [("Water", f"{r['water']} below street {r['trend']}"),
                                  ("Drainage", r["drainage"]), ("Action", r["action"]),
                                  ("Issue", r["issue"] or "—"), ("Updated", r["updated"])]))
        if st.button("View basin details →", type="primary", width="stretch"):
            data_store.select_basin(r["basin_id"])
            st.switch_page("dashboard.py")
    else:
        m = muni[muni["municipal_id"] == picked[1]]
        if not m.empty:
            m = m.iloc[0]
            st.html(ui.dispatch_card("no_data", "+", "Unmonitored municipal catch basin", f"#{m['municipal_id']}",
                                     [("Address", m["address"]), ("Type", m.get("basin_type", "")),
                                      ("Installed", m.get("install_date") if isinstance(m.get("install_date"), str)
                                       and m.get("install_date") else "unknown"),
                                      ("Owner", m.get("owner", ""))]))
            if st.button("+ Attach a DrainShield sensor to this basin", type="primary", width="stretch"):
                st.session_state["prefill"] = {"municipal_id": m["municipal_id"], "address": m["address"],
                                               "latitude": float(m["latitude"]), "longitude": float(m["longitude"])}
                st.switch_page("basin_setup.py")
    if picked and st.button("Clear selection", width="stretch"):
        st.session_state.pop("picked", None)
        st.rerun()

# ---------------------------------------------------------------------------
# DISPATCH LIST
# ---------------------------------------------------------------------------
st.subheader("Dispatch list")
st.caption("Most urgent first. Click a row to open the basin.")
cols = {"basin_id": "Basin", "address": "Address", "status": "Priority", "water": "Water below street",
        "trend": "Trend", "recovery": "Recovery time", "action": "Recommended action", "issue": "Issue",
        "updated": "Updated"}
if eng:
    cols.update({"battery_pct": "Battery %", "network": "Group"})
table = shown.assign(status=shown["category"].map(lambda c: cats[c]["emoji"]) + " " + shown["priority"])
table = table[list(cols)].rename(columns=cols)
picked_row = st.dataframe(table, hide_index=True, width="stretch", on_select="rerun",
                          selection_mode="single-row", key="dispatch")
if picked_row.selection.rows:
    data_store.select_basin(table.iloc[picked_row.selection.rows[0]]["Basin"])
    st.switch_page("dashboard.py")
