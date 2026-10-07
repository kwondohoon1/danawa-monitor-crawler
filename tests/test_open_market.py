import csv
import tempfile
import unittest
from pathlib import Path

from danawa_crawler.open_market import collect_open_market, parse_offers, pick, shipping_fee


def offer_html(mall: str, price: int, ship: str = "무료배송", store: str = "") -> str:
    logo = (f'<span class="txt_logo">{store}</span><span class="npay">네이버페이</span>' if store
            else f'<img src="//img.danawa.com/cmpny_info/images/{mall}_logo.gif" alt="{mall}몰">')
    return (f'<div class="diff_item " data-linkProduct="{mall}_1"><div class="d_mall">'
            f'<a href="https://prod.danawa.com/bridge/loadingBridge.html?pcode=1&cmpnyc={mall}&link_pcode=1">{logo}</a></div>'
            f'<span class="price "><em class="prc_c">{price:,}</em>원</span><span class="ship">({ship})</span></div>')


def offer(price: int, name: str) -> dict:
    return {"price": price, "mall": name, "name": name, "shipping": 0}


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


class ParseTests(unittest.TestCase):
    def test_reads_price_mall_and_shipping(self):
        html = offer_html("EE128", 1479000, "배송비 3,000원") + offer_html("TSC166", 1475000, store="린드스토어")
        self.assertEqual([
            {"price": 1475000, "mall": "TSC166", "name": "린드스토어(스마트스토어)", "shipping": 0},
            {"price": 1479000, "mall": "EE128", "name": "EE128몰", "shipping": 3000},
        ], parse_offers(html))

    def test_shipping_fee(self):
        self.assertEqual(0, shipping_fee("무료배송"))
        self.assertEqual(2500, shipping_fee("배송비 2,500원"))
        self.assertIsNone(shipping_fee("유/무료배송"))


class PickTests(unittest.TestCase):
    def test_skips_fake_low_offer(self):
        offers = [offer(1500000, "11번가"), offer(2440000, "G마켓"), offer(2450000, "옥션")]
        self.assertEqual((offers[1], offers[:1]), pick(offers, 2440000 * 0.85))

    def test_keeps_price_many_malls_agree_on(self):
        offers = [offer(3370300, "G마켓"), offer(3370300, "옥션"), offer(3370310, "11번가"), offer(4069420, "A")]
        self.assertEqual((offers[0], []), pick(offers, 4289990 * 0.85))

    def test_picks_cheapest_with_shipping(self):
        offers = [{"price": 1479000, "mall": "A", "name": "A", "shipping": 3000},
                  {"price": 1481000, "mall": "B", "name": "B", "shipping": 0}]
        self.assertEqual((offers[1], []), pick(offers, 1000000))

    def test_nothing_believable(self):
        offers = [offer(100, "A")]
        self.assertEqual((None, offers), pick(offers, 1000))


class CollectTests(unittest.TestCase):
    def test_writes_latest_and_hourly_open_prices(self):
        day = "2026-10-07"
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "latest").mkdir()
            with (out / "latest" / "gpu.csv").open("w", encoding="utf-8-sig", newline="") as file:
                csv.writer(file).writerows([
                    ["product_code", "product_name", day],
                    ["1", "RTX 5070 A", "2440000"],          # 사기 가격은 이미 보정된 전체 최저가
                    ["2", "RTX 5070 현금몰만", "1300000"],    # 오픈마켓 판매 없음 → 빠짐
                    ["3", "RTX 5070 중고", "900000"],         # 중고 → 확인 안 함
                ])
            pages = {"1": offer_html("TH201", 1500000) + offer_html("EE128", 2450000, "배송비 3,000원"), "2": ""}

            def factory(category):
                return lambda code: pages[code]

            collect_open_market(out, day, 9, ["gpu"], fetch_factory=factory)
            rows = read_rows(out / "latest" / "gpu_open.csv")
            self.assertEqual(1, len(rows))
            self.assertEqual(("1", "2450000", "3000", "EE128몰", "TH201몰:1500000"),
                             (rows[0]["product_code"], rows[0]["price"], rows[0]["shipping"], rows[0]["mall"], rows[0]["removed"]))
            self.assertEqual(rows, read_rows(out / "hourly" / day / "gpu_open_09.csv"))

    def test_failed_fetch_keeps_previous_row(self):
        day = "2026-10-07"
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "latest").mkdir()
            (out / "latest" / "ram.csv").write_text(f"product_code,product_name,{day}\n9,램,100\n", encoding="utf-8-sig")
            (out / "latest" / "ram_open.csv").write_text(
                "product_code,product_name,price,shipping,mall,offers,removed\n9,램,110,0,G마켓,3,\n", encoding="utf-8-sig")

            def factory(category):
                def fetch(code):
                    raise OSError("timeout")
                return fetch

            collect_open_market(out, day, 10, ["ram"], fetch_factory=factory)
            self.assertEqual("110", read_rows(out / "latest" / "ram_open.csv")[0]["price"])


if __name__ == "__main__":
    unittest.main()
