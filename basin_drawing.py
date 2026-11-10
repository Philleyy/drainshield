"""
basin_drawing.py
----------------
Draws a to-scale cross-section of a catch basin from its row in the basins CSV,
labelled with the depths a municipality works with (measured down from the street):
street/grate, sensor pod, incoming pipes/subdrains, outlet invert and sump floor.

What the ultrasonic sensor CAN'T see is drawn as such: the sump contents under the
water are hatched, and a restriction at the outlet or grate is labelled "inferred"
(it comes from how the basin behaved in storms, not from a direct measurement).

SVG is a text format for drawings: each shape is one line like
    <rect x="10" y="20" width="50" height="30" fill="blue"/>
"""

import basin_model as bm
from processing import HIGH_WATER_CM, NORMAL_BAND_CM

WATER = {"normal": "#2a78d6", "high": "#ec835a", "backup": "#d03b3b", "unknown": "#a9a8a2"}
STATUS_COLOR = {"ok": "#0ca30c", "watch": "#c98500", "clean_soon": "#d9622b", "urgent": "#d03b3b",
                "no_data": "#8a8984"}
CONCRETE, CONCRETE_DARK, CAST_IRON = "#c9c7c0", "#9e9c95", "#4a4844"
SEDIMENT = "#8b6a43"
SOIL, ASPHALT, AIR = "#efe6d6", "#3d3c39", "#f8f7f3"
TEXT, MUTED = "#0b0b0b", "#52514e"
ZONES = {"ok": "#0ca30c", "high": "#fab219", "backup": "#d03b3b"}

WIDTH, HEIGHT = 940, 660
LEFT = 205          # x of the outside of the left wall


def water_color(level_cm, at_limit, subdrain_cm=None):
    if level_cm is None:
        return WATER["unknown"]
    if at_limit or level_cm > HIGH_WATER_CM or (subdrain_cm is not None and level_cm >= subdrain_cm):
        return WATER["backup"]
    if level_cm > NORMAL_BAND_CM:
        return WATER["high"]
    return WATER["normal"]


def inlets_of(b):
    """Incoming pipes / subdrains as a list of dicts (depth from the grate in mm)."""
    if isinstance(b.get("inlets"), str) and b["inlets"]:
        return bm.text_to_inlets(b["inlets"])
    if int(b.get("subdrains", 0)) > 0:          # older files: one subdrain level
        return [{"kind": "Subdrain", "depth_mm": (b["grate_height_cm"] - b["subdrain_height_cm"]) * 10,
                 "diameter_mm": b["subdrain_diameter_cm"] * 10}]
    return []


def m_below(b, cm_above_floor):
    """Height above the floor (cm) -> '-1.40 m' (depth below the street)."""
    d = (b["grate_height_cm"] - cm_above_floor) / 100
    return "0.00 m" if abs(d) < 0.005 else f"−{d:.2f} m"


