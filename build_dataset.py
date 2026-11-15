"""
Construit LE jeu de données final, un seul dossier à donner aux Membres 3, 4 et 5 :  dataset/

    python3 build_dataset.py

Fichiers produits :
    earthtrend_master.csv.gz               <- LE fichier principal : 1 ligne = 1 commune x 1 mois
    earthtrend_provinces_monthly.csv.gz    résumé : 1 ligne = 1 province/préfecture x 1 mois
    earthtrend_regions_monthly.csv.gz      résumé : 1 ligne = 1 région x 1 mois
    DATA_DICTIONARY.md                     description de chaque colonne + statistiques

Utilise les données nettoyées (data/clean/) si elles existent, sinon les données brutes.
Lecture : pandas.read_csv("dataset/earthtrend_master.csv.gz", parse_dates=["date"], dtype={"region_code": str, "province_code": str})
"""
from pathlib import Path

import pandas as pd

from nasa_data import DATA_DIR

OUT = Path(__file__).parent / "dataset"
VARS = ["T2M", "PRECTOTCORR"]


def load_cells(start=2000, end=2024) -> pd.DataFrame:
    src = DATA_DIR / "clean" if (DATA_DIR / "clean").exists() else DATA_DIR
    frames = []
    for f in sorted(src.glob(f"cell_*_monthly_{start}_{end}.csv")):
        d = pd.read_csv(f, parse_dates=["date"])
        d["cell"] = f.name.split("_monthly")[0]
        for v in VARS:
            if f"{v}_flag" not in d.columns:
                d[f"{v}_flag"] = "ok"
            d[f"{v}_flag"] = d[f"{v}_flag"].fillna("ok").replace("", "ok")
        frames.append(d)
    print(f"[dataset] {len(frames)} cellules lues depuis {src.name}/")
    return pd.concat(frames, ignore_index=True)


def weighted(df, keys):
    """Moyenne mensuelle pondérée par la population 2024 (les valeurs vides sont ignorées)."""
    out = df.groupby(keys + ["date"]).apply(
        lambda g: pd.Series({
            "n_communes": g["commune_code"].nunique(),
            "population_2024": g.drop_duplicates("commune_code")["population_2024"].sum(),
            **{v: (g[v] * g["population_2024"]).sum() / g.loc[g[v].notna(), "population_2024"].sum()
               for v in VARS}}), include_groups=False).reset_index()
    out["n_communes"] = out["n_communes"].astype(int)
    out["population_2024"] = out["population_2024"].astype(int)
    out["year"], out["month"] = out["date"].dt.year, out["date"].dt.month
    return out.round({"T2M": 2, "PRECTOTCORR": 3})


def main():
    OUT.mkdir(exist_ok=True)
    com = pd.read_csv(DATA_DIR / "morocco_communes.csv", dtype={"code": str, "region_code": str, "province_code": str})
    com = com.rename(columns={"code": "commune_code", "name_fr": "commune", "name_ar": "commune_ar",
                              "type": "commune_type", "region_name": "region", "province_name": "province"})
    com = com[["commune_code", "commune", "commune_ar", "commune_type", "province_code", "province",
               "region_code", "region", "population_2024", "lat", "lon", "cell"]]
    cells = load_cells()

    master = com.merge(cells, on="cell", how="left")
    master = master[["date", "year", "month", "commune_code", "commune", "commune_ar", "commune_type",
                     "province_code", "province", "region_code", "region", "population_2024", "lat", "lon",
                     "cell", "T2M", "PRECTOTCORR", "T2M_flag", "PRECTOTCORR_flag"]]
    master = master.sort_values(["commune_code", "date"]).reset_index(drop=True)
    master["lat"], master["lon"] = master["lat"].round(4), master["lon"].round(4)
    master.to_csv(OUT / "earthtrend_master.csv.gz", index=False, encoding="utf-8")

    weighted(master, ["province_code", "province"]).to_csv(OUT / "earthtrend_provinces_monthly.csv.gz", index=False)
    weighted(master, ["region_code", "region"]).to_csv(OUT / "earthtrend_regions_monthly.csv.gz", index=False)

    n_c = master["commune_code"].nunique()
    stats = {
        "rows": len(master), "communes": n_c, "provinces": master["province_code"].nunique(),
        "regions": master["region_code"].nunique(), "cells": master["cell"].nunique(),
        "period": f"{master['date'].min():%Y-%m} -> {master['date'].max():%Y-%m}",
        "T2M_missing": int(master["T2M"].isna().sum()),
        "PRECTOTCORR_missing": int(master["PRECTOTCORR"].isna().sum()),
        "removed": int((master["PRECTOTCORR_flag"] == "removed").sum()),
    }
    write_dictionary(stats)
    for f in sorted(OUT.iterdir()):
        print(f"  {f.name:42s} {f.stat().st_size / 1e6:6.1f} Mo")
    print(f"\n{stats['rows']:,} lignes | {n_c} communes | {stats['regions']} régions | {stats['period']} | "
          f"valeurs vides : T2M {stats['T2M_missing']}, pluie {stats['PRECTOTCORR_missing']}")


