"""
basin_model.py
--------------
Describes a catch basin the way a municipality knows it: from its AS-BUILT plans
(plans tel que construit), not from precast shop drawings.

What a city technician usually knows (everything measured DOWN from the grate):
    * inside diameter of the basin
    * outlet invert depth (profondeur du radier) and outlet pipe diameter
    * depth and diameter of any other pipe coming in (subdrain, inlet lead)
    * sump depth (réserve): none, 300 mm standard, or 500 mm deep
    * whether there is a cast-iron trap (cloche) over the outlet
    * where our sensor pod was mounted (default 400 mm below the grate)

build_row() turns that into one row of the basins CSV, which the dashboard,
processing and drawing all use. The CSV works in cm measured UP from the sump floor.
(basin_catalog.py keeps the Lécuyer precast catalogue as a reference.)
"""

from basin_catalog import TRAPS, trap_for_pipe

DIAMETERS = {610: '610 mm (24") standard', 405: '405 mm (16")', 915: '915 mm (36") regard-puisard',
             1220: '1220 mm (48") regard-puisard'}
WALL_MM = {405: 75, 610: 95, 915: 100, 1220: 125}     # 915 and 1220 mm walls: VERIFY with the supplier
PIPE_SIZES_MM = [150, 200, 250, 300, 375, 450, 525, 600]
SUMPS = {0: "None (0 mm)", 300: "300 mm (standard)", 500: "500 mm (deep)"}
INLET_KINDS = ["Subdrain", "Incoming pipe"]
DEFAULT_SENSOR_DEPTH_MM = 400
DEFAULT_BLIND_ZONE_MM = 250


def default_config():
    return {
        "basin_id": "", "sensor_id": "", "municipal_id": "", "address": "",
        "latitude": 45.4440, "longitude": -73.7520,
        "diameter_mm": 610, "invert_depth_mm": 1400, "outlet_mm": 250, "has_trap": True,
        "sump_mm": 300, "inlets": [], "sensor_depth_mm": DEFAULT_SENSOR_DEPTH_MM,
        "blind_zone_mm": DEFAULT_BLIND_ZONE_MM,
        # only used to ESTIMATE the sediment in the sump (the sensor can't see under water)
        "catchment_m2": 600, "runoff_coeff": 0.9, "sediment_yield": 0.15,
        "sediment_at_install_mm": 50, "sim_scenario": "",
    }


def inlets_to_text(inlets):
    """[{"kind": "Subdrain", "depth_mm": 920, "diameter_mm": 150}] -> "Subdrain:920:150" """
    return "|".join(f"{i['kind']}:{i['depth_mm']:g}:{i['diameter_mm']:g}" for i in inlets)


def text_to_inlets(text):
    if not isinstance(text, str) or not text:
        return []
    out = []
    for part in text.split("|"):
        kind, depth, dia = part.split(":")
        out.append({"kind": kind, "depth_mm": float(depth), "diameter_mm": float(dia)})
    return out


def depth_mm(cfg):
    """Grate to sump floor."""
    return cfg["invert_depth_mm"] + cfg["sump_mm"]


def check(cfg):
    """List of (level, message) about a configuration: 'error' blocks saving."""
    msgs = []
    if cfg["outlet_mm"] >= cfg["diameter_mm"]:
        msgs.append(("error", "The outlet pipe is as wide as the basin."))
    lowest_seen = cfg["sensor_depth_mm"] + cfg["blind_zone_mm"]     # closest water to the street we can read
    if lowest_seen > cfg["invert_depth_mm"] - 100:
        msgs.append(("error", "The sensor is too deep: it can't see the first 100 mm of water above the outlet "
                              "invert. Mount it higher."))
    if cfg["sensor_depth_mm"] < 150:
        msgs.append(("warning", "The sensor pod is very close to the grate (less than 150 mm)."))
    if cfg["sump_mm"] == 0:
        msgs.append(("info", "No sump: sediment and debris go straight into the outlet pipe, and there is no "
                             "water seal for a trap."))
    elif cfg["has_trap"] and trap_for_pipe(cfg["outlet_mm"]) is None:
        msgs.append(("info", f"No standard trap for a ø{cfg['outlet_mm']} mm outlet: drawn without one."))
    for inlet in cfg["inlets"]:
        if inlet["depth_mm"] > cfg["invert_depth_mm"]:
            msgs.append(("warning", f"{inlet['kind']} at {inlet['depth_mm']:.0f} mm is deeper than the outlet "
                                    "invert: it would always be under water."))
        if inlet["depth_mm"] < lowest_seen:
            msgs.append(("info", f"{inlet['kind']} at {inlet['depth_mm']:.0f} mm is inside the sensor's blind "
                                 "zone: we can't tell when water reaches it."))
    return msgs


def build_row(cfg):
    """Field configuration (mm, measured down from the grate) -> basins CSV row (cm, up from the floor)."""
    import math
    depth = depth_mm(cfg)
    trap_name = trap_for_pipe(cfg["outlet_mm"]) if (cfg["has_trap"] and cfg["sump_mm"] > 0) else None
    trap = TRAPS.get(trap_name) if trap_name else None
    inlets = sorted(cfg["inlets"], key=lambda i: -i["depth_mm"])          # deepest (lowest) first
    lowest = inlets[0] if inlets else None
    d = cfg["diameter_mm"]
    return {
        "basin_id": cfg["basin_id"], "sensor_id": cfg.get("sensor_id", ""),
        "municipal_id": cfg.get("municipal_id", ""), "address": cfg.get("address", ""),
        "latitude": cfg["latitude"], "longitude": cfg["longitude"],
        "model": f"ø{d} mm", "shape": "round",
        "inner_width_cm": d / 10, "inner_length_cm": d / 10, "upper_inner_width_cm": d / 10,
        "wall_cm": WALL_MM.get(d, 95) / 10, "floor_cm": 10.0, "slab_cm": 20.0,
        "base_cm": depth / 10, "stack": "",
        "grate_height_cm": depth / 10,
        "invert_depth_cm": cfg["invert_depth_mm"] / 10,
        "sump_depth_cm": cfg["sump_mm"] / 10,
        "outlet_invert_cm": cfg["sump_mm"] / 10,
        "outlet_diameter_cm": cfg["outlet_mm"] / 10,
        "trap_model": trap_name or "",
        "trap_height_cm": trap["height_mm"] / 10 if trap else 0,
        "trap_width_cm": trap["width_mm"] / 10 if trap else 0,
        "trap_projection_cm": trap["projection_mm"] / 10 if trap else 0,
        "inlets": inlets_to_text(inlets),
        "subdrains": len(inlets),
        "subdrain_diameter_cm": lowest["diameter_mm"] / 10 if lowest else 0,
        "subdrain_height_cm": (depth - lowest["depth_mm"]) / 10 if lowest else 0,
        "sensor_depth_cm": cfg["sensor_depth_mm"] / 10,
        "sensor_height_cm": (depth - cfg["sensor_depth_mm"]) / 10,
        "sensor_blind_zone_cm": cfg["blind_zone_mm"] / 10,
        "basin_area_m2": round(math.pi * (d / 2000) ** 2, 3),
        "catchment_area_m2": cfg["catchment_m2"], "runoff_coeff": cfg["runoff_coeff"],
        "sediment_yield_kg_m2_yr": cfg["sediment_yield"],
        "sediment_at_install_cm": min(cfg["sediment_at_install_mm"], cfg["sump_mm"]) / 10,
        "sim_scenario": cfg["sim_scenario"],
    }
