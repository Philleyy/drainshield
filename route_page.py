"""
route_page.py: "Generate vacuum truck route"
--------------------------------------------
Picks the basins a vacuum crew should visit (🔴 Urgent first, then 🟠 Inspect), including the ones
predicted to back up in the next 24 h of forecast rain (predictive.py), and orders them into one
route from the public works yard (route_optimizer.py: OSRM road times, nearest neighbour + 2-opt).
Shows the route on the map, the time it takes, a printable crew sheet and Google Maps links.
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import data_store
import maintenance
import predictive
import route_optimizer as ro
import ui

ui.inject_css()
basins, readings, rain, events, _ = data_store.load_all()
now = data_store.now()
cats = data_store.CATEGORIES

st.title("Vacuum truck route")
st.caption("Basins to clean, in the order that takes the least time from the public works yard. "
           "🔴 Urgent ones first (they would back up in the coming rain), then 🟠 Inspect.")

# ---------------------------------------------------------------------------
# Which basins
# ---------------------------------------------------------------------------
SENSORS, DEMO = "Basins flagged by DrainShield sensors", "Demo: the 10 proposed pilot sites (no sensor data)"
source = st.radio("Basins to visit", [SENSORS, DEMO], horizontal=True,
                  help="The demo set shows the routing on real Dorval basins before sensors are installed.")


def sensor_stops():
    df = data_store.network_status(data_store.data_key(), data_store.log_key(), now)
    rows = []
    for _, r in df.iterrows():
        b = data_store.basin_row(basins, r["basin_id"])
        S = data_store.status_for(data_store.data_key(), r["basin_id"], now)
        last = maintenance.last_reset(data_store.entries_for(r["basin_id"], now))
        p = predictive.overflow_risk(b, S, rain, now, reset=last[0] if last else None)
        cat, reason = r["category"], r["action"]
        if cat in ("Normal",) and p["flag"]:                         # predicted, not yet flagged
            cat, reason = p["flag"], p["sentence"]
        elif cat == "Inspect" and p["flag"] == "Urgent":
            cat, reason = "Urgent", p["sentence"]
        if cat == "Offline":
            reason = r["action"]
        if cat in ("Urgent", "Inspect", "Offline"):
            rows.append({"basin_id": r["basin_id"], "address": r["address"], "latitude": r["latitude"],
                         "longitude": r["longitude"], "category": cat,
                         "priority": r["priority"] if cat == r["category"] else "Predicted to back up",
                         "reason": reason})
    return pd.DataFrame(rows, columns=["basin_id", "address", "latitude", "longitude", "category", "priority",
                                       "reason"])


def demo_stops():
    reg = data_store.municipal_basins()
    if "pilot_role" not in reg:
        return pd.DataFrame()
    a = reg[reg["pilot_role"] == "anchor"].sort_values("score", ascending=False).copy()
    a["basin_id"] = "#" + a["municipal_id"].astype(str)
    a["category"] = ["Urgent" if i < 3 else "Inspect" for i in range(len(a))]
    a["priority"] = a["category"].map({"Urgent": "Demo: shown as urgent", "Inspect": "Demo: shown as inspect"})
    a["reason"] = "Pilot anchor, tier " + a["tier"].astype(str)
    return a[["basin_id", "address", "latitude", "longitude", "category", "priority", "reason"]]


stops = sensor_stops() if source == SENSORS else demo_stops()
if source == DEMO:
    st.info("Demo set: the 10 pilot anchors from the prioritization. The 3 highest-scored are *shown* as urgent "
            "only to demonstrate urgent-first ordering: no sensor has measured them.")

with st.expander("Route settings", expanded=False):
    c1, c2, c3 = st.columns(3)
    depot_lat = c1.number_input("Yard latitude", value=ro.DORVAL_DEPOT["latitude"], format="%.5f")
    depot_lon = c2.number_input("Yard longitude", value=ro.DORVAL_DEPOT["longitude"], format="%.5f")
    leave = (now + pd.Timedelta(minutes=10)).ceil("15min")          # the next quarter hour, on the (demo) clock
    start = c3.time_input("Crew leaves the yard at", value=leave.time())
    c4, c5, c6 = st.columns(3)
    svc_u = c4.number_input("Minutes per 🔴 basin", 5, 60, ro.SERVICE_MIN["Urgent"])
    svc_i = c5.number_input("Minutes per 🟠 basin", 5, 60, ro.SERVICE_MIN["Inspect"])
    urgent_first = c6.toggle("🔴 Urgent first", value=True,
                             help="Off: shortest route overall, mixing urgent and inspect basins.")
    st.caption(f"Default yard: {ro.DORVAL_DEPOT['name']} (approximate position, confirm the gate with the city).")

if stops.empty:
    st.success("No basin needs a crew right now: no route to generate.")
    st.stop()

wanted = st.multiselect("Include", ["Urgent", "Inspect", "Offline"], default=["Urgent", "Inspect", "Offline"],
                        format_func=lambda c: f"{cats[c]['emoji']} {c}" + (" sensors (check on the way)"
                                                                            if c == "Offline" else ""))
stops = stops[stops["category"].isin(wanted)]
st.caption(f"{len(stops)} basin(s): " + ", ".join(f"{cats[c]['emoji']} {(stops['category'] == c).sum()} {c}"
                                                  for c in ["Urgent", "Inspect", "Offline"]))

if st.button("Generate vacuum truck route", type="primary", disabled=stops.empty):
    depot = {"name": "Yard", "latitude": depot_lat, "longitude": depot_lon}
    with st.spinner("Asking the road network for travel times..."):
        st.session_state["route_plan"] = ro.plan_route(
            stops, depot=depot, start_time=pd.Timestamp.combine(now.date(), start), priority_first=urgent_first,
            service_min={"Urgent": svc_u, "Inspect": svc_i, "Offline": 10})
        st.session_state["route_depot"] = depot

plan = st.session_state.get("route_plan")
if plan is None:
    st.stop()
depot = st.session_state["route_depot"]

# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------
if plan.note:
    st.warning(plan.note)
c = st.columns(4)
c[0].html(ui.tile("Basins", f"{len(plan.stops)}", f"{(plan.stops['category'] == 'Urgent').sum()} urgent", "neutral"))
c[1].html(ui.tile("Driving", f"{plan.drive_s / 60:.0f} min", f"{plan.drive_m / 1000:.1f} km · {plan.source}", "neutral"))
c[2].html(ui.tile("Cleaning", f"{plan.service_min:.0f} min", "time on site", "neutral"))
c[3].html(ui.tile("Total", f"{plan.total_min / 60:.1f} h", f"back at the yard {plan.back_at_depot}", "neutral"))

fig = go.Figure()
lat, lon = zip(*plan.geometry)
fig.add_trace(go.Scattermap(lat=lat, lon=lon, mode="lines", line=dict(width=4, color="#2a78d6"),
                            hoverinfo="skip", name="Route"))
for cat in ["Offline", "Inspect", "Urgent"]:
    s = plan.stops[plan.stops["category"] == cat]
    if not s.empty:
        fig.add_trace(go.Scattermap(lat=s["latitude"], lon=s["longitude"], mode="markers+text",
                                    marker=dict(size=22, color=cats[cat]["color"]), text=s["stop"].astype(str),
                                    textfont=dict(color="white", size=12), name=cat,
                                    customdata=s[["basin_id", "address", "arrive", "reason"]].values,
                                    hovertemplate="Stop %{text}: %{customdata[0]}<br>%{customdata[1]}<br>"
                                                  "Arrive %{customdata[2]}<br>%{customdata[3]}<extra></extra>"))
fig.add_trace(go.Scattermap(lat=[depot["latitude"]], lon=[depot["longitude"]], mode="markers+text",
                            marker=dict(size=18, color="#0b2d5b"), text=["Yard"], textposition="top center",
                            name="Yard", hoverinfo="text"))
all_lat, all_lon = list(lat) + [depot["latitude"]], list(lon) + [depot["longitude"]]
fig.update_layout(map=dict(style="carto-positron", zoom=ui.fit_zoom(all_lat, all_lon, 520),
                           center={"lat": (min(all_lat) + max(all_lat)) / 2, "lon": (min(all_lon) + max(all_lon)) / 2}),
                  margin=dict(l=0, r=0, t=0, b=0), height=520, showlegend=False)
st.plotly_chart(fig, width="stretch", config={"scrollZoom": False})

st.subheader("Crew sheet")
show = plan.stops.rename(columns={"stop": "#", "basin_id": "Basin", "address": "Address", "priority": "Why",
                                  "arrive": "Arrive", "service_min": "On site (min)", "depart": "Leave",
                                  "drive_min": "Drive (min)", "reason": "Note"})
st.dataframe(show[["#", "Basin", "Address", "Why", "Arrive", "On site (min)", "Leave", "Drive (min)", "Note"]],
             hide_index=True, width="stretch")
d1, d2 = st.columns([1, 2])
d1.download_button("Download crew sheet (CSV)", ro.crew_sheet_csv(plan),
                   file_name=f"vacuum_route_{now:%Y-%m-%d}.csv", mime="text/csv", width="stretch")
with d2:
    st.markdown("**Open in Google Maps** (one link per ~10 stops, in order):")
    for i, link in enumerate(plan.google_links, start=1):
        st.link_button(f"Leg {i} of {len(plan.google_links)}", link)
st.caption("Order: nearest neighbour, then 2-opt improvement, on OSRM driving times (OpenStreetMap). The public "
           "OSRM server is a free demo service; a city deployment would run its own.")

# ---------------------------------------------------------------------------
# Crew actions: the dispatcher sends the route, the crew logs each stop from the truck
# ---------------------------------------------------------------------------
st.subheader("Crew")
monitored = set(basins["basin_id"])
real = plan.stops[plan.stops["basin_id"].isin(monitored)]
if real.empty:
    st.caption("Demo stops have no sensor: crew actions are logged on monitored basins only.")
    st.stop()


def log(bid, action, note, sediment=None):
    maintenance.LOG_FILE = data_store.files()["log"]
    maintenance.add(bid, data_store.now(), action, sediment, note)
    st.cache_data.clear()


sent = [b for b in real["basin_id"]
        if any(data_store.entries_for(b, now)["action"].eq("Crew dispatched")
               & (data_store.entries_for(b, now)["time"] >= now - pd.Timedelta(hours=12)))]
c1, c2 = st.columns([1, 2])
if c1.button("📨 Send route to the crew", type="primary", width="stretch", disabled=len(sent) == len(real)):
    for b in real["basin_id"]:
        if b not in sent:
            log(b, "Crew dispatched", "Vacuum route sent from the dashboard")
    st.toast("Route sent: the issues are now 'Verified / crew dispatched'.")
    st.rerun()
c2.caption("Sending the route logs **Crew dispatched** on every stop: each issue moves from *Detected* to "
           "*Verified / crew dispatched*. " + (f"Already sent: {', '.join(sent)}." if sent else ""))

st.markdown("**From the truck's tablet**: one tap per stop closes the loop.")
for _, s in real.iterrows():
    cols = st.columns([2.2, 1, 1, 1])
    cols[0].markdown(f"**{s['stop']}. {s['basin_id']}** · {cats[s['category']]['emoji']} {s['priority']}")
    k = f"{s['basin_id']}_{now:%H%M}"
    if s["category"] == "Offline":
        if cols[1].button("🔧 Sensor fixed", key=f"fix_{k}", width="stretch"):
            log(s["basin_id"], "Inspected", "Sensor checked and fixed on the route")
            st.rerun()
    else:
        if cols[1].button("✅ Cleaned", key=f"clean_{k}", width="stretch"):
            log(s["basin_id"], "Cleaned / vacuumed", "Cleaned on the vacuum route", 10)
            st.rerun()
        if cols[2].button("👍 No issue", key=f"ok_{k}", width="stretch"):
            log(s["basin_id"], "No issue found", "Checked on the vacuum route")
            st.rerun()
    if cols[3].button("Open →", key=f"open_{k}", width="stretch"):
        data_store.select_basin(s["basin_id"])
        st.switch_page("dashboard.py")
st.caption("Each tap is written to the maintenance log with the time: the basin's status, the dispatch list and "
           "the map update at once. A cleaning resets the drainage history, so the next storm is judged fresh.")
