"""
dashboard.py: one catch basin, built for a dispatcher deciding in 3 seconds
--------------------------------------------------------------------------
    LIVE STATUS        -> is it flooding / backing up right now? (emergency dispatch)
    MAINTENANCE STATUS -> does it need a crew soon? (predictive maintenance)
Streamlit re-runs this script from top to bottom every time you click something.
"""

from datetime import timedelta

import pandas as pd
import streamlit as st
from plotly.subplots import make_subplots

import data_store
import maintenance
import processing as proc
import ui
import weather
from basin_drawing import basin_svg

ui.inject_css()
basins, readings, rain, events, _ = data_store.load_all()
key = data_store.data_key()
ids = list(basins["basin_id"])
if not ids:
    st.title("Basin")
    st.info("No catch basin has a sensor yet. Attach one on the **Add basin** page (or click a grey dot on the "
            "Network map), using the same ID as the sensor bridge.")
    st.page_link("basin_setup.py", label="Add basin →")
    st.stop()
if st.session_state.get("basin_id") not in ids:
    st.session_state["basin_id"] = ids[0]


def basin_label(basin_id):
    b = data_store.basin_row(basins, basin_id)
    return f"{basin_id} · {b['address']}" if isinstance(b.get("address"), str) and b["address"] else basin_id


with st.sidebar:
    st.divider()
    st.selectbox("Catch basin", ids, index=ids.index(st.session_state["basin_id"]), key="basin_select",
                 format_func=basin_label,
                 on_change=lambda: data_store.select_basin(st.session_state["basin_select"]))

now = data_store.now()
basin = data_store.basin_row(basins, st.session_state["basin_id"])
levels = data_store.levels_for(key, basin["basin_id"])
S = data_store.status_for(key, basin["basin_id"], now)
hist = S["history"]
inv, G = basin["outlet_invert_cm"], basin["grate_height_cm"]
eng = data_store.engineering()
forecast = weather.forecast_from_series(rain, now)
cat, priority, _ = data_store.triage(basin, S, forecast)

# ---------------------------------------------------------------------------
# HEADER + DEVICE STATUS PILL
# ---------------------------------------------------------------------------
h1, h2 = st.columns([3, 1.4], vertical_alignment="bottom")
h1.title(f"Catch basin {basin['basin_id']}")
online = S["minutes_since_reading"] is not None and S["minutes_since_reading"] <= proc.NO_DATA_AFTER_MIN
h2.html(f'<div style="text-align:right">{ui.device_pill(online, proc.battery_pct(S["battery_v"]), S["minutes_since_reading"], S["battery_status"])}</div>')
address = basin.get("address") if isinstance(basin.get("address"), str) else ""
muni_id = f" · municipal #{basin['municipal_id']}" if pd.notna(basin.get("municipal_id")) and basin.get("municipal_id") else ""
st.caption(f"{address or 'No address'}{muni_id} · ø{basin['inner_width_cm'] * 10:.0f} mm · outlet invert "
           f"{basin['invert_depth_cm'] / 100:.2f} m below street · as of **{now:%b %d, %Y %H:%M}**")

# ---------------------------------------------------------------------------
# ACTION BANNER + 3-PART DIAGNOSIS + CREW LOG BUTTON
# ---------------------------------------------------------------------------
live = proc.live_summary(basin, S)
live_key = {"normal": "ok", "rising": "rising", "high": "clean_soon", "backing_up": "urgent",
            "no_data": "no_data"}[S["live"]]
b_key, b_icon, b_head, _ = proc.action_banner(basin, S)
if priority == "Inspect before storm":
    b_key, b_icon = "urgent", "!"
    b_head = f"Inspect before the storm: {weather.describe(forecast)[2:]}"
parts = dict(proc.dispatch_summary(basin, S))
rows = []
if S["status"] not in ("ok",) or S["live"] == "no_data":
    if "Problem" in parts:
        rows.append(("1 · Observed", parts["Problem"]))
    if "Likely cause" in parts:
        conf = f' <span class="fs-pill" style="--c:#8a8984;--t:#2b2a28;--tint:#fff">{S["confidence"]} confidence</span>' \
            if S.get("confidence") else ""
        rows.append(("2 · Possible explanation", parts["Likely cause"] + conf))
    step = "Before the rain starts: " + parts.get("Recommended action", "").lower() \
        if priority == "Inspect before storm" else parts.get("Recommended action", "")
    rows.append(("3 · Next step", step))
