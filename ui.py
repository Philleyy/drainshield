"""
ui.py
-----
Small building blocks shared by the dashboard pages: colours, coloured cards,
tiles and pills (written as HTML so we control exactly how they look).
"""

import base64

import streamlit as st

import processing as proc

RISING = {"color": "#2a78d6", "text": "#1d5fae", "tint": "#e5effb"}   # "rising with the rain" (blue)

CSS = """<style>
.fs-card {border-radius:10px; padding:16px 20px; display:flex; gap:16px; align-items:flex-start;
          border-left:12px solid var(--c); background:var(--tint); height:100%; box-sizing:border-box;}
.fs-icon {flex:none; width:50px; height:50px; border-radius:50%; background:var(--c); color:#fff;
          font-size:24px; font-weight:800; display:flex; align-items:center; justify-content:center;}
.fs-label {font-size:13px; font-weight:800; letter-spacing:.06em; text-transform:uppercase; color:var(--t);}
.fs-head {font-size:22px; font-weight:700; color:#0b0b0b; line-height:1.25; margin:2px 0 8px;}
.fs-reason {font-size:14.5px; color:#2b2a28; margin:4px 0; display:flex; gap:8px;}
.fs-dot {flex:none; width:10px; height:10px; border-radius:50%; margin-top:6px;}
.fs-tile {border:1px solid #e4e3df; border-radius:10px; padding:11px 14px; background:#fff;}
.fs-tile .k {font-size:13px; color:#52514e;}
.fs-tile .v {font-size:26px; font-weight:750; line-height:1.15; margin:3px 0 2px;}
.fs-tile .s {font-size:12.5px; color:#52514e;}
.fs-pill {display:inline-block; padding:2px 9px; border-radius:999px; font-size:12px; font-weight:700;
          color:var(--t); background:var(--tint); border:1px solid var(--c); white-space:nowrap;}
.fs-table {width:100%; border-collapse:collapse; font-size:13.5px;}
.fs-table th {text-align:left; color:#52514e; font-weight:600; border-bottom:1px solid #e4e3df; padding:6px 7px;}
.fs-table td {border-bottom:1px solid #f0efec; padding:7px 7px; vertical-align:top;}
.fs-muted {color:#8a8984;}
.fs-rows {display:grid; grid-template-columns:max-content 1fr; gap:6px 14px; margin-top:4px; font-size:15px;}
.fs-rows .f {color:#52514e; font-weight:600; white-space:nowrap;}
.fs-rows .t {color:#0b0b0b;}
.fs-big {font-size:19px; font-weight:700; color:#0b0b0b; margin:0 0 6px;}
.fs-action {font-size:15px; font-weight:700; color:var(--t);}
.fs-device {display:inline-flex; gap:8px; align-items:center; padding:6px 12px; border-radius:999px;
            border:1px solid #e4e3df; background:#fff; font-size:13px; color:#2b2a28; white-space:nowrap;}
.fs-device .d {width:9px; height:9px; border-radius:50%;}
.fs-value {border:1px solid #e4e3df; border-left:8px solid var(--c); border-radius:10px; padding:12px 16px;
           background:#fff; margin-bottom:12px;}
.fs-value .k {font-size:13px; color:#52514e; font-weight:600; text-transform:uppercase; letter-spacing:.04em;}
.fs-value .v {font-size:30px; font-weight:780; line-height:1.15; margin:4px 0 2px; color:var(--t);}
.fs-value .s {font-size:14px; color:#2b2a28;}
.fs-value .a {font-size:14px; font-weight:700; color:var(--t); margin-top:4px;}
.fs-count {border-radius:10px; padding:10px 14px; background:var(--tint); border-left:8px solid var(--c);}
.fs-count .n {font-size:30px; font-weight:800; color:var(--t); line-height:1.1;}
.fs-count .l {font-size:13px; color:#2b2a28;}
</style>"""


def inject_css():
    st.html(CSS)


def colors(key):
    if key == "rising":
        return RISING
    if key == "neutral":
        return {"color": "#e4e3df", "text": "#0b0b0b", "tint": "#ffffff"}
    return proc.STATUS[key]


