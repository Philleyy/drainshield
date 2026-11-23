"""DrainShield sensor pod, option B: printable parts.

Design frame (mm): x = width (left/right), u = up, d = toward the basin centre.
The concrete wall is a 610 mm cylinder whose surface passes d = -36 at x = 0.
CadQuery frame: X = x, Y = -d, Z = u (right-handed, no mirroring).
Parts are built in place (installed position), checked for collisions,
then rotated to their print orientation and exported as STL + STEP.
"""
import math
import cadquery as cq
from cadquery import Vector as V

R, CZ = 305.0, 269.0                     # basin wall radius; axis at d = 269
FIT = 0.4                                # sliding-fit gap per side
INSERT_D, CLEAR_D = 4.0, 3.4             # M3 heat-set insert hole, M3 clearance hole


def P(x, u, d):
    return V(x, -d, u)


def box(xr, ur, dr):
    (x0, x1), (u0, u1), (d0, d1) = xr, ur, dr
    return cq.Workplane("XY").box(x1 - x0, d1 - d0, u1 - u0, centered=False).translate((x0, -d1, u0))


def wall_cyl(r, u0=-80, u1=160):
    """Solid cylinder sharing the basin's axis: intersect with it to stay r from the axis."""
    return cq.Workplane(obj=cq.Solid.makeCylinder(r, u1 - u0, V(0, -CZ, u0), V(0, 0, 1)))


def cyl(r, start, direction, length):
    return cq.Workplane(obj=cq.Solid.makeCylinder(r, length, start, direction))


def cone(r1, r2, start, direction, length):
    return cq.Workplane(obj=cq.Solid.makeCone(r1, r2, length, start, direction))


def loft(*rings):
    wires = [cq.Wire.makePolygon([P(*p) for p in ring], close=True) for ring in rings]
    return cq.Workplane(obj=cq.Solid.makeLoft(wires, True))


def rect_ring(xr, dr, u):
    (x0, x1), (d0, d1) = xr, dr
    return [(x0, u, d0), (x1, u, d0), (x1, u, d1), (x0, u, d1)]


def prism_x(x0, x1, pts_du):
    """Prism along x from a polygon given as (d, u) points."""
    a = [(x0, u, d) for d, u in pts_du]
    b = [(x1, u, d) for d, u in pts_du]
    return loft(a, b)


def wall_z(x):
    return CZ - math.sqrt(R * R - x * x)


# ------------------------------------------------------------------ body
def make_body():
    outer = box((-37.5, 37.5), (-2.5, 40), (-25.5, 25.5)).edges("|Z").fillet(2.0)
    body = outer.cut(box((-35, 35), (0, 41), (-23, 23)))
    body = body.cut(box((-22, 22), (-1.0, 0.01), (-15, 15)))          # window: 1.5 mm solid, pocketed from inside

    # radar posts (module ends 2.5 mm above the window)
    for x in (-22.2, 22.2):
        for d in (-9.5, 9.5):
            body = body.union(cyl(2.5, P(x, -1.0, d), V(0, 0, 1), 5.5))
            body = body.cut(cyl(1.25, P(x, 0.5, d), V(0, 0, 1), 4.1))  # M2.5 pilot

    # tray ledges: 45° chamfer underneath, so they print without support
    for top in (10.0, 23.0):
        for s in (-1, 1):
            w = 23.2
            body = body.union(prism_x(-35, 28, [(s * w, top - 2.5), (s * w, top), (s * (w - 2.5), top)]))

    # lid bosses (4 corners) with 45° gussets, M3 insert holes from the top
    for sx in (-1, 1):
        for sd in (-1, 1):
            xr = (27, 35.5) if sx > 0 else (-35.5, -27)
            dr = (15, 23.5) if sd > 0 else (-23.5, -15)
            cx_, cd_ = sx * 35.45, sd * 23.45
            body = body.union(box(xr, (29, 40), dr))
            body = body.union(loft(rect_ring((cx_ - 0.05, cx_ + 0.05), (cd_ - 0.05, cd_ + 0.05), 20.0), rect_ring(xr, dr, 29)))
            body = body.cut(cyl(INSERT_D / 2, P(sx * 31, 34, sd * 19), V(0, 0, 1), 6.1))

    # hood screw pads: left side and front, with 45° gussets
    # left pad sits above the ESP32 board's edge (board top at u = 29.7)
    body = body.union(box((-35.5, -30.5), (35.5, 40), (-5, 5)))
    body = body.union(loft(rect_ring((-35.5, -35.4), (-5, 5), 30.0), rect_ring((-35.5, -30.5), (-5, 5), 35.5)))
    body = body.cut(cyl(INSERT_D / 2, P(-37.6, 37.5, 0), V(1, 0, 0), 7.0))
    body = body.union(box((-5, 5), (32, 40), (17, 23.5)))
    body = body.union(loft(rect_ring((-5, 5), (23.4, 23.5), 25.0), rect_ring((-5, 5), (17, 23.5), 32)))
    body = body.cut(cyl(INSERT_D / 2, P(0, 36, 25.6), V(0, 1, 0), 7.6))   # +Y = toward the wall (-d)

    # floor pads for the shroud screws, inserts from underneath
    for sx in (-1, 1):
        for sd in (-1, 1):
            body = body.union(box((29, 35.5) if sx > 0 else (-35.5, -29), (-0.5, 3.5), (16, 23.5) if sd > 0 else (-23.5, -16)))
            body = body.cut(cyl(INSERT_D / 2, P(sx * 32, -2.6, sd * 19.5), V(0, 0, 1), 5.6))

    # T-rails on the back (slide into the bracket claws)
    for s in (-1, 1):
        body = body.union(box((25, 28) if s > 0 else (-28, -25), (-2.5, 28), (-27.1, -25.4)))
        body = body.union(box((23, 31) if s > 0 else (-31, -23), (-2.5, 28), (-28.6, -27.0)))

    # latch tooth: ramp underneath, flat on top (the bracket's latch catches the top)
    body = body.union(prism_x(-5, 5, [(-25.4, -2.5), (-27.0, -0.5), (-25.4, -0.5)]))
    return body


