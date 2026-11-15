"""
Point d'entrée UNIQUE pour récupérer une série climatique (Membres 3, 4, 5, dashboard).

    from data_access import get_series_for_city, get_series, DataError

    try:
        res = get_series_for_city("Fès")            # ou "Tokyo", "Paris", "Dakhla"...
        # res = get_series(34.03, -5.00)            # ou directement par coordonnées
    except DataError as e:
        st.error(e.user_message)                    # message clair, prêt à afficher
    else:
        df = res.df                                 # date | T2M | PRECTOTCORR | year | month | *_flag
        res.source                                  # "local" ou "nasa"
        res.note                                    # texte à afficher sous le graphique

Ordre de recherche :
  1. cellule déjà en local (data/clean/ puis data/)   -> aucun Internet
  2. sinon API NASA POWER -> téléchargement -> nettoyage -> mise en cache (le 2e appel sera local)
  3. sinon erreur claire (DataError) : ville introuvable / NASA indisponible / pas de données

Le nom d'une ville est cherché d'abord dans nos fichiers locaux (regions.py, cities_index.csv,
morocco_communes.csv) ; si elle n'y est pas, on demande ses coordonnées au géocodeur gratuit
Open-Meteo (NASA POWER ne connaît que des coordonnées, pas des noms de villes).
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

import pandas as pd
import requests

import nasa_data
from cities import cell_name, snap_to_cell
from clean_data import decide
from find_outliers import find
from nasa_data import get_nasa_data
from regions import ALL

VARIABLES = ["T2M", "PRECTOTCORR"]
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FIRST_YEAR = 1981            # NASA POWER commence en 1981


# ----------------------------------------------------------------------------
# Erreurs : toutes héritent de DataError et portent un message prêt à afficher
# ----------------------------------------------------------------------------
class DataError(Exception):
    code = "error"

    def __init__(self, message: str):
        super().__init__(message)
        self.user_message = message


class InvalidInput(DataError):
    code = "invalid_input"


class CityNotFound(DataError):
    code = "city_not_found"


class ServiceUnavailable(DataError):
    code = "service_unavailable"


class NasaUnavailable(ServiceUnavailable):
    code = "nasa_unavailable"


class NoData(DataError):
    code = "no_data"


# ----------------------------------------------------------------------------
# Résultat
# ----------------------------------------------------------------------------
@dataclass
class SeriesResult:
    df: pd.DataFrame
    source: str            # "local" (déjà sur disque) ou "nasa" (téléchargé à l'instant)
    label: str
    lat: float
    lon: float
    cell: str
    note: str


# ----------------------------------------------------------------------------
# 1) Trouver une ville -> coordonnées
# ----------------------------------------------------------------------------
def _data_dir() -> Path:
    return Path(nasa_data.DATA_DIR)


def _norm(s: str) -> str:
    """'Fès' / 'FES' / 'fes ' -> 'fes' ; 'El-Jadida' -> 'el jadida'."""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


@lru_cache(maxsize=4)
def _local_places(data_dir: str) -> dict:
    """nom normalisé -> (nom affiché, lat, lon). Priorité : regions.py > villes GeoNames > communes."""
    d = Path(data_dir)
    places: dict = {}
    for key, (lat, lon) in ALL.items():
        places.setdefault(_norm(key), (key.replace("_", " ").title(), lat, lon))
    idx = d / "cities_index.csv"
    if idx.exists():
        df = pd.read_csv(idx).sort_values("population", ascending=False)
        for r in df.itertuples():
            for n in (r.name, r.ascii):
                places.setdefault(_norm(n), (r.name, float(r.lat), float(r.lon)))
    com = d / "morocco_communes.csv"
    if com.exists():
        df = pd.read_csv(com, dtype=str).dropna(subset=["lat", "lon"])
        for r in df.itertuples():
            places.setdefault(_norm(r.name_fr), (r.name_fr, float(r.lat), float(r.lon)))
    return places


def _geocode(query: str) -> tuple[str, float, float]:
    try:
        r = requests.get(GEOCODE_URL, params={"name": query, "count": 1, "language": "fr"}, timeout=10)
        r.raise_for_status()
        results = r.json().get("results") or []
    except (requests.RequestException, ValueError):
        raise ServiceUnavailable(
            f"« {query} » n'est pas dans nos données locales et le service de recherche de villes "
            "est indisponible. Réessaie plus tard ou choisis une ville du Maroc.") from None
    if not results:
        raise CityNotFound(
            f"La ville « {query} » est introuvable : elle n'existe ni dans notre jeu de données "
            "ni dans le service de géolocalisation utilisé pour NASA POWER. "
            "Vérifie l'orthographe ou saisis sa latitude et sa longitude.")
    x = results[0]
    label = ", ".join(p for p in (x.get("name"), x.get("country")) if p)
    return label, float(x["latitude"]), float(x["longitude"])


def find_place(query: str) -> tuple[str, float, float]:
    """Nom de ville -> (nom, lat, lon). Local d'abord, géocodeur ensuite."""
    if not query or not str(query).strip() or len(str(query)) > 100:
        raise InvalidInput("Saisis le nom d'une ville (100 caractères maximum).")
    key = _norm(query)
    hit = _local_places(str(_data_dir())).get(key) or _read_place_cache().get(key)
    if hit:
        return tuple(hit)
    found = _geocode(str(query).strip())
    _save_place(key, found)
    return found


