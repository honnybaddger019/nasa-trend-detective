import os
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd


def _style_dark(fig, axes):
    fig.patch.set_facecolor("#0b1120")
    if not isinstance(axes, (list, tuple)):
        axes = [axes]
    for ax in axes:
        ax.set_facecolor("#111827")
        ax.tick_params(colors="#cbd5e1")
        ax.xaxis.label.set_color("#e2e8f0")
        ax.yaxis.label.set_color("#e2e8f0")
        ax.title.set_color("#f8fafc")
        for spine in ax.spines.values():
            spine.set_color("#334155")
        ax.grid(color="#1e293b", linestyle="--", linewidth=0.6, alpha=0.8)


def generate_all_member3_plots(
    stats_fes_casa: dict,
    stats_precip_fes: dict,
    morocco_summary: list,
    out_dir: str,
):
    os.makedirs(out_dir, exist_ok=True)
    plt.rcParams["font.sans-serif"] = "DejaVu Sans"

    # 1) 3-Panel Deliverable (Page 6 of Hackathon Plan)
    fig, axes = plt.subplots(1, 3, figsize=(17, 5.2))
    _style_dark(fig, list(axes))

    tr = stats_fes_casa["trend"]
    axes[0].plot(tr["years"], tr["yearly_values"], "o-", color="#38bdf8", lw=1.8, ms=4.5, label="Yearly Mean")
    axes[0].plot(tr["years"], tr["sens_line"], "-", color="#f97316", lw=2.4, label="Sen's Slope")
    axes[0].set_title(f"1. Trend: {stats_fes_casa['metadata']['region']} ({tr['start_year']}-{tr['end_year']})")
    axes[0].set_ylabel("Temperature (°C)")
    axes[0].set_xlabel("Year")
    axes[0].legend(loc="lower right", facecolor="#1e293b", edgecolor="#334155")
    axes[0].text(
        0.04, 0.83,
        f"Sen's slope: {tr['sens_slope_per_year']:+.4f} °C/yr\n"
        f"({tr['sens_slope_per_decade']:+.2f} °C/decade)\n"
        f"Mann-Kendall p = {tr['mk_p_value']:.4f}",
        transform=axes[0].transAxes, fontsize=9, color="#f8fafc",
        bbox=dict(boxstyle="round", facecolor="#1e293b", edgecolor="#f97316", alpha=0.9),
    )

    seas = stats_fes_casa["seasonality"]
    axes[1].plot(seas["months"], seas["seasonal_component"], "o-", color="#22c55e", lw=2.4, ms=5)
    axes[1].axhline(0, color="#64748b", ls="--", lw=0.9)
    axes[1].set_xticks(seas["months"])
    axes[1].set_xticklabels(seas["month_names"], fontsize=8)
    axes[1].set_title("2. Seasonality Component (Jan-Dec)")
    axes[1].set_ylabel("Seasonal Effect (°C)")
    axes[1].text(
        0.05, 0.86,
        f"Peak: {seas['peak_month']['name']} ({seas['peak_month']['effect']:+.1f} °C)\n"
        f"Trough: {seas['trough_month']['name']} ({seas['trough_month']['effect']:+.1f} °C)",
        transform=axes[1].transAxes, fontsize=9, color="#f8fafc",
        bbox=dict(boxstyle="round", facecolor="#1e293b", edgecolor="#22c55e", alpha=0.9),
    )

    comp = stats_fes_casa["comparison_regions"]
    labels = [comp["label_a"], comp["label_b"]]
    slopes = [comp["sens_slope_a"] * 10, comp["sens_slope_b"] * 10]
    bars = axes[2].bar(labels, slopes, color=["#f97316", "#38bdf8"], width=0.48)
    axes[2].set_title("3. Compare: Warming Rate (°C/decade)")
    axes[2].set_ylabel("Sen's Slope (°C / decade)")
    for b, val in zip(bars, slopes):
        axes[2].text(b.get_x() + b.get_width() / 2, val + 0.01, f"{val:+.2f}", ha="center", color="#f8fafc", fontweight="bold")
    axes[2].text(
        0.5, 0.86,
        f"Slope diff p = {comp['slope_difference_p_value']:.4f}\nMean diff = {comp['mean_difference_a_minus_b']:+.2f} °C",
        ha="center", transform=axes[2].transAxes, fontsize=9, color="#f8fafc",
        bbox=dict(boxstyle="round", facecolor="#1e293b", edgecolor="#38bdf8", alpha=0.9),
    )

    fig.suptitle("EarthTrend AI — Member 3 Statistical Proof | Source: NASA POWER (2000-2025)", color="#f8fafc", fontsize=12, fontweight="bold")
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, "01_member3_3panel_summary.png"), dpi=160)
    plt.close(fig)

    # 2) Monthly Series + Anomalies in Red
    fig, ax = plt.subplots(figsize=(14, 5.2))
    _style_dark(fig, ax)

    dates = pd.to_datetime(seas["dates"])
    obs = seas["observed"]
    trend_comp = seas["trend_component"]
    ax.plot(dates, obs, color="#38bdf8", lw=1.0, alpha=0.85, label="Monthly Mean T2M (°C)")
    ax.plot(dates, trend_comp, color="#f97316", lw=2.3, label="Long-Term Trend Component")

    anoms = stats_fes_casa["anomalies"]["all_anomalies"]
    if anoms:
        a_dates = pd.to_datetime([a["date_full"] for a in anoms])
        a_vals = [a["observed"] for a in anoms]
        ax.scatter(
            a_dates, a_vals, color="#ef4444", s=55, zorder=5,
            edgecolors="#ffffff", linewidth=0.7,
            label=f"Statistical Anomalies (|z|>={stats_fes_casa['anomalies']['z_threshold']}, n={len(anoms)})",
        )
        for top in anoms[:3]:
            ax.annotate(
                f"{top['date']} ({top['deviation']:+.1f}°C)",
                xy=(pd.to_datetime(top["date_full"]), top["observed"]),
                xytext=(8, 8), textcoords="offset points",
                fontsize=8, color="#fecaca",
                bbox=dict(boxstyle="round,pad=0.2", facecolor="#7f1d1d", alpha=0.8),
            )

    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.set_title(f"Monthly Temperature & Statistical Anomalies — {stats_fes_casa['metadata']['region']} | Source: NASA POWER (2000-2025)")
    ax.set_ylabel("Temperature (°C)")
    ax.legend(loc="upper left", facecolor="#1e293b", edgecolor="#334155")
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, "02_anomalies_highlighted.png"), dpi=160)
    plt.close(fig)

    # 3) All 12 Moroccan Regions Warming Ranking
    df_m = pd.DataFrame(morocco_summary).sort_values("temp_sens_slope_per_decade", ascending=True)
    fig, ax = plt.subplots(figsize=(12.5, 6.5))
    _style_dark(fig, ax)

    colors = ["#ef4444" if sig else "#64748b" for sig in df_m["temp_significant"]]
    bars = ax.barh(df_m["region"], df_m["temp_sens_slope_per_decade"], color=colors, height=0.62)
    ax.axvline(0, color="#94748b", lw=1.0)
    for bar, (_, row) in zip(bars, df_m.iterrows()):
        w = bar.get_width()
        sig_txt = "p < 0.05 *" if row["temp_significant"] else f"p={row['temp_mk_p_value']:.2f}"
        offset = 0.008 if w >= 0 else -0.008
        ha = "left" if w >= 0 else "right"
        ax.text(w + offset, bar.get_y() + bar.get_height() / 2, f"{w:+.2f} °C/dec ({sig_txt})", va="center", ha=ha, color="#f8fafc", fontsize=8.5)

    max_val = max(df_m["temp_sens_slope_per_decade"].max(), 0.2)
    min_val = min(df_m["temp_sens_slope_per_decade"].min(), 0.0)
    ax.set_xlim(min_val - 0.15 if min_val < 0 else 0, max_val * 1.45)
    ax.set_title("All Morocco (12 Regions): Warming Trend (Sen's Slope °C/decade) | Source: NASA POWER (2000-2025)")
    ax.set_xlabel("Warming Rate (°C per decade) — Red = Statistically Significant (Mann-Kendall p < 0.05)")
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, "03_morocco_12_regions_warming.png"), dpi=160)
    plt.close(fig)

    # 4) Precipitation Trend
    tr_p = stats_precip_fes["trend"]
    fig, ax = plt.subplots(figsize=(12, 4.8))
    _style_dark(fig, ax)

    ax.bar(tr_p["years"], tr_p["yearly_values"], color="#0ea5e9", alpha=0.75, label="Yearly Total Precipitation (mm)")
    ax.plot(tr_p["years"], tr_p["sens_line"], color="#facc15", lw=2.5, label=f"Sen's Slope ({tr_p['sens_slope_per_year']:+.2f} mm/yr, MK p={tr_p['mk_p_value']:.3f})")
    ax.axhline(tr_p["overall_mean"], color="#e2e8f0", ls="--", lw=1.0, label=f"2000-2025 Mean ({tr_p['overall_mean']:.0f} mm/yr)")
    ax.set_title(f"Annual Precipitation Trend — {stats_precip_fes['metadata']['region']} | Source: NASA POWER (2000-2025)")
    ax.set_ylabel("Total Annual Precipitation (mm)")
    ax.set_xlabel("Year")
    ax.legend(loc="upper right", facecolor="#1e293b", edgecolor="#334155")
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, "04_precipitation_trend_morocco.png"), dpi=160)
    plt.close(fig)

    # 5) Period 1 vs Period 2 Comparison
    cp = stats_fes_casa["comparison_periods"]
    fig, ax = plt.subplots(figsize=(7.5, 4.8))
    _style_dark(fig, ax)
    p_labels = [cp["label_a"], cp["label_b"]]
    p_means = [cp["mean_a"], cp["mean_b"]]
    bars = ax.bar(p_labels, p_means, color=["#38bdf8", "#f97316"], width=0.45)
    ax.set_ylim(min(p_means) - 1.5, max(p_means) + 1.5)
    for b, val in zip(bars, p_means):
        ax.text(b.get_x() + b.get_width() / 2, val + 0.08, f"{val:.2f} °C", ha="center", color="#f8fafc", fontweight="bold")
    ax.set_title(f"Period Comparison: {stats_fes_casa['metadata']['region']} | NASA POWER")
    ax.set_ylabel("Mean Temperature (°C)")
    ax.text(
        0.5, 0.88,
        f"Mean shift: {cp['mean_b'] - cp['mean_a']:+.2f} °C (Welch t-test p = {cp['mean_ttest_p_value']:.4f})",
        ha="center", transform=ax.transAxes, color="#f8fafc",
        bbox=dict(boxstyle="round", facecolor="#1e293b", edgecolor="#f97316"),
    )
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, "05_period_comparison.png"), dpi=160)
    plt.close(fig)

    # 6) Interactive Plotly HTML Report
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots

        fig_p = make_subplots(
            rows=2, cols=2,
            subplot_titles=(
                f"Yearly Trend: {stats_fes_casa['metadata']['region']}",
                "Monthly Seasonality (1-12)",
                "All Morocco Warming (°C/decade)",
                "Monthly Observed + Red Anomalies",
            ),
        )
        fig_p.add_trace(go.Scatter(x=tr["years"], y=tr["yearly_values"], mode="lines+markers", name="Yearly T2M"), row=1, col=1)
        fig_p.add_trace(go.Scatter(x=tr["years"], y=tr["sens_line"], mode="lines", name="Sen's Slope"), row=1, col=1)
        fig_p.add_trace(go.Scatter(x=seas["month_names"], y=seas["seasonal_component"], mode="lines+markers", name="Seasonal Effect"), row=1, col=2)
        fig_p.add_trace(go.Bar(y=df_m["region"], x=df_m["temp_sens_slope_per_decade"], orientation="h", name="°C/decade"), row=2, col=1)
        fig_p.add_trace(go.Scatter(x=seas["dates"], y=seas["observed"], mode="lines", name="Monthly T2M"), row=2, col=2)
        if anoms:
            fig_p.add_trace(
                go.Scatter(
                    x=[a["date_full"] for a in anoms],
                    y=[a["observed"] for a in anoms],
                    mode="markers",
                    marker=dict(color="red", size=9),
                    name="Anomalies",
                ),
                row=2, col=2,
            )

        fig_p.update_layout(
            template="plotly_dark",
            height=820,
            title_text="EarthTrend AI — Interactive Member 3 Report (Real NASA POWER Data, Morocco 2000-2025)",
        )
        fig_p.write_html(os.path.join(out_dir, "06_interactive_member3_dashboard.html"))
    except Exception as e:
        print("Plotly HTML skipped:", e)