# ------------------------------------------------------------------ lid
def make_lid():
    lid = box((-37.5, 37.5), (40, 43), (-25.5, 25.5)).edges("|Z").fillet(2.0)
    groove = box((-37.25, 37.25), (39.9, 41.2), (-25.25, 25.25)).cut(box((-35.25, 35.25), (39, 42), (-23.25, 23.25)))
    lid = lid.cut(groove)                       # 2.0 wide x 1.2 deep, centred on the 2.5 mm rim
    for sx in (-1, 1):
        for sd in (-1, 1):
            lid = lid.cut(cyl(CLEAR_D / 2, P(sx * 31, 39.9, sd * 19), V(0, 0, 1), 3.2))
    return lid


# ------------------------------------------------------------------ hood
APEX_BACK, APEX_FRONT, EAVE_U, EAVE_X = 96.0, 88.0, 44.0, 42.5


def make_hood():
    back, front = -36.0, 33.5
    outer = loft([(-EAVE_X, EAVE_U, back), (EAVE_X, EAVE_U, back), (0, APEX_BACK, back)],
                 [(-EAVE_X, EAVE_U, front), (EAVE_X, EAVE_U, front), (0, APEX_FRONT, front)])
    outer = outer.intersect(wall_cyl(R - 1.5))
    inner = loft([(-40, 43, -34), (40, 43, -34), (0, APEX_BACK - 3.5, -34)],
                 [(-40, 43, 31), (40, 43, 31), (0, APEX_FRONT - 3.5, 31)])
    inner = inner.intersect(wall_cyl(R - 4.0))
    hood = outer.cut(inner)

    # skirt: sleeve over the body top + drip edge, 30 -> 45
    skirt = box((-43.5, 43.5), (30, 45), (-40, 34)).intersect(wall_cyl(R - 1.5))
    skirt = skirt.cut(box((-37.5 - FIT, 37.5 + FIT), (29, 46), (-25.5 - FIT, 25.5 + FIT)))
    hood = hood.union(skirt)

    # screw holes (left side and front) with counterbores for the heads
    hood = hood.cut(cyl(CLEAR_D / 2, P(-44, 37.5, 0), V(1, 0, 0), 7))
    hood = hood.cut(cyl(3.3, P(-44, 37.5, 0), V(1, 0, 0), 2.5))
    hood = hood.cut(cyl(CLEAR_D / 2, P(0, 36, 34.5), V(0, 1, 0), 9))
    hood = hood.cut(cyl(3.3, P(0, 36, 34.5), V(0, 1, 0), 3))
    return hood


# ------------------------------------------------------------------ shroud
def make_shroud():
    flange = box((-37.5, 37.5), (-4.5, -2.5), (-25.5, 25.5)).edges("|Z").fillet(2.0)
    flange = flange.cut(box((-25, 25), (-5, -2), (-18, 18)))
    # back face stays vertical so a screwdriver can reach the latch behind it
    outer = loft(rect_ring((-27, 27), (-20, 20), -2.6), rect_ring((-35, 35), (-20, 28), -32))
    inner = loft(rect_ring((-25, 25), (-18, 18), -4.4), rect_ring((-33, 33), (-18, 26), -32.1))
    inner = inner.union(box((-24.9, 24.9), (-4.6, -2.4), (-17.9, 17.9)))
    shroud = flange.union(outer).cut(inner)
    for sx in (-1, 1):
        for sd in (-1, 1):
            shroud = shroud.cut(cyl(CLEAR_D / 2, P(sx * 32, -5, sd * 19.5), V(0, 0, 1), 3))
    return shroud


