"""
basin_catalog.py
----------------
The catalogue of precast catch basin models we know about, and the code that turns
"model + the parts stacked on top of it" into the dimensions the simulator,
the processing and the drawing need.

Sources: Lécuyer catalogue page 263 (P-1) and Phil's notes on the other Lécuyer
models (BNQ 2622-420 / BNQ 1809-300). Values marked VERIFY were NOT in those notes:
they are placeholders to check against the catalogue.

All catalogue values are in MILLIMETRES (like the catalogue).
The rest of the project works in CENTIMETRES, so compute_row() converts.

HOW A BASIN IS BUILT (bottom to top)
    base slab (dalle) + floor (plancher)      <- below the sump floor
    BASE section (contains the sump/réserve and the outlet pipe)
    rings (anneaux C, E, D, rubber), maybe a subdrain ring (anneau E avec drains)
    head (tête) and/or cast-iron frame and grate (fonte)  <- street level
"Depth" in this project = from the sump floor (top of the plancher) up to the grate.
"""

import math

# ---------------------------------------------------------------------------
# PARTS THAT CAN BE STACKED ON TOP OF THE BASE
# ---------------------------------------------------------------------------
PARTS = {
    "C": "Anneau C (rehaussement)",
    "E": "Anneau E (rehaussement)",
    "D": "Anneau D (ajustement)",
    "RUBBER": "Anneau en caoutchouc",
    "E_DRAINS": "Anneau E avec drains",
    "RISER": "Anneau de regard",
    "TRANS": "Dalle de transition",
    "SLOPE": "Section supérieure inclinée",
    "BOURRELET": "Bourrelet",
    "HEAD": "Tête",
    "FRAME": "Cadre et grille en fonte",
}
TOP_PARTS = {"HEAD", "FRAME", "SLOPE", "BOURRELET"}   # parts that are not plain concrete rings

# Cast-iron traps ("cloches") bolted over the outlet, inside the sump.
# Bottom lip sits at the sump depth (300 mm in a P-1, 500 mm in a P-4/P-8).
TRAPS = {
    "TP-3": {"pipe_mm": 200, "height_mm": 470, "width_mm": 375, "projection_mm": 90, "kg": 10},
    "TP-4": {"pipe_mm": 250, "height_mm": 535, "width_mm": 429, "projection_mm": 138, "kg": 15},
    "TP-5": {"pipe_mm": 300, "height_mm": 562, "width_mm": 452, "projection_mm": 157, "kg": 19},
}

PIPE_SIZES_MM = [150, 200, 250, 300, 375, 450, 525, 600, 750]

RING_610 = {
    "C": [400, 100, 150, 200, 250, 300, 450],
    "E": [75, 100, 125, 150, 200, 250, 300, 400, 450],
    "D": [25, 38, 50, 75, 100, 125, 150, 200, 250, 300, 400, 450],
    "RUBBER": [13, 25, 50, 75],
    "FRAME": [300],          # adjustable kit: 300 mm ±25 standard, 70 to 320 mm possible
    "HEAD": [300, 150, 200, 250],
}