def _place_cache_path() -> Path:
    return _data_dir() / "places_cache.json"


def _read_place_cache() -> dict:
    """Villes déjà trouvées par le géocodeur : elles marchent ensuite sans Internet."""
    try:
        return json.loads(_place_cache_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_place(key: str, place: tuple) -> None:
    try:                                              # bonus : jamais bloquant
        cache = _read_place_cache()
        cache[key] = list(place)
        _place_cache_path().write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


# ----------------------------------------------------------------------------
# 2) Nettoyage d'un fichier de cellule (mêmes règles que clean_data.py)
# ----------------------------------------------------------------------------
def _clean_cell(raw_path: Path, crosscheck: bool) -> pd.DataFrame:
    """Retire les valeurs aberrantes (vérifiées avec ERA5 si crosscheck) ; le brut n'est pas modifié."""
    df = pd.read_csv(raw_path, parse_dates=["date"])
    df["T2M_flag"] = ""
    df["PRECTOTCORR_flag"] = ""
    for o in find(raw_path):
        action, _ = decide(o, crosscheck)
        idx = df.index[df["date"].dt.strftime("%Y-%m") == o["date"]][0]
        df.loc[idx, f"{o['variable']}_flag"] = action
        if action == "removed":
            df.loc[idx, o["variable"]] = float("nan")
    try:                                              # le cache est un bonus : jamais bloquant
        out = raw_path.parent / "clean"
        out.mkdir(exist_ok=True)
        df.to_csv(out / raw_path.name, index=False)
    except OSError:
        pass
    return df


def _normalize_flags(df: pd.DataFrame) -> pd.DataFrame:
    for v in VARIABLES:
        col = f"{v}_flag"
        flags = df[col] if col in df.columns else pd.Series("", index=df.index)
        df[col] = flags.astype("object").fillna("").replace("", "ok")   # colonne vide lue en float -> texte
    return df


# ----------------------------------------------------------------------------
# 3) Fonction principale
# ----------------------------------------------------------------------------
def get_series(lat: float, lon: float, start: int = 2000, end: int = 2024, *,
               label: str | None = None, crosscheck: bool = True) -> SeriesResult:
    """Série mensuelle T2M / PRECTOTCORR du point (lat, lon). Lève DataError si impossible."""
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        raise InvalidInput("Latitude et longitude doivent être des nombres.") from None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise InvalidInput("Coordonnées invalides : latitude entre -90 et 90, longitude entre -180 et 180.")
    if not (FIRST_YEAR <= start <= end <= date.today().year):
        raise InvalidInput(f"Période invalide : choisis des années entre {FIRST_YEAR} et {date.today().year} (début <= fin).")

    d = _data_dir()
    cell_lat, cell_lon = snap_to_cell(lat, lon)
    cell = cell_name(cell_lat, cell_lon)
    fname = f"{cell}_monthly_{start}_{end}.csv"
    label = label or f"{lat:.2f}, {lon:.2f}"

    clean_path, raw_path = d / "clean" / fname, d / fname
    if clean_path.exists():                                   # cas 1 : déjà nettoyé en local
        df = pd.read_csv(clean_path, parse_dates=["date"])
        source = "local"
    else:
        source = "local" if raw_path.exists() else "nasa"     # brut déjà là, ou à télécharger
        try:
            get_nasa_data(cell_lat, cell_lon, start, end, VARIABLES, name=cell, cache_dir=d)
        except ConnectionError:
            raise NasaUnavailable(
                "NASA POWER est actuellement indisponible (ou ta connexion est coupée). "
                "Réessaie dans quelques minutes ou choisis une ville du Maroc, déjà disponible hors ligne.") from None
        except (KeyError, ValueError, requests.RequestException):
            raise NoData("NASA POWER n'a pas renvoyé de données exploitables pour ce point.") from None
        # ERA5 seulement si on vient de télécharger (donc Internet marche) ; sinon retrait par prudence
        df = _clean_cell(raw_path, crosscheck and source == "nasa")

    if df[VARIABLES].isna().all().all():
        raise NoData("Aucune donnée disponible pour ce point (zone non couverte par NASA POWER).")

    df = _normalize_flags(df)
    note = ("Données locales NASA POWER, nettoyées (valeurs aberrantes vérifiées avec ERA5)."
            if source == "local" else
            "Données téléchargées en direct depuis NASA POWER, nettoyées automatiquement.")
    note += " Grille de ~55 km : ce n'est pas une station météo locale."
    return SeriesResult(df, source, label, lat, lon, cell, note)


def get_series_for_city(query: str, start: int = 2000, end: int = 2024, **kw) -> SeriesResult:
    """Nom de ville -> série. C'est la fonction à appeler depuis la barre de recherche du dashboard."""
    label, lat, lon = find_place(query)
    return get_series(lat, lon, start, end, label=label, **kw)
