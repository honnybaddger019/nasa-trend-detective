"""Test hors-ligne (sans Internet) : python -m unittest discover tests"""
import sys, tempfile, unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import nasa_data as nd

FAKE = {"properties": {"parameter": {
    "T2M": {"202001": 10.0, "202002": -999, "202003": 14.0, "202013": 12.0,
            "202101": 11.0, "202102": 12.0, "202103": 15.0, "202113": 12.7},
    "PRECTOTCORR": {"202001": 1.0, "202002": 2.0, "202003": -999, "202013": 1.5,
                    "202101": 0.5, "202102": 0.7, "202103": 0.2, "202113": 0.5},
}}}


class TestNasa(unittest.TestCase):
    def test_parse_cleaning(self):
        df = nd.parse_power(FAKE, ["T2M", "PRECTOTCORR"])
        self.assertEqual(len(df), 6)                         # mois 13 supprimés
        self.assertEqual(int(df["T2M"].isna().sum()), 1)     # -999 -> NaN
        self.assertTrue(df["date"].is_monotonic_increasing)

    def test_cache(self):
        with tempfile.TemporaryDirectory() as d, \
             mock.patch.object(nd, "_download", return_value=FAKE) as dl:
            a = nd.get_nasa_data(34, -5, 2020, 2021, ["T2M", "PRECTOTCORR"], name="x", cache_dir=d)
            b = nd.get_nasa_data(34, -5, 2020, 2021, ["T2M", "PRECTOTCORR"], name="x", cache_dir=d)
            self.assertEqual(dl.call_count, 1)               # 2e appel = cache
            self.assertEqual(len(a), len(b))

    def test_yearly(self):
        df = nd.parse_power(FAKE, ["T2M"])
        self.assertEqual(len(nd.yearly_means(df, "T2M", min_months=3)), 1)  # 2020 a 2 mois valides -> ignoré


if __name__ == "__main__":
    unittest.main()
