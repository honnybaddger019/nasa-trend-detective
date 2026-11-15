import json
import os
import unicodedata
import requests
import pandas as pd
from shapely.geometry import Point, shape
from shapely.ops import unary_union

# Sources fiables dyal GeoJSON dyal 12 jihat dyal l-Maghrib
GEOJSON_URLS = [
    "https://raw.githubusercontent.com/abdelghanibelgaid/morocco-map/7795c93c17db0a98b0fee33e7851d2e9faee76bb/maps/morocco.geojson",
    "https://raw.githubusercontent.com/Salah-Zkara/Morocco-GeoJson/master/Morocco-Regions.geojson",
    "https://raw.githubusercontent.com/i-emek/Morocco-Geospatial-Visualisations/main/data/rgph-2024/regions.geojson",
]


def _normalize_text(txt: str) -> str:
    if not txt:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(txt))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def map_region_to_climate_zone(region_name: str) -> str:
    n = _normalize_text(region_name)
    if "tanger" in n or "tetouan" in n or "hoceima" in n:
        return "North (Tangier-Rif)"
    if "oriental" in n or "oujda" in n:
        return "Northeast (Oriental)"
    if "rabat" in n or "casablanca" in n or "settat" in n:
        return "Atlantic Coast"
    if "fes" in n or "meknes" in n or "marrakech" in n:
        return "Center & Interior Plains"
    if "beni" in n or "khenifra" in n or "tadala" in n:
        return "Mountains & Atlas"
    if "souss" in n or "agadir" in n or "guelmim" in n:
        return "Southwest"
    if "draa" in n or "tafilalet" in n or "laayoune" in n or "dakhla" in n or "oued" in n:
        return "South & Southeast (Saharan/Pre-Saharan)"
    return "Other"


def _extract_region_name(props: dict, idx: int) -> str:
    for key in ["name_fr", "region", "Region", "nom", "NOM", "NAME_1", "name", "libelle", "Region_Fr"]:
        if key in props and props[key]:
            return str(props[key]).strip()
    return f"Region_{idx+1}"


def load_morocco_geojson(cache_path: str) -> dict:
    """
    Loads Morocco 12-regions GeoJSON and normalizes 'properties.region_name'.
    """
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)

    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    last_err = None
    for url in GEOJSON_URLS:
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            gj = r.json()
            if "features" in gj and len(gj["features"]) >= 10:
                for i, feat in enumerate(gj["features"]):
                    props = feat.setdefault("properties", {})
                    rname = _extract_region_name(props, i)
                    props["region_name"] = rname
                    props["climate_zone"] = map_region_to_climate_zone(rname)
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(gj, f, ensure_ascii=False)
                return gj
        except Exception as e:
            last_err = e

    raise RuntimeError(f"Could not download Morocco GeoJSON from sources. Last error: {last_err}")


def clip_grid_to_morocco(df_coords: pd.DataFrame, geojson_data: dict) -> pd.DataFrame:
    """
    Takes unique (lat, lon) points, keeps ONLY points inside Morocco's borders,
    and assigns each grid cell its official Moroccan Region + Climate Zone.
    """
    regions = []
    for feat in geojson_data["features"]:
        geom = shape(feat["geometry"])
        rname = feat["properties"]["region_name"]
        czone = feat["properties"]["climate_zone"]
        regions.append((rname, czone, geom))

    national_poly = unary_union([g for _, _, g in regions])

    unique_pts = df_coords[["lat", "lon"]].drop_duplicates().copy()
    matched_rows = []
    for _, row in unique_pts.iterrows():
        pt = Point(float(row["lon"]), float(row["lat"]))
        # buffer(0.15) kay-khalli hta l-cells li 3la sahel/hodoud ma y-di3ouch
        if national_poly.buffer(0.15).contains(pt):
            assigned_region, assigned_zone = None, None
            for rname, czone, geom in regions:
                if geom.contains(pt):
                    assigned_region, assigned_zone = rname, czone
                    break
            if assigned_region is None:
                # Aqreb jiha l points li 3la l-bhar/hodoud
                best = min(regions, key=lambda item: item[2].distance(pt))
                if best[2].distance(pt) <= 0.30:
                    assigned_region, assigned_zone = best[0], best[1]
            if assigned_region is not None:
                matched_rows.append({
                    "lat": float(row["lat"]),
                    "lon": float(row["lon"]),
                    "region_name": assigned_region,
                    "climate_zone": assigned_zone,
                })

    return pd.DataFrame(matched_rows)