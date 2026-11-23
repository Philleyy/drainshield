# DrainShield sensor pod: print files (option B, prototype v1)

Ridged hood, slide-down wall bracket with a latch, window shroud. Sized for a 610 mm precast catch basin.
All sizes in millimetres. Every STL is already turned the way it should sit on the printer bed.

## Print these first (about an hour)

| File | What it tests |
|---|---|
| `07_bracket.stl` + `test_1_rail_coupon.stl` | The rail should slide into the bracket claws by hand, without wobble, and the latch should click over the tooth. |
| `test_2/3/4_window_*.stl` | 1.5, 2.0 and 3.0 mm radar windows (1, 2, 3 notches). Hold each under the radar and compare readings. |

If the slide is too tight, too loose, or the latch won't click, stop and adjust before printing the rest.

## Then the full set

| File | Size (mm) | Supports | Notes |
|---|---|---|---|
| `01_body.stl` | 75 × 54 × 42.5 | None | Floor on the bed. The radar window is the 1.5 mm floor patch: must print solid. |
| `02_lid.stl` | 75 × 51 × 3 | None | Gasket groove faces up as printed. |
| `03_hood.stl` | 87 × 69 × 66 | None | Open side down. Roof slopes are 45°+. |
| `04_shroud.stl` | 75 × 54 × 30 | None | Flange on the bed. |
| `05_tray_lower.stl` | 62 × 45 × 2 | None | Battery tray, with Velcro strap slots. |
| `06_tray_upper.stl` | 62 × 45 × 5 | None | ESP32 tray with two standoffs. |
| `07_bracket.stl` | 69 × 10 × 42 | None | Prints standing up. Use a brim (it's tall and thin). |

The only overhangs are the tops of small screw holes and ledges under 3 mm, which bridge fine.

## Suggested slicer settings

- Material: **PETG** (handles water and cold better than PLA). PLA is OK for a table demo only.
- 0.4 mm nozzle, 0.2 mm layers.
- 4 walls (perimeters). Bottom and top shell at least 2.5 mm, so the floor, window and lid print fully solid.
- 30–40 % infill (gyroid or grid).
- No supports. Brim on the bracket only.
- Total plastic for one pod: under 190 g even if printed solid.

## Fits built in

| Feature | Value |
|---|---|
| Rails in bracket claws, hood sleeve over body, shroud to bracket | 0.4 mm gap per side |
| Radar window | 1.5 mm solid; 2.5 mm air gap to the radar chip |
| M3 heat-set insert holes | Ø 4.0 mm (check your inserts' recommended hole) |
| M3 clearance holes | Ø 3.4 mm |
| Gasket groove (lid underside) | 2.0 wide × 1.2 deep, for 2 mm O-ring cord |
| Concrete screw holes (bracket) | Ø 6.5 mm, 90° countersink, for 6 mm (1/4") flat-head stainless screws |

## Hardware

- 10 × M3 heat-set inserts (4 lid, 2 hood, 4 shroud)
- 4 × M3 × 8 (lid), 1 × M3 × 10 (hood, left side), 1 × M3 × 12 (hood, front), 4 × M3 × 6 (shroud), stainless
- 6 × M2.5 × 6 self-tapping screws for the boards (4 radar, 2 ESP32)
- About 260 mm of 2 mm rubber O-ring cord (or a TPU-printed gasket)
- 2 × 6 mm (1/4") stainless flat-head concrete screws, 30–40 mm long
- 20 mm Velcro strap for the battery

## Assembly

1. Press the heat-set inserts in with a soldering iron: 4 in the lid bosses (top corners), 1 on the left side, 1 on the front, 4 under the floor.
2. Screw the radar board to the 4 floor posts, chip facing down at the window. Plug in the Qwiic cable.
3. Drop in the lower tray (it rests on ledges). Strap the battery to it. Run the battery lead and Qwiic cable up the slot at the right end.
4. Drop in the upper tray. Screw the ESP32 board to its standoffs. Plug in the Qwiic cable, then the battery (check + and − first).
5. Power on and check that readings reach the website.
6. Lay the O-ring cord in the lid groove. Screw the lid down evenly.
7. Slide the hood over the top and fit its 2 screws (left and front).
8. Screw the shroud under the floor.
9. Water test: spray, then submerge 10 minutes; look for drops inside.
10. Screw the bracket to the wall, then slide the pod down until the latch clicks. To remove: push the latch arm toward the wall with a flat screwdriver from below and lift.

## Measure before the full print

These positions came from a layout, not from the real boards:

- Radar board posts: x = ±22.2, d = ±9.5 (centre of the floor).
- ESP32 standoffs: (−29, 8.5) and (23, −9) on the upper tray.
- Board connector heights and the Qwiic connector beside the radar posts.

Measure the real boards with calipers. If they differ, edit the numbers in `src/pod.py` and rerun `build.py`, or import the STEP files into Onshape and move the posts there.

## Files

- `stl/`: print files, already oriented for the bed.
- `step/`: the same parts as STEP for CAD (Onshape, Fusion), plus `assembly_installed.step` with all parts in place.
- `src/`: the CadQuery source (`pod.py`, `build.py`). `python build.py` rebuilds everything and checks for collisions.