if "Device" in parts:
    rows.append(("Sensor", parts["Device"]))
if S.get("lifecycle"):
    rows.append(("Issue status", S["lifecycle"]))
if not rows:
    rows = [("", "No action needed")]
st.html(ui.dispatch_card(b_key, b_icon, "What to do", b_head, rows))


c1, c2 = st.columns([1.6, 3])
with c1.expander("✅ Log maintenance"):
    with st.form("log_form", clear_on_submit=True, border=False):
        action = st.radio("What did the crew do?", maintenance.ACTIONS, index=4)
        sed = st.number_input("If cleaned: sediment left in the sump (mm)", 0, 1000, 0, 10,
                              help="Usually 0. Used to restart the sump-fill estimate.")
        note = st.text_input("Note (optional)")
        if st.form_submit_button("Save", type="primary", width="stretch"):
            maintenance.add(basin["basin_id"], now, action, sed if action == "Cleaned / vacuumed" else None, note)
            st.cache_data.clear()
            st.rerun()
c2.page_link("network.py", label="← Back to the network map")
st.write("")

# ---------------------------------------------------------------------------
# DRAWING | VALUE CARDS + HYDROGRAPH
# ---------------------------------------------------------------------------
health, detail, health_key, health_action = proc.drainage_health(basin, S)
w = S.get("worst_event")
restriction = None
if w and w["diagnosis"] == "outlet" and w["status"] != "ok":
    restriction = (w["status"], f"Inferred restriction: {'≤' if w['reached_limit'] else '~'}"
                                f"{w['capacity_pct']:.0f}% capacity")
grate_blocked = bool(w and w["diagnosis"] == "grate")

left, right = st.columns([1.45, 1], gap="large", vertical_alignment="center")
with left:
    stale = S["live"] == "no_data"
    ui.svg_image(basin_svg(basin, S["level_cm"], S["at_sensor_limit"], S["raining_now"], stale,
                           restriction=restriction, grate_blocked=grate_blocked,
                           sediment_cm=S["sediment_cm"]), max_width=820)
    st.caption("Depths are measured down from the street. The sensor only sees the water surface: what's in "
               "the sump and any restriction are **inferred** from how the basin behaves in storms.")

with right:
    if S["level_cm"] is None or stale:
        st.html(ui.value_card("no_data", "Live water depth", "Unknown", live["value"]))
    else:
        depth = proc.depth_below_street_m(basin, S["level_cm"])
        value = (f"≤ {proc.closest_readable_m(basin):.2f} m" if S["at_sensor_limit"] else f"{depth:.2f} m")
        sub = "below street · " + ("above the sensor's range" if S["at_sensor_limit"] else live["title"].lower())
        st.html(ui.value_card(live_key, "Live water depth", value, sub))
    w_ = S.get("worst_event")
    fill = f"Est. sump fill: ~{S['sediment_pct']:.0f}%"
    if stale:
        st.html(ui.value_card("no_data", "Drainage performance", "Unknown", "No recent data"))
    elif not w_:
        st.html(ui.value_card(S["sediment_status"], "Drainage performance", "Not tested yet",
                              f"No storm big enough yet · {fill}"))
    elif w_["diagnosis"] == "grate":
        st.html(ui.value_card(w_["status"], "Drainage performance", "Grate blocked",
                              f"Only ~{w_['grate_pct']:.0f}% of the runoff gets in · {fill}", health_action))
    else:
        bound = "≤ " if w_["reached_limit"] else "~"
        rec = ("recovers in < 10 min" if w_["drain_min"] < 10 else
               f"recovery {proc.nice_duration(w_['drain_min'])} (normal < 10 min)")
        st.html(ui.value_card(health_key, "Drainage performance", health,
                              f"Est. {bound}{w_['capacity_pct']:.0f}% outlet capacity · {rec} · {fill}",
                              health_action))

# ---------------------------------------------------------------------------
# HYDROGRAPH + HISTORY: open in the Engineering view, folded away in the Crew view
# ---------------------------------------------------------------------------
detail_box = st.container() if eng else st.expander("Hydrograph and storm history (engineering detail)")
if eng:
    st.subheader("Hydrograph")
