"""
Télécharge les données NASA POWER pour plusieurs villes (avec cache CSV dans data/).

    python3 run_download.py                     # toutes les villes du Maroc (36)
    python3 run_download.py --world             # + villes méditerranéennes / monde
    python3 run_download.py --only fes rabat    # seulement certaines villes
    python3 run_download.py --custom tokyo 35.68 139.69     # n'importe quel point du monde
    python3 run_download.py --start 2010 --end 2024         # autre période
"""
import argparse
import csv
import time
from pathlib import Path

from nasa_data import DATA_DIR, get_nasa_data, summary, yearly_means
from regions import ALL, MOROCCO, WORLD

VARIABLES = ["T2M", "PRECTOTCORR"]
PAUSE = 1.0   # secondes entre deux téléchargements (politesse envers l'API NASA)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", type=int, default=2000)
    p.add_argument("--end", type=int, default=2024)
    p.add_argument("--world", action="store_true", help="ajoute les villes hors Maroc")
    p.add_argument("--only", nargs="+", help="noms de villes (voir regions.py)")
    p.add_argument("--custom", nargs=3, metavar=("NOM", "LAT", "LON"), action="append",
                   help="ajoute un point : --custom tokyo 35.68 139.69")
    p.add_argument("--plot", nargs="+", default=["fes", "casablanca", "rabat"])
    a = p.parse_args()

    if a.only:
        unknown = [c for c in a.only if c not in ALL]
        if unknown:
            raise SystemExit(f"Villes inconnues : {unknown}. Liste : {sorted(ALL)}")
        regions = {c: ALL[c] for c in a.only}
    else:
        regions = dict(MOROCCO)
        if a.world:
            regions.update(WORLD)
    for name, lat, lon in a.custom or []:
        regions[name.lower()] = (float(lat), float(lon))

    DATA_DIR.mkdir(exist_ok=True)
    yearly, failed, rows = {}, [], []
    for i, (name, (lat, lon)) in enumerate(regions.items(), 1):
        print(f"\n({i}/{len(regions)}) {name}")
        cached = (DATA_DIR / f"{name}_monthly_{a.start}_{a.end}.csv").exists()
        try:
            df = get_nasa_data(lat, lon, a.start, a.end, VARIABLES, name=name)
        except Exception as err:                       # une ville qui échoue ne bloque pas les autres
            print(f"  ECHEC {name} : {err}")
            failed.append(name)
            continue
        s = summary(df, "T2M")
        print(f"  T2M moyenne {s['mean']} °C | manquantes {s['missing']} | {s['period']}")
        yearly[name] = yearly_means(df, "T2M")
        rows.append({"name": name, "lat": lat, "lon": lon, "start": a.start, "end": a.end})
        if not cached:
            time.sleep(PAUSE)

    # index des régions disponibles (utile pour la liste déroulante du dashboard)
    with open(DATA_DIR / "regions.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["name", "lat", "lon", "start", "end"])
        w.writeheader()
        w.writerows(rows)

    print(f"\nTerminé : {len(rows)} villes OK, {len(failed)} échecs {failed or ''}")
    print("Index : data/regions.csv")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(9, 4))
        for name in [n for n in a.plot if n in yearly]:
            y = yearly[name]
            ax.plot(y["year"], y["value"], marker="o", label=name.capitalize())
        ax.set_title("Température moyenne annuelle (°C) - source : NASA POWER")
        ax.set_xlabel("Année")
        ax.set_ylabel("T2M (°C)")
        ax.legend()
        ax.grid(alpha=.3)
        fig.tight_layout()
        fig.savefig("data/yearly_T2M.png", dpi=150)
        print("Graphique : data/yearly_T2M.png")
    except ImportError:
        print("(matplotlib non installé : graphique ignoré)")


if __name__ == "__main__":
    main()
