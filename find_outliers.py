"""
Liste les valeurs SUSPECTES des données (sans rien modifier) pour que les Membres 3 et 4 décident.

    python3 find_outliers.py

Règles (par cellule NASA) :
  - pluie : moyenne mensuelle > 15 mm/jour (soit ~450 mm dans le mois)
  - pluie (pic isolé) : >= 5 mm/jour ET très au-dessus de l'historique de la cellule (z >= 5)
  - température : écart > 4 écarts-types à la moyenne du même mois de l'année
Résultat : data/outliers_to_check.csv (cellule, date, variable, valeur, normale du mois, raison)
"""
import argparse
from pathlib import Path

import pandas as pd

from nasa_data import DATA_DIR

RAIN_MAX = 15.0     # mm/jour
Z_MAX = 4.0
SPIKE_MIN = 5.0     # mm/jour : seuil bas pour la règle « pic isolé »
SPIKE_Z = 5.0       # écarts-types au-dessus de la moyenne de la cellule


def find(path: Path) -> list[dict]:
    d = pd.read_csv(path, parse_dates=["date"])
    out = []
    zr = (d["PRECTOTCORR"] - d["PRECTOTCORR"].mean()) / d["PRECTOTCORR"].std()
    rain_mask = (d["PRECTOTCORR"] > RAIN_MAX) | ((d["PRECTOTCORR"] >= SPIKE_MIN) & (zr >= SPIKE_Z))
    for _, r in d[rain_mask].iterrows():
        typical = d.loc[d["month"] == r["month"], "PRECTOTCORR"].median()
        out.append({"cell": path.name.split("_monthly")[0], "date": r["date"].strftime("%Y-%m"),
                    "variable": "PRECTOTCORR", "value": r["PRECTOTCORR"],
                    "typical_for_month": round(typical, 2),
                    "reason": f"pluie suspecte : {r['PRECTOTCORR']:.1f} mm/jour (~{r['PRECTOTCORR'] * 30:.0f} mm dans le mois)"})
    g = d.groupby("month")["T2M"]
    z = (d["T2M"] - g.transform("mean")) / g.transform("std")
    for _, r in d[z.abs() > Z_MAX].iterrows():
        out.append({"cell": path.name.split("_monthly")[0], "date": r["date"].strftime("%Y-%m"),
                    "variable": "T2M", "value": r["T2M"],
                    "typical_for_month": round(g.get_group(r["month"]).mean(), 2),
                    "reason": f"température à plus de {Z_MAX:g} écarts-types de la normale du mois"})
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir", type=Path, default=DATA_DIR)
    p.add_argument("--pattern", default="cell_*_monthly_*.csv")
    a = p.parse_args()
    rows = [x for f in sorted(a.data_dir.glob(a.pattern)) for x in find(f)]
    df = pd.DataFrame(rows, columns=["cell", "date", "variable", "value", "typical_for_month", "reason"])
    df.to_csv(a.data_dir / "outliers_to_check.csv", index=False)
    print(f"{len(df)} valeurs suspectes dans {len(list(a.data_dir.glob(a.pattern)))} fichiers "
          f"-> {a.data_dir / 'outliers_to_check.csv'}")
    if len(df):
        print(df.sort_values("value", ascending=False).head(10).to_string(index=False))


if __name__ == "__main__":
    main()
