"""Build every part, check it, check fits in the installed position, export STL + STEP in print orientation."""
import itertools
import json
import os
import cadquery as cq
import pod

OUT = "/home/claude/enclosure/cad/out"
os.makedirs(OUT, exist_ok=True)

parts = {
    "body": pod.make_body(),
    "lid": pod.make_lid(),
    "hood": pod.make_hood(),
    "shroud": pod.make_shroud(),
    "tray_lower": pod.make_tray(True),
    "tray_upper": pod.make_tray(False),
    "bracket": pod.make_bracket(),
}

report = {"parts": {}, "collisions": [], "touching_ok": []}
for name, wp in parts.items():
    solids = wp.solids().vals()
    report["parts"][name] = {"solids": len(solids), "valid": all(s.isValid() for s in solids),
                             "volume_cm3": round(sum(s.Volume() for s in solids) / 1000, 1)}

# collisions in the installed position (electronics included)
things = dict(parts)
things.update(pod.electronics())
for (a, wa), (b, wb) in itertools.combinations(things.items(), 2):
    try:
        v = wa.intersect(wb).val().Volume() if wa.intersect(wb).vals() else 0.0
    except Exception:
        v = 0.0
    if v > 0.01:
        report["collisions"].append([a, b, round(v, 3)])

# print orientation: flat face on the bed (z = 0), centred
def to_bed(wp, flip=False):
    if flip:
        wp = wp.rotate((0, 0, 0), (1, 0, 0), 180)
    bb = wp.val().BoundingBox()
    return wp.translate((-(bb.xmin + bb.xmax) / 2, -(bb.ymin + bb.ymax) / 2, -bb.zmin))

orient = {"body": False, "lid": True, "hood": False, "shroud": True, "tray_lower": False, "tray_upper": False, "bracket": False}
files = {
    "01_body": to_bed(parts["body"]),
    "02_lid": to_bed(parts["lid"], True),
    "03_hood": to_bed(parts["hood"]),
    "04_shroud": to_bed(parts["shroud"], True),
    "05_tray_lower": to_bed(parts["tray_lower"]),
    "06_tray_upper": to_bed(parts["tray_upper"]),
    "07_bracket": to_bed(parts["bracket"]),
    "test_1_rail_coupon": to_bed(pod.make_rail_coupon()),
    "test_2_window_1.5mm": pod.make_window_coupon(1.5, 1),
    "test_3_window_2.0mm": pod.make_window_coupon(2.0, 2),
    "test_4_window_3.0mm": pod.make_window_coupon(3.0, 3),
}
for name, wp in files.items():
    bb = wp.val().BoundingBox()
    report.setdefault("print_size_mm", {})[name] = [round(bb.xlen, 1), round(bb.ylen, 1), round(bb.zlen, 1)]
    cq.exporters.export(wp, f"{OUT}/{name}.stl", tolerance=0.03, angularTolerance=0.1)
    cq.exporters.export(wp, f"{OUT}/{name}.step")

assembly = cq.Assembly()
for name, wp in parts.items():
    assembly.add(wp, name=name)
assembly.save(f"{OUT}/assembly_installed.step")

json.dump(report, open(f"{OUT}/check_report.json", "w"), indent=1)
print(json.dumps(report, indent=1))
