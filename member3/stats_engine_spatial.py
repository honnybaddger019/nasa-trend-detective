import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.tsa.seasonal import seasonal_decompose
import pymannkendall as mk


# ==============================================================================
# 1. SPI-6 (Standardized Precipitation Index - Gamma 6-month) per Grid Cell
# ==============================================================================
def compute_spi6_series(monthly_precip: pd.Series) -> pd.Series:
    """
    Calculates 6-month Standardized Precipitation Index (Gamma distribution)
    matching WMO standard: SPI <= -1.5 severe drought, >= +1.5 very wet.
    """
    s = monthly_precip.sort_index().astype(float)
    roll6 = s.rolling(window=6, min_periods=6).sum()
    spi = pd.Series(index=s.index, dtype=float)

    for m in range(1, 13):
        idx = roll6.index[roll6.index.month == m]
        vals = roll6.loc[idx].dropna()
        if len(vals) < 6:
            continue

        n_total = len(vals)
        zeros = (vals <= 0).sum()
        q = zeros / n_total
        pos = vals[vals > 0]

        if len(pos) >= 4 and pos.std() > 1e-6:
            try:
                shape, _, scale = stats.gamma.fit(pos.values, floc=0)
                cdf_vals = np.where(
                    vals.values <= 0,
                    q,
                    q + (1.0 - q) * stats.gamma.cdf(vals.values, shape, loc=0, scale=scale),
                )
                cdf_vals = np.clip(cdf_vals, 0.00135, 0.99865)  # bounds -> [-3, +3]
                spi.loc[vals.index] = stats.norm.ppf(cdf_vals)
                continue
            except Exception:
                pass

        # Fallback l manatiq sahrawiya li fiha 0 chta f sayf
        std_v = vals.std(ddof=1)
        if std_v > 1e-6:
            spi.loc[vals.index] = np.clip((vals - vals.mean()) / std_v, -3.0, 3.0)
        else:
            spi.loc[vals.index] = 0.0

    return spi


def compute_all_cells_spi6(df_grid: pd.DataFrame) -> pd.DataFrame:
    """
    Adds 'SPI_6' column across every grid cell in Morocco.
    """
    df = df_grid.sort_values(["cell_id", "date"]).copy()
    spi_parts = []
    for _, grp in df.groupby("cell_id", sort=False):
        s = grp.set_index("date")["PRECTOTCORR"]
        spi_s = compute_spi6_series(s)
        tmp = grp[["cell_id", "date"]].copy()
        tmp["SPI_6"] = spi_s.values
        spi_parts.append(tmp)
    spi_df = pd.concat(spi_parts, ignore_index=True)
    return df.merge(spi_df, on=["cell_id", "date"], how="left")


# ==============================================================================
# 2. SPATIAL GRID ANALYSIS (Trend + Mann-Kendall + Sen's slope per Grid Cell)
# ==============================================================================
def _cell_trend_stats(years: np.ndarray, values: np.ndarray) -> dict:
    if len(values) < 4 or np.all(np.isnan(values)):
        return {"mean": np.nan, "sens_slope": np.nan, "linreg_slope": np.nan, "mk_p": np.nan, "mk_trend": "insufficient"}

    mask = ~np.isnan(values)
    x, y = years[mask].astype(float), values[mask].astype(float)
    if len(y) < 4:
        return {"mean": np.nan, "sens_slope": np.nan, "linreg_slope": np.nan, "mk_p": np.nan, "mk_trend": "insufficient"}

    ols = stats.linregress(x, y)
    theil = stats.theilslopes(y, x)
    mk_res = mk.original_test(y)

    return {
        "mean": float(np.mean(y)),
        "sens_slope": float(theil.slope),
        "linreg_slope": float(ols.slope),
        "linreg_stderr": float(ols.stderr),
        "mk_p": float(mk_res.p),
        "mk_trend": str(mk_res.trend),
        "significant": bool(mk_res.p < 0.05),
    }


