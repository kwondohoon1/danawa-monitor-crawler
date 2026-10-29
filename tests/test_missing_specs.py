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


class PartialFailureTests(unittest.TestCase):
    def _setup(self, out):
        write(out / "latest" / "gpu.csv", ["product_code", "product_name"], [[str(i), f"카드 {i}"] for i in range(1, 4)])
        fields = COMPONENTS["gpu"].spec_fields
        old = ["old", "1", "카드 1", "u"] + [""] * (len(fields) - 4)
        old[fields.index("chipset")] = "RTX 5080"
        old[fields.index("fetch_status")] = "ok"
        write(out / "specs" / "gpu_specs.csv", fields, [old])

    def test_failed_products_keep_previous_specs(self):
        from danawa_crawler.component_specs import crawl_component_specs
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._setup(out)

            def fake(component, item, collected_at, timeout, retries):
                if item.product_code == "2":
                    row = component_specs.empty_row(component, item, collected_at, "ok")
                    row["chipset"] = "RTX 5070"
                    return row
                return component_specs.empty_row(component, item, collected_at, "error", "ConnectTimeout")

            with mock.patch.object(component_specs, "fetch_one", fake), mock.patch.object(component_specs, "probe", lambda *a, **k: True):
                total, errors = crawl_component_specs(COMPONENTS["gpu"], out / "latest" / "gpu.csv", out / "specs" / "gpu_specs.csv", 2, 1, 0, None)
            self.assertEqual((3, 2), (total, errors))
            rows = {r["product_code"]: r for r in read_rows(out / "specs" / "gpu_specs.csv")}
            self.assertEqual(("RTX 5080", "ok", "old"), (rows["1"]["chipset"], rows["1"]["fetch_status"], rows["1"]["collected_at"]))  # 실패 → 이전 스펙 유지
            self.assertEqual(("RTX 5070", "ok"), (rows["2"]["chipset"], rows["2"]["fetch_status"]))                                  # 성공 → 새 값
            self.assertEqual("error", rows["3"]["fetch_status"])                                                                    # 이전 값도 없으면 error

    def test_unreachable_keeps_file_untouched(self):
        from danawa_crawler.component_specs import crawl_component_specs
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._setup(out)
            before = read_rows(out / "specs" / "gpu_specs.csv")
            with mock.patch.object(component_specs, "probe", lambda *a, **k: False):
                total, errors = crawl_component_specs(COMPONENTS["gpu"], out / "latest" / "gpu.csv", out / "specs" / "gpu_specs.csv", 2, 1, 0, None)
            self.assertEqual((3, 3), (total, errors))
            self.assertEqual(before, read_rows(out / "specs" / "gpu_specs.csv"))

    def test_probe_waits_then_gives_up(self):
        calls = []
        session = mock.Mock()
        session.get.side_effect = component_specs.requests.ConnectTimeout("blocked")
        with mock.patch.object(component_specs, "get_session", lambda: session), mock.patch.object(component_specs.time, "sleep", calls.append):
            ok = component_specs.probe(COMPONENTS["gpu"], component_specs.ComponentInput(0, "1", "x", "https://prod.danawa.com/info/?pcode=1"), 5, waits=(0, 1, 2))
        self.assertFalse(ok)
        self.assertEqual([1, 2], calls)


if __name__ == "__main__":
    unittest.main()
