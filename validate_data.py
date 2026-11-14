"""
Vérifie que TOUTES les données téléchargées sont propres, avant de les donner au Membre 3.

    python3 validate_data.py

Contrôles par fichier cell_*.csv : bon nombre de lignes (12 mois x nb d'années), dates mensuelles
continues et sans doublon, aucune valeur manquante, température plausible (-50 à 60 °C),
pluie >= 0 et plausible (< 500 mm/jour). Vérifie aussi que chaque commune de
data/morocco_communes.csv a bien son fichier. Écrit le détail dans data/validation_report.csv.
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

from nasa_data import DATA_DIR


def check_file(path: Path, expected_rows: int, start: int, end: int) -> dict:
    df = pd.read_csv(path, parse_dates=["date"])
    issues = []
    r = {"file": path.name, "rows": len(df)}

    if len(df) != expected_rows:
        issues.append(f"{len(df)} lignes au lieu de {expected_rows}")
    for col in ("T2M", "PRECTOTCORR"):
        if col not in df.columns:
            issues.append(f"colonne {col} absente")
            continue
        miss = int(df[col].isna().sum())
        r[f"missing_{col}"] = miss
        if miss:
            issues.append(f"{miss} valeurs manquantes dans {col}")
    if df["date"].duplicated().any():
        issues.append("dates en double")
    expected = pd.date_range(f"{start}-01-01", f"{end}-12-01", freq="MS")
    if set(df["date"]) != set(expected):
        issues.append("dates non continues / hors période")
    if "T2M" in df.columns:
        r["T2M_min"], r["T2M_max"] = round(df["T2M"].min(), 2), round(df["T2M"].max(), 2)
        if df["T2M"].min() < -50 or df["T2M"].max() > 60:
            issues.append("température hors de -50..60 °C")
    if "PRECTOTCORR" in df.columns:
        r["P_max"] = round(df["PRECTOTCORR"].max(), 2)
        if df["PRECTOTCORR"].min() < 0 or df["PRECTOTCORR"].max() > 500:
            issues.append("pluie négative ou > 500 mm/jour")
    r["issues"] = "; ".join(issues)
    return r


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", type=int, default=2000)
    p.add_argument("--end", type=int, default=2024)
    p.add_argument("--data-dir", type=Path, default=DATA_DIR)
    a = p.parse_args()

    files = sorted(a.data_dir.glob(f"cell_*_monthly_{a.start}_{a.end}.csv"))
    if not files:
        sys.exit(f"Aucun fichier cell_*_monthly_{a.start}_{a.end}.csv dans {a.data_dir}")
    expected_rows = 12 * (a.end - a.start + 1)
    rep = pd.DataFrame([check_file(f, expected_rows, a.start, a.end) for f in files])
    rep.to_csv(a.data_dir / "validation_report.csv", index=False)

    bad = rep[rep["issues"] != ""]
    print(f"{len(rep)} fichiers vérifiés ({expected_rows} lignes attendues chacun)")
    print(f"  valeurs manquantes au total : {int(rep.filter(like='missing_').sum().sum())}")
    print(f"  T2M globale : {rep['T2M_min'].min()} à {rep['T2M_max'].max()} °C | pluie max : {rep['P_max'].max()} mm/jour")

    missing_files = []
    comm = a.data_dir / "morocco_communes.csv"
    if comm.exists():
        c = pd.read_csv(comm, dtype=str)
        missing_files = sorted(set(f for f in c["file"] if not (a.data_dir / f).exists()))
        print(f"  communes : {len(c)} | fichiers manquants : {len(missing_files)}")

    if len(bad) or missing_files:
        print("\nPROBLEMES :")
        for _, row in bad.iterrows():
            print(f"  {row['file']} -> {row['issues']}")
        for f in missing_files:
            print(f"  fichier absent : {f}")
        sys.exit(1)
    print("\nOK : données complètes et propres, prêtes pour le Membre 3.")


if __name__ == "__main__":
    main()
