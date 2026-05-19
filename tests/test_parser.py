import unittest

from danawa_crawler.core import Category, parse_products


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

        products = parse_products(html, category, "https://example.test", "2026-05-18T09:00:00+09:00")

        self.assertEqual(len(products), 1)
        self.assertEqual(products[0].product_code, "123456")
        self.assertEqual(products[0].product_name, "테스트 모니터 27")
        self.assertEqual(products[0].price, 125000)
        self.assertEqual(products[0].price_text, "125,000원")


if __name__ == "__main__":
    unittest.main()

