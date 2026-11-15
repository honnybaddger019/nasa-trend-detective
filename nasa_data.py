"""
Membre 2 - Data Engineer : télécharger et nettoyer les données NASA POWER.

Fonction principale :
    get_nasa_data(lat, lon, start, end, variable="T2M")  ->  DataFrame propre (+ cache CSV)

Variables utiles :
    T2M           température à 2 m (°C)
    PRECTOTCORR   précipitations corrigées (mm/jour)
"""
from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import requests

POWER_URL = "https://power.larc.nasa.gov/api/temporal/{freq}/point"
DATA_DIR = Path(__file__).parent / "data"
MISSING = -999  # valeur "manquante" utilisée par NASA POWER


# ----------------------------------------------------------------------------
# 1) Téléchargement
# ----------------------------------------------------------------------------
def _download(lat, lon, start, end, variables, freq, retries=3, timeout=60):
    """Appelle l'API NASA POWER et renvoie le JSON brut."""
    if freq == "monthly":
        s, e = str(start), str(end)                      # années : 2000, 2024
    else:                                                # daily : YYYYMMDD
        s, e = f"{start}0101", f"{end}1231"
    params = {
        "parameters": ",".join(variables),
        "community": "AG",
        "latitude": lat,
        "longitude": lon,
        "start": s,
        "end": e,
        "format": "JSON",
    }
    url = POWER_URL.format(freq=freq)
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, params=params, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as err:
            last_error = err
            print(f"  [NASA] tentative {attempt}/{retries} échouée : {err}")
            time.sleep(2 * attempt)
    raise ConnectionError(
        "Impossible de joindre NASA POWER. Vérifie ta connexion Internet, "
        "ou utilise un fichier CSV déjà présent dans data/."
    ) from last_error


# ----------------------------------------------------------------------------
# 2) Nettoyage : JSON NASA -> DataFrame
# ----------------------------------------------------------------------------
def parse_power(raw: dict, variables, freq="monthly") -> pd.DataFrame:
    """Transforme le JSON de NASA POWER en DataFrame propre."""
    params = raw["properties"]["parameter"]
    frames = []
    for var in variables:
        s = pd.Series(params[var], name=var)
        s.index = s.index.astype(str)
        if freq == "monthly":
            s = s[~s.index.str.endswith("13")]            # "YYYY13" = moyenne annuelle -> on enlève
            s.index = pd.to_datetime(s.index, format="%Y%m")
        else:
            s.index = pd.to_datetime(s.index, format="%Y%m%d")
        frames.append(s)

    df = pd.concat(frames, axis=1).sort_index()
    df.index.name = "date"
    df = df.replace(MISSING, float("nan"))                # -999 -> NaN
    df = df.reset_index()
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month
    return df


# ----------------------------------------------------------------------------
# 3) Fonction principale (avec cache CSV)
# ----------------------------------------------------------------------------
def get_nasa_data(lat, lon, start, end, variable="T2M", freq="monthly",
                  name=None, cache_dir=DATA_DIR, refresh=False) -> pd.DataFrame:
    """
    Renvoie un DataFrame propre : date | <variable(s)> | year | month

    lat, lon : coordonnées (ex. Fès : 34.03, -5.00)
    start, end : années (ex. 2000, 2024)
    variable : "T2M", "PRECTOTCORR", ou une liste ["T2M", "PRECTOTCORR"]
    freq : "monthly" (défaut) ou "daily"
    name : nom du fichier cache (ex. "fes") ; sinon lat_lon
    refresh : True = retélécharger même si le CSV existe
    """
    variables = [variable] if isinstance(variable, str) else list(variable)
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    label = name or f"{lat}_{lon}"
    path = cache_dir / f"{label}_{freq}_{start}_{end}.csv"

    # 1) cache : si le CSV existe et contient toutes les variables -> pas d'Internet
    if path.exists() and not refresh:
        df = pd.read_csv(path, parse_dates=["date"])
        if all(v in df.columns for v in variables):
            print(f"[cache] {path.name} ({len(df)} lignes)")
            return df

    # 2) sinon : téléchargement + nettoyage + sauvegarde
    print(f"[NASA] téléchargement {label} {start}-{end} ({', '.join(variables)}) ...")
    raw = _download(lat, lon, start, end, variables, freq)
    df = parse_power(raw, variables, freq)
    n_missing = int(df[variables].isna().sum().sum())
    df.to_csv(path, index=False)
    print(f"[NASA] OK : {len(df)} lignes, {n_missing} valeurs manquantes (-999) -> {path.name}")
    return df


# ----------------------------------------------------------------------------
# 4) Agrégation annuelle
# ----------------------------------------------------------------------------
def yearly_means(df: pd.DataFrame, variable="T2M", min_months=9) -> pd.DataFrame:
    """Moyenne annuelle ; une année avec moins de `min_months` mois valides est ignorée."""
    g = df.dropna(subset=[variable]).groupby("year")[variable]
    out = g.agg(value="mean", n_months="count").reset_index()
    return out[out["n_months"] >= min_months][["year", "value"]].reset_index(drop=True)


def summary(df: pd.DataFrame, variable="T2M") -> dict:
    """Petit résumé (utile pour vérifier / donner au Membre 3)."""
    return {
        "rows": len(df),
        "period": f"{df['date'].min():%Y-%m} -> {df['date'].max():%Y-%m}",
        "missing": int(df[variable].isna().sum()),
        "mean": round(float(df[variable].mean()), 2),
        "min": round(float(df[variable].min()), 2),
        "max": round(float(df[variable].max()), 2),
    }
