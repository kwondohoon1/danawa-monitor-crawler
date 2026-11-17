"""Danawa list filters (searchAttributeValue[]) and the monitor '디스플레이 기술' column (2026-11).

The new filter '디스플레이 기술' (퀀텀닷(QD) / Mini LED / 나노셀(NanoCell)) is not in the spec summary of the
product page, and the detail table that has it only exists on the new-design page (about half the pages still
come in the old design), so display_tech is filled from the list filtered by each option.
"""

import csv
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from danawa_crawler import core, monitor_specs
from danawa_crawler.core import Category, Product, fetch_ajax_product_list, fetch_list_context, load_categories

MINI_LED = "373925|1145746|1145746|OR"

# Part of /api/list/search-option/?categoryCode=757&mode=extend (2026-11-17)
SEARCH_OPTION = {
    "filterGroups": [
        {"type": "attribute", "id": "attr-attr_373926", "title": "패널 형태", "baseOptions": [], "metadata": {"attributeSeq": 373926}},
        {
            "type": "attribute",
            "id": "attr-attr_373925",
            "title": "디스플레이 기술",
            "allOptions": [
                {"id": "1145745", "label": "퀀텀닷(QD)", "value": "1145745", "metadata": {"multiSelectType": "OR"}},
                {"id": "1145746", "label": "Mini LED", "value": "1145746", "metadata": {"multiSelectType": "OR"}},
                {"id": "1145747", "label": "나노셀(NanoCell)", "value": "1145747", "metadata": {"multiSelectType": "OR"}},
            ],
            "metadata": {"attributeSeq": 373925},
        },
    ]
}


def make_context(search_attributes=()) -> core.DanawaListContext:
    fields = {name: "" for name in core.DanawaListContext.__dataclass_fields__}
    fields["search_attributes"] = search_attributes
    return core.DanawaListContext(**fields)


def product(code: str) -> Product:
    return Product(category="x", product_code=code, product_name=code, price=1, price_text="1원", product_url="", collected_at="x")


class ListFilterTests(unittest.TestCase):
    def test_filter_is_sent_as_search_attribute_value(self):
        session = mock.Mock()
        session.post.return_value = mock.Mock(text="<html></html>", encoding="utf-8")
        fetch_ajax_product_list(session, make_context((MINI_LED,)), 1, 90, "https://prod.danawa.com/list/?cate=112757", 5)
        data = session.post.call_args.kwargs["data"]
        self.assertIn(("searchAttributeValue[]", MINI_LED), data)

    def test_plain_list_sends_no_filter(self):
        session = mock.Mock()
        session.post.return_value = mock.Mock(text="<html></html>", encoding="utf-8")
        fetch_ajax_product_list(session, make_context(), 1, 90, "https://prod.danawa.com/list/?cate=112757", 5)
        data = session.post.call_args.kwargs["data"]
        self.assertFalse([key for key, _ in data if key == "searchAttributeValue[]"])

    def test_list_context_keeps_category_filter(self):
        category = Category(slug="monitor_miniled", name="모니터 Mini LED", url="https://prod.danawa.com/list/?cate=112757",
                            search_attributes=(MINI_LED,))
        with mock.patch.object(core, "fetch_with_requests", return_value="<html></html>"), \
                mock.patch.object(core, "parse_list_context", return_value=make_context()):
            context = fetch_list_context(category, 90, 5)
        self.assertEqual(context.search_attributes, (MINI_LED,))

    def test_categories_csv_reads_the_filter_column(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "categories.csv"
            config.write_text(
                "slug,name,url,pages,search_attributes\n"
                "monitor,모니터,https://prod.danawa.com/list/?cate=112757,\n"
                f"monitor_miniled,모니터 Mini LED,https://prod.danawa.com/list/?cate=112757,,{MINI_LED}\n",
                encoding="utf-8",
            )
            categories = {c.slug: c for c in load_categories(config)}
        self.assertEqual(categories["monitor"].search_attributes, ())
        self.assertEqual(categories["monitor_miniled"].search_attributes, (MINI_LED,))

    def test_repo_config_has_the_mini_led_category(self):
        categories = {c.slug: c for c in load_categories(Path(__file__).resolve().parents[1] / "config" / "categories.csv")}
        self.assertEqual(categories["monitor_miniled"].search_attributes, (MINI_LED,))
        self.assertEqual(categories["monitor"].search_attributes, ())


class DisplayTechTests(unittest.TestCase):
    def test_options_come_from_the_search_option_answer(self):
        self.assertEqual(
            monitor_specs.display_tech_options(SEARCH_OPTION),
            [("퀀텀닷(QD)", "373925|1145745|1145745|OR"), ("Mini LED", MINI_LED), ("나노셀(NanoCell)", "373925|1145747|1145747|OR")],
        )

    def test_missing_filter_is_an_error(self):
        with self.assertRaises(ValueError):
            monitor_specs.display_tech_options({"filterGroups": []})

    def test_products_get_every_option_they_are_listed_under(self):
        lists = {"373925|1145745|1145745|OR": ["1", "2"], MINI_LED: ["2", "3"], "373925|1145747|1145747|OR": []}
        answer = mock.Mock(json=mock.Mock(return_value=SEARCH_OPTION))
        session = mock.Mock(get=mock.Mock(return_value=answer))

        def fake_crawl(category, **kwargs):
            return [product(code) for code in lists[category.search_attributes[0]]]

        with mock.patch.object(core, "fetch_list_context", return_value=make_context()), \
                mock.patch.object(core, "make_session", return_value=session), \
                mock.patch.object(core, "crawl_category", side_effect=fake_crawl):
            tech = monitor_specs.display_tech_by_code(5)
        self.assertEqual(tech, {"1": "퀀텀닷(QD)", "2": "퀀텀닷(QD) / Mini LED", "3": "Mini LED"})

    def run_crawl(self, tmp: Path, tech):
        source = tmp / "monitor.csv"
        source.write_text("product_code,product_name\n1,A\n2,B\n", encoding="utf-8")
        output = tmp / "monitor_specs.csv"

        def fake_fetch(item, collected_at, timeout, retries):
            row = monitor_specs.empty_row(item, collected_at, "ok")
            row["full_spec"] = "모니터"
            return row

        with mock.patch.object(monitor_specs, "fetch_one", side_effect=fake_fetch), \
                mock.patch.object(monitor_specs, "display_tech_by_code", side_effect=tech):
            monitor_specs.crawl_monitor_specs(source, output, workers=1, timeout=5, retries=0, limit=None)
        with output.open(encoding="utf-8-sig") as file:
            return {row["product_code"]: row["display_tech"] for row in csv.DictReader(file)}

    def test_spec_csv_gets_display_tech_column(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_crawl(Path(tmp), lambda timeout: {"2": "Mini LED"})
        self.assertEqual(result, {"1": "", "2": "Mini LED"})

    def test_failed_filter_list_keeps_the_previous_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.run_crawl(Path(tmp), lambda timeout: {"2": "Mini LED"})

            def broken(timeout):
                raise ConnectionError("blocked")

            result = self.run_crawl(Path(tmp), broken)
        self.assertEqual(result, {"1": "", "2": "Mini LED"})


if __name__ == "__main__":
    unittest.main()