with detail_box:
    pass
    # ---- hydrograph ----
    o1, o2, o3, _ = st.columns([1, 1.3, 0.8, 1.5])
    window = o1.selectbox("Show", ["Last 24 h", "Last 7 days", "Everything"], index=1)
    past = hist[hist["start"] <= now] if not hist.empty else hist
    storm_opts = ["(none)"] + [f"{e['start']:%b %d %H:%M} · {e['total_mm']:.0f} mm" for _, e in past.iloc[::-1].iterrows()]
    zoom = o2.selectbox("Zoom on a storm", storm_opts)
    whole = o3.toggle("Full depth", value=False)
    if zoom != "(none)":
        e = past.iloc[::-1].iloc[storm_opts.index(zoom) - 1]
        t0, t1 = e["start"] - timedelta(hours=1), min(e["end"] + timedelta(hours=6), now)
    else:
        span = {"Last 24 h": timedelta(days=1), "Last 7 days": timedelta(days=7), "Everything": now - (levels["timestamp"].min() if not levels.empty else now)}[window]
        t0, t1 = now - span, now

    def elev(cm_above_floor):
        """Height above the floor -> elevation relative to the street (m, negative = below)."""
        return (cm_above_floor - G) / 100

    lv = levels[(levels["timestamp"] >= t0) & (levels["timestamp"] <= t1)].copy()
    lv["elev"] = elev(lv["level_cm"] + inv)
    gap = lv["timestamp"].diff() > timedelta(minutes=proc.NO_DATA_AFTER_MIN)
    if gap.any():
        br = lv.loc[gap, ["timestamp"]].copy()
        br["timestamp"] -= timedelta(minutes=1)
        lv = pd.concat([lv, br]).sort_values("timestamp")
    rn = rain[(rain["timestamp"] >= t0) & (rain["timestamp"] <= t1)].set_index("timestamp")["rain_mm"]
    rn = rn.resample("h").sum()                     # mm in each hour = mm/h

    sub_cm = proc.subdrain_above_invert_cm(basin)
    limit = basin["sensor_height_cm"] - basin["sensor_blind_zone_cm"]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.2, 0.8], vertical_spacing=0.04)
    fig.add_bar(x=rn.index, y=rn.values, marker_color="#8a8984", name="Rain (mm/h)",
                hovertemplate="%{x|%b %d %H:%M}<br>Rain: %{y:.1f} mm/h<extra></extra>", row=1, col=1)
    fig.add_scatter(x=lv["timestamp"], y=lv["elev"], mode="lines", line=dict(color="#2a78d6", width=2),
                    name="Water surface", connectgaps=False,
                    hovertemplate="%{x|%b %d %H:%M}<br>%{y:.2f} m (below street)<extra></extra>", row=2, col=1)
    high_top = min(proc.HIGH_WATER_CM, sub_cm) if sub_cm is not None else proc.HIGH_WATER_CM
    for lo, hi, color in [(inv - 10, inv + proc.NORMAL_BAND_CM, "#0ca30c"),
                          (inv + proc.NORMAL_BAND_CM, inv + high_top, "#fab219"),
                          (inv + high_top, G, "#d03b3b")]:
        fig.add_hrect(y0=elev(lo), y1=elev(hi), fillcolor=color, opacity=0.09, line_width=0, layer="below",
                      row=2, col=1)
    lines = [(G, "Street", "#0b0b0b", "solid"), (limit, "Sensor range limit", "#52514e", "dash"),
             (inv, "Outlet invert (normal)", "#52514e", "dot")]
    if sub_cm is not None:
        lines.append((inv + sub_cm, "Subdrain / inlet", "#d03b3b", "dash"))
    if whole:
        lines.append((0, "Sump floor", "#52514e", "solid"))
    for yv, name, color, dash in lines:
        fig.add_hline(y=elev(yv), line_dash=dash, line_color=color, line_width=1.2, row=2, col=1,
                      annotation_text=name, annotation_position="top left", annotation_font=dict(size=11, color=color))
    if whole:
        y_range = [elev(0) - 0.05, 0.08]
    else:
        vals = lv["elev"].dropna()
        hi = max(vals.max() if not vals.empty else elev(inv), elev(inv + 15))
        y_range = [elev(inv) - 0.12, hi + 0.08]
    fig.update_yaxes(title_text="mm/h", autorange="reversed", row=1, col=1, gridcolor="#eeede9")
    fig.update_yaxes(title_text="m relative to street", range=y_range, row=2, col=1, gridcolor="#eeede9",
                     zeroline=False, tickformat=".2f")
    fig.update_xaxes(range=[t0, t1], gridcolor="#eeede9")
    fig.update_layout(height=430, showlegend=False, margin=dict(l=55, r=10, t=6, b=30),
                      plot_bgcolor="#ffffff", paper_bgcolor="rgba(0,0,0,0)", hovermode="x unified",
                      bargap=0.05, font=dict(color="#0b0b0b"))
    st.plotly_chart(fig, width="stretch", theme=None)

    # ---------------------------------------------------------------------------
    # STORM HISTORY (the evidence behind the maintenance status)
    # ---------------------------------------------------------------------------
    st.markdown("#### Storm and maintenance history")
    if hist.empty:
        st.write("No storms yet.")
    else:
        na = '<span class="fs-muted">—</span>'
        rows = []
        for _, e in hist.tail(8).iloc[::-1].iterrows():
            if e["diagnosis"] == "raining":
                result = '<span class="fs-pill" style="--c:#2a78d6;--t:#1d5fae;--tint:#e5effb">Raining now</span>'
            elif e["status"] in proc.STATUS:
                text = proc.DIAGNOSIS[e["diagnosis"]] if e["diagnosis"] in ("outlet", "grate") else (
                    "Normal" if e["status"] == "ok" else None)
                result = ui.pill(e["status"], text)
            else:
                result = ""
            if pd.isna(e["peak_cm"]):
                peak = na
            elif e["reached_limit"]:
                peak = f"≤ {proc.closest_readable_m(basin):.2f} m"
            else:
                peak = f"{proc.depth_below_street_m(basin, e['peak_cm']):.2f} m"
            if e["diagnosis"] == "grate":
                drainage = f"grate: ~{e['grate_pct']:.0f}% gets in"
            elif not pd.isna(e["capacity_pct"]):
                drainage = f"{'≤' if e['reached_limit'] else '~'}{e['capacity_pct']:.0f}%"
            else:
                drainage = na
            if pd.isna(e["drain_min"]) or e["diagnosis"] in ("raining", "no_data"):
                drain = na
            else:
                drain = "< 10 min" if e["drain_min"] < 10 else proc.nice_duration(e["drain_min"])
            rows.append(f"<tr><td>{e['start']:%b %d}</td><td>{e['total_mm']:.0f} mm</td><td>{peak}</td>"
                        f"<td>{drain}</td><td>{drainage}</td><td>{result}</td></tr>")
        st.html('<table class="fs-table"><tr><th>Storm</th><th>Rain</th><th>Highest water (below street)</th>'
                '<th>Drained in</th><th>Drainage capacity (est.)</th><th>Result</th></tr>' + "".join(rows) + "</table>")

