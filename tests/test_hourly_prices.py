import csv
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from danawa_crawler.core import KST
from danawa_crawler.hourly_prices import (
    README_END,
    README_START,
    next_slot,
    prune_old_days,
    record_hour,
    slot_done,
    update_readme,
)


def write_latest(output_dir: Path, category: str, day: str, prices: dict[str, str]) -> None:
    path = output_dir / "latest" / f"{category}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["product_code", "product_name", day, "2026-09-29"])
        writer.writeheader()
        for code, price in prices.items():
            writer.writerow({"product_code": code, "product_name": f"상품{code}", day: price, "2026-09-29": "1"})


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


class NextSlotTests(unittest.TestCase):
    def at(self, hour, minute=0):
        return datetime(2026, 9, 30, hour, minute, tzinfo=KST)

    def test_before_window_waits_for_seven(self):
        self.assertEqual(self.at(7), next_slot(self.at(6, 7)))
        self.assertEqual(self.at(7), next_slot(self.at(0, 30)))

    def test_inside_window_moves_to_next_hour(self):
        self.assertEqual(self.at(8), next_slot(self.at(7, 3)))
        self.assertEqual(self.at(18), next_slot(self.at(17, 59)))

    def test_after_last_slot_is_finished(self):
        self.assertIsNone(next_slot(self.at(18, 4)))
        self.assertIsNone(next_slot(self.at(23, 0)))


class RecordHourTests(unittest.TestCase):
    def test_snapshots_day_table_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "data"
            day = "2026-09-30"
            for category in ("gpu", "ram", "ssd"):
                write_latest(output, category, day, {"1": "100", "2": ""})
            record_hour(output, day, 7, "2026-09-30T07:00:04+09:00")
            self.assertTrue(slot_done(output, day, 7))
            self.assertFalse(slot_done(output, day, 8))

            write_latest(output, "gpu", day, {"1": "90", "3": "50"})
            record_hour(output, day, 8, "2026-09-30T08:00:03+09:00", ["gpu"])
            self.assertTrue(slot_done(output, day, 8, ["gpu"]))
            self.assertFalse(slot_done(output, day, 8))

            snapshot = read_rows(output / "hourly" / day / "gpu_07.csv")
            self.assertEqual([{"product_code": "1", "product_name": "상품1", "price": "100"},
                              {"product_code": "2", "product_name": "상품2", "price": ""}], snapshot)

            table = {row["product_code"]: row for row in read_rows(output / "hourly" / day / "gpu.csv")}
            self.assertEqual(("100", "90"), (table["1"]["07:00"], table["1"]["08:00"]))
            self.assertEqual(("", "50"), (table["3"]["07:00"], table["3"]["08:00"]))

    def test_re_recording_an_hour_replaces_its_manifest_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "data"
            day = "2026-09-30"
            write_latest(output, "gpu", day, {"1": "100"})
            record_hour(output, day, 9, "2026-09-30T09:00:00+09:00", ["gpu"])
            record_hour(output, day, 9, "2026-09-30T09:30:00+09:00", ["gpu"])
            manifest = read_rows(output / "hourly" / day / "collected.csv")
            self.assertEqual(1, len(manifest))
            self.assertEqual("2026-09-30T09:30:00+09:00", manifest[0]["collected_at"])

    def test_prune_keeps_seven_days(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "data"
            for day in ("2026-09-23", "2026-09-24", "2026-09-30"):
                (output / "hourly" / day).mkdir(parents=True)
            self.assertEqual(["2026-09-23"], prune_old_days(output, "2026-09-30"))
            self.assertEqual({"2026-09-24", "2026-09-30"}, {p.name for p in (output / "hourly").iterdir()})


class ReadmeTests(unittest.TestCase):
    def test_section_is_inserted_then_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "data"
            readme = Path(tmp) / "README.md"
            readme.write_text("# 제목\n\n## 가격정보 바로가기\n\n- 링크\n", encoding="utf-8")
            day = "2026-09-30"
            for category in ("gpu", "ram", "ssd"):
                write_latest(output, category, day, {"1": "100"})
            record_hour(output, day, 7, "2026-09-30T07:00:04+09:00")

            now = datetime(2026, 9, 30, 9, 30, tzinfo=KST)
            update_readme(readme, output, day, now=now)
            update_readme(readme, output, day, now=now)
            text = readme.read_text(encoding="utf-8")

            self.assertEqual(1, text.count(README_START))
            self.assertLess(text.index(README_END), text.index("## 가격정보 바로가기"))
            self.assertIn("| 07:00 | 07:00 | [1개](https://github.com/kwondohoon1/danawa-monitor-crawler/blob/main/data/hourly/2026-09-30/gpu_07.csv)", text)
            self.assertIn("| 08:00 | 미수집 | — | — | — |", text)
            self.assertIn("| 10:00 | 대기 | — | — | — |", text)
            self.assertIn("data/hourly/2026-09-30/ssd.csv", text)


if __name__ == "__main__":
    unittest.main()