def basin_svg(b, level_cm=None, at_limit=False, raining=False, stale=False,
              restriction=None, grate_blocked=False, sediment_cm=None):
    """b: one basin row.  level_cm: water above the outlet invert (None = unknown).
    restriction: None, or (status_key, short text) for an inferred outlet restriction.
    grate_blocked: draw the grate as covered (inferred)."""
    G = b["grate_height_cm"]
    inv, sump, D = b["outlet_invert_cm"], b["sump_depth_cm"], b["outlet_diameter_cm"]
    below = b["floor_cm"] + b["slab_cm"]
    s = min(HEIGHT / (G + 30 + below), 3.4)
    top_px = 36

    def y(cm):
        return top_px + (G + 30 - cm) * s

    wall, w = b["wall_cm"] * s, b["inner_width_cm"] * s
    x_out_l, x_in_l = LEFT, LEFT + wall
    x_in_r, x_out_r = x_in_l + w, x_in_l + w + wall
    hs, blind = b["sensor_height_cm"], b["sensor_blind_zone_cm"]
    limit = hs - blind
    inlets = inlets_of(b)
    sub = (b["subdrain_height_cm"] - inv) if inlets else None

    out = []
    add = out.append
    add(f'<svg viewBox="0 0 {WIDTH} {y(-below) + 14:.0f}" xmlns="http://www.w3.org/2000/svg" '
        f'font-family="Helvetica, Arial, sans-serif">')
    add('<defs><pattern id="hatch" width="9" height="9" patternUnits="userSpaceOnUse" '
        'patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="9" stroke="#ffffff" '
        'stroke-width="2.5" opacity="0.55"/></pattern>'
        f'<pattern id="above" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
        f'<line x1="0" y1="0" x2="0" y2="8" stroke="{WATER["backup"]}" stroke-width="3" opacity="0.35"/>'
        '</pattern></defs>')

    # ---------- ground, walls, floor, slab ----------
    add(f'<rect x="{x_out_l - 45}" y="{y(G)}" width="{x_out_r - x_out_l + 90}" height="{y(-below) - y(G)}" fill="{SOIL}"/>')
    add(f'<rect x="{x_out_l - 25}" y="{y(-b["floor_cm"])}" width="{x_out_r - x_out_l + 50}" '
        f'height="{b["slab_cm"] * s}" fill="{CONCRETE_DARK}"/>')
    add(f'<rect x="{x_out_l}" y="{y(G)}" width="{wall}" height="{y(0) - y(G)}" fill="{CONCRETE}"/>')
    add(f'<rect x="{x_in_r}" y="{y(G)}" width="{wall}" height="{y(0) - y(G)}" fill="{CONCRETE}"/>')
    add(f'<rect x="{x_out_l}" y="{y(0)}" width="{x_out_r - x_out_l}" height="{b["floor_cm"] * s}" fill="{CONCRETE}"/>')
    add(f'<rect x="{x_in_l}" y="{y(G)}" width="{w}" height="{y(0) - y(G)}" fill="{AIR}"/>')
    # street and cast-iron frame/grate
    add(f'<rect x="{x_out_l - 45}" y="{y(G) - 4}" width="{x_out_r - x_out_l + 90}" height="7" fill="{ASPHALT}"/>')
    add(f'<rect x="{x_out_l}" y="{y(G)}" width="{wall}" height="{12 * s}" fill="{CAST_IRON}"/>')
    add(f'<rect x="{x_in_r}" y="{y(G)}" width="{wall}" height="{12 * s}" fill="{CAST_IRON}"/>')
    add(f'<rect x="{x_in_l}" y="{y(G) - 4}" width="{w}" height="8" fill="{CAST_IRON}"/>')
    for k in range(1, 8):
        gx = x_in_l + k * w / 8
        add(f'<line x1="{gx}" x2="{gx}" y1="{y(G) - 4}" y2="{y(G) + 4}" stroke="#fcfcfb" stroke-width="2"/>')

    # ---------- water ----------
    known = level_cm is not None
    level_floor = inv + (level_cm if known else 0)
    level_floor = max(0.0, min(level_floor, G))
    color = WATER["unknown"] if (stale or not known) else water_color(level_cm, at_limit, sub)
    add(f'<rect x="{x_in_l}" y="{y(level_floor)}" width="{w}" height="{y(0) - y(level_floor)}" '
        f'fill="{color}" fill-opacity="0.72"/>')
    add(f'<line x1="{x_in_l}" x2="{x_in_r}" y1="{y(level_floor)}" y2="{y(level_floor)}" stroke="{color}" stroke-width="3"/>')
    if sump > 0:   # the sump under the water: the sensor can't see what's in it
        add(f'<rect x="{x_in_l}" y="{y(sump)}" width="{w}" height="{y(0) - y(sump)}" fill="url(#hatch)"/>')
        sed = 0 if sediment_cm is None else max(0.0, min(sediment_cm, sump))
        if sed > 0.5:   # ESTIMATED sediment: dashed outline = inferred, not measured
            add(f'<rect x="{x_in_l + 2}" y="{y(sed)}" width="{w - 4}" height="{y(0) - y(sed)}" fill="{SEDIMENT}" '
                f'fill-opacity="0.55" stroke="{SEDIMENT}" stroke-width="2" stroke-dasharray="6 4"/>')
            add(f'<text x="{x_in_l + 6}" y="{min(y(sed / 2) + 6, y(0) - 6)}" font-size="17" fill="#ffffff" '
                f'font-weight="700">est. sediment ~{100 * sed / sump:.0f}%</text>')
        else:
            add(f'<text x="{x_in_l + 6}" y="{y(sump / 2) + 5}" font-size="19" fill="#ffffff" font-weight="700">'
                f'sump: not visible</text>')
    if at_limit and not stale:
        add(f'<rect x="{x_in_l}" y="{y(G) + 4}" width="{w}" height="{y(level_floor) - y(G) - 4}" fill="url(#above)"/>')
        add(f'<text x="{(x_in_l + x_in_r) / 2}" y="{y(G) + 26}" font-size="23" fill="{TEXT}" '
            f'text-anchor="middle">maybe higher</text>')

    # ---------- outlet pipe stub (right wall) and trap ----------
    stub_end = x_out_r + 34
    add(f'<rect x="{x_in_r}" y="{y(inv + D)}" width="{stub_end - x_in_r}" height="{D * s}" fill="#e7e5df" '
        f'stroke="{CONCRETE_DARK}" stroke-width="1.5"/>')
    if level_floor > inv:
        top = min(level_floor, inv + D)
        add(f'<rect x="{x_in_r}" y="{y(top)}" width="{stub_end - x_in_r}" height="{y(inv) - y(top)}" '
            f'fill="{color}" fill-opacity="0.45"/>')
    if b["trap_height_cm"] > 0:
        top_cm = sump + b["trap_height_cm"]
        px = x_in_r - b["trap_projection_cm"] * s
        r = min(b["trap_projection_cm"] * s, (top_cm - sump) * s * 0.4)
        add(f'<path d="M{x_in_r},{y(top_cm)} Q{px},{y(top_cm)} {px},{y(top_cm) + r} L{px},{y(sump)}" '
            f'fill="none" stroke="{CAST_IRON}" stroke-width="5"/>')
    if restriction:
        key, _ = restriction
        rc = STATUS_COLOR[key]
        cx = (x_in_r + stub_end) / 2 if b["trap_height_cm"] == 0 else x_in_r - b["trap_projection_cm"] * s / 2
        cy = y(inv + D / 2) if b["trap_height_cm"] == 0 else y(sump) - 2
        add(f'<circle cx="{cx}" cy="{cy}" r="13" fill="{rc}" stroke="#fff" stroke-width="2"/>')
        add(f'<text x="{cx}" y="{cy + 6}" font-size="24" font-weight="800" fill="#fff" text-anchor="middle">!</text>')

    # ---------- incoming pipes / subdrains (left wall) ----------
    for inlet in inlets:
        h = G - inlet["depth_mm"] / 10
        d = inlet["diameter_mm"] / 10
        add(f'<rect x="{x_out_l - 30}" y="{y(h + d)}" width="{wall + 30}" height="{d * s}" fill="#e7e5df" '
            f'stroke="{CONCRETE_DARK}"/>')
    if sub is not None:
        add(f'<line x1="{x_in_l}" x2="{x_in_r}" y1="{y(inv + sub)}" y2="{y(inv + sub)}" '
            f'stroke="{WATER["backup"]}" stroke-width="1.5" stroke-dasharray="6 4"/>')

    # ---------- grate covered (inferred) ----------
    if grate_blocked:
        for k in range(9):
            lx = x_in_l - 8 + k * (w + 16) / 9
            add(f'<ellipse cx="{lx}" cy="{y(G) - 7}" rx="11" ry="5" fill="{["#8a6d2f", "#a07b2c", "#6f7a2a"][k % 3]}" '
                f'transform="rotate({(k * 37) % 50 - 25} {lx} {y(G) - 7})"/>')

    # ---------- sensor pod: wedge wall mount + ultrasonic cone ----------
    wy = y(hs)
    add(f'<polygon points="{x_in_l},{wy - 20} {x_in_l},{wy + 6} {x_in_l + 26},{wy + 6}" fill="{TEXT}"/>')
    add(f'<rect x="{x_in_l + 4}" y="{wy + 6}" width="18" height="5" fill="#2a78d6"/>')
    cone_bottom = y(max(level_floor, 0))
    spread = (cone_bottom - wy) * 0.18
    add(f'<polygon points="{x_in_l + 13},{wy + 11} {max(x_in_l, x_in_l + 13 - spread)},{cone_bottom} '
        f'{min(x_in_r, x_in_l + 13 + spread)},{cone_bottom}" fill="#2a78d6" opacity="0.10"/>')
    add(f'<line x1="{x_in_l + 13}" x2="{x_in_l + 13}" y1="{wy + 11}" y2="{cone_bottom - 2}" stroke="{TEXT}" '
        f'stroke-width="1.2" stroke-dasharray="4 4"/>')
    # blind zone: the sensor can't read water above this line
    add(f'<line x1="{x_in_l}" x2="{x_in_r}" y1="{y(limit)}" y2="{y(limit)}" stroke="{MUTED}" '
        f'stroke-width="1" stroke-dasharray="2 4"/>')

    # ---------- water label ----------
    if known:
        depth = (G - level_floor) / 100
        txt = f"≤ {depth:.2f} m" if at_limit else f"{depth:.2f} m"
        ly = min(y(level_floor) - 10, y(inv + 4) - 10)
        add(f'<text x="{x_in_l + 30}" y="{ly}" font-size="32" font-weight="700" fill="{TEXT}">{txt}</text>')
        add(f'<text x="{x_in_l + 30}" y="{ly + 17}" font-size="18" fill="{TEXT}">below street</text>'
            if y(level_floor) - y(sump) > 40 else "")
    else:
        add(f'<text x="{(x_in_l + x_in_r) / 2}" y="{y(inv + 25)}" font-size="54" font-weight="700" '
            f'fill="{MUTED}" text-anchor="middle">?</text>')

    # ---------- colour gauge on the left ----------
    gx = 150
    high_top = min(HIGH_WATER_CM, sub) if sub is not None else HIGH_WATER_CM
    zones = [(max(inv - 10, 0), inv + NORMAL_BAND_CM, ZONES["ok"], "Normal"),
             (inv + NORMAL_BAND_CM, inv + high_top, ZONES["high"], "High"),
             (inv + high_top, G, ZONES["backup"], "Backing up")]
    for lo, hi, zc, name in zones:
        add(f'<rect x="{gx}" y="{y(hi)}" width="13" height="{y(lo) - y(hi)}" fill="{zc}"/>')
        add(f'<text x="{gx - 8}" y="{(y(lo) + y(hi)) / 2 + 5}" font-size="23" fill="{TEXT}" text-anchor="end">{name}</text>')
    add(f'<path d="M{gx + 15},{y(level_floor)} l11,-7 v14 z" fill="{TEXT}"/>')

    # ---------- reference depths (right) ----------
    refs = [(G, f"{m_below(b, G)}  Street / grate", TEXT,
             (STATUS_COLOR["clean_soon"], "Grate covered (inferred)") if grate_blocked else None),
            (hs, f"{m_below(b, hs)}  Sensor pod", TEXT, None),
            (limit, f"{m_below(b, limit)}  Sensor range limit", MUTED, None)]
    for inlet in inlets:
        h = G - inlet["depth_mm"] / 10
        refs.append((h, f"{m_below(b, h)}  {inlet['kind']} ø{inlet['diameter_mm']:.0f}", WATER["backup"], None))
    refs.append((inv, f"{m_below(b, inv)}  Outlet invert ø{D * 10:.0f}", TEXT,
                 (STATUS_COLOR[restriction[0]], restriction[1]) if restriction else None))
    refs.append((0, f"{m_below(b, 0)}  Sump floor ({sump * 10:.0f} mm sump)" if sump > 0
                 else f"{m_below(b, 0)}  Floor (no sump)", TEXT, None))
    lx = stub_end + 12
    last_y = -100
    for h, text, tc, extra in sorted(refs, key=lambda r: -r[0]):
        ty = max(y(h) + 7, last_y + 27)
        add(f'<line x1="{x_out_r}" x2="{lx - 4}" y1="{y(h)}" y2="{y(h)}" stroke="{tc}" stroke-width="1" '
            f'stroke-dasharray="2 2"/>')
        if abs(ty - (y(h) + 7)) > 2:
            add(f'<line x1="{lx - 4}" x2="{lx}" y1="{y(h)}" y2="{ty - 5}" stroke="{tc}" stroke-width="1"/>')
        add(f'<text x="{lx + 2}" y="{ty}" font-size="23" fill="{tc}">{text}</text>')
        last_y = ty
        if extra:
            for k, part in enumerate(extra[1].split(": ")):
                add(f'<text x="{lx + 2}" y="{ty + 24 * (k + 1)}" font-size="20" font-weight="700" '
                    f'fill="{extra[0]}">{"! " if k == 0 else "  "}{part}</text>')
            last_y = ty + 24 * len(extra[1].split(": "))
    if raining:
        for k in range(14):
            rx = x_out_l - 55 + k * 22
            ry = 4 + (k % 3) * 9
            add(f'<line x1="{rx}" y1="{ry}" x2="{rx - 5}" y2="{ry + 13}" stroke="{WATER["normal"]}" '
                f'stroke-width="2" stroke-linecap="round"/>')
    add('</svg>')
    return "".join(out)