def css_vars(key):
    c = colors(key)
    return f"--c:{c['color']}; --t:{c['text']}; --tint:{c['tint']};"


def pill(key, text=None):
    s = proc.STATUS[key]
    return f'<span class="fs-pill" style="{css_vars(key)}">{s["icon"]} {text or s["label"]}</span>'


def tile(title, value, sub, key):
    return (f'<div class="fs-tile"><div class="k">{title}</div>'
            f'<div class="v" style="color:{colors(key)["text"]}">{value}</div><div class="s">{sub}</div></div>')


def card(color_key, icon, label, headline, reasons=()):
    items = "".join(f'<div class="fs-reason"><span class="fs-dot" style="background:{colors(k)["color"]}">'
                    f'</span><span>{t}</span></div>' for k, t in reasons)
    return (f'<div class="fs-card" style="{css_vars(color_key)}"><div class="fs-icon">{icon}</div>'
            f'<div><div class="fs-label">{label}</div><div class="fs-head">{headline}</div>{items}</div></div>')


def svg_image(svg, max_width=600, alt="Cross-section of the catch basin"):
    """Show an SVG drawing (base64 is just a way to put the SVG text inside the page)."""
    encoded = base64.b64encode(svg.encode()).decode()
    st.markdown(f'<img src="data:image/svg+xml;base64,{encoded}" style="width:100%;max-width:{max_width}px" '
                f'alt="{alt}">', unsafe_allow_html=True)


def live_card(color_key, icon, title, value, action):
    return (f'<div class="fs-card" style="{css_vars(color_key)}"><div class="fs-icon">{icon}</div><div>'
            f'<div class="fs-label">Live status</div><div class="fs-head">{title}</div>'
            f'<div class="fs-big">{value}</div><div class="fs-action">→ {action}</div></div></div>')


def dispatch_card(color_key, icon, label, title, rows):
    grid = "".join(f'<div class="f">{f}</div><div class="t">{t}</div>' for f, t in rows)
    return (f'<div class="fs-card" style="{css_vars(color_key)}"><div class="fs-icon">{icon}</div><div>'
            f'<div class="fs-label">{label}</div><div class="fs-head">{title}</div>'
            f'<div class="fs-rows">{grid}</div></div></div>')


def value_card(color_key, title, value, sub, action=None):
    act = f'<div class="a">→ {action}</div>' if action else ""
    return (f'<div class="fs-value" style="{css_vars(color_key)}"><div class="k">{title}</div>'
            f'<div class="v">{value}</div><div class="s">{sub}</div>{act}</div>')


def device_pill(online, battery_pct, minutes_since, battery_key):
    if minutes_since is None:
        return '<span class="fs-device"><span class="d" style="background:#8a8984"></span>Never reported</span>'
    import processing as proc
    ago = "just now" if minutes_since < 1 else f"{proc.nice_duration(minutes_since)} ago"
    dot = "#0ca30c" if online and battery_key == "ok" else "#fab219" if online else "#d03b3b"
    state = "Online" if online else "Offline"
    batt = f" · {battery_pct}% battery" if battery_pct is not None else ""
    return (f'<span class="fs-device"><span class="d" style="background:{dot}"></span>'
            f'{state}{batt} · updated {ago}</span>')


def count_tile(color, tint, text_color, n, label):
    return (f'<div class="fs-count" style="--c:{color};--t:{text_color};--tint:{tint}">'
            f'<div class="n">{n}</div><div class="l">{label}</div></div>')


def fit_zoom(lats, lons, height_px, width_px=900, margin=0.8):
    """Map zoom level that shows every point (web-mercator tiles are 256 px; keep a margin around them)."""
    import math
    lat_span = max(max(lats) - min(lats), 0.002)
    lon_span = max(max(lons) - min(lons), 0.002)
    z_lon = math.log2(360 * width_px * margin / (256 * lon_span))
    z_lat = math.log2(360 * height_px * margin / (256 * lat_span * 1.42))   # 1 deg lat ~ 1.42 deg lon at 45 N
    return max(min(z_lon, z_lat, 16), 9)
