# EarthTrend AI — jeu de données final (Maroc)

**Source** : NASA POWER (température `T2M` et pluie `PRECTOTCORR`, mensuel, 2000-01 -> 2024-12), découpage HCP 2024.
**Contenu** : 1,503 communes, 75 provinces/préfectures, 12 régions, 450,900 lignes.

## Quel fichier utiliser ?
| Fichier | 1 ligne = | Quand l'utiliser |
|---|---|---|
| `earthtrend_master.csv.gz` | 1 commune x 1 mois | **par défaut**, pour tout (filtre par `region`, `province`, `commune`) |
| `earthtrend_provinces_monthly.csv.gz` | 1 province x 1 mois | graphiques / stats par province (déjà agrégé) |
| `earthtrend_regions_monthly.csv.gz` | 1 région x 1 mois | graphiques / stats par région (déjà agrégé) |

```python
import pandas as pd
df = pd.read_csv("dataset/earthtrend_master.csv.gz", parse_dates=["date"],
                 dtype={"region_code": str, "province_code": str})   # garde les zéros : "01", "01.511"
fes = df[df["region"] == "Fès-Meknès"]
fes.groupby("year")["T2M"].mean()
```

## Colonnes de `earthtrend_master.csv.gz`
| Colonne | Description |
|---|---|
| `date`, `year`, `month` | mois (date = 1er du mois) |
| `commune_code`, `commune`, `commune_ar` | code officiel HCP, nom français, nom arabe |
| `commune_type` | `urban` ou `rural` |
| `province_code`, `province`, `region_code`, `region` | hiérarchie administrative |
| `population_2024` | population de la commune (RGPH 2024) |
| `lat`, `lon` | centroïde de la commune |
| `cell` | cellule NASA (0,5° x 0,625°, ~55 km) : des communes proches partagent les mêmes valeurs |
| `T2M` | température de l'air à 2 m, moyenne mensuelle, **°C** |
| `PRECTOTCORR` | précipitations, moyenne mensuelle, **mm/jour** |
| `T2M_flag`, `PRECTOTCORR_flag` | `ok` = normal ; `removed` = valeur aberrante retirée (la valeur est alors vide) ; `kept` = suspecte mais confirmée par ERA5 |

Les fichiers agrégés ont : `date, year, month`, le code et le nom de l'unité, `n_communes`, `population_2024`, `T2M`, `PRECTOTCORR`
(moyenne **pondérée par la population** des communes ; les valeurs vides sont ignorées).

## Qualité
- Valeurs vides : T2M = 0, PRECTOTCORR = 444 (valeurs aberrantes retirées après vérification avec ERA5).
- Journal des valeurs retirées : `data/clean/CLEANING_LOG.csv` ; données brutes conservées dans `data/`.
- Pour une moyenne annuelle, ignorer les années avec moins de 9 mois valides.

## Limites (à dire dans le pitch)
NASA POWER est un produit sur grille (satellite + modèles), pas une station météo locale. Les valeurs de 2 communes
dans la même cellule sont identiques : une analyse « par commune » est en réalité une analyse par cellule de 55 km.
Les données montrent une évolution dans le temps, pas sa cause.

## Sources à citer
NASA POWER ; HCP (RGPH 2024, CC BY 4.0) via `zkousama/morocco-communes` ; © contributeurs OpenStreetMap (ODbL) pour les centroïdes ;
ERA5 (Copernicus/ECMWF) via Open-Meteo pour le contrôle qualité.