MODELS = {
    "P-1": {
        "label": "P-1 · Puisard ø610, réserve 300 mm",
        "shape": "round", "inner_mm": 610, "wall_mm": 95, "floor_mm": 100, "slab_mm": 200,
        "bases": [
            {"label": "Sans drains: base 1000 mm", "base_mm": 1000, "sump_mm": 300, "drains": None},
            {"label": "Avec drains: base 750 mm + anneau E à drains", "base_mm": 750, "sump_mm": 300,
             "drains": "ring"},
        ],
        "drain_above_invert_mm": 450, "max_outlet_mm": 375, "default_outlet_mm": 250,
        "parts": RING_610, "default_stack": [("C", 400), ("FRAME", 300)], "road": True,
        "notes": "Standard municipal street catch basin. Max 3 pipe connections (4 with subdrains). "
                 "A subdrain ring needs a total depth of at least 1050 mm.",
    },
    "P-4": {
        "label": "P-4 · Puisard ø610, réserve 500 mm",
        "shape": "round", "inner_mm": 610, "wall_mm": 95, "floor_mm": 100, "slab_mm": 200,
        "bases": [
            {"label": "Sans drains: base 1200 mm", "base_mm": 1200, "sump_mm": 500, "drains": None},
            {"label": "Avec drains: base 950 mm + anneau E à drains", "base_mm": 950, "sump_mm": 500,
             "drains": "ring"},
        ],
        "drain_above_invert_mm": 450, "max_outlet_mm": 375, "default_outlet_mm": 250,
        "parts": RING_610, "default_stack": [("C", 400), ("FRAME", 300)], "road": True,
        "notes": "Deeper 500 mm sump for high-debris areas or heavy grit loading. "
                 "Same footprint and rings as the P-1.",
    },
    "P-6": {
        "label": "P-6 · Puisard ø405 (hors réseau routier)",
        "shape": "round", "inner_mm": 405, "wall_mm": 75, "floor_mm": 75, "slab_mm": 0,   # slab: VERIFY
        "bases": [
            {"label": "Standard: base 900 mm, réserve 300 mm", "base_mm": 900, "sump_mm": 300, "drains": None},
            {"label": "Courte: base 675 mm, réserve 200 mm", "base_mm": 675, "sump_mm": 200, "drains": None},
        ],
        "drain_above_invert_mm": None, "max_outlet_mm": 250, "default_outlet_mm": 200,
        "parts": {"C": [100, 150, 200, 300], "FRAME": [300]},                               # VERIFY
        "default_stack": [("FRAME", 300)], "road": False,
        "notes": "NOT for roadways: landscaping, parks, backyards. Ring sizes for the P-6 were not in "
                 "the notes, so check them in the catalogue.",
    },
    "P-8": {
        "label": "P-8 · Puisard hybride ø610, réserve 500 mm",
        "shape": "round", "inner_mm": 610, "wall_mm": 75, "floor_mm": 100, "slab_mm": 200,
        "bases": [
            {"label": "Base 1200 mm (drains coulés dans la base, optionnels)", "base_mm": 1200,
             "sump_mm": 500, "drains": "base"},
        ],
        "drain_above_invert_mm": 50, "max_outlet_mm": 300, "default_outlet_mm": 250,
        "parts": {"C": [400, 100, 150, 200, 300], "E": [150, 200, 300, 400], "D": [50, 75, 100],
                  "RUBBER": [13, 25, 50, 75], "HEAD": [200], "FRAME": [200, 300]},
        "default_stack": [("C", 400), ("HEAD", 200), ("FRAME", 200)], "road": True,
        "notes": "Round inside, flat back wall to sit against the curb (head T-15A, 352×581 grate). "
                 "No anneau E à drains: subdrains are cast in the base, 50 mm above the outlet invert.",
    },
    "P-10M": {
        "label": "P-10 modifié · Puisard rectangulaire 950×1150",
        "shape": "rect", "inner_mm": 950, "length_mm": 1150, "wall_mm": 150, "floor_mm": 200,  # wall: VERIFY
        "slab_mm": 0,
        "bases": [{"label": "Base 1650 mm", "base_mm": 1650, "sump_mm": 500, "drains": None}],
        "drain_above_invert_mm": None, "max_outlet_mm": 750, "default_outlet_mm": 450,
        "parts": {"D": [50, 75, 100, 150, 200], "FRAME": [300]},                            # VERIFY
        "default_stack": [("FRAME", 300)], "road": True,
        "notes": "High-capacity basin with twin cast-iron grates (4360 cm² open area). Pipes must enter "
                 "at 90° to the walls (ø750 faces A/C, ø600 face B). No standard trap above ø300.",
    },
    "PF-750": {
        "label": "PF-750 · Puisard de fossé 950×1150",
        "shape": "rect", "inner_mm": 950, "length_mm": 1150, "wall_mm": 150, "floor_mm": 200,  # wall: VERIFY
        "slab_mm": 0,
        "bases": [{"label": "Base 1800 mm", "base_mm": 1800, "sump_mm": 300, "drains": None}],
        "drain_above_invert_mm": None, "max_outlet_mm": 750, "default_outlet_mm": 450,
        "parts": {"SLOPE": [417, 313, 625]},
        "default_stack": [("SLOPE", 417)], "road": False,
        "notes": "Ditch catch basin: sloped top (1:2 = 313, 1:3 = 417 or 1:4 = 625 mm) with a 70 kg "
                 "galvanized steel grate that follows the ditch bank.",
    },
    "P-900": {
        "label": "P-900 · Regard-puisard ø915",
        "shape": "round", "inner_mm": 915, "wall_mm": 100, "floor_mm": 150, "slab_mm": 0,      # wall: VERIFY
        "bases": [
            {"label": "Base 960 mm", "base_mm": 960, "sump_mm": 300, "drains": None},
            {"label": "Base 810 mm", "base_mm": 810, "sump_mm": 300, "drains": None},
            {"label": "Base 1110 mm", "base_mm": 1110, "sump_mm": 300, "drains": None},
        ],
        "drain_above_invert_mm": None, "max_outlet_mm": 450, "default_outlet_mm": 300,
        "parts": {"RISER": [300, 600, 900, 1200], "HEAD": [300, 200, 250, 350, 400, 450],
                  "D": [25, 50, 75, 100, 150, 200], "RUBBER": [13, 25, 50, 75], "FRAME": [300]},
        "default_stack": [("RISER", 300), ("HEAD", 250), ("FRAME", 300)], "road": True,
        "notes": "Catch basin manhole: used when pipe sizes or angles exceed P-1/P-4 limits. Ladder "
                 "rungs inside (watch for false echoes!) and a ø760 chimney at the top.",
    },
    "P-1200": {
        "label": "P-1200 · Regard-puisard ø1220",
        "shape": "round", "inner_mm": 1220, "upper_inner_mm": 915, "wall_mm": 125,            # wall: VERIFY
        "floor_mm": 150, "slab_mm": 0,
        "bases": [
            {"label": "Base 1200 mm", "base_mm": 1200, "sump_mm": 300, "drains": None},
            {"label": "Base 1800 mm", "base_mm": 1800, "sump_mm": 300, "drains": None},
        ],
        "drain_above_invert_mm": None, "max_outlet_mm": 600, "default_outlet_mm": 375,
        "parts": {"TRANS": [200], "RISER": [300, 600, 900, 1200], "HEAD": [300, 250],
                  "D": [25, 50, 75, 100, 150, 200], "FRAME": [300]},
        "default_stack": [("TRANS", 200), ("RISER", 300), ("HEAD", 250), ("FRAME", 300)], "road": True,
        "notes": "Heavy-duty catch basin manhole. A 200 mm transition slab steps down from the ø1220 "
                 "base to a ø915 riser shaft.",
    },
    "CUSTOM": {
        "label": "Custom · enter the dimensions yourself",
        "shape": "round", "inner_mm": 610, "wall_mm": 95, "floor_mm": 100, "slab_mm": 200,
        "bases": [{"label": "Custom base", "base_mm": 1000, "sump_mm": 300, "drains": "ring"}],
        "drain_above_invert_mm": 450, "max_outlet_mm": 750, "default_outlet_mm": 250,
        "parts": {k: [] for k in PARTS}, "default_stack": [("C", 400), ("FRAME", 300)], "road": True,
        "notes": "Use this for a basin that is not in the catalogue.",
    },
}


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------
def trap_for_pipe(pipe_mm):
    """Smallest standard trap that fits this outlet pipe, or None if there isn't one."""
    for name, trap in TRAPS.items():
        if trap["pipe_mm"] >= pipe_mm:
            return name
    return None


