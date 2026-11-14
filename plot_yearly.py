"""
Graphiques de la température moyenne annuelle (T2M) pour TOUT le Maroc, 2000-2024.

    python3 plot_yearly.py              # température
    python3 plot_yearly.py PRECTOTCORR  # pluie

Crée 3 images dans plots/ (lance d'abord build_admin.py) :
    yearly_T2M_regions.png   les 12 régions + la moyenne du Maroc
    yearly_T2M_provinces.png carte de chaleur : chaque ligne = une province, couleur = écart à sa moyenne
    yearly_T2M_morocco.png   moyenne nationale (pondérée par la population) + droite de tendance

T2M = "Temperature at 2 Meters" : la température de l'air à 2 m au-dessus du sol, variable NASA POWER.
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from admin import unit_series, units
from nasa_data import DATA_DIR

VAR = sys.argv[1] if len(sys.argv) > 1 else "T2M"
PLOTS_DIR = Path(__file__).parent / "plots"          # les graphiques ont leur propre dossier
PLOTS_DIR.mkdir(exist_ok=True)
SRC_DIR = DATA_DIR / "clean" if (DATA_DIR / "clean").exists() else DATA_DIR   # données nettoyées si disponibles
LABEL = {"T2M": ("Température moyenne annuelle (°C)", "T2M (°C)", "°C"),
         "PRECTOTCORR": ("Précipitations moyennes annuelles (mm/jour)", "mm/jour", "mm/jour")}[VAR]
SRC = "source : NASA POWER, 2000-2024, moyenne annuelle pondérée par la population"


def yearly(level, code):
    s = unit_series(level, code, VAR, data_dir=SRC_DIR)
    s["year"] = s["date"].dt.year
    y = s.groupby("year")["value"].agg(["mean", "count"])
    return y[y["count"] >= 9]["mean"]            # année ignorée si < 9 mois valides


def main():
    regs = units("region")
    reg = {r.code: yearly("region", r.code) for r in regs.itertuples()}

    # moyenne nationale : régions pondérées par la population 2024
    pop = regs.set_index("code")["population_2024"].astype(float)
    df = pd.DataFrame(reg)
    national = (df * pop[df.columns]).sum(axis=1) / pop[df.columns].sum()

    # 1) 12 régions
    fig, ax = plt.subplots(figsize=(11, 6))
    cmap = plt.get_cmap("tab20")
    for i, r in enumerate(regs.itertuples()):
        ax.plot(reg[r.code].index, reg[r.code].values, lw=1.4, color=cmap(i), label=r.name_fr)
    ax.plot(national.index, national.values, lw=3.2, color="black", label="Maroc (moyenne)")
    ax.set_title(f"{LABEL[0]} — 12 régions du Maroc\n{SRC}", fontsize=11)
    ax.set_xlabel("Année"); ax.set_ylabel(LABEL[1]); ax.grid(alpha=.3)
    ax.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), fontsize=8)
    fig.tight_layout(); fig.savefig(PLOTS_DIR / f"yearly_{VAR}_regions.png", dpi=150); plt.close(fig)

    # 2) carte de chaleur : provinces x années (écart à la moyenne de la province)
    provs = units("province")
    rows, names = [], []
    for p in provs.itertuples():
        try:
            y = yearly("province", p.code)
        except ValueError:                        # préfecture sans commune propre
            continue
        rows.append(y - y.mean()); names.append(p.name_fr)
    heat = pd.DataFrame(rows, index=names)
    order = heat.mean(axis=1).sort_index().index
    lim = float(np.nanpercentile(np.abs(heat.values), 98))
    fig, ax = plt.subplots(figsize=(11, max(6, 0.17 * len(heat))))
    im = ax.imshow(heat.loc[order].values, aspect="auto", cmap="RdBu_r", vmin=-lim, vmax=lim)
    ax.set_yticks(range(len(order))); ax.set_yticklabels(order, fontsize=6)
    ax.set_xticks(range(0, heat.shape[1], 2)); ax.set_xticklabels(heat.columns[::2], fontsize=8)
    ax.set_title(f"Écart à la moyenne 2000-2024 de chaque province ({LABEL[2]})\n{SRC}", fontsize=10)
    fig.colorbar(im, ax=ax, label=f"écart ({LABEL[2]})", shrink=0.6)
    fig.tight_layout(); fig.savefig(PLOTS_DIR / f"yearly_{VAR}_provinces.png", dpi=150); plt.close(fig)

    # 3) moyenne nationale + droite de tendance (simple régression linéaire)
    slope, icpt = np.polyfit(national.index, national.values, 1)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.plot(national.index, national.values, marker="o", color="tab:blue", label="Maroc (moyenne annuelle)")
    ax.plot(national.index, slope * national.index + icpt, color="tab:red", lw=2,
            label=f"tendance linéaire : {slope:+.3f} {LABEL[2]}/an")
    ax.set_title(f"{LABEL[0]} — Maroc\n{SRC}", fontsize=11)
    ax.set_xlabel("Année"); ax.set_ylabel(LABEL[1]); ax.grid(alpha=.3); ax.legend()
    fig.tight_layout(); fig.savefig(PLOTS_DIR / f"yearly_{VAR}_morocco.png", dpi=150); plt.close(fig)

    print(f"3 graphiques enregistrés dans {PLOTS_DIR}/ :")
    for n in ("regions", "provinces", "morocco"):
        print(f"  yearly_{VAR}_{n}.png")
    print(f"Maroc : {national.iloc[0]:.2f} -> {national.iloc[-1]:.2f} {LABEL[2]} "
          f"({national.index[0]}-{national.index[-1]}), tendance linéaire {slope:+.3f}/an")


if __name__ == "__main__":
    main()