def compute_national_grid_summary(df_grid: pd.DataFrame) -> pd.DataFrame:
    """
    Computes T2M & PRECTOTCORR trends (Mann-Kendall + Sen's slope + annual means)
    for EVERY Grid Cell inside Morocco.
    """
    yearly_cell = (
        df_grid.groupby(["cell_id", "lat", "lon", "region_name", "climate_zone", "year"], as_index=False)
        .agg(T2M_mean=("T2M", "mean"), PRECTOTCORR_sum=("PRECTOTCORR", "sum"))
    )

    records = []
    for (cid, lat, lon, rname, czone), grp in yearly_cell.groupby(
        ["cell_id", "lat", "lon", "region_name", "climate_zone"]
    ):
        grp = grp.sort_values("year")
        yrs = grp["year"].values
        st_t = _cell_trend_stats(yrs, grp["T2M_mean"].values)
        st_p = _cell_trend_stats(yrs, grp["PRECTOTCORR_sum"].values)

        records.append({
            "cell_id": cid,
            "lat": float(lat),
            "lon": float(lon),
            "region_name": rname,
            "climate_zone": czone,
            "temp_mean_C": round(st_t["mean"], 2),
            "temp_sens_slope_yr": round(st_t["sens_slope"], 5),
            "temp_sens_slope_decade": round(st_t["sens_slope"] * 10, 3),
            "temp_mk_p": round(st_t["mk_p"], 5),
            "temp_mk_trend": st_t["mk_trend"],
            "temp_significant": st_t.get("significant", False),
            "precip_annual_mean_mm": round(st_p["mean"], 1),
            "precip_sens_slope_mm_yr": round(st_p["sens_slope"], 3),
            "precip_sens_slope_mm_decade": round(st_p["sens_slope"] * 10, 2),
            "precip_mk_p": round(st_p["mk_p"], 5),
            "precip_mk_trend": st_p["mk_trend"],
            "precip_significant": st_p.get("significant", False),
        })

    return pd.DataFrame(records)


