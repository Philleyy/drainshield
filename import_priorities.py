"""
import_priorities.py: add the pilot prioritization to the dashboard
--------------------------------------------------------------------
Reads the prioritization analysis (puisards_dorval_prioritized.csv: catchment area,
local low points, tiers A-F, combined score, the 10 pilot sites) and keeps only what
the dashboard needs, in data/basin_priorities.csv (one row per city catch basin).

    python import_priorities.py path/to/puisards_dorval_prioritized.csv

Run it again whenever the analysis is updated. The tiers are a RANKING for choosing
pilot sites (prioritization, not prediction): they come from the inventory points,
not from real terrain, and only about a third of the basins have an elevation.
"""

import argparse
import os

import pandas as pd

OUT = os.path.join("data", "basin_priorities.csv")


def compatibility(row):
    """Can our bracket go in this basin, in plain words."""
    if row["FLAG_DUP_COORD"]:
        return "Duplicate position in the inventory: check on site"
    if not row["FLAG_VISIBLE"]:
        return "Not visible on site (paved over?)"
    return {"CIRCULAIRE": "Round: fits the DrainShield bracket",
            "INCONNU": "Type unknown in the inventory: check on site",
            "RECTANGULAIRE": "Rectangular: bracket not designed yet",
            "DE TROTTOIR": "Curb inlet: bracket not designed yet"}.get(row["TYPE_PUISARD_EG"], "Unknown")


def main(path):
    p = pd.read_csv(path, low_memory=False)
    tier = p["TIER"].fillna("")
    out = pd.DataFrame({
        "municipal_id": p["ID_PUISARD"].astype(str),
        "tier": tier.str.extract(r"^([A-F]):", expand=False).fillna("–"),   # "–" = not sensor-compatible
        "tier_label": tier,
        "score": p["COMBINED_SCORE"].round(3),
        "catchment_m2": p["CATCH_AREA_75M_M2"],          # nearest-basin area within 75 m (rough)
        "low_point": p["LOCAL_LOW_POINT"] | p["LOW_VS_NEIGHBOURS"],    # same rule as the tiers
        "below_neighbours_m": (-p["ELEV_VS_NEIGHBOURS_M"]).round(2),   # + = lower than the basins around it
        "elevation_known": p["ELEV_KNOWN"],
        "sensor_compatible": p["SENSOR_COMPATIBLE"],
        "compatibility": p.apply(compatibility, axis=1),
        "pilot_site": p["PILOT_SITE"].astype("Int64"),
        "pilot_role": p["PILOT_ROLE"],
    })
    os.makedirs("data", exist_ok=True)
    out.to_csv(OUT, index=False)
    print(f"Saved {len(out):,} basins to {OUT}")
    print(out["tier"].value_counts().sort_index().to_string())
    print(f"Pilot sites: {out['pilot_site'].nunique()} ({out['pilot_site'].notna().sum()} basins)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", help="puisards_dorval_prioritized.csv")
    main(ap.parse_args().csv)
