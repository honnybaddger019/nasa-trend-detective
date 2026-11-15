"""Régions disponibles : (latitude, longitude). Clé = nom de fichier (sans accents)."""

MOROCCO = {
    "casablanca": (33.57, -7.59), "rabat": (34.02, -6.84), "fes": (34.03, -5.00),
    "meknes": (33.89, -5.55), "marrakech": (31.63, -8.00), "tanger": (35.76, -5.83),
    "tetouan": (35.57, -5.37), "agadir": (30.43, -9.60), "oujda": (34.68, -1.91),
    "kenitra": (34.26, -6.58), "sale": (34.05, -6.80), "temara": (33.93, -6.91),
    "mohammedia": (33.69, -7.38), "el_jadida": (33.26, -8.51), "safi": (32.30, -9.24),
    "essaouira": (31.51, -9.77), "beni_mellal": (32.34, -6.36), "khouribga": (32.88, -6.91),
    "settat": (33.00, -7.62), "nador": (35.17, -2.93), "al_hoceima": (35.25, -3.94),
    "taza": (34.21, -4.01), "larache": (35.19, -6.15), "ouarzazate": (30.92, -6.89),
    "errachidia": (31.93, -4.43), "laayoune": (27.15, -13.20), "dakhla": (23.68, -15.96),
    "guelmim": (28.99, -10.06), "ifrane": (33.53, -5.11), "chefchaouen": (35.17, -5.27),
    "khenifra": (32.94, -5.67), "taroudant": (30.47, -8.88), "tiznit": (29.70, -9.73),
    "berkane": (34.92, -2.32), "midelt": (32.68, -4.74), "azrou": (33.44, -5.22),
}

# Villes méditerranéennes / mondiales pour comparer (le plan suggère une 2e ville méditerranéenne)
WORLD = {
    "marseille": (43.30, 5.37), "barcelone": (41.39, 2.17), "madrid": (40.42, -3.70),
    "lisbonne": (38.72, -9.14), "rome": (41.90, 12.50), "athenes": (37.98, 23.73),
    "tunis": (36.81, 10.18), "alger": (36.75, 3.06), "le_caire": (30.04, 31.24),
    "istanbul": (41.01, 28.98), "paris": (48.86, 2.35), "dakar": (14.72, -17.47),
}

ALL = {**MOROCCO, **WORLD}
