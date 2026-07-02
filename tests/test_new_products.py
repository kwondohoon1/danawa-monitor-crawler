import csv
import tempfile
import unittest
from pathlib import Path

from danawa_crawler.new_products import update_new_products


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class NewProductsTests(unittest.TestCase):
    def test_initial_registry_uses_earliest_known_price_date(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            write_csv(
                output_dir / "latest" / "monitor.csv",
                ["product_code", "product_name", "2026-07-02"],
                [{"product_code": "100", "product_name": "Alpha", "2026-07-02": "200"}],
            )
            write_csv(
                output_dir / "history" / "monitor_price_history.csv",
                ["product_code", "product_name", "2026-07-02", "2026-07-01", "2026-06-30"],
                [
                    {
                        "product_code": "100",
                        "product_name": "Alpha",
                        "2026-07-02": "200",
                        "2026-07-01": "190",
                        "2026-06-30": "0",
                    }
                ],
            )

            added, total = update_new_products(output_dir, "monitor")

            self.assertEqual((added, total), (1, 1))
            with (output_dir / "new_products" / "monitor.csv").open(
                "r", encoding="utf-8-sig", newline=""
            ) as file:
                row = next(csv.DictReader(file))
            self.assertEqual(row["first_collected_date"], "2026-07-01")

    def test_registry_only_adds_unseen_codes_and_keeps_missing_products(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            registry_path = output_dir / "new_products" / "monitor.csv"
            write_csv(
                registry_path,
                ["product_code", "product_name", "first_collected_date"],
                [
                    {
                        "product_code": "100",
                        "product_name": "Old name",
                        "first_collected_date": "2026-07-01",
                    },
                    {
                        "product_code": "999",
                        "product_name": "No longer listed",
                        "first_collected_date": "2026-06-01",
                    },
                ],
            )
            write_csv(
                output_dir / "latest" / "monitor.csv",
                ["product_code", "product_name", "2026-07-02"],
                [
                    {"product_code": "100", "product_name": "Exact name", "2026-07-02": "200"},
                    {"product_code": "200", "product_name": "New product", "2026-07-02": "300"},
                ],
            )

            added, total = update_new_products(output_dir, "monitor")

            self.assertEqual((added, total), (1, 3))
            with registry_path.open("r", encoding="utf-8-sig", newline="") as file:
                rows = {row["product_code"]: row for row in csv.DictReader(file)}
            self.assertEqual(rows["100"]["product_name"], "Exact name")
            self.assertEqual(rows["100"]["first_collected_date"], "2026-07-01")
            self.assertEqual(rows["200"]["first_collected_date"], "2026-07-02")
            self.assertIn("999", rows)


if __name__ == "__main__":
    unittest.main()
