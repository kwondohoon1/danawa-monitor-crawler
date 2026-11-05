import csv
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from danawa_crawler.open_market import collect_open_market, parse_offers, pick, shipping_fee


def offer_html(mall: str, price: int, ship: str = "무료배송", store: str = "", code: str = "1") -> str:
    logo = (f'<span class="txt_logo">{store}</span><span class="npay">네이버페이</span>' if store
            else f'<img src="//img.danawa.com/cmpny_info/images/{mall}_logo.gif" alt="{mall}몰">')
    return (f'<div class="diff_item " data-linkProduct="{mall}_{code}"><div class="d_mall">'
            f'<a href="https://prod.danawa.com/bridge/loadingBridge.html?pcode=1&cmpnyc={mall}&link_pcode={code}">{logo}</a></div>'
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
            {"price": 1475000, "mall": "TSC166", "name": "린드스토어(스마트스토어)", "shipping": 0, "code": "1"},
            {"price": 1479000, "mall": "EE128", "name": "EE128몰", "shipping": 3000, "code": "1"},
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


class ElevenStoreTests(unittest.TestCase):
    def test_blocked_11st_store_is_removed_and_cached(self):
        from danawa_crawler.listings import Listings, split
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "blocked_listings.csv").write_text("product_code,mall,link_pcode,store,note\n,,,ebiz,사기\n", encoding="utf-8-sig")
            asked = []

            def fake(code):
                asked.append(code)
                return {"9490264322": ("1194021", "ebiz"), "7": ("1", "정상스토어")}[code]

            listings = Listings(out, fetch_store=fake)
            offers = [{"price": 1868370, "mall": "TH201", "code": "9490264322"}, {"price": 2000000, "mall": "TH201", "code": "7"},
                      {"price": 2148900, "mall": "TX222A", "code": "5"}]
            kept, removed = split(offers, "2026-11-02", listings)
            self.assertEqual([2000000, 2148900], [o["price"] for o in kept])
            self.assertEqual([(offers[0], "막아 둔 11번가 스토어 ebiz")], removed)
            self.assertEqual(["9490264322", "7"], asked)                     # 가장 싼 11번가 판매부터, 막힌 게 아니면 거기서 끝
            listings.save()
            again = Listings(out, fetch_store=lambda code: (_ for _ in ()).throw(AssertionError("cached")))
            self.assertEqual(("1194021", "ebiz"), again.store_of("9490264322"))
            self.assertEqual("ebiz", again.store_blocked("TH201", "9490264322"))

    def test_store_lookup_failure_keeps_offer(self):
        from danawa_crawler.listings import Listings, split
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "blocked_listings.csv").write_text("product_code,mall,link_pcode,store,note\n,,,ebiz,사기\n", encoding="utf-8-sig")

            def fail(code):
                raise OSError("timeout")

            offers = [{"price": 1868370, "mall": "TH201", "code": "9490264322"}]
            kept, removed = split(offers, "2026-11-02", Listings(out, fetch_store=fail))
            self.assertEqual((offers, []), (kept, removed))

    def test_store_lookup_gives_up_when_11st_blocks(self):
        # 11번가가 GitHub 서버를 502로 막았을 때 상품마다 기다리다 매시 수집이 몇 시간씩 늘어졌다 (2026-11-03~05)
        from danawa_crawler.listings import STORE_FAIL_LIMIT, Listings
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            asked = []

            def fail(code):
                asked.append(code)
                raise OSError("502 Bad Gateway")

            listings = Listings(out, fetch_store=fail)
            with mock.patch("builtins.print"):
                for code in [str(n) for n in range(STORE_FAIL_LIMIT + 20)] + ["0", "1"]:
                    self.assertEqual(("", ""), listings.store_of(code))
            self.assertEqual([str(n) for n in range(STORE_FAIL_LIMIT)], asked)   # same product never asked twice
            listings.save()
            self.assertFalse((out / "state" / "eleven_stores.csv").exists())    # failures are not written down


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
            self.assertEqual(("1", "2450000", "3000", "EE128몰", "TH201몰:1500000", "", ""),
                             (rows[0]["product_code"], rows[0]["price"], rows[0]["shipping"], rows[0]["mall"], rows[0]["removed"],
                              rows[0]["price2"], rows[0]["mall2"]))
            self.assertEqual(rows, read_rows(out / "hourly" / day / "gpu_open_09.csv"))

    def test_new_gmarket_listing_far_below_is_fake_but_old_one_is_kept(self):
        # 2026-11-01 사기 판매자: 새 상품번호(48942xxxxx)로 시세보다 20~35% 싸게 올림. 오래된 G마켓 상품은 혼자 싸도 유지
        day = "2026-11-02"
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "latest").mkdir()
            with (out / "latest" / "gpu.csv").open("w", encoding="utf-8-sig", newline="") as file:
                csv.writer(file).writerows([
                    ["product_code", "product_name", day],
                    ["1", "RTX 5080 A", "3029000"],      # 전체 최저가(보정 뒤)
                    ["2", "RTX 5080 B", "1950720"],      # 새 G마켓 상품 하나뿐 — 비교할 가격이 없어 남긴다(가격은 못 믿지만 근거 없음)
                    ["3", "RTX 5080 C", "2311990"],      # 오래된 G마켓 상품이 혼자 싸다 → 유지
                    ["4", "RTX 5080 D", "2331990"],      # 새 G마켓 상품 여럿이 같이 싸다(계정 여러 개) → 전부 빼기
                ])
            pages = {
                "1": offer_html("EE128", 2311990, code="4894257337") + offer_html("EE715", 3029000, code="F702607886")
                     + offer_html("TY618D", 3029000, code="11614892742"),
                "2": offer_html("EE128", 1950720, code="4894257384"),
                "3": offer_html("EE128", 2311990, code="4774903003") + offer_html("TY618D", 3029000, code="11614892742"),
                "4": offer_html("EE128", 2091990, code="4894264936") + offer_html("EE128", 2215990, code="4894264197")
                     + offer_html("EE128", 2331990, code="4894266279") + offer_html("TX222A", 2662000, code="11899934534"),
            }

            def factory(category):
                return lambda code: pages[code]

            collect_open_market(out, day, 8, ["gpu"], fetch_factory=factory)
            rows = {r["product_code"]: r for r in read_rows(out / "latest" / "gpu_open.csv")}
            self.assertEqual(("3029000", "TY618D몰", "3029000", "EE715몰"), (rows["1"]["price"], rows["1"]["mall"], rows["1"]["price2"], rows["1"]["mall2"]))
            self.assertIn("EE128몰:2311990(새 G마켓 상품 4894257337, 믿을 만한 가격 3,029,000)", rows["1"]["removed"])
            self.assertEqual("1950720", rows["2"]["price"])
            self.assertEqual(("2311990", "EE128몰", "3029000"), (rows["3"]["price"], rows["3"]["mall"], rows["3"]["price2"]))
            self.assertEqual(("2662000", "TX222A몰", ""), (rows["4"]["price"], rows["4"]["mall"], rows["4"]["price2"]))
            # 처음 본 날 기록: 새 상품은 오늘, 오래된 상품번호는 과거
            seen = {(r["mall"], r["link_pcode"]): r["first_seen"] for r in read_rows(out / "state" / "listings_seen.csv")}
            self.assertEqual(day, seen[("EE128", "4894257384")])
            self.assertEqual("2026-09-01", seen[("EE128", "4774903003")])
            self.assertNotIn(("TY618D", "11614892742"), seen)     # G마켓·옥션만 기록

    def test_blocked_listing_and_product(self):
        day = "2026-11-02"
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "latest").mkdir()
            (out / "latest" / "gpu.csv").write_text(f"product_code,product_name,{day}\n1,A,3000000\n2,B,3000000\n", encoding="utf-8-sig")
            (out / "blocked_listings.csv").write_text("product_code,mall,link_pcode,store,note\n,EE128,4774903003,,사기\n2,,,,상품 전체 제외\n,TX222A,,,판매 안 함\n", encoding="utf-8-sig")
            pages = {"1": offer_html("EE128", 2311990, code="4774903003") + offer_html("TX222A", 2662000, code="5") + offer_html("TY618D", 3029000, code="7"),
                     "2": offer_html("TY618D", 3029000, code="8")}
            collect_open_market(out, day, 8, ["gpu"], fetch_factory=lambda category: (lambda code: pages[code]))
            rows = {r["product_code"]: r for r in read_rows(out / "latest" / "gpu_open.csv")}
            self.assertEqual(["1"], sorted(rows))
            self.assertEqual(("3029000", "EE128몰:2311990(수동 제외) TX222A몰:2662000(수동 제외)"), (rows["1"]["price"], rows["1"]["removed"]))

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
