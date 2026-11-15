"""
Télécharge les données NASA pour TOUTES les villes d'un pays / continent (liste GeoNames).

    python3 download_cities.py --country MA EH --dry-run     # compte seulement (rien n'est téléchargé)
    python3 download_cities.py --country MA EH               # tout le Maroc (EH = Sahara : Laâyoune, Dakhla)
    python3 download_cities.py --continent africa --min-pop 100000
    python3 download_cities.py --country FR ES --min-pop 50000
    python3 download_cities.py --country MA --source cities5000     # + de petites villes

Résultat : un CSV par CELLULE NASA dans data/ + data/cities_index.csv (ville -> fichier).
"""
import argparse
import time

import pandas as pd

from cities import cell_name, load_cities, select
from nasa_data import DATA_DIR, get_nasa_data

VARIABLES = ["T2M", "PRECTOTCORR"]
MAX_WITHOUT_YES = 300      # au-delà, on demande --yes (sécurité)
INDEX = DATA_DIR / "cities_index.csv"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--country", nargs="+", help="codes pays : MA FR ES ...")
    p.add_argument("--continent", help="africa | europe | asia | america | australia | pacific ...")
    p.add_argument("--min-pop", type=int, default=0, help="population minimale")
    p.add_argument("--source", default="cities15000",
                   help="cities15000 (défaut) | cities5000 | cities1000 | cities500")
    p.add_argument("--start", type=int, default=2000)
    p.add_argument("--end", type=int, default=2024)
    p.add_argument("--pause", type=float, default=1.0)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--yes", action="store_true", help="confirme un gros téléchargement")
    a = p.parse_args()
    if not (a.country or a.continent):
        raise SystemExit("Précise --country MA (par ex.) ou --continent africa")

    cities = select(load_cities(a.source), a.country, a.continent, a.min_pop)
    cells = cities.drop_duplicates("cell")[["cell", "cell_lat", "cell_lon"]]
    todo = [r for r in cells.itertuples()
            if not (DATA_DIR / f"{r.cell}_monthly_{a.start}_{a.end}.csv").exists()]
    print(f"{len(cities)} villes -> {len(cells)} cellules NASA distinctes "
          f"({len(cells) - len(todo)} déjà en cache, {len(todo)} à télécharger)")
    print(f"Durée estimée : ~{len(todo) * (a.pause + 2) / 60:.0f} min")
    if a.dry_run:
        print(cities[["name", "country", "population", "cell"]].head(15).to_string(index=False))
        return
    if len(todo) > MAX_WITHOUT_YES and not a.yes:
        raise SystemExit(f"{len(todo)} téléchargements : c'est long. Relance avec --yes pour confirmer "
                         "(ou réduis avec --min-pop).")

    failed = set()
    for i, r in enumerate(todo, 1):
        print(f"({i}/{len(todo)}) {r.cell}")
        try:
            get_nasa_data(r.cell_lat, r.cell_lon, a.start, a.end, VARIABLES, name=r.cell)
        except Exception as err:               # une cellule qui échoue ne bloque pas les autres
            print(f"  ECHEC : {err}")
            failed.add(r.cell)
        time.sleep(a.pause)

    # index ville -> fichier (fusionné avec les exécutions précédentes)
    ok = cities[~cities["cell"].isin(failed)].copy()
    ok["file"] = [f"{c}_monthly_{a.start}_{a.end}.csv" for c in ok["cell"]]
    out = ok[["geonameid", "name", "ascii", "country", "continent", "lat", "lon",
              "population", "cell", "file"]]
    if INDEX.exists():
        out = pd.concat([pd.read_csv(INDEX), out]).drop_duplicates("geonameid", keep="last")
    out.to_csv(INDEX, index=False)
    print(f"\nTerminé : {len(ok)} villes indexées, {len(failed)} cellules en échec {sorted(failed) or ''}")
    print(f"Index : {INDEX}")


if __name__ == "__main__":
    main()
