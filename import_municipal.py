"""
import_municipal.py
-------------------
Makes a small slice of the Ville de Montréal open-data catch basin layer
("Puisards d'égout", file ego_puisard_p.csv, ~180 000 basins, 78 MB) that the
dashboard can show as grey "unmonitored" dots.

Run it from the project folder with the path to the downloaded file:
    python import_municipal.py C:/Users/you/Downloads/ego_puisard_p.csv
    python import_municipal.py ego_puisard_p.csv --owner "DORVAL - ILE DORVAL"

It writes data/municipal_basins.csv with only the basins of one municipality
(default: Dorval). Don't commit the full 78 MB file to GitHub:
it's too big, and the slice is all the dashboard needs.

Column mapping (Montréal file -> ours):
    ID_PUISARD        -> municipal_id
    ADRESSE           -> address
    LATITUDE/LONGITUDE-> latitude/longitude
    TYPE_PUISARD_EG   -> basin_type      (CIRCULAIRE, RECTANGULAIRE, DE TROTTOIR...)
    DATE_INSTALLATION -> install_date    (1900-01-01 means "unknown" in the source)
    PROPRIETAIRE      -> owner           (the municipality)
    ELEVATION_TERRAIN -> ground_elevation_m (-999 means "unknown")
"""

import argparse
import os

import pandas as pd

DEFAULT_OWNER = "DORVAL - ILE DORVAL"
OUT = os.path.join("data", "municipal_basins.csv")


def make_slice(source, owner=DEFAULT_OWNER):
    df = pd.read_csv(source, encoding="utf-8-sig", low_memory=False)
    df = df[(df["PROPRIETAIRE"] == owner) & (df["STATUT_ACTIF"] == "EXISTANT")]
    out = pd.DataFrame({
        "municipal_id": df["ID_PUISARD"].astype(str),
        "address": df["ADRESSE"].fillna("").str.strip(),
        "latitude": df["LATITUDE"].round(6),
        "longitude": df["LONGITUDE"].round(6),
        "basin_type": df["TYPE_PUISARD_EG"].str.capitalize(),
        "install_date": df["DATE_INSTALLATION"].where(df["DATE_INSTALLATION"] != "1900-01-01", ""),
        "owner": df["PROPRIETAIRE"].str.title(),
        "ground_elevation_m": df["ELEVATION_TERRAIN"].where(df["ELEVATION_TERRAIN"] > -900),
    })
    return out.sort_values("municipal_id").reset_index(drop=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", help="path to ego_puisard_p.csv from donnees.montreal.ca")
    parser.add_argument("--owner", default=DEFAULT_OWNER, help="municipality (PROPRIETAIRE column)")
    args = parser.parse_args()
    sliced = make_slice(args.source, args.owner)
    os.makedirs("data", exist_ok=True)
    sliced.to_csv(OUT, index=False)
    print(f"Saved {len(sliced)} catch basins of {args.owner} to {OUT}")