# ------------------------------------------------------------------ trays
def make_tray(lower):
    u0 = 10.0 if lower else 23.0
    tray = box((-34.7, 27.7), (u0, u0 + 2), (-22.7, 22.7))
    if lower:
        for s in (-1, 1):                                          # slots for a 20 mm Velcro strap
            tray = tray.cut(box((-15, 9), (u0 - 1, u0 + 3), (18.5, 21) if s > 0 else (-21, -18.5)))
    else:
        for s in (-1, 1):                                          # clear the lid bosses
            dr = (14.6, 23) if s > 0 else (-23, -14.6)
            tray = tray.cut(box((-35, -26.6), (u0 - 1, u0 + 3), dr))
            tray = tray.cut(box((26.6, 28), (u0 - 1, u0 + 3), dr))
        for x, d in ((-29, 8.5), (23, -9)):                         # ESP32 standoffs
            tray = tray.union(cyl(2.5, P(x, u0 + 1.9, d), V(0, 0, 1), 3.1))
            tray = tray.cut(cyl(1.1, P(x, u0 + 1, d), V(0, 0, 1), 4.1))
    return tray


# ------------------------------------------------------------------ bracket
def make_bracket():
    base = box((-34.4, 34.4), (-14, 28), (-37.5, -29)).intersect(wall_cyl(R - 0.2))   # back follows the wall
    base = base.cut(box((-6.5, 6.5), (-15, 22), (-38, -28)))                           # slot the latch flexes into
    br = base
    for s in (-1, 1):
        br = br.union(box((31.4, 34.4) if s > 0 else (-34.4, -31.4), (-4.5, 28), (-29.05, -25.9)))   # claw sides
        br = br.union(box((28.6, 34.4) if s > 0 else (-34.4, -28.6), (-4.5, 28), (-26.6, -25.9)))    # claw lips
        br = br.union(box((23, 31) if s > 0 else (-31, -23), (-4.5, -2.9), (-29.05, -26.8)))         # stop tabs
    # latch: 1.6 mm spring arm hanging from the plate, bump with a ramp on top, flat underneath
    br = br.union(box((-5, 5), (-14, 24), (-29.5, -27.9)))
    br = br.union(prism_x(-5, 5, [(-28.0, -0.1), (-26.0, -0.1), (-28.0, 2.5)]))
    # two countersunk holes for 6 mm stainless concrete screws (flat head)
    for x, u in ((-15, 20), (15, 2)):
        br = br.cut(cyl(3.25, P(x, u, -29.0), V(0, 1, 0), 12))
        br = br.cut(cone(6.6, 3.25, P(x, u, -28.95), V(0, 1, 0), 3.35))
    return br


# ------------------------------------------------------------------ coupons
def make_rail_coupon():
    c = box((-37.5, 37.5), (-2.5, 20), (-25.5, -23))
    for s in (-1, 1):
        c = c.union(box((25, 28) if s > 0 else (-28, -25), (-2.5, 20), (-27.1, -25.3)))
        c = c.union(box((23, 31) if s > 0 else (-31, -23), (-2.5, 20), (-28.6, -27.0)))
    c = c.union(prism_x(-5, 5, [(-25.4, -2.5), (-27.0, -0.5), (-25.4, -0.5)]))
    return c


def make_window_coupon(t, notches):
    c = cq.Workplane("XY").box(30, 30, t, centered=False)
    for i in range(notches):
        c = c.cut(cq.Workplane("XY").box(3, 3, t + 2, centered=False).translate((3 + 5 * i, -1, -1)))
    return c


# ------------------------------------------------------------------ electronics (for collision checks only)
def electronics():
    return {
        "radar board": box((-25.4, 25.4), (4.5, 6.1), (-12.7, 12.7)),
        "radar module": box((-9.3, 9.3), (1.5, 4.5), (-7.5, 7.5)),
        "battery": box((-33, 27), (12.1, 19.1), (-18, 18)),
        "esp board": box((-32.2, 26.2), (28.1, 29.7), (-11.45, 11.45)),
        "esp usb-c": box((20.3, 27.7), (29.7, 32.9), (-4.5, 4.5)),
    }