# ==============================================================================
# 3. REGIONAL & CLIMATE ZONE AGGREGATION (12 Regions + North/South/Coast/Atlas)
# ==============================================================================
def analyze_single_series(
    df_sub: pd.DataFrame,
    value_col: str = "T2M",
    agg_mode: str = "mean",
    label: str = "Morocco",
    z_threshold: float = 2.0,
    split_year: int = None,
) -> dict:
    """
    Aggregates grid cells into a regional/national monthly & yearly time series,
    then computes full Trend + Mann-Kendall + Seasonality + Z-score Anomalies + Period comparison.
    """
    if agg_mode == "sum":
        # Average across cells per month, then sum over months per year
        monthly_s = df_sub.groupby("date")[value_col].mean().sort_index().asfreq("MS")
        yearly_s = monthly_s.groupby(monthly_s.index.year).sum(min_count=10).dropna()
    else:
        monthly_s = df_sub.groupby("date")[value_col].mean().sort_index().asfreq("MS")
        yearly_s = monthly_s.groupby(monthly_s.index.year).mean().dropna()

    y = yearly_s.values.astype(float)
    x = yearly_s.index.values.astype(float)
    if len(y) < 4:
        return {"error": "Need at least 4 years of data."}

    ols = stats.linregress(x, y)
    theil = stats.theilslopes(y, x)
    mk_res = mk.original_test(y)

    # Seasonality
    m_filled = monthly_s.interpolate(method="linear").dropna()
    seasonality = {}
    anomalies = {"count": 0, "all_anomalies": [], "top_anomalies": []}

    if len(m_filled) >= 24:
        decomp = seasonal_decompose(m_filled, model="additive", period=12, extrapolate_trend="freq")
        sdf = pd.DataFrame({"month": m_filled.index.month, "seasonal": decomp.seasonal.values, "val": m_filled.values})
        mpat = sdf.groupby("month")["seasonal"].mean()
        mavg = sdf.groupby("month")["val"].mean()
        mnames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        pk, tr_m = int(mpat.idxmax()), int(mpat.idxmin())
        seasonality = {
            "months": list(range(1, 13)),
            "month_names": mnames,
            "seasonal_component": [round(float(mpat.loc[m]), 3) for m in range(1, 13)],
            "monthly_climatology": [round(float(mavg.loc[m]), 3) for m in range(1, 13)],
            "peak_month": {"name": mnames[pk - 1], "effect": round(float(mpat.loc[pk]), 3)},
            "trough_month": {"name": mnames[tr_m - 1], "effect": round(float(mpat.loc[tr_m]), 3)},
            "dates": [d.strftime("%Y-%m-%d") for d in m_filled.index],
            "observed": [round(float(v), 3) for v in m_filled.values],
            "trend_component": [round(float(v), 3) for v in decomp.trend.values],
        }

        resid = decomp.resid.dropna()
        expected = (decomp.trend + decomp.seasonal).reindex(resid.index)
        obs_r = m_filled.reindex(resid.index)
        z = (resid - resid.mean()) / (resid.std(ddof=1) if resid.std(ddof=1) > 1e-9 else 1.0)
        anom_list = []
        for d in z[z.abs() >= z_threshold].index:
            anom_list.append({
                "date": d.strftime("%Y-%m"),
                "date_full": d.strftime("%Y-%m-%d"),
                "observed": round(float(obs_r.loc[d]), 2),
                "expected": round(float(expected.loc[d]), 2),
                "deviation": round(float(obs_r.loc[d] - expected.loc[d]), 2),
                "z_score": round(float(z.loc[d]), 2),
                "direction": "high" if z.loc[d] > 0 else "low",
            })
        anom_list = sorted(anom_list, key=lambda item: abs(item["z_score"]), reverse=True)
        anomalies = {"count": len(anom_list), "z_threshold": z_threshold, "top_anomalies": anom_list[:8], "all_anomalies": anom_list}

    # Period comparison
    period_cmp = {}
    if split_year and len(yearly_s[yearly_s.index < split_year]) >= 4 and len(yearly_s[yearly_s.index >= split_year]) >= 4:
        p1, p2 = yearly_s[yearly_s.index < split_year], yearly_s[yearly_s.index >= split_year]
        _, p_mean = stats.ttest_ind(p1.values, p2.values, equal_var=False)
        period_cmp = {
            "label_1": f"{int(p1.index.min())}-{int(p1.index.max())}",
            "label_2": f"{int(p2.index.min())}-{int(p2.index.max())}",
            "mean_1": round(float(p1.mean()), 3),
            "mean_2": round(float(p2.mean()), 3),
            "shift": round(float(p2.mean() - p1.mean()), 3),
            "ttest_p_value": float(p_mean),
        }

    return {
        "label": label,
        "years": [int(yr) for yr in x],
        "yearly_values": [round(float(v), 3) for v in y],
        "sens_line": [round(float(theil.slope * yr + theil.intercept), 3) for yr in x],
        "linreg_line": [round(float(ols.slope * yr + ols.intercept), 3) for yr in x],
        "overall_mean": round(float(np.mean(y)), 3),
        "sens_slope_yr": round(float(theil.slope), 5),
        "sens_slope_decade": round(float(theil.slope * 10), 3),
        "linreg_r2": round(float(ols.rvalue ** 2), 3),
        "mk_p_value": float(mk_res.p),
        "mk_trend": str(mk_res.trend),
        "mk_significant": bool(mk_res.p < 0.05),
        "seasonality": seasonality,
        "anomalies": anomalies,
        "period_comparison": period_cmp,
        "_yearly_series": yearly_s,
    }


