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
    def test_initial_run_creates_baseline_without_marking_old_products_as_new(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            write_csv(
                output_dir / "latest" / "gpu.csv",
                ["product_code", "product_name", "2026-07-02"],
                [{"product_code": "122000100", "product_name": "Alpha", "2026-07-02": "200"}],
            )

            added, total = update_new_products(output_dir, "gpu")

            self.assertEqual((added, total), (0, 0))
            with (output_dir / "new_products" / "gpu.csv").open(
                "r", encoding="utf-8-sig", newline=""
            ) as file:
                self.assertEqual(list(csv.DictReader(file)), [])
            with (output_dir / "state" / "known_products" / "gpu.csv").open(
                "r", encoding="utf-8-sig", newline=""
            ) as file:
                row = next(csv.DictReader(file))
            self.assertEqual(row["product_code"], "122000100")

    def test_registry_only_adds_unseen_codes_and_keeps_missing_products(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            registry_path = output_dir / "new_products" / "gpu.csv"
            write_csv(
                output_dir / "state" / "known_products" / "gpu.csv",
                ["product_code", "product_name"],
                [
                    {"product_code": "122000100", "product_name": "Old name"},
                    {"product_code": "122000999", "product_name": "No longer listed"},
                ],
            )
            write_csv(
                registry_path,
                ["product_code", "product_name", "first_collected_date"],
                [
                    {
                        "product_code": "122000100",
                        "product_name": "Old name",
                        "first_collected_date": "2026-07-01",
                    },
                ],
            )
            write_csv(
                output_dir / "latest" / "gpu.csv",
                ["product_code", "product_name", "2026-07-02"],
                [
                    {"product_code": "122000100", "product_name": "Exact name", "2026-07-02": "200"},
                    {"product_code": "122000200", "product_name": "New product", "2026-07-02": "300"},
                ],
            )

            added, total = update_new_products(output_dir, "gpu")

            self.assertEqual((added, total), (1, 2))
            with registry_path.open("r", encoding="utf-8-sig", newline="") as file:
                ordered_rows = list(csv.DictReader(file))
                rows = {row["product_code"]: row for row in ordered_rows}
            self.assertEqual(
                [row["product_code"] for row in ordered_rows],
                ["122000100", "122000200"],
            )
            self.assertEqual(rows["122000100"]["product_name"], "Exact name")
            self.assertEqual(rows["122000100"]["first_collected_date"], "2026-07-01")
            self.assertEqual(rows["122000200"]["first_collected_date"], "2026-07-02")
            with (output_dir / "state" / "known_products" / "gpu.csv").open(
                "r", encoding="utf-8-sig", newline=""
            ) as file:
                known_codes = {row["product_code"] for row in csv.DictReader(file)}
            self.assertEqual(known_codes, {"122000100", "122000200", "122000999"})

    def test_old_used_and_overseas_products_are_excluded_but_remembered(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            write_csv(
                output_dir / "state" / "known_products" / "gpu.csv",
                ["product_code", "product_name"],
                [],
            )
            write_csv(
                output_dir / "latest" / "gpu.csv",
                ["product_code", "product_name", "2026-07-03"],
                [
                    {"product_code": "121999999", "product_name": "Old product", "2026-07-03": "100"},
                    {"product_code": "122000001", "product_name": "Recent (중고)", "2026-07-03": "100"},
                    {"product_code": "122000002", "product_name": "Recent 해외 구매", "2026-07-03": "100"},
                    {"product_code": "122000003", "product_name": "Recent new", "2026-07-03": "100"},
                ],
            )

            added, total = update_new_products(output_dir, "gpu")

            self.assertEqual((added, total), (1, 1))
            with (output_dir / "new_products" / "gpu.csv").open(
                "r", encoding="utf-8-sig", newline=""
            ) as file:
                rows = list(csv.DictReader(file))
            self.assertEqual(rows[0]["product_code"], "122000003")
            with (output_dir / "state" / "known_products" / "gpu.csv").open(
                "r", encoding="utf-8-sig", newline=""
            ) as file:
                self.assertEqual(len(list(csv.DictReader(file))), 4)


SPEC_FIELDS = ["product_code", "product_name", "registration_month", "fetch_status"]


class SpecBasedNewProductsTests(unittest.TestCase):
    def test_monitor_registry_is_rebuilt_from_registration_month_window(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            write_csv(
                output_dir / "latest" / "monitor.csv",
                ["product_code", "product_name", "2026-07-22"],
                [{"product_code": "100", "product_name": "In window", "2026-07-22": "100"}],
            )
            write_csv(
                output_dir / "specs" / "monitor_specs.csv",
                SPEC_FIELDS,
                [
                    {"product_code": "100", "product_name": "In window", "registration_month": "2026/07", "fetch_status": "ok"},
                    {"product_code": "101", "product_name": "Edge of window", "registration_month": "2026/05", "fetch_status": "ok"},
                    {"product_code": "102", "product_name": "Too old", "registration_month": "2026/04", "fetch_status": "ok"},
                    {"product_code": "103", "product_name": "No month", "registration_month": "", "fetch_status": "error"},
                    {"product_code": "104", "product_name": "Recent (중고)", "registration_month": "2026/07", "fetch_status": "ok"},
                    {"product_code": "105", "product_name": "Recent 해외 구매", "registration_month": "2026/07", "fetch_status": "ok"},
                ],
            )

            added, total = update_new_products(output_dir, "monitor")

            self.assertEqual((added, total), (2, 2))
            with (output_dir / "new_products" / "monitor.csv").open(
                "r", encoding="utf-8-sig", newline=""
            ) as file:
                rows = list(csv.DictReader(file))
            self.assertEqual({row["product_code"] for row in rows}, {"100", "101"})
            self.assertTrue(all(row["first_collected_date"] == "2026-07-22" for row in rows))

    def test_monitor_rebuild_keeps_first_collected_date_and_drops_expired(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            write_csv(
                output_dir / "latest" / "monitor.csv",
                ["product_code", "product_name", "2026-07-22"],
                [{"product_code": "100", "product_name": "Still new", "2026-07-22": "100"}],
            )
            write_csv(
                output_dir / "new_products" / "monitor.csv",
                ["product_code", "product_name", "first_collected_date"],
                [
                    {"product_code": "100", "product_name": "Old name", "first_collected_date": "2026-07-01"},
                    {"product_code": "200", "product_name": "Expired", "first_collected_date": "2026-04-05"},
                ],
            )
            write_csv(
                output_dir / "specs" / "monitor_specs.csv",
                SPEC_FIELDS,
                [
                    {"product_code": "100", "product_name": "Still new", "registration_month": "2026/06", "fetch_status": "ok"},
                    {"product_code": "200", "product_name": "Expired", "registration_month": "2026/02", "fetch_status": "ok"},
                ],
            )

            added, total = update_new_products(output_dir, "monitor")

            self.assertEqual((added, total), (0, 1))
            with (output_dir / "new_products" / "monitor.csv").open(
                "r", encoding="utf-8-sig", newline=""
            ) as file:
                rows = list(csv.DictReader(file))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["product_code"], "100")
            self.assertEqual(rows[0]["product_name"], "Still new")
            self.assertEqual(rows[0]["first_collected_date"], "2026-07-01")

    def test_monitor_rebuild_does_not_touch_known_products_state(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            write_csv(
                output_dir / "latest" / "monitor.csv",
                ["product_code", "product_name", "2026-07-22"],
                [{"product_code": "100", "product_name": "New", "2026-07-22": "100"}],
            )
            write_csv(
                output_dir / "specs" / "monitor_specs.csv",
                SPEC_FIELDS,
                [{"product_code": "100", "product_name": "New", "registration_month": "2026/07", "fetch_status": "ok"}],
            )

            update_new_products(output_dir, "monitor")

            self.assertFalse((output_dir / "state" / "known_products" / "monitor.csv").exists())


if __name__ == "__main__":
    unittest.main()