def stack_to_text(stack):
    """[("C", 400), ("FRAME", 300)] -> "C:400|FRAME:300" (how it's stored in the CSV)."""
    return "|".join(f"{kind}:{mm:g}" for kind, mm in stack)


def text_to_stack(text):
    if not isinstance(text, str) or not text:
        return []
    return [(part.split(":")[0], float(part.split(":")[1])) for part in text.split("|")]


def default_sensor_mm(base_mm, stack):
    """Default sensor height above the sump floor: 100 mm below the top of the concrete rings
    (for a standard P-1: in the upper half of the 400 mm anneau C)."""
    height = base_mm
    for kind, mm in stack:
        if kind in TOP_PARTS:
            break
        height += mm
    return height - 100


def default_config(model_key, base_index=0):
    """A complete, sensible configuration for a new basin of this model."""
    m = MODELS[model_key]
    base = m["bases"][base_index]
    stack = list(m["default_stack"])
    if base["drains"] == "ring":
        stack.insert(0, ("E_DRAINS", 400))
    outlet = m["default_outlet_mm"]
    return {
        "basin_id": "", "latitude": 45.4440, "longitude": -73.7520,
        "model": model_key, "base_index": base_index, "base_mm": base["base_mm"],
        "sump_mm": base["sump_mm"], "outlet_invert_mm": base["sump_mm"],
        "shape": m["shape"], "inner_mm": m["inner_mm"], "length_mm": m.get("length_mm", m["inner_mm"]),
        "wall_mm": m["wall_mm"], "floor_mm": m["floor_mm"], "slab_mm": m["slab_mm"],
        "stack": stack, "outlet_mm": outlet, "has_trap": trap_for_pipe(outlet) is not None,
        "subdrains": 2 if base["drains"] == "ring" else 0, "subdrain_mm": 150,
        "subdrain_above_invert_mm": m["drain_above_invert_mm"] or 450,
        "sensor_height_mm": default_sensor_mm(base["base_mm"], stack), "blind_zone_mm": 250,
        "catchment_m2": 600, "runoff_coeff": 0.9, "sediment_yield": 0.15,
        "sediment_at_install_mm": 50, "sim_scenario": "healthy",
    }


def depth_mm(cfg):
    """Sump floor to top of the grate."""
    return cfg["base_mm"] + sum(mm for _, mm in cfg["stack"])


