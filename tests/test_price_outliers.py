import csv
import tempfile
import unittest
from pathlib import Path

from danawa_crawler.price_outliers import clean_lowest, fix_price_outliers, parse_mall_prices


def mall_item(mall: str, price: int, cash: bool = False) -> str:
    badge = '<span class="badge__cash">현금</span>' if cash else ""
    return (f'<li class="list-item">{badge}<a href="https://prod.danawa.com/bridge/loadingBridge.html?pcode=1&cmpnyc={mall}'
            f'&link_pcode=9">x</a><span class="text__num">{price:,}</span><span class="text__unit">원</span></li>')


def mall_page(*items: str) -> str:
    return '<div id="lowPriceCompanyArea"><ul class="list__mall-price">' + "".join(items) + "</ul></div>"


def write_price_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(header)
        writer.writerows(rows)


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


class ParseTests(unittest.TestCase):
    def test_reads_mall_prices_and_skips_cash(self):
        html = mall_page(mall_item("TH201", 1534160), mall_item("EE128", 2445900), mall_item("PXC11", 2180000, cash=True))
        self.assertEqual([(1534160, "TH201"), (2445900, "EE128")], parse_mall_prices(html))

    def test_missing_list(self):
        self.assertEqual([], parse_mall_prices("<html></html>"))


class CleanTests(unittest.TestCase):
    def test_removes_one_seller_far_below_others(self):
        prices = [(1534160, "TH201"), (2445900, "EE128"), (2458980, "PV203"), (2472200, "EE715"), (2494300, "ED901")]
        self.assertEqual((2445900, [(1534160, "TH201")]), clean_lowest(prices))

    def test_keeps_normal_spread(self):
        prices = [(2297090, "A"), (2305000, "B"), (2338370, "C"), (2348230, "D")]
        self.assertEqual((2297090, []), clean_lowest(prices))

    def test_keeps_price_close_to_previous_price(self):
        prices = [(1189750, "TH201"), (1899000, "TJ918"), (2457990, "A"), (2460000, "B"), (2470000, "C")]
        self.assertEqual((1899000, [(1189750, "TH201")]), clean_lowest(prices, baseline=1899000))
        self.assertEqual(2457990, clean_lowest(prices)[0])

    def test_two_malls(self):
        self.assertEqual((1000, [(700, "A")]), clean_lowest([(700, "A"), (1000, "B")]))
        self.assertEqual((950, []), clean_lowest([(950, "A"), (1000, "B")]))

    def test_single_or_empty(self):
        self.assertEqual((500, []), clean_lowest([(500, "A")]))
        self.assertEqual((None, []), clean_lowest([]))


