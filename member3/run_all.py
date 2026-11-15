import json
import os
import zipfile
import pandas as pd

from nasa_fetcher import fetch_all_morocco_regions
from stats_engine import analyze_earth_trends, summarize_all_morocco
from generate_plots import generate_all_member3_plots


def zip_project(folder_path: str, zip_name: str):
    with zipfile.ZipFile(zip_name, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(folder_path):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, os.path.dirname(folder_path))
                zf.write(full_path, rel_path)
    print(f"\n[SUCCESS] ZIP package ready: {os.path.abspath(zip_name)}")


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(base_dir, "data")
    out_dir = os.path.join(base_dir, "output")
    plots_dir = os.path.join(out_dir, "plots")
    os.makedirs(plots_dir, exist_ok=True)

    print("=== STEP 1: Downloading REAL NASA POWER Data (Morocco 12 Regions, 2000-2025) ===")
    datasets = fetch_all_morocco_regions(data_dir, start="20000101", end="20251231")

    print("\n=== STEP 2: Computing Member 3 Statistics (Fes vs Casablanca + All Morocco) ===")
    df_fes = datasets["Fes-Meknes (Fes)"]
    df_casa = datasets["Casablanca-Settat (Casablanca)"]

    stats_fes_casa = analyze_earth_trends(
        df_a=df_fes,
        df_b=df_casa,
        date_col="date",
        value_col="T2M",
        region_a_name="Fes-Meknes",
        region_b_name="Casablanca-Settat",
        variable_name="Temperature",
        unit="C",
        agg_mode="mean",
        split_year=2013,
    )

    stats_precip_fes = analyze_earth_trends(
        df_a=df_fes,
        df_b=df_casa,
        date_col="date",
        value_col="PRECTOTCORR",
        region_a_name="Fes-Meknes",
        region_b_name="Casablanca-Settat",
        variable_name="Precipitation",
        unit="mm",
        agg_mode="sum",
        split_year=2013,
    )

    morocco_summary = summarize_all_morocco(datasets)

    with open(os.path.join(out_dir, "stats_fes_vs_casablanca_temp.json"), "w", encoding="utf-8") as f:
        json.dump(stats_fes_casa, f, indent=2)
    with open(os.path.join(out_dir, "stats_fes_vs_casablanca_precip.json"), "w", encoding="utf-8") as f:
        json.dump(stats_precip_fes, f, indent=2)
    with open(os.path.join(out_dir, "morocco_12_regions_summary.json"), "w", encoding="utf-8") as f:
        json.dump(morocco_summary, f, indent=2)
    pd.DataFrame(morocco_summary).to_csv(os.path.join(out_dir, "morocco_12_regions_summary.csv"), index=False)

    print("\n=== STEP 3: Generating Real Graphs (PNG + Interactive HTML) ===")
    generate_all_member3_plots(stats_fes_casa, stats_precip_fes, morocco_summary, plots_dir)

    print("\n=== SUMMARY (REAL NASA DATA 2000-2025) ===")
    tr = stats_fes_casa["trend"]
    comp = stats_fes_casa["comparison_regions"]
    print(f"Fes-Meknes Temp Mean: {tr['overall_mean']} C")
    print(f"Fes-Meknes Sen's Slope: {tr['sens_slope_per_year']:+.4f} C/yr ({tr['sens_slope_per_decade']:+.2f} C/decade)")
    print(f"Fes-Meknes Mann-Kendall p-value: {tr['mk_p_value']:.6f} ({tr['mk_trend']})")
    print(f"Anomalies found (|z|>=2): {stats_fes_casa['anomalies']['count']}")
    print(f"Fes vs Casablanca slope diff p-value: {comp['slope_difference_p_value']:.4f}")
    print("\nTop 3 fastest warming regions in Morocco:")
    for row in morocco_summary[:3]:
        print(f"  - {row['region']}: {row['temp_sens_slope_per_decade']:+.2f} C/decade (p={row['temp_mk_p_value']:.4f})")

    print("\n=== STEP 4: Packaging Everything into ZIP ===")
    zip_out = os.path.join(os.path.dirname(base_dir), "member3_earthtrend_complete.zip")
    zip_project(base_dir, zip_out)


if __name__ == "__main__":
    main()