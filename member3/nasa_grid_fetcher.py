import calendar
import os
import time
import numpy as np
import pandas as pd
import requests

from morocco_geo import clip_grid_to_morocco, load_morocco_geojson

# 4 tiles <= 10° x 10° li kay-ghattiw l-Maghrib kamel (min Lagouira 20.5N tal Tanger 36.2N)
MOROCCO_REGIONAL_TILES = [
    {"name": "north_west", "lat_min": 29.0, "lat_max": 36.5, "lon_min": -11.5, "lon_max": -5.0},
    {"name": "north_east", "lat_min": 29.0, "lat_max": 36.5, "lon_min": -5.0,  "lon_max": -0.8},
    {"name": "south_west", "lat_min": 20.5, "lat_max": 29.0, "lon_min": -17.5, "lon_max": -8.5},
    {"name": "south_east", "lat_min": 20.5, "lat_max": 29.0, "lon_min": -8.5,  "lon_max": -3.0},
]


def _fetch_regional_monthly_tile(parameter: str, tile: dict, start_year: int, end_year: int) -> pd.DataFrame:
    """
    Calls NASA POWER Regional Monthly API (1 parameter per request).
    """
    url = "https://power.larc.nasa.gov/api/temporal/monthly/regional"
    params = {
        "parameters": parameter,
        "community": "AG",
        "latitude-min": tile["lat_min"],
        "latitude-max": tile["lat_max"],
        "longitude-min": tile["lon_min"],
        "longitude-max": tile["lon_max"],
        "start": str(start_year),
        "end": str(end_year),
        "format": "JSON",
    }
    resp = requests.get(url, params=params, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    fill_val = float(data.get("header", {}).get("fill_value", -999.0))
    rows = []

    for feat in data.get("features", []):
        coords = feat["geometry"]["coordinates"]
        lon, lat = round(float(coords[0]), 4), round(float(coords[1]), 4)
        p_dict = feat["properties"]["parameter"].get(parameter, {})
        for ym, val in p_dict.items():
            ym_str = str(ym)
            # Hayyed 'YYYY13' (annual summary dyal POWER)
            if len(ym_str) != 6 or ym_str.endswith("13"):
                continue
            v = float(val)
            if v == fill_val or v <= -900:
                v = np.nan
            rows.append({"lat": lat, "lon": lon, "ym": ym_str, parameter: v})

    return pd.DataFrame(rows)


def _fetch_point_monthly_fallback(parameter: str, lat: float, lon: float, start_year: int, end_year: int) -> pd.DataFrame:
    url = "https://power.larc.nasa.gov/api/temporal/monthly/point"
    params = {
        "parameters": parameter,
        "community": "AG",
        "latitude": lat,
        "longitude": lon,
        "start": str(start_year),
        "end": str(end_year),
        "format": "JSON",
    }
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    fill_val = float(data.get("header", {}).get("fill_value", -999.0))
    p_dict = data["properties"]["parameter"].get(parameter, {})
    rows = []
    for ym, val in p_dict.items():
        ym_str = str(ym)
        if len(ym_str) != 6 or ym_str.endswith("13"):
            continue
        v = float(val)
        if v == fill_val or v <= -900:
            v = np.nan
        rows.append({"lat": round(lat, 4), "lon": round(lon, 4), "ym": ym_str, parameter: v})
    return pd.DataFrame(rows)


def fetch_morocco_grid_monthly(
    data_dir: str,
    start_year: int = 2000,
    end_year: int = 2025,
    progress_callback=None,
) -> tuple[pd.DataFrame, dict]:
    """
    Downloads REAL NASA POWER Monthly Regional grid for ALL Morocco (T2M + PRECTOTCORR),
    clips strictly inside Morocco's borders, converts PRECTOTCORR to mm/month, and caches CSV.
    """
    os.makedirs(data_dir, exist_ok=True)
    geojson_path = os.path.join(data_dir, "morocco_regions.geojson")
    geojson_data = load_morocco_geojson(geojson_path)

    cache_csv = os.path.join(data_dir, f"morocco_grid_monthly_{start_year}_{end_year}.csv")
    if os.path.exists(cache_csv):
        df_cached = pd.read_csv(cache_csv)
        df_cached["date"] = pd.to_datetime(df_cached["date"])
        return df_cached, geojson_data

    def _log(msg):
        print(msg)
        if progress_callback:
            progress_callback(msg)

    param_frames = {}
    for param in ["T2M", "PRECTOTCORR"]:
        tile_dfs = []
        for tile in MOROCCO_REGIONAL_TILES:
            _log(f"Downloading NASA POWER Monthly Regional [{param}] — tile {tile['name']} ({start_year}-{end_year})...")
            try:
                df_tile = _fetch_regional_monthly_tile(param, tile, start_year, end_year)
                if not df_tile.empty:
                    tile_dfs.append(df_tile)
            except Exception as e:
                _log(f"  Tile {tile['name']} warning ({e}), using 0.5° grid point fallback...")
                lats = np.arange(tile["lat_min"] + 0.25, tile["lat_max"], 0.75)
                lons = np.arange(tile["lon_min"] + 0.25, tile["lon_max"], 0.75)
                pts = pd.DataFrame([(la, lo) for la in lats for lo in lons], columns=["lat", "lon"])
                pts_clipped = clip_grid_to_morocco(pts, geojson_data)
                for _, pr in pts_clipped.iterrows():
                    try:
                        tile_dfs.append(_fetch_point_monthly_fallback(param, pr["lat"], pr["lon"], start_year, end_year))
                        time.sleep(0.15)
                    except Exception:
                        pass
            time.sleep(0.4)

        df_p = pd.concat(tile_dfs, ignore_index=True).drop_duplicates(subset=["lat", "lon", "ym"])
        param_frames[param] = df_p

    # Merge T2M & PRECTOTCORR
    df_all = pd.merge(
        param_frames["T2M"],
        param_frames["PRECTOTCORR"],
        on=["lat", "lon", "ym"],
        how="inner",
    )

    # Clip strictly to Morocco's 12 regions
    _log("Clipping grid cells to Morocco's official borders & assigning 12 regions...")
    clipped_meta = clip_grid_to_morocco(df_all[["lat", "lon"]], geojson_data)
    df_all = df_all.merge(clipped_meta, on=["lat", "lon"], how="inner")

    # Parse date + convert PRECTOTCORR (mm/day -> mm/month)
    df_all["year"] = df_all["ym"].str[:4].astype(int)
    df_all["month"] = df_all["ym"].str[4:6].astype(int)
    df_all["date"] = pd.to_datetime(df_all["ym"] + "01", format="%Y%m%d")
    df_all["days_in_month"] = [
        calendar.monthrange(int(y), int(m))[1] for y, m in zip(df_all["year"], df_all["month"])
    ]
    df_all["PRECTOTCORR_MM_DAY"] = df_all["PRECTOTCORR"]
    df_all["PRECTOTCORR"] = (df_all["PRECTOTCORR"] * df_all["days_in_month"]).round(2)
    df_all["cell_id"] = df_all["lat"].round(3).astype(str) + "_" + df_all["lon"].round(3).astype(str)

    df_all = df_all.sort_values(["cell_id", "date"]).reset_index(drop=True)
    df_all.to_csv(cache_csv, index=False)
    _log(f"Saved {len(df_all)} rows ({df_all['cell_id'].nunique()} grid cells inside Morocco) to {cache_csv}")
    return df_all, geojson_data


def load_member2_grid_csv(csv_path: str, geojson_path: str) -> tuple[pd.DataFrame, dict]:
    """
    Mlli yssifet lik Member 2 fichier CSV dyalo (fih lat, lon, date/ym, T2M, PRECTOTCORR),
    khedem b had l-function direct!
    """
    geojson_data = load_morocco_geojson(geojson_path)
    df = pd.read_csv(csv_path)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        df["year"] = df["date"].dt.year
        df["month"] = df["date"].dt.month
    if "region_name" not in df.columns:
        meta = clip_grid_to_morocco(df[["lat", "lon"]], geojson_data)
        df = df.merge(meta, on=["lat", "lon"], how="inner")
    df["cell_id"] = df["lat"].round(3).astype(str) + "_" + df["lon"].round(3).astype(str)
    return df, geojson_data