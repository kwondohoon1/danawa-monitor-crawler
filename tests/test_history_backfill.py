import csv
import tempfile
import unittest
from pathlib import Path

from danawa_crawler.history_backfill import backfill_price_csv, read_sammy_monitor_prices


class HistoryBackfillTests(unittest.TestCase):
    def test_read_sammy_monitor_prices_uses_id_dates_and_numeric_prices(self):
        prices = read_sammy_monitor_prices(
            "Id,Name,2026-05-01 12:00:00,2026-05-02 12:00:00\n"
            '100,Alpha,"12,300",\n'
        )

        self.assertEqual(prices, {"100": {"2026-05-01": "12300", "2026-05-02": "0"}})

    def test_backfill_keeps_existing_values_and_fills_missing_with_zero(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "monitor.csv"
            with path.open("w", encoding="utf-8-sig", newline="") as file:
                writer = csv.DictWriter(
                    file,
                    fieldnames=["product_code", "product_name", "2026-05-02", "2026-05-01", "2026-04-30"],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "product_code": "100",
                        "product_name": "Alpha",
                        "2026-05-02": "999",
                    }
                )
                writer.writerow({"product_code": "200", "product_name": "Beta"})

            result = backfill_price_csv(path, {"100": {"2026-05-02": "222", "2026-05-01": "111"}})

            with path.open("r", encoding="utf-8-sig", newline="") as file:
                rows = list(csv.DictReader(file))

        self.assertEqual(rows[0]["2026-05-02"], "999")
        self.assertEqual(rows[0]["2026-05-01"], "111")
        self.assertEqual(rows[0]["2026-04-30"], "0")
        self.assertEqual(rows[1]["2026-05-02"], "0")
        self.assertEqual(result.filled_from_legacy, 1)
        self.assertEqual(result.filled_with_zero, 4)


if __name__ == "__main__":
    unittest.main()
