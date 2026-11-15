import json
import os
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import time
from stats_engine_spatial import (
    aggregate_by_administrative_region,
    analyze_single_series,
    build_national_json_for_ai,
    compare_two_zones_or_regions,
    compute_all_cells_spi6,
    compute_national_grid_summary,
)
REGION_NAME_MAP = {
    "Fès-Meknès": "Fez-Meknes",
    "Rabat-Salé-Kénitra": "Rabat-Salé-Kenitra",
    "Tanger-Tétouan-Al Hoceima": "Tangier-Tetouan-Al Hoceima",
}

CLIMATE_ZONE_MAP = {
    "Béni Mellal-Khénifra": "Mountains & Atlas",
    "Casablanca-Settat": "Atlantic Coast",
    "Dakhla-Oued Ed-Dahab": "South & Southeast (Saharan/Pre-Saharan)",
    "Drâa-Tafilalet": "South & Southeast (Saharan/Pre-Saharan)",
    "Fez-Meknes": "Center & Interior Plains",
    "Guelmim-Oued Noun": "Southwest",
    "Laâyoune-Sakia El Hamra": "South & Southeast (Saharan/Pre-Saharan)",
    "Marrakech-Safi": "Center & Interior Plains",
    "Oriental": "Northeast (Oriental)",
    "Rabat-Salé-Kenitra": "Atlantic Coast",
    "Souss-Massa": "Southwest",
    "Tangier-Tetouan-Al Hoceima": "North (Tangier-Rif)",
}
st.set_page_config(
    page_title="EarthTrend AI — Morocco National Spatial Analysis",
    page_icon="🇲🇦",
    layout="wide",
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

@st.cache_data(show_spinner="Loading prepared Morocco climate dataset...")
def load_morocco_dataset(start_yr: int, end_yr: int):

    grid_path = os.path.join(DATA_DIR, "earthtrend_master.csv")
    geojson_path = os.path.join(DATA_DIR, "morocco_regions.geojson")

    if not os.path.exists(grid_path):
        raise FileNotFoundError(f"Grid dataset not found: {grid_path}")

    if not os.path.exists(geojson_path):
        raise FileNotFoundError(f"GeoJSON not found: {geojson_path}")

    df = pd.read_csv(
        grid_path,
        usecols=["date", "year", "month", "region", "cell", "lat", "lon", "T2M", "PRECTOTCORR"],
    )

    df["date"] = pd.to_datetime(df["date"])
    df = df[(df["year"] >= start_yr) & (df["year"] <= end_yr)].copy()

    df["region_name"] = df["region"].replace(REGION_NAME_MAP)
    df["cell_id"] = df["cell"].astype(str).str.replace("^cell_", "", regex=True)

    cell_region = (
        df.groupby("cell_id")["region_name"]
        .agg(lambda s: s.dropna().mode().iloc[0] if not s.dropna().empty else None)
        .reset_index()
    )

    df_cells = (
        df.groupby(["cell_id", "date", "year", "month"], as_index=False)
        .agg(
            T2M=("T2M", "mean"),
            PRECTOTCORR_MM_DAY=("PRECTOTCORR", "mean"),
            lat=("lat", "mean"),
            lon=("lon", "mean"),
        )
    )

    coords = df_cells["cell_id"].str.split("_", n=1, expand=True)
    if coords.shape[1] == 2:
        df_cells["lat"] = pd.to_numeric(coords[0], errors="coerce").fillna(df_cells["lat"])
        df_cells["lon"] = pd.to_numeric(coords[1], errors="coerce").fillna(df_cells["lon"])

    df_cells = df_cells.merge(cell_region, on="cell_id", how="left")
    df_cells["climate_zone"] = df_cells["region_name"].map(CLIMATE_ZONE_MAP)
    df_cells["days_in_month"] = df_cells["date"].dt.days_in_month
    df_cells["PRECTOTCORR"] = df_cells["PRECTOTCORR_MM_DAY"] * df_cells["days_in_month"]
    df_cells["ym"] = df_cells["year"] * 100 + df_cells["month"]

    df_cells = df_cells.sort_values(["cell_id", "date"]).reset_index(drop=True)

    with open(geojson_path, "r", encoding="utf-8") as f:
        geojson_data = json.load(f)

    def _signed_area(ring):
        return sum(
            ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1]
            for i in range(len(ring) - 1)
        )

    for feat in geojson_data.get("features", []):
        geom = feat.get("geometry", {})
        gtype = geom.get("type")
        if gtype == "Polygon":
            rings = geom["coordinates"]
            if rings and _signed_area(rings[0]) > 0:
                rings[0] = rings[0][::-1]
            for i in range(1, len(rings)):
                if _signed_area(rings[i]) < 0:
                    rings[i] = rings[i][::-1]
        elif gtype == "MultiPolygon":
            for poly in geom["coordinates"]:
                if poly and _signed_area(poly[0]) > 0:
                    poly[0] = poly[0][::-1]
                for i in range(1, len(poly)):
                    if _signed_area(poly[i]) < 0:
                        poly[i] = poly[i][::-1]

    df_cells = compute_all_cells_spi6(df_cells)

    return df_cells, geojson_data

