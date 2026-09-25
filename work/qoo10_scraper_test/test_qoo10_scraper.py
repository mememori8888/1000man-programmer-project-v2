import csv
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from qoo10_scraper import CSV_HEADER, normalize_price, unique, write_csv


class ScraperUnitTests(unittest.TestCase):
    def test_price_uses_last_yen_value(self):
        self.assertEqual(normalize_price("通常 2,000円 セール 1,480円"), 1480)

    def test_price_missing(self):
        self.assertIsNone(normalize_price("価格未定"))

    def test_unique_cleans_and_preserves_order(self):
        self.assertEqual(unique([" M ", "M", "Black\n", ""]), ["M", "Black"])

    def test_csv_has_a_through_ad_columns(self):
        self.assertEqual(len(CSV_HEADER), 30)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.csv"
            write_csv(path, [["name", "M / Black", "desc", 4800, "", 10, 1, 1, 10] + [""] * 21])
            with path.open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.reader(handle))
            self.assertEqual(len(rows[0]), 30)
            self.assertEqual(len(rows[1]), 30)
            self.assertEqual(rows[1][3], "4800")


if __name__ == "__main__":
    unittest.main()
