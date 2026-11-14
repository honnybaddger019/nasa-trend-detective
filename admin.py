"""
Séries NASA par commune, province ou région (à utiliser par les autres membres / le dashboard).

    from admin import unit_series, units
    units("region")                          # tableau des 12 régions
    s = unit_series("region", "03")          # série mensuelle de la région 03 : date | value | n_cells
    s = unit_series("province", "01.511", "PRECTOTCORR")
    s = unit_series("commune", "01.511.01.0")

Pour une province ou une région : moyenne des cellules NASA de ses communes, pondérée par la
population 2024 (weighted=False pour une moyenne simple).
"""
import pandas as pd

from nasa_data import DATA_DIR

_FILES = {"commune": "morocco_communes.csv", "province": "morocco_provinces.csv",
          "region": "morocco_regions.csv"}
_COL = {"commune": "code", "province": "province_code", "region": "region_code"}


def units(level: str) -> pd.DataFrame:
    """Tableau des communes / provinces / régions (lance d'abord build_admin.py)."""
    return pd.read_csv(DATA_DIR / _FILES[level], dtype={"code": str, "region_code": str,
                                                         "province_code": str})


def unit_series(level, code, variable="T2M", start=2000, end=2024, weighted=True, data_dir=DATA_DIR):
    com = units("commune")
    sel = com[com[_COL[level]] == str(code)]
    if sel.empty:
        raise ValueError(f"Aucune commune pour {level} {code!r} (codes : voir units('{level}'))")
    weights = sel.groupby("cell")["population_2024"].sum().clip(lower=1)

    frames = []
    for cell, w in weights.items():
        path = data_dir / f"{cell}_monthly_{start}_{end}.csv"
        if not path.exists():
            continue
        df = pd.read_csv(path, parse_dates=["date"])[["date", variable]].dropna()
        df["w"] = float(w) if weighted else 1.0
        frames.append(df)
    if not frames:
        raise FileNotFoundError("Aucune cellule téléchargée pour cette unité : lance build_admin.py")

    allc = pd.concat(frames)
    allc["vw"] = allc[variable] * allc["w"]
    g = allc.groupby("date").agg(vw=("vw", "sum"), w=("w", "sum"), n_cells=(variable, "count")).reset_index()
    g["value"] = g["vw"] / g["w"]
    return g[["date", "value", "n_cells"]]
