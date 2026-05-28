import unittest

from danawa_crawler.core import Category, has_next_page, move_page_numbers, parse_products
from danawa_crawler.keyboard_specs import extract_keyboard_specs
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

    def test_parse_bundle_detail_products_with_option_names(self):
        html = """
        <ul class="product_list">
          <li id="productItem63143933" class="prod_item">
            <p class="prod_name">
              <a href="//prod.danawa.com/info/?pcode=63143933">한성컴퓨터 TFG Cloud CL 유무선 기계식 코튼캔디</a>
            </p>
            <div class="prod_pricelist">
              <ul>
                <li id="productInfoDetail_63143933">
                  <p class="price_sect">
                    <a href="https://prod.danawa.com/info/?pcode=63143933&cate=112782"><strong>94,000</strong>원</a>
                  </p>
                  <p class="memory_sect"><span class="text">딥블루 뽀송</span></p>
                </li>
                <li id="productInfoDetail_94120037">
                  <p class="price_sect">
                    <a href="https://prod.danawa.com/info/?pcode=94120037&cate=112782"><strong>91,000</strong>원</a>
                  </p>
                  <p class="memory_sect"><span class="text">중고</span></p>
                </li>
              </ul>
            </div>
          </li>
        </ul>
        """
        category = Category(slug="keyboard", name="키보드", url="https://prod.danawa.com/list/?cate=112782")

        products = parse_products(html, category, "2026-05-18T09:00:00+09:00")
        by_code = {product.product_code: product for product in products}

        self.assertEqual(len(products), 2)
        self.assertEqual(
            by_code["63143933"].product_name,
            "한성컴퓨터 TFG Cloud CL 유무선 기계식 코튼캔디 (딥블루 뽀송)",
        )
        self.assertEqual(
            by_code["94120037"].product_name,
            "한성컴퓨터 TFG Cloud CL 유무선 기계식 코튼캔디 (중고)",
        )
        self.assertEqual(by_code["63143933"].price, 94000)
        self.assertEqual(by_code["94120037"].price, 91000)

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
            <span><u>450nits</u></span> /
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
        self.assertEqual(specs["brightness"], "450nits")
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

    def test_parse_keyboard_specs(self):
        html = """
        <div class="spec_list">
          <div class="items">
            <span>키보드</span> /
            <span>텐키리스</span> /
            <span>유선+무선</span> /
            <span>기계식</span> /
            <span>내장 배터리</span> /
            <span>4000mAh</span> /
            <span>88키</span> /
            <span>키압: 45g</span> /
            <span>1000Hz</span> /
            <span>1ms 응답속도</span> /
            <span>동시입력: 무한</span> /
            <span>PBT</span> /
            <span>이중사출 키캡</span> /
            <span>멀티페어링</span> /
            <span>멀티미디어</span> /
            <span>래피드 트리거</span>
          </div>
        </div>
        <div>등록월: 2025.06.</div>
        """

        specs = extract_keyboard_specs(html, "테스트 저소음 바다축 키보드")

        self.assertEqual(specs["size"], "텐키리스")
        self.assertEqual(specs["key_layout"], "93~84키")
        self.assertEqual(specs["connection_type"], "유선+무선")
        self.assertEqual(specs["battery"], "내장 배터리")
        self.assertEqual(specs["battery_capacity"], "4000~5999mAh")
        self.assertEqual(specs["switch_contact_type"], "기계식")
        self.assertEqual(specs["switch_type"], "저소음")
        self.assertEqual(specs["actuation_force"], "45g")
        self.assertEqual(specs["key_switch"], "저소음 바다축")
        self.assertEqual(specs["polling_rate"], "1000Hz")
        self.assertEqual(specs["response_time"], "1ms 응답속도")
        self.assertEqual(specs["rollover"], "무한")
        self.assertEqual(specs["keycap_material"], "PBT")
        self.assertEqual(specs["keycap_printing"], "이중사출 키캡")
        self.assertEqual(specs["extra_features"], "멀티페어링 / 멀티미디어 / 래피드 트리거")
        self.assertIn("키보드", specs["full_spec"])
        self.assertEqual(specs["registration_month"], "2025/06")


if __name__ == "__main__":
    unittest.main()
