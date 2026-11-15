"""
Découpage administratif du Maroc (HCP 2024) -> données NASA par commune, province et région.

    python3 build_admin.py                 # construit les tables + télécharge les cellules NASA manquantes
    python3 build_admin.py --no-download   # construit seulement les tables (rapide, sans NASA)

Source du découpage : jeu de données ouvert "morocco-communes" (github.com/zkousama/morocco-communes),
construit à partir du HCP (RGPH 2024, licence CC BY 4.0) et d'OpenStreetMap (centroïdes, licence ODbL).
Cites-les dans le README / les slides.

Résultat dans data/ :
    morocco_regions.csv     12 régions
    morocco_provinces.csv   75 provinces/préfectures (+ 8 préfectures d'arrondissements)
    morocco_communes.csv    1 503 communes, avec la cellule NASA et le fichier CSV de chacune
"""
import argparse
import json
import time

import pandas as pd
import requests

from cities import snap_to_cell, cell_name
from nasa_data import DATA_DIR, get_nasa_data

BASE = "https://raw.githubusercontent.com/zkousama/morocco-communes/main/data/v1/attributes/"
ADMIN_DIR = DATA_DIR / "admin"
VARIABLES = ["T2M", "PRECTOTCORR"]


def fetch(name: str, refresh=False):
    """Télécharge un fichier du jeu de données (une seule fois, ensuite lu depuis data/admin/)."""
    ADMIN_DIR.mkdir(parents=True, exist_ok=True)
    path = ADMIN_DIR / name
    if refresh or not path.exists():
        print(f"[admin] téléchargement {name} ...")
        r = requests.get(BASE + name, timeout=60)
        r.raise_for_status()
        path.write_bytes(r.content)
    return path


def build_tables(start=2000, end=2024):
    regions = pd.read_csv(fetch("regions.csv"), dtype=str, encoding="utf-8-sig")
    provinces = pd.read_csv(fetch("provinces.csv"), dtype=str, encoding="utf-8-sig")
    raw = json.loads(fetch("communes.json").read_text(encoding="utf-8"))

    rows = []
    for x in raw:
        c = x.get("centroid") or {}
        rows.append({
            "code": x["code"], "name_fr": x["name"]["fr"], "name_ar": x["name"]["ar"],
            "type": x["type"],
            "region_code": x["parents"]["region"], "province_code": x["parents"]["province"],
            "population_2024": (x["population"].get("2024") or {}).get("total"),
            "population_2014": (x["population"].get("2014") or {}).get("total"),
            "area_km2": x.get("areaKm2"), "lat": c.get("lat"), "lon": c.get("lng"),
        })
    com = pd.DataFrame(rows)

    # commune sans centroïde : on prend la moyenne des communes de sa province
    for i in com.index[com["lat"].isna()]:
        sib = com[(com["province_code"] == com.at[i, "province_code"]) & com["lat"].notna()]
        com.loc[i, ["lat", "lon"]] = [sib["lat"].mean(), sib["lon"].mean()]
        print(f"[admin] pas de centroïde pour {com.at[i, 'name_fr']} : moyenne de sa province")

    cells = [snap_to_cell(a, b) for a, b in zip(com["lat"], com["lon"])]
    com["cell_lat"] = [c[0] for c in cells]
    com["cell_lon"] = [c[1] for c in cells]
    com["cell"] = [cell_name(*c) for c in cells]
    com["file"] = [f"{c}_monthly_{start}_{end}.csv" for c in com["cell"]]

    reg_names = regions.set_index("code")["name_fr"]
    prov_names = provinces.set_index("code")["name_fr"]
    com.insert(6, "region_name", com["region_code"].map(reg_names))
    com.insert(8, "province_name", com["province_code"].map(prov_names))

    # nombre de communes et de cellules par province / région
    for tbl, col in ((provinces, "province_code"), (regions, "region_code")):
        g = com.groupby(col)
        tbl["n_communes_found"] = tbl["code"].map(g.size()).fillna(0).astype(int)
        tbl["n_cells"] = tbl["code"].map(g["cell"].nunique()).fillna(0).astype(int)

    DATA_DIR.mkdir(exist_ok=True)
    com.to_csv(DATA_DIR / "morocco_communes.csv", index=False, encoding="utf-8-sig")
    provinces.to_csv(DATA_DIR / "morocco_provinces.csv", index=False, encoding="utf-8-sig")
    regions.to_csv(DATA_DIR / "morocco_regions.csv", index=False, encoding="utf-8-sig")

    n_prov = int((provinces["type"] != "prefecture_of_arrondissements").sum())
    print(f"\n{len(regions)} régions | {n_prov} provinces et préfectures "
          f"(+ {len(provinces) - n_prov} préfectures d'arrondissements) | {len(com)} communes "
          f"({(com['type'] == 'urban').sum()} urbaines, {(com['type'] == 'rural').sum()} rurales)")
    print(f"{com['cell'].nunique()} cellules NASA couvrent toutes les communes")
    return com


def download(com, start=2000, end=2024, pause=1.0):
    cells = com.drop_duplicates("cell")[["cell", "cell_lat", "cell_lon"]]
    todo = [r for r in cells.itertuples() if not (DATA_DIR / f"{r.cell}_monthly_{start}_{end}.csv").exists()]
    print(f"{len(cells) - len(todo)} cellules déjà en cache, {len(todo)} à télécharger "
          f"(~{len(todo) * (pause + 2) / 60:.0f} min)")
    failed = []
    for i, r in enumerate(todo, 1):
        print(f"({i}/{len(todo)}) {r.cell}")
        try:
            get_nasa_data(r.cell_lat, r.cell_lon, start, end, VARIABLES, name=r.cell)
        except Exception as err:          # une cellule qui échoue ne bloque pas les autres
            print(f"  ECHEC : {err}")
            failed.append(r.cell)
        time.sleep(pause)
    print(f"\nTerminé. Échecs : {failed or 'aucun'}  (relance la commande pour réessayer)")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", type=int, default=2000)
    p.add_argument("--end", type=int, default=2024)
    p.add_argument("--pause", type=float, default=1.0)
    p.add_argument("--no-download", action="store_true")
    a = p.parse_args()
    com = build_tables(a.start, a.end)
    if not a.no_download:
        download(com, a.start, a.end, a.pause)


if __name__ == "__main__":
    main()
