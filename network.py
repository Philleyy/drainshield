"""
network.py: the overview (home screen)
--------------------------------------
* Every catch basin of the municipality (Ville de Montréal open data). Without a sensor, they are
  coloured by PILOT PRIORITY (import_priorities.py): purple = big catchment and/or local low point.
  Ringed dots = the 10 proposed pilot sites (1 anchor + 2 neighbours/controls each).
* Basins with a DrainShield sensor are coloured by what to do:
      🔴 Urgent · 🟠 Inspect · 🟢 Normal · ⚫ Offline (sensor problem)
  The pills at the top filter the map and the list.
* Weather readiness banner: real rain forecast for the next 12 h (Environment Canada GEM),
  and which monitored basins must be cleaned BEFORE it starts.
* Click a pin or search a basin to see its card. Click a dispatch-list row to open the basin.
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
basins, readings, rain, events, _ = data_store.load_all()
now = data_store.now()
df = data_store.network_status(data_store.data_key(), data_store.log_key(), now)
forecast = weather.forecast_from_series(rain, now)
cats = data_store.CATEGORIES
eng = data_store.engineering()

registry = data_store.municipal_basins()
attached = set(basins["municipal_id"].dropna().astype(str)) if "municipal_id" in basins else set()
unmonitored = registry[~registry["municipal_id"].isin(attached)]
owner = registry["owner"].iloc[0] if "owner" in registry and not registry.empty else "the municipality"

with st.sidebar:
    st.divider()
    st.markdown("**Map layers**")
    street_map = st.toggle("Street map", value=True, help="Needs internet. Turn off if the map stays blank.")
    radar = st.toggle("Live ECCC weather radar", value=False, help="Environment Canada 1 km precipitation radar.")
    by_priority = st.toggle("Colour by pilot priority", value=True,
                            help="Basins without a sensor, coloured by catchment area × local low point "
                                 "(a ranking to choose pilot sites, not a flood prediction).")
    show_pilots = st.toggle("Show the 10 pilot sites", value=True)

st.title(f"{owner.replace('Dorval - Ile Dorval', 'Dorval')} catch basins")
st.caption(f"{len(registry):,} catch basins from the Ville de Montréal open data · "
           f"{len(df)} with a DrainShield sensor · {now:%b %d, %Y %H:%M}")

# ---------------------------------------------------------------------------
# WEATHER READINESS BANNER
# ---------------------------------------------------------------------------
before_storm = df[df["priority"] == "Inspect before storm"]
flooding = df[df["priority"] == "Flooding / backing up now"]
inspect = df[df["category"] == "Inspect"]
if df.empty:
    key, call = "no_data", "No sensor installed yet: attach one from the map or the Add basin page."
elif not flooding.empty:
    key, call = "urgent", f"{len(flooding)} catch basin(s) backing up right now: dispatch crews."
elif not before_storm.empty:
    key, call = "urgent", (f"⚠️ {len(before_storm)} catch basin(s) with slow drainage need cleaning "
                           f"before the rain starts: {', '.join(before_storm['basin_id'])}.")
elif weather.is_heavy(forecast):
    key, call = "rising", "Heavy rain coming, and no monitored basin is flagged for slow drainage."
elif not inspect.empty:
    key, call = "clean_soon", f"{len(inspect)} catch basin(s) to add to the next vacuum route."
else:
    key, call = "ok", "Network ready: no action needed."
wet = forecast is not None and forecast["total_mm"] >= 0.5
st.html(ui.card(key, "🌧" if wet else "☀", "Weather readiness · Environment Canada GEM forecast",
                weather.describe(forecast), [(key, call)]))

# ---------------------------------------------------------------------------
# SENSOR HEALTH (engineering view)
# ---------------------------------------------------------------------------
if eng and not df.empty:
    low = df[(df["battery_pct"].notna()) & (df["battery_pct"] < 15) & df["online"]]
    c = st.columns(4)
    c[0].html(ui.tile("Sensors online", f"{int(df['online'].sum())}", f"of {len(df)}", "ok"))
    c[1].html(ui.tile("Offline", f"{int((~df['online']).sum())}", "no reading for 1 h+", "no_data"))
    c[2].html(ui.tile("Low battery (<15%)", f"{len(low)}", ", ".join(low["basin_id"]) or "none", "watch"))
    c[3].html(ui.tile("Data irregularities", "0", "not detected (rule not built yet)", "neutral"))

# ---------------------------------------------------------------------------
# FILTER PILLS
# ---------------------------------------------------------------------------
labels = {c: f"{s['emoji']} {int((df['category'] == c).sum())} {c}" for c, s in cats.items()}
labels["No sensor"] = f"⚪ {len(unmonitored):,} No sensor"
chosen = st.pills("Filter", list(labels), selection_mode="multi", default=list(labels),
                  format_func=lambda c: labels[c], label_visibility="collapsed", key="filter") or list(labels)
shown = df[df["category"].isin(chosen)].copy()
show_grey = "No sensor" in chosen

# ---------------------------------------------------------------------------
# SEARCH + MAP + SELECTED BASIN CARD
# ---------------------------------------------------------------------------
def pick_from_map():
    pts = st.session_state["map"].selection.points
    if pts:
        cd = pts[0].get("customdata")
        if cd:
            st.session_state["picked"] = (cd[1], cd[0])


def pick_from_search():
    choice = st.session_state.get("search")
    if choice:
        kind, ident = choice.split(":", 1)
        st.session_state["picked"] = ("basin" if kind == "b" else "muni", ident)


search_labels = {f"b:{r['basin_id']}": f"🛰 {r['basin_id']} · {r['address']}" for _, r in df.iterrows()}
search_labels.update({f"m:{m}": f"#{m} · {a}" for m, a in zip(unmonitored["municipal_id"], unmonitored["address"])})
st.selectbox("Find a basin", list(search_labels), index=None, key="search", on_change=pick_from_search,
             placeholder="🔍 Search by basin ID, city catch basin number or street...",
             label_visibility="collapsed", format_func=lambda k: search_labels[k])

map_col, card_col = st.columns([1.75, 1], gap="medium")
picked = st.session_state.get("picked")
with map_col:
    pts = df if not df.empty else registry
    center = {"lat": (pts["latitude"].min() + pts["latitude"].max()) / 2,
              "lon": (pts["longitude"].min() + pts["longitude"].max()) / 2}
    span = max(pts["longitude"].max() - pts["longitude"].min(),
               (pts["latitude"].max() - pts["latitude"].min()) * 1.6, 0.004)
    zoom = min(16.0, math.log2(360 * 2.2 / span) - 0.3)
    if picked:
        src = df[df["basin_id"] == picked[1]] if picked[0] == "basin" else registry[registry["municipal_id"] == picked[1]]
        if not src.empty:
            center, zoom = {"lat": src["latitude"].iloc[0], "lon": src["longitude"].iloc[0]}, 17.0
    fig = go.Figure()
    pilots = registry[registry["pilot_site"].notna()] if "pilot_site" in registry else registry.iloc[0:0]
    if show_pilots and not pilots.empty:          # a dark ring under each pilot basin
        for size, color in ((19, "#0b2d5b"), (15, "#ffffff")):
            fig.add_trace(go.Scattermap(
                lat=pilots["latitude"], lon=pilots["longitude"], mode="markers", marker=dict(size=size, color=color),
                customdata=list(zip(pilots["municipal_id"], ["muni"] * len(pilots))), hoverinfo="skip"))
    if show_grey and not unmonitored.empty:
        groups = (list(data_store.PRIORITY)[::-1] if by_priority else [None])   # highest priority drawn on top
        for level in groups:
            g = unmonitored if level is None else unmonitored[unmonitored["priority_level"] == level]
            _, color, size, _ = data_store.PRIORITY[level] if level else (None, "#a9a8a2", 6, None)
            pilot_txt = [f"<br>⭐ Pilot site {int(ps)} · {role}" if pd.notna(ps) else ""
                         for ps, role in zip(g["pilot_site"], g["pilot_role"])]
            fig.add_trace(go.Scattermap(
                lat=g["latitude"], lon=g["longitude"], mode="markers", name=level or "No sensor",
                marker=dict(size=size, color=color, opacity=0.9),
                customdata=list(zip(g["municipal_id"], ["muni"] * len(g), g["tier_label"].fillna(""), pilot_txt)),
                text=g["address"],
                hovertemplate="Catch basin #%{customdata[0]}<br>%{text}<br>%{customdata[2]}%{customdata[3]}"
                              "<extra>No sensor</extra>"))
    if not shown.empty:
        shown["size"] = shown["category"].map(lambda c: cats[c]["size"])
        shown["kind"] = "basin"
        sensors = px.scatter_map(
            shown, lat="latitude", lon="longitude", color="category", size="size", size_max=22,
            color_discrete_map={c: s["color"] for c, s in cats.items()},
            category_orders={"category": list(cats)[::-1]}, hover_name="basin_id", custom_data=["basin_id", "kind"],
            hover_data={"address": True, "priority": True, "water": True, "size": False, "kind": False,
                        "latitude": False, "longitude": False, "category": False},
            labels={"address": "Address", "priority": "Status", "water": "Water below street"})
        for trace in sensors.data:
            fig.add_trace(trace)
    if picked:
        src = df[df["basin_id"] == picked[1]] if picked[0] == "basin" else registry[registry["municipal_id"] == picked[1]]
        if not src.empty:
            fig.add_trace(go.Scattermap(lat=src["latitude"], lon=src["longitude"], mode="markers", hoverinfo="skip",
                                        marker=dict(size=34, color="#0b2d5b", opacity=0.25), showlegend=False,
                                        customdata=[(picked[1], picked[0])]))
    layers = [{"sourcetype": "raster", "source": [weather.RADAR_TILES], "opacity": 0.55, "below": "traces"}] if radar else []
    fig.update_layout(map=dict(style="carto-positron" if street_map else "white-bg", center=center, zoom=zoom,
                               layers=layers),
                      margin=dict(l=0, r=0, t=0, b=0), showlegend=False, height=560)
    st.plotly_chart(fig, width="stretch", on_select=pick_from_map, selection_mode="points", key="map")
    if by_priority and show_grey:
        st.html('<div class="fs-muted" style="font-size:0.85rem">Pilot priority (basins without a sensor): ' + " · ".join(
            f'<span style="color:{c}">●</span> {lvl} ({legend})' for lvl, (_, c, _, legend) in data_store.PRIORITY.items())
            + (" · ◎ ringed = pilot site" if show_pilots else "") + "</div>")

with card_col:
    if not picked:
        st.markdown("**Click a dot, or search a basin.**")
        st.caption("Dots without a sensor are coloured by pilot priority (purple = highest). Click one to see why, "
                   "or to attach a sensor.")
        top = df[df["category"].isin(["Urgent", "Inspect", "Offline"])].head(6)
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
                                 r["address"] or "Monitored basin", f"{r['basin_id']} · {r['priority']}",
                                 [("Water", f"{r['water']} below street {r['trend']}"),
                                  ("Drainage", r["drainage"]), ("Action", r["action"]),
                                  ("Issue", r["issue"] or "—"), ("Updated", r["updated"])]))
        if st.button("View basin details →", type="primary", width="stretch"):
            data_store.select_basin(r["basin_id"])
            st.switch_page("dashboard.py")
    else:
        m = registry[registry["municipal_id"] == picked[1]]
        if not m.empty:
            m = m.iloc[0]
            installed = m.get("install_date") if isinstance(m.get("install_date"), str) and m.get("install_date") \
                else "unknown"
            rows = [("Address", m["address"]), ("Type", m.get("basin_type", "")), ("Installed", installed)]
            if pd.notna(m.get("tier_label")):
                low = ("elevation unknown" if m.get("elevation_known") != True              # noqa: E712 (NaN-safe)
                       else f"yes, {m['below_neighbours_m']:.2f} m below its neighbours" if m.get("low_point") == True
                       else "no")
                score = f" · score {m['score']:.2f}" if pd.notna(m.get("score")) else ""
                rows += [("Priority", f"{m['priority_level']} (tier {m['tier']}){score}"
                          if m.get("tier") not in (None, "–") and pd.notna(m.get("tier")) else m["priority_level"]),
                         ("Catchment", f"~{m['catchment_m2']:,.0f} m² (est.)" if pd.notna(m.get("catchment_m2")) else "—"),
                         ("Low point", low), ("Sensor fit", str(m.get("compatibility", "—")).split(":")[0])]
                if pd.notna(m.get("pilot_site")):
                    rows.append(("Pilot site", f"⭐ Site {int(m['pilot_site'])} · {m['pilot_role']}"))
            st.html(ui.dispatch_card("no_data", "+", "City catch basin · no sensor", f"#{m['municipal_id']}", rows))
            if st.button("+ Attach a DrainShield sensor to this basin", type="primary", width="stretch"):
                st.session_state["prefill"] = {"municipal_id": m["municipal_id"], "address": m["address"],
                                               "latitude": float(m["latitude"]), "longitude": float(m["longitude"])}
                st.switch_page("basin_setup.py")
    if picked and st.button("Clear selection", width="stretch"):
        st.session_state.pop("picked", None)
        st.rerun()

# ---------------------------------------------------------------------------
# DISPATCH LIST (basins with a sensor)
# ---------------------------------------------------------------------------
st.subheader("Dispatch list")
if df.empty:
    st.info("No sensor installed yet. Click a grey dot on the map (or use **Add basin**) to attach one, then "
            "start `sensor_bridge.py` with the same basin ID (see the **Live sensor** page).")
else:
    st.caption("Most urgent first. Click a row to open the basin.")
    cols = {"basin_id": "Basin", "address": "Address", "status": "Priority", "water": "Water below street",
            "trend": "Trend", "recovery": "Recovery time", "action": "Recommended action", "issue": "Issue",
            "updated": "Updated"}
    if eng:
        cols["battery_pct"] = "Battery %"
    table = shown.assign(status=shown["category"].map(lambda c: cats[c]["emoji"]) + " " + shown["priority"])
    table = table[list(cols)].rename(columns=cols)
    picked_row = st.dataframe(table, hide_index=True, width="stretch", on_select="rerun",
                              selection_mode="single-row", key="dispatch")
    if picked_row.selection.rows:
        data_store.select_basin(table.iloc[picked_row.selection.rows[0]]["Basin"])
        st.switch_page("dashboard.py")

# ---------------------------------------------------------------------------
# PILOT PLAN (from the prioritization)
# ---------------------------------------------------------------------------
if not pilots.empty:
    with st.expander(f"⭐ Proposed pilot: {pilots['pilot_site'].nunique()} sites, {len(pilots)} basins"):
        st.caption("Each site = one **anchor** (top-ranked basin) + two **neighbours** used as controls, so a clog "
                   "can be told apart from the whole street being overloaded. Ranking from catchment area × local "
                   "low point: provisional, to check on site and against Dorval's known flood sectors.")
        plan = pilots.sort_values(["pilot_site", "pilot_role"]).assign(
            site=pilots["pilot_site"].astype(int),
            sensor=pilots["municipal_id"].isin(attached).map({True: "✅ installed", False: ""}))
        cols = {"site": "Site", "pilot_role": "Role", "municipal_id": "City #", "address": "Address",
                "tier_label": "Tier", "score": "Score", "catchment_m2": "Catchment (m²)",
                "below_neighbours_m": "Below neighbours (m)", "sensor": "Sensor"}
        sel = st.dataframe(plan[list(cols)].rename(columns=cols), hide_index=True, width="stretch",
                           on_select="rerun", selection_mode="single-row", key="pilot_table")
        if sel.selection.rows:
            st.session_state["picked"] = ("muni", plan.iloc[sel.selection.rows[0]]["municipal_id"])
            st.rerun()
        st.caption("Click a row to show it on the map.")

# ---------------------------------------------------------------------------
# THE FULL CITY REGISTRY
# ---------------------------------------------------------------------------
with st.expander(f"All {len(registry):,} catch basins (Ville de Montréal open data)"):
    full = registry.assign(sensor=registry["municipal_id"].isin(attached).map({True: "yes", False: ""}))
    if "score" in full:
        full = full.sort_values(["score", "catchment_m2"], ascending=False, na_position="last")
    cols = {"municipal_id": "City #", "address": "Address", "priority_level": "Priority", "tier_label": "Tier",
            "score": "Score", "catchment_m2": "Catchment (m²)", "below_neighbours_m": "Below neighbours (m)",
            "compatibility": "Sensor fit", "pilot_site": "Pilot site", "basin_type": "Type", "sensor": "Sensor"}
    cols = {k: v for k, v in cols.items() if k in full}
    st.dataframe(full[list(cols)].rename(columns=cols), hide_index=True, width="stretch", height=360)
    st.caption("Source: Ville de Montréal, « Puisards d'égout » (ego_puisard_p.csv), every active basin owned by "
               f"{owner}; priority from the DrainShield prioritization (highest score first). Use the search icon "
               "at the top right of the table to find a street.")
