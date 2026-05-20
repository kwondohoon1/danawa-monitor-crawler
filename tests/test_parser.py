import unittest

from danawa_crawler.core import Category, has_next_page, move_page_numbers, parse_products
from danawa_crawler.monitor_specs import parse_monitor_specs


class ParserTests(unittest.TestCase):
    def test_parse_product_code_name_and_lowest_price(self):
        html = """
        <ul class="product_list">
          <li id="productItem123456" class="prod_item">
            <p class="prod_name">
              <a href="//prod.danawa.com/info/?pcode=123456">테스트 모니터 27</a>
            </p>
            <div class="prod_pricelist">
              <p class="price_sect"><a><strong>129,000</strong>원</a></p>
              <p class="price_sect"><a><strong>125,000</strong>원</a></p>
            </div>
          </li>
          <li id="productItem999999" class="prod_ad_item">
            <p class="prod_name">
              <a href="//prod.danawa.com/info/?pcode=999999">광고 상품</a>
            </p>
            <p class="price_sect"><a><strong>1,000</strong>원</a></p>
          </li>
        </ul>
        """
        category = Category(slug="monitor", name="모니터", url="https://prod.danawa.com/list/?cate=112757")

        products = parse_products(html, category, "2026-05-18T09:00:00+09:00")

        self.assertEqual(len(products), 1)
        self.assertEqual(products[0].product_code, "123456")
        self.assertEqual(products[0].product_name, "테스트 모니터 27")
        self.assertEqual(products[0].price, 125000)
        self.assertEqual(products[0].price_text, "125,000원")

    def test_parse_move_page_numbers(self):
        html = """
        <a onclick="javascript:movePage(2); return false;">2</a>
        <a onclick="javascript:movePage(11); return false;">다음 페이지</a>
        """

        self.assertEqual(move_page_numbers(html), [2, 11])
        self.assertTrue(has_next_page(html, 10))
        self.assertFalse(has_next_page(html, 11))

    def test_parse_monitor_top_specs(self):
        html = """
        <div class="spec_list">
          <div class="items">
            <span><u>모니터</u></span> /
            <a><u><b>68.5cm(27인치)</b></u></a> /
            <a><u><b>4K UHD(3840 x 2160)</b></u></a> /
            <a><u><b>120Hz</b></u></a> /
            <a><u><b>IPS Black</b></u></a> /
            <a><u><b>와이드(16:9)</b></u></a> /
            <span><u>평면</u></span> /
            <span><u><b>[색상영역]</b></u></span>
            <a><u>DCI-P3</u></a>: <a><u>99%</u></a> /
            <span><u><b>[게임특화]</b></u></span>
            <a><u>G-Sync 호환</u></a> /
            <a><u>FreeSync</u></a> /
            <span><u>듀얼 모드</u></span>: <span><u>4K 120Hz ↔ FHD 240Hz</u></span>
          </div>
        </div>
        <div class="prod_info">
          등록월: 2026.02. ㅣ 제조사: 테스트
        </div>
        """

        specs = parse_monitor_specs(html)

        self.assertEqual(specs["inch"], "68.5cm(27인치)")
        self.assertEqual(specs["resolution"], "4K UHD(3840x2160)")
        self.assertEqual(specs["refresh_rate"], "120Hz")
        self.assertEqual(specs["panel"], "IPS Black")
        self.assertEqual(specs["aspect_ratio"], "와이드(16:9)")
        self.assertEqual(specs["shape"], "평면")
        self.assertEqual(specs["special_features"], "G-Sync 호환 / FreeSync / 듀얼 모드: 4K 120Hz ↔ FHD 240Hz")
        self.assertIn("4K UHD(3840x2160)", specs["full_spec"])
        self.assertEqual(specs["registration_month"], "2026/02")

    def test_parse_monitor_resolution_without_resolution_label(self):
        html = """
        <div class="spec_list">
          <div class="items">
            <span><u>모니터</u></span> /
            <span><u>54.6cm</u></span> /
            <span><u>1920x1080(FHD)</u></span> /
            <span><u>와이드(16:9)</u></span> /
            <span><u>평면</u></span>
          </div>
        </div>
        """

        specs = parse_monitor_specs(html)

        self.assertEqual(specs["inch"], "54.6cm")
        self.assertEqual(specs["resolution"], "1920x1080(FHD)")


if __name__ == "__main__":
    unittest.main()
