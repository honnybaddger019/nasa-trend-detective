import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from regions import ALL, MOROCCO


class TestRegions(unittest.TestCase):
    def test_coordinates_valid(self):
        for name, (lat, lon) in ALL.items():
            self.assertTrue(-90 <= lat <= 90 and -180 <= lon <= 180, name)

    def test_morocco_box(self):                      # le Maroc est entre ~21-36°N et ~1-17°W
        for name, (lat, lon) in MOROCCO.items():
            self.assertTrue(21 <= lat <= 36 and -17.5 <= lon <= -1, name)

    def test_no_name_clash(self):
        from regions import WORLD
        self.assertFalse(set(MOROCCO) & set(WORLD))


if __name__ == "__main__":
    unittest.main()