class FixTests(unittest.TestCase):
    def test_fixes_dropped_price_in_latest_and_history_and_logs(self):
        day = "2026-10-04"
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            header = ["product_code", "product_name", day, "2026-10-03"]
            rows = [["1", "사기 의심", "1534160", "2458980"], ["2", "정상", "2440000", "2450000"], ["3", "신상품", "990000", ""]]
            write_price_csv(out / "latest" / "gpu.csv", header, rows)
            write_price_csv(out / "history" / "gpu_price_history.csv", header, rows)
            pages = {
                "1": mall_page(mall_item("TH201", 1534160), mall_item("EE128", 2445900), mall_item("PV203", 2458980), mall_item("EE715", 2472200)),
                "3": mall_page(mall_item("A", 990000), mall_item("B", 1000000), mall_item("C", 1010000)),
            }
            asked = []

            def factory(category):
                def fetch(code):
                    asked.append(code)
                    return pages[code]
                return fetch

            results = fix_price_outliers(out, day, 18, ["gpu"], fetch_factory=factory)

            self.assertEqual(["1", "3"], sorted(asked))  # 떨어진 상품과 새 상품만 확인 (정상 상품은 안 염)
            self.assertEqual(1, len(results))
            latest = {row["product_code"]: row[day] for row in read_rows(out / "latest" / "gpu.csv")}
            history = {row["product_code"]: row[day] for row in read_rows(out / "history" / "gpu_price_history.csv")}
            self.assertEqual({"1": "2445900", "2": "2440000", "3": "990000"}, latest)
            self.assertEqual(latest, history)
            log = read_rows(out / "hourly" / day / "price_fixes.csv")
            self.assertEqual("1534160", log[0]["crawled_price"])
            self.assertEqual("2445900", log[0]["fixed_price"])
            self.assertEqual("TH201:1534160", log[0]["removed"])

    def test_market_based_fix_and_suspect_single_mall(self):
        day = "2026-10-04"
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            header = ["product_code", "product_name", day, "2026-10-03"]
            rows = [[str(i), f"RTX 5080 사기가 {i}", "1500000", "2450000"] for i in range(1, 6)]        # 사기 가격 5개
            rows += [[str(i), f"RTX 5080 정상 {i}", str(2400000 + i * 10000), "2450000"] for i in range(6, 15)]
            rows += [["20", "사기 단독 신규", "2180000", ""],          # 시세 범위지만 의심 쇼핑몰 단독 새 상품
                     ["21", "11번가 단독 기존", "2380000", "2390000"],  # 의심 쇼핑몰 단독이어도 기존 상품·시세 범위
                     ["22", "단독 사기가", "1600000", "2400000"]]       # 시세보다 크게 싼데 다른 쇼핑몰 없음 → 빼기
            rows += [["23", "옥션 단독 구형", "1700000", "1710000"]]   # 시세보다 싸지만 일반 판매처 단독 → 유지
            write_price_csv(out / "latest" / "gpu.csv", header, rows)
            codes = [row[0] for row in rows]
            write_price_csv(out / "specs" / "gpu_specs.csv",
                            ["collected_at", "product_code", "product_name", "product_url", "chipset", "interface", "memory_type", "memory_size"],
                            [["2026-10-04", code, "x", "u", "RTX 5080", "", "", "16GB"] for code in codes])
            pages = {str(i): mall_page(mall_item("TH201", 1500000), mall_item("EE128", 2440000), mall_item("EE715", 2450000)) for i in range(1, 6)}
            pages["20"] = mall_page(mall_item("TH201", 2180000))
            pages["21"] = mall_page(mall_item("TH201", 2380000))
            pages["22"] = mall_page(mall_item("TH201", 1600000))
            pages["23"] = mall_page(mall_item("EE715", 1700000))
            asked = []

            def factory(category):
                def fetch(code):
                    asked.append(code)
                    return pages[code]
                return fetch

            results = fix_price_outliers(out, day, 7, ["gpu"], fetch_factory=factory)
            latest = {row["product_code"]: row[day] for row in read_rows(out / "latest" / "gpu.csv")}
            self.assertEqual("2440000", latest["1"])      # 시세보다 크게 싼 가격 → 시세 범위의 가장 싼 쇼핑몰
            self.assertEqual("2460000", latest["6"])      # 정상가는 그대로 (상품 페이지도 안 엶)
            self.assertNotIn("6", asked)
            self.assertEqual("", latest["20"])            # 의심 쇼핑몰 단독 신규 상품 → 빼기
            self.assertEqual("2380000", latest["21"])     # 기존 상품·시세 범위 → 유지 (안 엶)
            self.assertEqual("", latest["22"])            # 시세보다 크게 싸고 의심 쇼핑몰 단독 → 빼기
            self.assertEqual("1700000", latest["23"])     # 일반 판매처 단독이면 시세보다 싸도 유지
            self.assertEqual({"1", "2", "3", "4", "5", "20", "22"}, {row["product_code"] for row in results})

    def test_thin_mall_product_near_market_is_kept(self):
        # 판매처가 적은 상품: 11번가 정상가 576,000 + 비싼 판매처 1,061,000 → 시세 범위면 576,000 그대로
        day = "2026-10-06"
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            rows = [[str(i), f"RTX 5060 {i}", str(600000 + i * 5000), "620000"] for i in range(1, 10)]
            rows += [["50", "GALAX 5060", "576000", "1061000"]]
            write_price_csv(out / "latest" / "gpu.csv", ["product_code", "product_name", day, "2026-10-05"], rows)
            write_price_csv(out / "specs" / "gpu_specs.csv",
                            ["collected_at", "product_code", "product_name", "product_url", "chipset", "interface", "memory_type", "memory_size"],
                            [["d", row[0], "x", "u", "RTX 5060", "", "", "8GB"] for row in rows])

            def factory(category):
                def fetch(code):
                    raise AssertionError("시세 범위 상품은 페이지를 열지 않는다")
                return fetch

            self.assertEqual([], fix_price_outliers(out, day, 10, ["gpu"], fetch_factory=factory))
            self.assertEqual("576000", {r["product_code"]: r[day] for r in read_rows(out / "latest" / "gpu.csv")}["50"])

    def test_failed_page_keeps_price(self):
        day = "2026-10-04"
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            write_price_csv(out / "latest" / "ram.csv", ["product_code", "product_name", day, "2026-10-03"], [["9", "램", "100", "200"]])

            def factory(category):
                def fetch(code):
                    raise OSError("timeout")
                return fetch

            self.assertEqual([], fix_price_outliers(out, day, 9, ["ram"], fetch_factory=factory))
            self.assertEqual("100", read_rows(out / "latest" / "ram.csv")[0][day])


if __name__ == "__main__":
    unittest.main()
