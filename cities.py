"""
Liste de villes du monde (GeoNames) + regroupement par cellule de grille NASA.

NASA POWER (météo) a une résolution de 0,5° (latitude) x 0,625° (longitude), soit ~55 x 60 km.
Deux villes dans la même cellule reçoivent EXACTEMENT les mêmes données : on télécharge donc
une seule fois par cellule.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pandas as pd
import requests

GEONAMES_DIR = Path(__file__).parent / "data" / "geonames"
GEONAMES_URL = "https://download.geonames.org/export/dump/{source}.zip"
# source : cities15000 (villes > 15 000 hab.), cities5000, cities1000, cities500
COLUMNS = ["geonameid", "name", "ascii", "alt", "lat", "lon", "fclass", "fcode", "country",
           "cc2", "admin1", "admin2", "admin3", "admin4", "population", "elevation", "dem",
           "timezone", "modified"]


def load_cities(source="cities15000") -> pd.DataFrame:
    """Charge la liste GeoNames (la télécharge une fois, puis la lit depuis data/geonames/)."""
    txt = GEONAMES_DIR / f"{source}.txt"
    if not txt.exists():
        GEONAMES_DIR.mkdir(parents=True, exist_ok=True)
        zpath = GEONAMES_DIR / f"{source}.zip"
        if not zpath.exists():
            print(f"[GeoNames] téléchargement de {source}.zip ...")
            r = requests.get(GEONAMES_URL.format(source=source), timeout=120)
            r.raise_for_status()
            zpath.write_bytes(r.content)
        with zipfile.ZipFile(zpath) as z:
            z.extract(f"{source}.txt", GEONAMES_DIR)
    df = pd.read_csv(txt, sep="\t", header=None, names=COLUMNS, usecols=range(len(COLUMNS)),
                     dtype={"cc2": str, "admin1": str, "admin2": str, "admin3": str, "admin4": str},
                     keep_default_na=False, na_values=[""], quoting=3)
    df["continent"] = df["timezone"].fillna("").str.split("/").str[0].str.lower()
    return df


def snap_to_cell(lat: float, lon: float) -> tuple[float, float]:
    """Centre de la cellule NASA (0,5° x 0,625°) qui contient ce point."""
    return (round(round((lat + 90) / 0.5) * 0.5 - 90, 1),
            round(round((lon + 180) / 0.625) * 0.625 - 180, 3))


def cell_name(lat: float, lon: float) -> str:
    return f"cell_{lat:.1f}_{lon:.3f}"


def select(df, countries=None, continent=None, min_pop=0) -> pd.DataFrame:
    """Filtre par pays (codes ISO : MA, FR...), continent (africa, europe, asia, america...), population."""
    if countries:
        df = df[df["country"].isin([c.upper() for c in countries])]
    if continent:
        df = df[df["continent"] == continent.lower()]
    df = df[df["population"] >= min_pop].copy()
    cells = df.apply(lambda r: snap_to_cell(r["lat"], r["lon"]), axis=1)
    df["cell_lat"] = [c[0] for c in cells]
    df["cell_lon"] = [c[1] for c in cells]
    df["cell"] = [cell_name(a, b) for a, b in cells]
    return df.sort_values("population", ascending=False).reset_index(drop=True)
