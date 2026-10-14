import csv
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from danawa_crawler import component_specs
from danawa_crawler.component_specs import COMPONENTS, crawl_missing_specs


def write(path: Path, header: list[str], rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(header)
        writer.writerows(rows)


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


class MissingSpecsTests(unittest.TestCase):
    def test_fetches_only_products_without_specs(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            write(out / "latest" / "ssd.csv", ["product_code", "product_name", "2026-10-14"],
                  [["1", "기존 SSD (1TB)", "100"], ["2", "새 SSD (2TB)", "200"]])
            fields = COMPONENTS["ssd"].spec_fields
            write(out / "specs" / "ssd_specs.csv", fields, [["x", "1"] + [""] * (len(fields) - 2)])
            asked = []

            def fake(component, item, collected_at, timeout, retries):
                asked.append(item.product_code)
                row = component_specs.empty_row(component, item, collected_at, "ok")
                row["capacity"] = "2TB"
                return row

            with mock.patch.object(component_specs, "fetch_one", fake):
                self.assertEqual(1, crawl_missing_specs(out, "ssd"))
                self.assertEqual(0, crawl_missing_specs(out, "ssd"))   # 이미 받은 상품은 다시 안 받음
            self.assertEqual(["2"], asked)
            rows = read_rows(out / "specs" / "ssd_specs_new.csv")
            self.assertEqual([("2", "2TB")], [(r["product_code"], r["capacity"]) for r in rows])


if __name__ == "__main__":
    unittest.main()
