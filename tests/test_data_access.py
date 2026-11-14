"""Tests hors-ligne de data_access : python3 -m unittest discover tests"""
import sys, tempfile, unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
import requests

import data_access as da
import nasa_data as nd
from test_nasa_data import FAKE


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        p = mock.patch.object(nd, "DATA_DIR", self.dir)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)
        da._local_places.cache_clear()


class TestLocal(Base):
    def test_local_cell_never_calls_nasa(self):
        lat, lon = da.snap_to_cell(34.03, -5.00)
        name = da.cell_name(lat, lon)
        (self.dir / "clean").mkdir()
        pd.DataFrame({"date": pd.date_range("2020-01-01", periods=24, freq="MS"),
                      "T2M": 15.0, "PRECTOTCORR": 1.0, "year": [2020] * 12 + [2021] * 12,
                      "month": list(range(1, 13)) * 2, "T2M_flag": "", "PRECTOTCORR_flag": ""}
                     ).to_csv(self.dir / "clean" / f"{name}_monthly_2020_2021.csv", index=False)
        with mock.patch.object(da, "get_nasa_data", side_effect=AssertionError("réseau !")):
            res = da.get_series_for_city("Fès", 2020, 2021)     # Fès est dans regions.py
        self.assertEqual(res.source, "local")
        self.assertEqual(len(res.df), 24)
        self.assertTrue((res.df["T2M_flag"] == "ok").all())


class TestNasa(Base):
    def test_download_then_cache(self):
        with mock.patch.object(nd, "_download", return_value=FAKE) as dl:
            a = da.get_series(48.86, 2.35, 2020, 2021, crosscheck=False)
            b = da.get_series(48.86, 2.35, 2020, 2021, crosscheck=False)
        self.assertEqual((a.source, b.source), ("nasa", "local"))
        self.assertEqual(dl.call_count, 1)
        self.assertIn("T2M_flag", a.df.columns)

    def test_nasa_down(self):
        with mock.patch.object(nd, "_download", side_effect=ConnectionError("x")):
            with self.assertRaises(da.NasaUnavailable) as c:
                da.get_series(48.86, 2.35, 2020, 2021)
        self.assertIn("indisponible", c.exception.user_message)

    def test_no_data(self):
        empty = {"properties": {"parameter": {v: {"202001": -999, "202002": -999} for v in da.VARIABLES}}}
        with mock.patch.object(nd, "_download", return_value=empty):
            with self.assertRaises(da.NoData):
                da.get_series(0.0, -30.0, 2020, 2020, crosscheck=False)


class TestInputs(Base):
    def test_invalid(self):
        for args in [(9999, 0), (0, 999), ("a", 0)]:
            with self.assertRaises(da.InvalidInput):
                da.get_series(*args)
        with self.assertRaises(da.InvalidInput):
            da.get_series(34, -5, 2024, 2000)
        with self.assertRaises(da.InvalidInput):
            da.find_place("   ")

    def _geo(self, payload=None, exc=None):
        resp = mock.Mock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = payload
        return mock.patch.object(da.requests, "get", side_effect=exc, return_value=resp)

    def test_unknown_city(self):
        with self._geo({}):
            with self.assertRaises(da.CityNotFound):
                da.find_place("Zzzxqv")

    def test_geocoder_down(self):
        with self._geo(exc=requests.ConnectionError("x")):
            with self.assertRaises(da.ServiceUnavailable):
                da.find_place("Zzzxqv")

    def test_world_city_geocoded(self):
        with self._geo({"results": [{"name": "Tokyo", "country": "Japon", "latitude": 35.69, "longitude": 139.69}]}):
            self.assertEqual(da.find_place("Tokyo"), ("Tokyo, Japon", 35.69, 139.69))

    def test_geocoded_city_remembered_offline(self):
        payload = {"results": [{"name": "Tokyo", "country": "Japon", "latitude": 35.69, "longitude": 139.69}]}
        with self._geo(payload):
            first = da.find_place("Tokyo")
        with self._geo(exc=requests.ConnectionError("x")) as g:     # Internet coupé
            again = da.find_place("tokyo ")
        self.assertEqual(first, again)
        g.assert_not_called()


if __name__ == "__main__":
    unittest.main()