def compare_two_zones_or_regions(res_a: dict, res_b: dict) -> dict:
    ya, yb = res_a["_yearly_series"], res_b["_yearly_series"]
    xa, va = ya.index.values.astype(float), ya.values.astype(float)
    xb, vb = yb.index.values.astype(float), yb.values.astype(float)

    oa, ob = stats.linregress(xa, va), stats.linregress(xb, vb)
    denom = np.sqrt(oa.stderr ** 2 + ob.stderr ** 2)
    df_s = len(xa) + len(xb) - 4
    p_slope = float(2 * (1 - stats.t.cdf(abs((oa.slope - ob.slope) / denom), df=df_s))) if denom > 1e-12 and df_s > 0 else 1.0
    _, p_mean = stats.ttest_ind(va, vb, equal_var=False)

    return {
        "label_a": res_a["label"],
        "label_b": res_b["label"],
        "mean_a": res_a["overall_mean"],
        "mean_b": res_b["overall_mean"],
        "mean_diff": round(res_a["overall_mean"] - res_b["overall_mean"], 3),
        "mean_ttest_p": float(p_mean),
        "sens_slope_a_yr": res_a["sens_slope_yr"],
        "sens_slope_b_yr": res_b["sens_slope_yr"],
        "slope_diff_p": p_slope,
        "slopes_significantly_different": bool(p_slope < 0.05),
    }


def aggregate_by_administrative_region(df_grid: pd.DataFrame, df_cells_summary: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregates Grid Cell results into the 12 Administrative Regions of Morocco
    (exact regional-level trend + annual mean for Choropleth Maps).
    """
    rows = []
    for rname, grp_cells in df_cells_summary.groupby("region_name"):
        df_reg = df_grid[df_grid["region_name"] == rname]
        st_t = analyze_single_series(df_reg, value_col="T2M", agg_mode="mean", label=rname)
        st_p = analyze_single_series(df_reg, value_col="PRECTOTCORR", agg_mode="sum", label=rname)
        rows.append({
            "region_name": rname,
            "climate_zone": grp_cells["climate_zone"].iloc[0],
            "n_grid_cells": int(len(grp_cells)),
            "temp_mean_C": st_t["overall_mean"],
            "temp_sens_slope_decade": st_t["sens_slope_decade"],
            "temp_mk_p": round(st_t["mk_p_value"], 5),
            "temp_significant": st_t["mk_significant"],
            "temp_anomalies": st_t["anomalies"]["count"],
            "precip_annual_mean_mm": st_p["overall_mean"],
            "precip_sens_slope_mm_yr": st_p["sens_slope_yr"],
            "precip_sens_slope_mm_decade": st_p["sens_slope_decade"],
            "precip_mk_p": round(st_p["mk_p_value"], 5),
            "precip_significant": st_p["mk_significant"],
        })
    return pd.DataFrame(rows).sort_values("temp_sens_slope_decade", ascending=False).reset_index(drop=True)


def build_national_json_for_ai(
    df_regions_summary: pd.DataFrame,
    df_cells_summary: pd.DataFrame,
    national_temp: dict,
    national_precip: dict,
    comparison: dict = None,
) -> dict:
    """
    Clean JSON summary ready for Member 4 (Claude API) & Member 5 (Dashboard).
    """
    return {
        "scope": "National Spatial Analysis — Morocco (0.5 deg Grid Cells + 12 Regions)",
        "source": "NASA POWER Regional Monthly API",
        "n_grid_cells": int(len(df_cells_summary)),
        "pct_cells_significant_warming": round(float(df_cells_summary["temp_significant"].mean() * 100), 1),
        "national_temperature": {
            "mean_C": national_temp["overall_mean"],
            "sens_slope_per_decade_C": national_temp["sens_slope_decade"],
            "mk_p_value": national_temp["mk_p_value"],
            "mk_trend": national_temp["mk_trend"],
            "top_anomalies": national_temp["anomalies"]["top_anomalies"][:5],
        },
        "national_precipitation": {
            "annual_mean_mm": national_precip["overall_mean"],
            "sens_slope_mm_per_decade": national_precip["sens_slope_decade"],
            "mk_p_value": national_precip["mk_p_value"],
            "mk_trend": national_precip["mk_trend"],
        },
        "fastest_warming_regions": df_regions_summary.head(3)[["region_name", "temp_sens_slope_decade", "temp_mk_p"]].to_dict("records"),
        "driest_regions": df_regions_summary.sort_values("precip_annual_mean_mm").head(3)[["region_name", "precip_annual_mean_mm", "precip_sens_slope_mm_decade"]].to_dict("records"),
        "regional_comparison": comparison,
        "all_12_regions": df_regions_summary.to_dict("records"),
    }