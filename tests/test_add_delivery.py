import csv
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from danawa_crawler import core
from danawa_crawler.core import Category, Product, ajax_payload, fetch_list_context


def make_context(add_delivery: str = "N") -> core.DanawaListContext:
    fields = {name: "" for name in core.DanawaListContext.__dataclass_fields__}
    fields["add_delivery"] = add_delivery
    return core.DanawaListContext(**fields)


class AddDeliveryTests(unittest.TestCase):
    def test_list_context_asks_for_prices_with_shipping(self):
        category = Category(slug="monitor_ship", name="모니터", url="https://prod.danawa.com/list/?cate=112757",
                            add_delivery=True)
        with mock.patch.object(core, "fetch_with_requests", return_value="<html></html>"), \
                mock.patch.object(core, "parse_list_context", return_value=make_context("N")):
            context = fetch_list_context(category, 90, 5)
        self.assertEqual(ajax_payload(context, 1, 90)["addDelivery"], "Y")

    def test_plain_category_keeps_page_setting(self):
        category = Category(slug="monitor", name="모니터", url="https://prod.danawa.com/list/?cate=112757")
        with mock.patch.object(core, "fetch_with_requests", return_value="<html></html>"), \
                mock.patch.object(core, "parse_list_context", return_value=make_context("N")):
            context = fetch_list_context(category, 90, 5)
        self.assertEqual(ajax_payload(context, 1, 90)["addDelivery"], "N")

    def test_main_writes_separate_shipping_files(self):
        seen = []

        def fake_crawl(category, **kwargs):
            seen.append(category)
            return [Product(category=category.slug, product_code="58937813", product_name="MSI MAG 275QF",
                            price=291460, price_text="291,460원", product_url="", collected_at="x")]

        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "categories.csv"
            config.write_text("slug,name,url,pages\nmonitor,모니터,https://prod.danawa.com/list/?cate=112757,\n",
                              encoding="utf-8")
            out = Path(tmp) / "data"
            with mock.patch.object(core, "crawl_category", side_effect=fake_crawl):
                code = core.main(["--config", str(config), "--output", str(out), "--category", "monitor",
                                  "--fetcher", "requests", "--add-delivery"])
            self.assertEqual(code, 0)
            self.assertEqual([c.slug for c in seen], ["monitor_ship"])
            self.assertTrue(seen[0].add_delivery)
            self.assertTrue((out / "latest" / "monitor_ship.csv").exists())
            self.assertTrue((out / "history" / "monitor_ship_price_history.csv").exists())
            self.assertFalse((out / "latest" / "monitor.csv").exists())
            self.assertFalse((out / "latest" / "danawa_products.csv").exists())
            with (out / "latest" / "monitor_ship.csv").open(encoding="utf-8-sig") as file:
                row = next(csv.DictReader(file))
            self.assertEqual(row["product_code"], "58937813")
            self.assertIn("291460", row.values())


if __name__ == "__main__":
    unittest.main()
