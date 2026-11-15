import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
import cities as c


class TestCities(unittest.TestCase):
    def test_snap(self):
        lat, lon = c.snap_to_cell(34.03, -5.00)
        self.assertAlmostEqual(lat % 0.5, 0, places=6)
        self.assertAlmostEqual((lon + 180) % 0.625, 0, places=6)
        self.assertLess(abs(lat - 34.03), 0.26)
        self.assertLess(abs(lon + 5.00), 0.32)

    def test_close_cities_share_cell(self):                 # Rabat et Salé : même cellule
        self.assertEqual(c.snap_to_cell(34.02, -6.84), c.snap_to_cell(34.05, -6.80))

    def test_select(self):
        df = pd.DataFrame({"name": ["a", "b", "c"], "country": ["MA", "MA", "FR"],
                           "lat": [34.02, 34.05, 48.86], "lon": [-6.84, -6.80, 2.35],
                           "population": [500000, 900000, 2000000],
                           "continent": ["africa", "africa", "europe"]})
        s = c.select(df, countries=["ma"])
        self.assertEqual(len(s), 2)
        self.assertEqual(s["cell"].nunique(), 1)
        self.assertEqual(s.iloc[0]["name"], "b")             # trié par population
        self.assertEqual(len(c.select(df, continent="europe")), 1)
        self.assertEqual(len(c.select(df, min_pop=1_000_000)), 1)


if __name__ == "__main__":
    unittest.main()