def write_dictionary(s):
    (OUT / "DATA_DICTIONARY.md").write_text(f"""# EarthTrend AI — jeu de données final (Maroc)

**Source** : NASA POWER (température `T2M` et pluie `PRECTOTCORR`, mensuel, {s['period']}), découpage HCP 2024.
**Contenu** : {s['communes']:,} communes, {s['provinces']} provinces/préfectures, {s['regions']} régions, {s['rows']:,} lignes.

## Quel fichier utiliser ?
| Fichier | 1 ligne = | Quand l'utiliser |
|---|---|---|
| `earthtrend_master.csv.gz` | 1 commune x 1 mois | **par défaut**, pour tout (filtre par `region`, `province`, `commune`) |
| `earthtrend_provinces_monthly.csv.gz` | 1 province x 1 mois | graphiques / stats par province (déjà agrégé) |
| `earthtrend_regions_monthly.csv.gz` | 1 région x 1 mois | graphiques / stats par région (déjà agrégé) |

```python
import pandas as pd
df = pd.read_csv("dataset/earthtrend_master.csv.gz", parse_dates=["date"],
                 dtype={{"region_code": str, "province_code": str}})   # garde les zéros : "01", "01.511"
fes = df[df["region"] == "Fès-Meknès"]
fes.groupby("year")["T2M"].mean()
```

## Colonnes de `earthtrend_master.csv.gz`
| Colonne | Description |
|---|---|
| `date`, `year`, `month` | mois (date = 1er du mois) |
| `commune_code`, `commune`, `commune_ar` | code officiel HCP, nom français, nom arabe |
| `commune_type` | `urban` ou `rural` |
| `province_code`, `province`, `region_code`, `region` | hiérarchie administrative |
| `population_2024` | population de la commune (RGPH 2024) |
| `lat`, `lon` | centroïde de la commune |
| `cell` | cellule NASA (0,5° x 0,625°, ~55 km) : des communes proches partagent les mêmes valeurs |
| `T2M` | température de l'air à 2 m, moyenne mensuelle, **°C** |
| `PRECTOTCORR` | précipitations, moyenne mensuelle, **mm/jour** |
| `T2M_flag`, `PRECTOTCORR_flag` | `ok` = normal ; `removed` = valeur aberrante retirée (la valeur est alors vide) ; `kept` = suspecte mais confirmée par ERA5 |

Les fichiers agrégés ont : `date, year, month`, le code et le nom de l'unité, `n_communes`, `population_2024`, `T2M`, `PRECTOTCORR`
(moyenne **pondérée par la population** des communes ; les valeurs vides sont ignorées).

## Qualité
- Valeurs vides : T2M = {s['T2M_missing']}, PRECTOTCORR = {s['PRECTOTCORR_missing']} (valeurs aberrantes retirées après vérification avec ERA5).
- Journal des valeurs retirées : `data/clean/CLEANING_LOG.csv` ; données brutes conservées dans `data/`.
- Pour une moyenne annuelle, ignorer les années avec moins de 9 mois valides.

## Limites (à dire dans le pitch)
NASA POWER est un produit sur grille (satellite + modèles), pas une station météo locale. Les valeurs de 2 communes
dans la même cellule sont identiques : une analyse « par commune » est en réalité une analyse par cellule de 55 km.
Les données montrent une évolution dans le temps, pas sa cause.

## Sources à citer
NASA POWER ; HCP (RGPH 2024, CC BY 4.0) via `zkousama/morocco-communes` ; © contributeurs OpenStreetMap (ODbL) pour les centroïdes ;
ERA5 (Copernicus/ECMWF) via Open-Meteo pour le contrôle qualité.
""", encoding="utf-8")


if __name__ == "__main__":
    main()
