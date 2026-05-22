import csv
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from danawa_crawler.core import REQUEST_RETRIES, make_session, now_kst_iso, Product, write_history, write_latest


class PriceCsvTests(unittest.TestCase):
    def test_price_collection_timestamp_uses_kst(self):
        timestamp = now_kst_iso()

        self.assertTrue(timestamp.endswith("+09:00"))
        self.assertEqual(timedelta(hours=9), datetime.fromisoformat(timestamp).utcoffset())

    def test_make_session_retries_get_and_post_requests(self):
        session = make_session()
        retry = session.adapters["https://"].max_retries

        self.assertEqual(retry.total, REQUEST_RETRIES)
        self.assertIn("GET", retry.allowed_methods)
        self.assertIn("POST", retry.allowed_methods)
        self.assertIn(429, retry.status_forcelist)
        self.assertIn(503, retry.status_forcelist)

    def test_write_latest_keeps_only_base_and_recent_date_columns(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "data"
            latest_dir = output_dir / "latest"
            latest_dir.mkdir(parents=True)
            dates = [f"2026-05-{day:02d}" for day in range(10, 18)]

            with (latest_dir / "monitor.csv").open("w", encoding="utf-8-sig", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=["product_code", "product_name", *dates])
                writer.writeheader()
                writer.writerow(
                    {
                        "product_code": "100",
                        "product_name": "Alpha",
                        **{date: str(100 + index) for index, date in enumerate(dates)},
                    }
                )

            write_latest(
                output_dir,
                {
                    "monitor": [
                        Product(
                            category="monitor",
                            product_code="100",
                            product_name="Alpha",
                            price=200,
                            price_text="200원",
                            product_url="",
                            collected_at="2026-05-18T09:00:00+09:00",
                        ),
                        Product(
                            category="monitor",
                            product_code="200",
                            product_name="Beta",
                            price=None,
                            price_text="",
                            product_url="",
                            collected_at="2026-05-18T09:00:00+09:00",
                        ),
                    ]
                },
                "2026-05-18",
                history_days=8,
            )

            with (latest_dir / "monitor.csv").open("r", encoding="utf-8-sig", newline="") as file:
                reader = csv.DictReader(file)
                rows = list(reader)

            self.assertEqual(
                reader.fieldnames,
                [
                    "product_code",
                    "product_name",
                    "2026-05-18",
                    "2026-05-17",
                    "2026-05-16",
                    "2026-05-15",
                    "2026-05-14",
                    "2026-05-13",
                    "2026-05-12",
                    "2026-05-11",
                ],
            )
            self.assertEqual(rows[0]["product_code"], "100")
            self.assertEqual(rows[0]["2026-05-17"], "107")
            self.assertEqual(rows[0]["2026-05-18"], "200")
            self.assertEqual(rows[1]["product_code"], "200")
            self.assertEqual(rows[1]["2026-05-18"], "")

    def test_write_latest_creates_fixed_date_columns_starting_today(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "data"
            write_latest(
                output_dir,
                {
                    "monitor": [
                        Product(
                            category="monitor",
                            product_code="100",
                            product_name="Alpha",
                            price=200,
                            price_text="200원",
                            product_url="",
                            collected_at="2026-05-18T09:00:00+09:00",
                        )
                    ]
                },
                "2026-05-18",
                history_days=8,
                write_combined=False,
            )

            with (output_dir / "latest" / "monitor.csv").open("r", encoding="utf-8-sig", newline="") as file:
                reader = csv.DictReader(file)
                rows = list(reader)

            self.assertEqual(
                reader.fieldnames,
                [
                    "product_code",
                    "product_name",
                    "2026-05-18",
                    "2026-05-17",
                    "2026-05-16",
                    "2026-05-15",
                    "2026-05-14",
                    "2026-05-13",
                    "2026-05-12",
                    "2026-05-11",
                ],
            )
            self.assertEqual(rows[0]["2026-05-11"], "")
            self.assertEqual(rows[0]["2026-05-18"], "200")

    def test_write_history_keeps_sixty_days_in_one_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "data"
            write_history(
                output_dir,
                {
                    "monitor": [
                        Product(
                            category="monitor",
                            product_code="100",
                            product_name="Alpha",
                            price=200,
                            price_text="200원",
                            product_url="",
                            collected_at="2026-05-18T09:00:00+09:00",
                        )
                    ]
                },
                "2026-05-18",
            )

            with (output_dir / "history" / "monitor_price_history.csv").open(
                "r", encoding="utf-8-sig", newline=""
            ) as file:
                reader = csv.DictReader(file)
                rows = list(reader)

            self.assertEqual(len(reader.fieldnames), 62)
            self.assertEqual(reader.fieldnames[:3], ["product_code", "product_name", "2026-05-18"])
            self.assertEqual(reader.fieldnames[-1], "2026-03-20")
            self.assertEqual(rows[0]["2026-05-18"], "200")
            self.assertEqual(rows[0]["2026-03-20"], "")

    def test_write_latest_can_skip_combined_csv(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "data"
            write_latest(
                output_dir,
                {
                    "monitor": [
                        Product(
                            category="monitor",
                            product_code="100",
                            product_name="Alpha",
                            price=200,
                            price_text="200원",
                            product_url="",
                            collected_at="2026-05-18T09:00:00+09:00",
                        )
                    ]
                },
                "2026-05-18",
                write_combined=False,
            )

            self.assertTrue((output_dir / "latest" / "monitor.csv").exists())
            self.assertFalse((output_dir / "latest" / "danawa_products.csv").exists())


if __name__ == "__main__":
    unittest.main()