# ==============================================================================
# SIDEBAR CONTROLS
# ==============================================================================
st.sidebar.title("🇲🇦 Morocco Climate Detective")
st.sidebar.caption("National Grid + 12 Regions")
st.sidebar.info("Available dataset: January 2000 – December 2024")

base_start = 2000

#df_full, morocco_gj = load_morocco_dataset(base_start, 2025)

start_time = time.perf_counter()

with st.spinner("Loading climate data and calculating SPI-6..."):
     df_full, morocco_gj = load_morocco_dataset(base_start, 2024)

elapsed = time.perf_counter() - start_time

st.success(f"Data loaded successfully in {elapsed:.2f} seconds")


max_year = int(df_full["year"].max())
year_range = st.sidebar.slider("Filter Year Range", base_start, max_year, (base_start, max_year))
yr_min, yr_max = year_range
df_filtered = df_full[(df_full["year"] >= yr_min) & (df_full["year"] <= yr_max)].copy()

split_yr = None
if yr_max - yr_min >= 8:
    split_yr = st.sidebar.slider("Period 1 vs 2 Split Year", yr_min + 4, yr_max - 4, (yr_min + yr_max) // 2)

z_thresh = st.sidebar.slider("Anomaly Z-score Threshold", 1.5, 3.0, 2.0, step=0.1)

regions_list = sorted(df_filtered["region_name"].unique().tolist())
zones_list = sorted(df_filtered["climate_zone"].unique().tolist())

compare_mode = st.sidebar.radio("Compare Level", ["Administrative Regions (12)", "Climate Zones (North/South/Coast/Atlas)"])
if compare_mode.startswith("Administrative"):
    sel_a = st.sidebar.selectbox("Area A", regions_list, index=0)
    sel_b = st.sidebar.selectbox("Area B", regions_list, index=min(1, len(regions_list) - 1))
    filter_col = "region_name"
else:
    sel_a = st.sidebar.selectbox("Zone A", zones_list, index=0)
    sel_b = st.sidebar.selectbox("Zone B", zones_list, index=min(1, len(zones_list) - 1))
    filter_col = "climate_zone"

var_choice = st.sidebar.radio("Variable for Deep Dive", ["Temperature (T2M)", "Precipitation (PRECTOTCORR)"])
val_col = "T2M" if var_choice.startswith("Temperature") else "PRECTOTCORR"
agg_mode = "mean" if val_col == "T2M" else "sum"
unit = "°C" if val_col == "T2M" else "mm"

# ==============================================================================
# COMPUTE NATIONAL + REGIONAL + COMPARISON STATS LIVE
# ==============================================================================
df_cells_summary = compute_national_grid_summary(df_filtered)
df_regions_summary = aggregate_by_administrative_region(df_filtered, df_cells_summary)

nat_temp = analyze_single_series(df_filtered, "T2M", "mean", "All Morocco", z_thresh, split_yr)
nat_precip = analyze_single_series(df_filtered, "PRECTOTCORR", "sum", "All Morocco", z_thresh, split_yr)

res_a = analyze_single_series(df_filtered[df_filtered[filter_col] == sel_a], val_col, agg_mode, sel_a, z_thresh, split_yr)
res_b = analyze_single_series(df_filtered[df_filtered[filter_col] == sel_b], val_col, agg_mode, sel_b, z_thresh, split_yr)
cmp_ab = compare_two_zones_or_regions(res_a, res_b)

# ==============================================================================
# HEADER & NATIONAL KPI CARDS
# ==============================================================================
st.title("🇲🇦 EarthTrend AI — Morocco National Climate Analysis")
st.caption(
    f"NASA POWER 0.5° Regional Grid ({len(df_cells_summary)} grid cells inside Morocco) | "
    f"12 Regions | Period: {yr_min}–{yr_max}"
)

k1, k2, k3, k4 = st.columns(4)
k1.metric("National Warming Rate", f"{nat_temp['sens_slope_decade']:+.2f} °C/decade", f"MK p = {nat_temp['mk_p_value']:.4f}")
k2.metric("Cells w/ Significant Warming", f"{df_cells_summary['temp_significant'].mean()*100:.1f}%", f"{int(df_cells_summary['temp_significant'].sum())}/{len(df_cells_summary)} cells (p<0.05)")
k3.metric("National Rainfall Trend", f"{nat_precip['sens_slope_decade']:+.1f} mm/dec", f"Mean: {nat_precip['overall_mean']:.0f} mm/yr")
k4.metric(f"{sel_a[:12]} vs {sel_b[:12]}", f"p = {cmp_ab['slope_diff_p']:.4f}", f"Mean diff: {cmp_ab['mean_diff']:+.2f} {unit}")

# ==============================================================================
# TABS
# ==============================================================================
t1, t2, t3, t4, t5 = st.tabs([
    "🗺️ National Maps (12 Regions + Grid)",
    "🌵 SPI-6 Drought Grid Map",
    "⚖️ Compare Regions & Climate Zones",
    "🌦️ Seasonality & Anomalies",
    "🧾 National JSON (Member 4 & 5)",
])

# --- TAB 1: NATIONAL CHOROPLETH + GRID MAPS (Exact match to your 3rd & 2nd reference images) ---
with t1:
    st.subheader("12 Administrative Regions: Temperature & Rainfall Trends in Morocco")
    c_map1, c_map2 = st.columns(2)

    with c_map1:
        fig_ch_t = go.Figure(go.Choropleth(
            geojson=morocco_gj,
            locations=df_regions_summary["region_name"],
            featureidkey="properties.region_name",
            z=df_regions_summary["temp_sens_slope_decade"],
            colorscale="YlOrRd",
            colorbar_title="°C/dec",
            text=df_regions_summary.apply(
                lambda r: f"{r['region_name']}<br>Warming: {r['temp_sens_slope_decade']:+.2f} °C/dec<br>Mean: {r['temp_mean_C']:.1f} °C<br>MK p={r['temp_mk_p']:.4f}",
                axis=1,
            ),
            hoverinfo="text",
        ))
        fig_ch_t.update_geos(fitbounds="locations", visible=False, bgcolor="#0b1120")
        fig_ch_t.update_layout(template="plotly_dark", height=500, title="Temperature Trend by Region (°C / decade)")
        st.plotly_chart(fig_ch_t, use_container_width=True)

    with c_map2:
        fig_ch_p = go.Figure(go.Choropleth(
            geojson=morocco_gj,
            locations=df_regions_summary["region_name"],
            featureidkey="properties.region_name",
            z=df_regions_summary["precip_annual_mean_mm"],
            colorscale="Blues",
            colorbar_title="mm/yr",
            text=df_regions_summary.apply(
                lambda r: f"{r['region_name']}<br>Mean Annual Precip: {r['precip_annual_mean_mm']:.0f} mm<br>Trend: {r['precip_sens_slope_mm_decade']:+.1f} mm/dec<br>MK p={r['precip_mk_p']:.4f}",
                axis=1,
            ),
            hoverinfo="text",
        ))
        fig_ch_p.update_geos(fitbounds="locations", visible=False, bgcolor="#0b1120")
        fig_ch_p.update_layout(template="plotly_dark", height=500, title="Average Annual Precipitation by Region (mm/yr)")
        st.plotly_chart(fig_ch_p, use_container_width=True)

    st.subheader("0.5° Spatial Grid Cells Across Morocco (Mann-Kendall & Sen's Slope)")
    grid_metric = st.radio(
        "Select Grid Layer",
        ["Warming Trend (°C/decade)", "Mean Annual Precipitation (mm/yr)", "Precipitation Trend (mm/decade)"],
        horizontal=True,
    )
    if grid_metric.startswith("Warming"):
        z_col, cscale, z_title = "temp_sens_slope_decade", "YlOrRd", "°C/dec"
    elif grid_metric.startswith("Mean Annual"):
        z_col, cscale, z_title = "precip_annual_mean_mm", "Blues", "mm/yr"
    else:
        z_col, cscale, z_title = "precip_sens_slope_mm_decade", "RdBu", "mm/dec"

    fig_grid = go.Figure(go.Scattergeo(
        lat=df_cells_summary["lat"],
        lon=df_cells_summary["lon"],
        mode="markers",
        marker=dict(
            size=10,
            symbol="square",
            color=df_cells_summary[z_col],
            colorscale=cscale,
            showscale=True,
            colorbar=dict(title=z_title),
            line=dict(
                width=[1.5 if sig else 0.3 for sig in df_cells_summary["temp_significant"]],
                color=["#ffffff" if sig else "#334155" for sig in df_cells_summary["temp_significant"]],
            ),
        ),
        text=df_cells_summary.apply(
            lambda r: (
                f"<b>{r['region_name']}</b> ({r['lat']:.2f}, {r['lon']:.2f})<br>"
                f"Temp mean: {r['temp_mean_C']} °C | Warming: {r['temp_sens_slope_decade']:+.2f} °C/dec (p={r['temp_mk_p']:.4f})<br>"
                f"Precip mean: {r['precip_annual_mean_mm']} mm/yr | Trend: {r['precip_sens_slope_mm_decade']:+.1f} mm/dec"
            ),
            axis=1,
        ),
        hoverinfo="text",
    ))
    fig_grid.update_geos(
        scope="africa",
        lataxis_range=[20.5, 36.5],
        lonaxis_range=[-17.5, -0.5],
        showcountries=True, countrycolor="#64748b",
        showland=True, landcolor="#111827",
        bgcolor="#0b1120",
    )
    fig_grid.update_layout(template="plotly_dark", height=540, title=f"Grid Cell Spatial Analysis: {grid_metric} (White border = p < 0.05)")
    st.plotly_chart(fig_grid, use_container_width=True)
    st.dataframe(df_regions_summary, use_container_width=True)

# --- TAB 2: SPI-6 DROUGHT GRID MAP (Exact match to your 1st reference image) ---
with t2:
    st.subheader("Standardized Precipitation Index (Gamma), 6-Month (SPI-6)")
    st.caption("SPI <= -1.5 = Severe Drought (Red) | SPI >= +1.5 = Very Wet (Blue)")

    avail_dates = sorted(df_filtered.dropna(subset=["SPI_6"])["date"].unique())
    if avail_dates:
        date_labels = [pd.Timestamp(d).strftime("%Y-%m") for d in avail_dates]
        default_idx = date_labels.index("2022-12") if "2022-12" in date_labels else len(date_labels) - 1
        chosen_ym = st.select_slider("Select Month for National SPI-6 Drought Map", options=date_labels, value=date_labels[default_idx])

        df_spi_slice = df_filtered[df_filtered["date"].dt.strftime("%Y-%m") == chosen_ym].dropna(subset=["SPI_6"])

        fig_spi = go.Figure(go.Scattergeo(
            lat=df_spi_slice["lat"],
            lon=df_spi_slice["lon"],
            mode="markers",
            marker=dict(
                size=11,
                symbol="square",
                color=df_spi_slice["SPI_6"],
                colorscale="RdBu",
                cmin=-3.0, cmax=3.0,
                showscale=True,
                colorbar=dict(title="SPI-6"),
            ),
            text=df_spi_slice.apply(
                lambda r: f"{r['region_name']} ({r['lat']:.2f}, {r['lon']:.2f})<br>SPI-6: {r['SPI_6']:+.2f}<br>Month Precip: {r['PRECTOTCORR']:.1f} mm",
                axis=1,
            ),
            hoverinfo="text",
        ))
        fig_spi.update_geos(
            scope="africa",
            lataxis_range=[20.5, 36.5],
            lonaxis_range=[-17.5, -0.5],
            showcountries=True, countrycolor="#64748b",
            showland=True, landcolor="#111827",
            bgcolor="#0b1120",
        )
        fig_spi.update_layout(template="plotly_dark", height=540, title=f"Morocco SPI-6 Drought / Wetness Grid — {chosen_ym}")
        st.plotly_chart(fig_spi, use_container_width=True)

        # National SPI-6 Time Series
        spi_nat = df_filtered.groupby("date")["SPI_6"].mean().dropna()
        fig_spi_ts = go.Figure(go.Bar(
            x=spi_nat.index, y=spi_nat.values,
            marker_color=["#ef4444" if v < 0 else "#3b82f6" for v in spi_nat.values],
            name="National Mean SPI-6",
        ))
        fig_spi_ts.add_hline(y=-1.5, line_dash="dash", line_color="#fca5a5", annotation_text="Severe Drought (-1.5)")
        fig_spi_ts.update_layout(template="plotly_dark", title="Morocco National Average SPI-6 Over Time (Drought vs Wet Periods)", yaxis_title="SPI-6")
        st.plotly_chart(fig_spi_ts, use_container_width=True)

# --- TAB 3: COMPARE REGIONS & CLIMATE ZONES ---
with t3:
    st.subheader(f"Compare: {sel_a} vs {sel_b} ({var_choice})")
    c1, c2 = st.columns(2)
    with c1:
        fig_ab = go.Figure()
        fig_ab.add_trace(go.Scatter(x=res_a["years"], y=res_a["yearly_values"], mode="lines+markers", name=sel_a, line=dict(color="#f97316")))
        fig_ab.add_trace(go.Scatter(x=res_a["years"], y=res_a["sens_line"], mode="lines", name=f"{sel_a} Sen's slope", line=dict(color="#f97316", dash="dash")))
        fig_ab.add_trace(go.Scatter(x=res_b["years"], y=res_b["yearly_values"], mode="lines+markers", name=sel_b, line=dict(color="#38bdf8")))
        fig_ab.add_trace(go.Scatter(x=res_b["years"], y=res_b["sens_line"], mode="lines", name=f"{sel_b} Sen's slope", line=dict(color="#38bdf8", dash="dash")))
        fig_ab.update_layout(template="plotly_dark", title=f"{sel_a} vs {sel_b} — Yearly Trend", hovermode="x unified", yaxis_title=f"{var_choice} ({unit})")
        st.plotly_chart(fig_ab, use_container_width=True)

    with c2:
        fig_bar = go.Figure(go.Bar(
            x=[sel_a, sel_b],
            y=[res_a["sens_slope_decade"], res_b["sens_slope_decade"]],
            marker_color=["#f97316", "#38bdf8"],
            text=[f"{res_a['sens_slope_decade']:+.3f}", f"{res_b['sens_slope_decade']:+.3f}"],
            textposition="outside",
        ))
        fig_bar.update_layout(
            template="plotly_dark",
            title=f"Trend Comparison ({unit}/decade) | Slope diff p = {cmp_ab['slope_diff_p']:.4f}",
            yaxis_title=f"Sen's Slope ({unit}/decade)",
        )
        st.plotly_chart(fig_bar, use_container_width=True)
        st.json(cmp_ab)

# --- TAB 4: SEASONALITY & ANOMALIES ---
with t4:
    st.subheader(f"Seasonality & Anomalies — {sel_a} ({var_choice})")
    seas = res_a["seasonality"]
    anom = res_a["anomalies"]
    if seas:
        cs1, cs2 = st.columns(2)
        with cs1:
            fig_s = go.Figure(go.Scatter(x=seas["month_names"], y=seas["seasonal_component"], mode="lines+markers", line=dict(color="#22c55e", width=3)))
            fig_s.add_hline(y=0, line_dash="dash", line_color="#64748b")
            fig_s.update_layout(template="plotly_dark", title=f"Seasonal Component — {sel_a}", yaxis_title=f"Effect ({unit})")
            st.plotly_chart(fig_s, use_container_width=True)

        with cs2:
            fig_an = go.Figure()
            fig_an.add_trace(go.Scatter(x=seas["dates"], y=seas["observed"], mode="lines", name="Observed", line=dict(color="#38bdf8", width=1.2)))
            fig_an.add_trace(go.Scatter(x=seas["dates"], y=seas["trend_component"], mode="lines", name="Trend", line=dict(color="#f97316", width=2.2)))
            if anom["all_anomalies"]:
                fig_an.add_trace(go.Scatter(
                    x=[a["date_full"] for a in anom["all_anomalies"]],
                    y=[a["observed"] for a in anom["all_anomalies"]],
                    mode="markers", name="Anomalies",
                    marker=dict(color="#ef4444", size=9, line=dict(color="white", width=1)),
                ))
            fig_an.update_layout(template="plotly_dark", title=f"Monthly Anomalies (|z| >= {z_thresh}) — {sel_a}", yaxis_title=unit)
            st.plotly_chart(fig_an, use_container_width=True)

        if anom["all_anomalies"]:
            st.dataframe(pd.DataFrame(anom["all_anomalies"]).drop(columns=["date_full"]), use_container_width=True)

# --- TAB 5: NATIONAL JSON CONTRACT ---
with t5:
    st.subheader("National JSON Summary (Ready for Member 4 Claude AI & Member 5)")
    nat_json = build_national_json_for_ai(df_regions_summary, df_cells_summary, nat_temp, nat_precip, cmp_ab)
    st.download_button(
        "⬇️ Download Morocco National Stats JSON",
        data=json.dumps(nat_json, indent=2, ensure_ascii=False).encode("utf-8"),
        file_name=f"morocco_national_stats_{yr_min}_{yr_max}.json",
        mime="application/json",
    )
    st.json(nat_json)