def check_config(cfg):
    """Return a list of (level, message) warnings about a configuration."""
    msgs = []
    m = MODELS[cfg["model"]]
    depth = depth_mm(cfg)
    if not m["road"]:
        msgs.append(("info", f"{cfg['model']} is not designed for roadways."))
    if cfg["outlet_mm"] > m["max_outlet_mm"]:
        msgs.append(("error", f"Outlet ø{cfg['outlet_mm']} mm is bigger than the maximum for "
                              f"{cfg['model']} (ø{m['max_outlet_mm']} mm)."))
    if any(k == "E_DRAINS" for k, _ in cfg["stack"]) and depth < 1050:
        msgs.append(("error", "A subdrain ring needs a total depth of at least 1050 mm."))
    if cfg["has_trap"] and trap_for_pipe(cfg["outlet_mm"]) is None:
        msgs.append(("warning", f"No standard trap (TP-3/4/5) for a ø{cfg['outlet_mm']} mm outlet."))
    lowest_readable = cfg["sensor_height_mm"] - cfg["blind_zone_mm"]
    if lowest_readable < cfg["outlet_invert_mm"] + 100:
        msgs.append(("error", "The sensor is too low: its blind zone hides the first 100 mm above "
                              "the normal water level. Move it up."))
    if cfg["sensor_height_mm"] > depth - 150:
        msgs.append(("warning", "The sensor is very close to the grate (less than 150 mm)."))
    if cfg["subdrains"] and lowest_readable < cfg["outlet_invert_mm"] + cfg["subdrain_above_invert_mm"]:
        msgs.append(("info", "The sensor can't see water reaching the subdrains (they are inside its "
                             "blind zone or above it)."))
    for kind, mm in cfg["stack"]:
        options = m["parts"].get(kind, [])
        if options and mm not in options:
            msgs.append(("info", f"{PARTS.get(kind, kind)} {mm:g} mm is not a standard size for "
                                 f"{cfg['model']} (standard: {', '.join(f'{o:g}' for o in options)})."))
    if cfg["sediment_at_install_mm"] >= cfg["sump_mm"]:
        msgs.append(("error", "Sediment at installation fills the whole sump."))
    return msgs


def compute_row(cfg):
    """Configuration (mm) -> one row of the basins CSV (cm), as used by the rest of the project."""
    m = MODELS[cfg["model"]]
    trap = TRAPS.get(trap_for_pipe(cfg["outlet_mm"])) if cfg["has_trap"] else None
    if cfg["shape"] == "round":
        area = math.pi * (cfg["inner_mm"] / 2000) ** 2
    else:
        area = (cfg["inner_mm"] / 1000) * (cfg["length_mm"] / 1000)
    return {
        "basin_id": cfg["basin_id"], "latitude": cfg["latitude"], "longitude": cfg["longitude"],
        "model": cfg["model"], "shape": cfg["shape"],
        "inner_width_cm": cfg["inner_mm"] / 10, "inner_length_cm": cfg["length_mm"] / 10,
        "upper_inner_width_cm": m.get("upper_inner_mm", cfg["inner_mm"]) / 10,
        "wall_cm": cfg["wall_mm"] / 10, "floor_cm": cfg["floor_mm"] / 10, "slab_cm": cfg["slab_mm"] / 10,
        "base_cm": cfg["base_mm"] / 10, "stack": stack_to_text(cfg["stack"]),
        "grate_height_cm": depth_mm(cfg) / 10,
        "sump_depth_cm": cfg["sump_mm"] / 10,                 # = height of the trap's bottom lip
        "outlet_invert_cm": cfg["outlet_invert_mm"] / 10,
        "outlet_diameter_cm": cfg["outlet_mm"] / 10,
        "trap_model": trap_for_pipe(cfg["outlet_mm"]) if trap else "",
        "trap_height_cm": trap["height_mm"] / 10 if trap else 0,
        "trap_width_cm": trap["width_mm"] / 10 if trap else 0,
        "trap_projection_cm": trap["projection_mm"] / 10 if trap else 0,
        "subdrains": int(cfg["subdrains"]), "subdrain_diameter_cm": cfg["subdrain_mm"] / 10,
        "subdrain_height_cm": (cfg["outlet_invert_mm"] + cfg["subdrain_above_invert_mm"]) / 10,
        "sensor_height_cm": cfg["sensor_height_mm"] / 10,
        "sensor_blind_zone_cm": cfg["blind_zone_mm"] / 10,
        "basin_area_m2": round(area, 3), "catchment_area_m2": cfg["catchment_m2"],
        "runoff_coeff": cfg["runoff_coeff"], "sediment_yield_kg_m2_yr": cfg["sediment_yield"],
        "sediment_at_install_cm": cfg["sediment_at_install_mm"] / 10,
        "sim_scenario": cfg["sim_scenario"],
    }
