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


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


class SpecBasedNewProductsTests(unittest.TestCase):
    def test_monitor_records_only_unseen_products_registered_within_window(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            write_csv(
                output_dir / "state" / "known_products" / "monitor.csv",
                ["product_code", "product_name"],
                [{"product_code": "1", "product_name": "Seen before"}],
            )
            write_csv(
                output_dir / "latest" / "monitor.csv",
                ["product_code", "product_name", "2026-07-22"],
                [
                    {"product_code": "1", "product_name": "Seen before", "2026-07-22": "100"},
                    {"product_code": "2", "product_name": "Unseen recent", "2026-07-22": "100"},
                    {"product_code": "3", "product_name": "Unseen old", "2026-07-22": "100"},
                    {"product_code": "4", "product_name": "Unseen no spec yet", "2026-07-22": "100"},
                    {"product_code": "5", "product_name": "Unseen recent (중고)", "2026-07-22": "100"},
                ],
            )
            write_csv(
                output_dir / "specs" / "monitor_specs.csv",
                SPEC_FIELDS,
                [
                    {"product_code": "1", "product_name": "Seen before", "registration_month": "2026/07", "fetch_status": "ok"},
                    {"product_code": "2", "product_name": "Unseen recent", "registration_month": "2026/07", "fetch_status": "ok"},
                    {"product_code": "3", "product_name": "Unseen old", "registration_month": "2026/04", "fetch_status": "ok"},
                    {"product_code": "5", "product_name": "Unseen recent (중고)", "registration_month": "2026/07", "fetch_status": "ok"},
                ],
            )

            added, total = update_new_products(output_dir, "monitor")

            self.assertEqual((added, total), (1, 1))
            rows = read_rows(output_dir / "new_products" / "monitor.csv")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["product_code"], "2")
            self.assertEqual(rows[0]["first_collected_date"], "2026-07-22")
            self.assertEqual(rows[0]["registration_month"], "2026/07")
            known_codes = {
                row["product_code"]
                for row in read_rows(output_dir / "state" / "known_products" / "monitor.csv")
            }
            # 스펙이 아직 없는 4번은 known에 올리지 않고 다음 실행에서 재평가한다.
            self.assertEqual(known_codes, {"1", "2", "3", "5"})

    def test_monitor_pending_product_is_recorded_once_spec_appears(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            write_csv(
                output_dir / "state" / "known_products" / "monitor.csv",
                ["product_code", "product_name"],
                [],
            )
            write_csv(
                output_dir / "latest" / "monitor.csv",
                ["product_code", "product_name", "2026-07-22"],
                [{"product_code": "7", "product_name": "Brand new", "2026-07-22": "100"}],
            )
            write_csv(output_dir / "specs" / "monitor_specs.csv", SPEC_FIELDS, [])

            added, total = update_new_products(output_dir, "monitor")
            self.assertEqual((added, total), (0, 0))

            write_csv(
                output_dir / "latest" / "monitor.csv",
                ["product_code", "product_name", "2026-07-23", "2026-07-22"],
                [{"product_code": "7", "product_name": "Brand new", "2026-07-23": "100", "2026-07-22": "100"}],
            )
            write_csv(
                output_dir / "specs" / "monitor_specs.csv",
                SPEC_FIELDS,
                [{"product_code": "7", "product_name": "Brand new", "registration_month": "2026/07", "fetch_status": "ok"}],
            )

            added, total = update_new_products(output_dir, "monitor")

            self.assertEqual((added, total), (1, 1))
            rows = read_rows(output_dir / "new_products" / "monitor.csv")
            self.assertEqual(rows[0]["product_code"], "7")
            self.assertEqual(rows[0]["first_collected_date"], "2026-07-23")

    def test_monitor_registry_expires_by_registration_month_and_keeps_dates(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            write_csv(
                output_dir / "state" / "known_products" / "monitor.csv",
                ["product_code", "product_name"],
                [
                    {"product_code": "10", "product_name": "Old name"},
                    {"product_code": "20", "product_name": "Expired"},
                    {"product_code": "30", "product_name": "No reg info"},
                ],
            )
            write_csv(
                output_dir / "new_products" / "monitor.csv",
                ["product_code", "product_name", "first_collected_date", "registration_month"],
                [
                    {"product_code": "10", "product_name": "Old name", "first_collected_date": "2026-07-01", "registration_month": ""},
                    {"product_code": "20", "product_name": "Expired", "first_collected_date": "2026-04-05", "registration_month": "2026/03"},
                    {"product_code": "30", "product_name": "No reg info", "first_collected_date": "2026-07-02", "registration_month": ""},
                ],
            )
            write_csv(
                output_dir / "latest" / "monitor.csv",
                ["product_code", "product_name", "2026-07-22"],
                [{"product_code": "10", "product_name": "Renamed", "2026-07-22": "100"}],
            )
            write_csv(
                output_dir / "specs" / "monitor_specs.csv",
                SPEC_FIELDS,
                [{"product_code": "10", "product_name": "Renamed", "registration_month": "2026/06", "fetch_status": "ok"}],
            )

            added, total = update_new_products(output_dir, "monitor")

            self.assertEqual((added, total), (0, 2))
            rows = {row["product_code"]: row for row in read_rows(output_dir / "new_products" / "monitor.csv")}
            # 20번은 저장된 등록년월이 3개월 밖이라 스펙에서 사라졌어도 만료된다.
            self.assertEqual(set(rows), {"10", "30"})
            self.assertEqual(rows["10"]["product_name"], "Renamed")
            self.assertEqual(rows["10"]["first_collected_date"], "2026-07-01")
            self.assertEqual(rows["10"]["registration_month"], "2026/06")
            # 등록년월을 알 수 없는 항목은 판단할 근거가 없으므로 유지한다.
            self.assertEqual(rows["30"]["first_collected_date"], "2026-07-02")

    def test_monitor_initial_run_creates_baseline_without_new_products(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            write_csv(
                output_dir / "latest" / "monitor.csv",
                ["product_code", "product_name", "2026-07-22"],
                [{"product_code": "100", "product_name": "Already listed", "2026-07-22": "100"}],
            )
            write_csv(
                output_dir / "specs" / "monitor_specs.csv",
                SPEC_FIELDS,
                [{"product_code": "100", "product_name": "Already listed", "registration_month": "2026/07", "fetch_status": "ok"}],
            )

            added, total = update_new_products(output_dir, "monitor")

            self.assertEqual((added, total), (0, 0))
            self.assertEqual(read_rows(output_dir / "new_products" / "monitor.csv"), [])
            known_codes = {
                row["product_code"]
                for row in read_rows(output_dir / "state" / "known_products" / "monitor.csv")
            }
            self.assertEqual(known_codes, {"100"})


if __name__ == "__main__":
    unittest.main()