# ---------------------------------------------------------------------------
# DETAILS
# ---------------------------------------------------------------------------
with st.expander("As-built details"):
    inlets = basin.get("inlets") if isinstance(basin.get("inlets"), str) else ""
    st.markdown(f"""
| | |
|---|---|
| Inside diameter | {basin['inner_width_cm'] * 10:.0f} mm |
| Outlet invert depth (radier) | {basin['invert_depth_cm'] * 10:.0f} mm below the grate, ø{basin['outlet_diameter_cm'] * 10:.0f} mm |
| Sump (réserve) | {basin['sump_depth_cm'] * 10:.0f} mm, floor at {G * 10:.0f} mm |
| Cast-iron trap | {basin['trap_model'] or 'none'} |
| Incoming pipes / subdrains | {inlets.replace('|', ', ').replace(':', ' ', 1) if inlets else 'none'} |
| Sensor pod | {basin['sensor_depth_cm'] * 10:.0f} mm below the grate, sees water up to {(G - limit) * 10:.0f} mm below the grate |
""")

with st.expander("How the status is decided"):
    st.markdown(f"""
- **Live status** is the water level right now. It turns red when the water backs up more than
  {proc.HIGH_WATER_CM} cm above the outlet invert or reaches a subdrain. The sensor can't read water closer
  than {proc.closest_readable_m(basin):.2f} m below the street, so above that it says "≤".
- **Maintenance status** comes from storms: after each one we compare the rise with what this basin did
  when it was clean (its first {proc.LEARNING_STORMS} storms).
  Rose much more and drained slowly → outlet or trap restricted. Rose much less in a big rain → grate covered.
  Clogging doesn't fix itself, so the worst storm since the last cleaning counts.
- **Drainage capacity** ≈ 1 ÷ (how many times higher than normal it rose). It's a rough estimate (±30%).
- **Sump fill** is estimated from rain and drainage area, never measured: the sensor can't see under water.
""")
