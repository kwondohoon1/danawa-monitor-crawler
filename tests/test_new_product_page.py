"""Danawa's new (Next.js) product page, rolled out from 2026-11 next to the old one.

Until the parsers knew it, the monitor/keyboard/laptop spec crawls failed every day (spec_list not found)
and the TV crawl saved 484 products with empty specs.
"""

import csv
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from danawa_crawler import monitor_specs, tv_specs
from danawa_crawler.component_specs import COMPONENTS, extract_component_specs
from danawa_crawler.keyboard_specs import extract_keyboard_specs
from danawa_crawler.laptop_specs import parse_laptop_specs
from danawa_crawler.monitor_specs import keep_previous_specs, parse_monitor_specs, too_many_errors
from danawa_crawler.tv_specs import parse_tv_specs


def old_page(*parts: str) -> str:
    """Old page: <div class="spec_list"><div class="items"> with ' / ' text between the values."""
    body = ""
    for part in parts:
        if part.startswith("["):
            body += f"<span><u><b>{part}</b></u></span> "
        elif part.startswith("출시가"):
            body += f"<span>{part}</span>"
        else:
            body += f"<a><u><b>{part}</b></u></a> / "
    return (f'<div class="spec_list"><div class="items">{body}</div></div>'
            '<div class="prod_info">등록월: 2026.02. ㅣ 제조사: 테스트</div>')


def new_page(*parts: str) -> str:
    """New page: spans and tooltip buttons in [data-testid=ProductHeader-specs] (markup copied from a real page)."""
    body = []
    for part in parts:
        if part.startswith("["):
            body.append(f'<span class="font-bold">{part}</span><span class="text-dnw-gray-300"> </span>')
            continue
        if part.startswith("출시가"):
            price = part.split(":", 1)[1].strip().removesuffix("원")
            body.append(f'<span data-testid="ProductHeader-initial-price">출시가<!-- -->: <!-- -->{price}<!-- -->원</span>')
            continue
        body.append(f'<button type="button" class="cursor-help"><span class="underline">{part}</span></button>')
        body.append('<span class="text-dnw-gray-300"> / </span>')
    html = "".join(body)
    return ('<html><script>self.__next_f.push([1,"0:[]"])</script>'
            '<h1 data-testid="ProductHeader-name">테스트</h1>'
            f'<div data-testid="ProductHeader-specs" class="mt-dnw-6 flex flex-wrap">{html}</div>'
            '<div>관심 공유 신고 인쇄 등록월 : 2026.02. 제조사: 테스트</div></html>')


MONITOR = ["모니터", "80cm(32인치)", "4K UHD(3840 x 2160)", "60Hz", "IPS", "와이드(16:9)", "평면", "350nits",
           "[게임특화]", "조준선 표시", "FreeSync", "[단자정보]", "HDMI", "DP", "출시가: 263,000원"]


