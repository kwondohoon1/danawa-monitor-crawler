import json
import unittest
from unittest import mock

from danawa_crawler import keyboard_specs
from danawa_crawler.core import (
    Category,
    CrawlerError,
    ajax_payload,
    category_context_url,
    context_from_next_page,
    parse_list_context,
)


def next_page_html(*payloads: str) -> str:
    scripts = "".join(
        f"<script>self.__next_f.push([1,{json.dumps(payload, ensure_ascii=False)}])</script>" for payload in payloads
    )
    return f"<!DOCTYPE html><html><head></head><body>{scripts}</body></html>"


HDD_PAYLOAD = (
    '4e:["$","$L12",null,{"state":{"queries":[{"state":{"data":{"viewModel":{'
    '"currentCategory":{"code":"11229614","name":"HDD","depth":2,"group":11},'
    '"uiCategoryHierarchyCodes":["29417","29614"],'
    '"physicsCategory":{"physicsCate1":"861","physicsCate2":"877","physicsCate3":"","physicsCate4":""},'
    '"powerLinkKeyword":"하드디스크","categoryMappingCode":"714",'
    '"originCategory":{"code":"112763","depth":2,"group":11}}}},'
    '"queryKey":["category","page","11229614"]},'
)
HDD_PRODUCTS = (
    '{"state":{"data":{"products":[],"totalCount":400,"currentPage":1,"pageSize":30,"totalPages":14}},'
    '"queryKey":["productList","11229614",1,30]}]}}]\n'
)


class ListContextTests(unittest.TestCase):
    def test_context_url_uses_legacy_index_page(self):
        category = Category(slug="monitor", name="모니터", url="https://prod.danawa.com/list/?cate=112757")
        url = category_context_url(category, 90)
        self.assertTrue(url.startswith("https://prod.danawa.com/list/index.php?"))
        self.assertIn("cate=112757", url)
        self.assertIn("listCount=90", url)

    def test_context_from_next_page_uses_origin_category_code(self):
        # The RSC payload is split across push() calls, so the parser must join them first.
        payload = HDD_PAYLOAD + HDD_PRODUCTS
        html = next_page_html(payload[:120], payload[120:])

        context = context_from_next_page(html)

        self.assertEqual(context.category_code, "763")
        self.assertEqual(context.list_category_code, "29614")
        self.assertEqual(context.group, "11")
        self.assertEqual(context.depth, "2")
        self.assertEqual(context.physics_cate1, "861")
        self.assertEqual(context.physics_cate2, "877")
        self.assertEqual(context.physics_cate3, "0")
        self.assertEqual(context.power_link_keyword, "하드디스크")
        self.assertEqual(context.category_mapping_code, "714")
        self.assertEqual(context.total_count, 400)

        payload_fields = ajax_payload(context, 2, 90)
        self.assertEqual(payload_fields["categoryCode"], "763")
        self.assertEqual(payload_fields["listCategoryCode"], "29614")
        self.assertEqual(payload_fields["page"], 2)

    def test_parse_list_context_dispatches_on_page_type(self):
        legacy_html = """
        <script>
        var oGlobalSetting = {
            nCategoryCode : 757,
            nListCategoryCode : 757,
            sPhysicsCate1 : '860',
            sPhysicsCate2 : '13735',
            nListGroup : 11,
            nListDepth : 2
        };
        var oExpansionContent = {
            nPriceCompareListPackageType : 1
        };
        </script>
        <input id="totalProductCount" value="4,417">
        """
        legacy = parse_list_context(legacy_html)
        self.assertEqual(legacy.category_code, "757")
        self.assertEqual(legacy.total_count, 4417)

        modern = parse_list_context(next_page_html(HDD_PAYLOAD + HDD_PRODUCTS))
        self.assertEqual(modern.category_code, "763")

        with self.assertRaises(CrawlerError):
            parse_list_context("<html><body>maintenance</body></html>")


class EmptySpecTests(unittest.TestCase):
    def test_empty_spec_list_is_not_an_error(self):
        html = '<html><div class="spec_list">\n    <div class="items"></div>\n</div></html>'
        response = mock.Mock(text=html)
        response.raise_for_status.return_value = None
        session = mock.Mock()
        session.get.return_value = response
        item = keyboard_specs.KeyboardInput(
            index=0,
            product_code="118977349",
            product_name="라이트컴 Coms 다용도 만능크리너 소 (CK0003) (1개)",
            product_url="https://prod.danawa.com/info/?pcode=118977349&cate=112782",
        )

        with mock.patch.object(keyboard_specs, "get_session", return_value=session):
            row = keyboard_specs.fetch_one(item, "2026-09-29T00:00:00+09:00", timeout=5, retries=0)

        self.assertEqual(row["fetch_status"], "no_spec")
        self.assertEqual(row["error"], "")

    def test_missing_spec_list_is_still_an_error(self):
        response = mock.Mock(text="<html><body>no specs here</body></html>")
        response.raise_for_status.return_value = None
        session = mock.Mock()
        session.get.return_value = response
        item = keyboard_specs.KeyboardInput(
            index=0,
            product_code="1",
            product_name="x",
            product_url="https://prod.danawa.com/info/?pcode=1",
        )

        with mock.patch.object(keyboard_specs, "get_session", return_value=session):
            row = keyboard_specs.fetch_one(item, "2026-09-29T00:00:00+09:00", timeout=5, retries=0)

        self.assertEqual(row["fetch_status"], "error")


if __name__ == "__main__":
    unittest.main()
