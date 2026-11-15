"""
Crée une version NETTOYEE des données (data/clean/) sans jamais toucher aux fichiers bruts.

    python3 clean_data.py --crosscheck   # recommandé : vérifie chaque valeur suspecte avec ERA5 (Open-Meteo)
    python3 clean_data.py                # sans Internet : toute valeur suspecte est retirée

Valeurs suspectes (mêmes règles que find_outliers.py) : pluie > 15 mm/jour (ou pic isolé >= 5 mm/jour très au-dessus de l'historique), ou température à plus de
4 écarts-types de la normale du mois.

Avec --crosscheck, chaque valeur suspecte est comparée à ERA5 (réanalyse indépendante de NASA, via l'API
gratuite Open-Meteo) pour le même mois et le même point :
    pluie        : retirée si NASA dépasse ERA5 de plus de 5 mm/jour ET qu'ERA5 ne voit pas de forte pluie
                   (ERA5 >= 5 mm/jour = événement réel : valeur gardée même si NASA l'exagère)
    température  : retirée si l'écart avec ERA5 dépasse 3 °C
Sinon la valeur est GARDEE (c'est probablement un vrai événement).

Dans data/clean/*.csv : les colonnes T2M et PRECTOTCORR (valeur retirée = vide) + T2M_flag et
PRECTOTCORR_flag : "" = normal | "removed" = retirée | "kept" = suspecte mais confirmée, gardée.
Journal complet : data/clean/CLEANING_LOG.csv.
"""
import argparse
import calendar
import re
import time
from pathlib import Path

import pandas as pd
import requests

from find_outliers import find
from nasa_data import DATA_DIR

ERA5_URL = "https://archive-api.open-meteo.com/v1/archive"
ERA5_VAR = {"PRECTOTCORR": "precipitation_sum", "T2M": "temperature_2m_mean"}
MAX_GAP = {"PRECTOTCORR": 5.0, "T2M": 3.0}          # mm/jour, °C
ERA5_RAIN_EXTREME = 5.0   # si ERA5 voit AUSSI > 5 mm/jour, l'événement est réel : on garde (même si NASA exagère)


def era5_month_mean(lat, lon, ym, variable, retries=3):
    """Moyenne mensuelle ERA5 (même unité que NASA : mm/jour ou °C) ; None si l'API échoue."""
    y, m = map(int, ym.split("-"))
    params = {"latitude": lat, "longitude": lon, "start_date": f"{y}-{m:02d}-01",
              "end_date": f"{y}-{m:02d}-{calendar.monthrange(y, m)[1]}",
              "daily": ERA5_VAR[variable], "timezone": "UTC"}
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(ERA5_URL, params=params, timeout=60)
            r.raise_for_status()
            vals = [v for v in r.json()["daily"][ERA5_VAR[variable]] if v is not None]
            return sum(vals) / len(vals) if vals else None
        except (requests.RequestException, KeyError, ValueError) as err:
            print(f"  [ERA5] tentative {attempt}/{retries} : {err}")
            time.sleep(2 * attempt)
    return None


def coords(cell: str):
    m = re.match(r"cell_(-?[\d.]+)_(-?[\d.]+)", cell)
    return (float(m.group(1)), float(m.group(2))) if m else (None, None)


def decide(row, crosscheck):
    """-> (action, era5_value). action = 'removed' | 'kept'."""
    if not crosscheck:
        return "removed", None
    lat, lon = coords(row["cell"])
    era5 = era5_month_mean(lat, lon, row["date"], row["variable"]) if lat is not None else None
    time.sleep(0.3)
    if era5 is None:                              # pas de vérification possible -> par prudence on retire
        return "removed", None
    gap = (row["value"] - era5) if row["variable"] == "PRECTOTCORR" else abs(row["value"] - era5)
    real_event = row["variable"] == "PRECTOTCORR" and era5 >= ERA5_RAIN_EXTREME
    removed = gap > MAX_GAP[row["variable"]] and not real_event
    return ("removed" if removed else "kept"), round(era5, 2)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--crosscheck", action="store_true")
    p.add_argument("--data-dir", type=Path, default=DATA_DIR)
    a = p.parse_args()

    out_dir = a.data_dir / "clean"
    out_dir.mkdir(exist_ok=True)
    files = sorted(a.data_dir.glob("cell_*_monthly_*.csv"))
    log = []
    for f in files:
        df = pd.read_csv(f, parse_dates=["date"])
        df["T2M_flag"] = ""
        df["PRECTOTCORR_flag"] = ""
        for o in find(f):
            action, era5 = decide(o, a.crosscheck)
            idx = df.index[df["date"].dt.strftime("%Y-%m") == o["date"]][0]
            df.loc[idx, f"{o['variable']}_flag"] = action
            if action == "removed":
                df.loc[idx, o["variable"]] = float("nan")
            log.append({**o, "era5": era5, "action": action})
            print(f"  {o['cell']} {o['date']} {o['variable']} NASA={o['value']} ERA5={era5} -> {action}")
        df.to_csv(out_dir / f.name, index=False)

    cols = ["cell", "date", "variable", "value", "typical_for_month", "era5", "action", "reason"]
    pd.DataFrame(log, columns=cols).to_csv(out_dir / "CLEANING_LOG.csv", index=False)
    n = pd.Series([x["action"] for x in log]).value_counts().to_dict()
    print(f"\n{len(files)} fichiers -> {out_dir}/")
    print(f"{len(log)} valeurs suspectes : {n.get('removed', 0)} retirées, {n.get('kept', 0)} gardées (confirmées par ERA5)")
    print(f"Journal : {out_dir / 'CLEANING_LOG.csv'}  |  fichiers bruts non modifiés")


if __name__ == "__main__":
    main()