class NewProductPageTests(unittest.TestCase):
    def test_monitor_specs_are_the_same_on_both_pages(self):
        old, new = parse_monitor_specs(old_page(*MONITOR)), parse_monitor_specs(new_page(*MONITOR))
        self.assertEqual(old, new)
        self.assertEqual("80cm(32인치)", new["inch"])
        self.assertEqual("4K UHD(3840x2160)", new["resolution"])
        self.assertEqual("IPS", new["panel"])
        self.assertEqual("조준선 표시 / FreeSync", new["special_features"])
        self.assertEqual("2026/02", new["registration_month"])
        self.assertTrue(new["full_spec"].endswith("[단자정보] HDMI / DP / 출시가: 263,000원"), new["full_spec"])

    def test_other_categories_read_the_new_page(self):
        laptop = ["노트북", "35.56cm(14인치)", "1.28kg", "[CPU]", "인텔", "코어 울트라9(S2)", "[구성]", "32GB", "출시가: 2,199,000원"]
        self.assertEqual(parse_laptop_specs(old_page(*laptop), "ASUS 젠북 14"), parse_laptop_specs(new_page(*laptop), "ASUS 젠북 14"))
        tv = ["TV", "163cm(65인치)", "4K UHD(3840 x 2160)", "120Hz", "[화질]", "HDR10", "돌비비전"]
        self.assertEqual(parse_tv_specs(old_page(*tv)), parse_tv_specs(new_page(*tv)))
        self.assertEqual("120Hz", parse_tv_specs(new_page(*tv))["refresh_rate"])
        keyboard = ["키보드", "텐키리스", "유선", "기계식", "87키", "PBT"]
        self.assertEqual(extract_keyboard_specs(old_page(*keyboard), "x"), extract_keyboard_specs(new_page(*keyboard), "x"))
        gpu = ["RTX 5070", "PCIe5.0x16", "GDDR7", "베이스클럭: 2325MHz"]
        component = COMPONENTS["gpu"]
        self.assertEqual(extract_component_specs(component, old_page(*gpu), "x 12GB"),
                         extract_component_specs(component, new_page(*gpu), "x 12GB"))

    def test_new_page_is_not_an_error(self):
        response = mock.Mock(text=new_page(*MONITOR))
        response.raise_for_status.return_value = None
        session = mock.Mock()
        session.get.return_value = response
        item = monitor_specs.MonitorInput(0, "124130592", "레노버 ThinkVision T32P-20", "https://prod.danawa.com/info/?pcode=124130592")
        with mock.patch.object(monitor_specs, "get_session", return_value=session):
            row = monitor_specs.fetch_one(item, "2026-11-05T09:00:00+09:00", timeout=5, retries=0)
        self.assertEqual("ok", row["fetch_status"])
        self.assertEqual("60Hz", row["refresh_rate"])


class RetryAndKeepTests(unittest.TestCase):
    def test_retry_uses_a_new_connection(self):
        bad = mock.Mock(text="<html>no specs</html>")
        good = mock.Mock(text=old_page(*MONITOR))
        for response in (bad, good):
            response.raise_for_status.return_value = None
        first, second = mock.Mock(), mock.Mock()
        first.get.return_value, second.get.return_value = bad, good
        item = monitor_specs.MonitorInput(0, "1", "x", "https://prod.danawa.com/info/?pcode=1")
        monitor_specs._thread_local.session = first
        try:
            with mock.patch.object(monitor_specs, "make_session", return_value=second), mock.patch.object(monitor_specs.time, "sleep"):
                row = monitor_specs.fetch_one(item, "t", timeout=5, retries=1)
        finally:
            monitor_specs._thread_local.session = None
        self.assertEqual("ok", row["fetch_status"])
        first.close.assert_called_once()                 # the stuck connection was dropped

    def test_failed_products_keep_previous_specs(self):
        fields = tv_specs.SPEC_FIELDS
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tv_specs.csv"
            with path.open("w", encoding="utf-8-sig", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=fields)
                writer.writeheader()
                writer.writerow({**{f: "" for f in fields}, "product_code": "1", "product_name": "옛 이름",
                                 "refresh_rate": "120Hz", "full_spec": "TV / 120Hz", "fetch_status": "ok"})
                writer.writerow({**{f: "" for f in fields}, "product_code": "2", "fetch_status": "error"})
            rows = [
                {**{f: "" for f in fields}, "product_code": "1", "product_name": "새 이름", "fetch_status": "error", "error": "x"},
                {**{f: "" for f in fields}, "product_code": "2", "product_name": "b", "fetch_status": "error", "error": "x"},
                {**{f: "" for f in fields}, "product_code": "3", "product_name": "c", "refresh_rate": "60Hz", "fetch_status": "ok"},
            ]
            kept = keep_previous_specs(path, rows, fields)
        self.assertEqual(1, kept)
        self.assertEqual(("ok", "120Hz", "새 이름"), (rows[0]["fetch_status"], rows[0]["refresh_rate"], rows[0]["product_name"]))
        self.assertEqual("error", rows[1]["fetch_status"])           # never read before → stays an error
        self.assertEqual("60Hz", rows[2]["refresh_rate"])

    def test_error_share(self):
        self.assertTrue(too_many_errors(1, 100, 0.0))
        self.assertFalse(too_many_errors(0, 100, 0.0))
        self.assertFalse(too_many_errors(5, 100, 0.05))
        self.assertTrue(too_many_errors(6, 100, 0.05))


if __name__ == "__main__":
    unittest.main()
