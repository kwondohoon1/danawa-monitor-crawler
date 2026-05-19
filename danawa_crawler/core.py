from __future__ import annotations

import argparse
import csv
import math
import re
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, parse_qsl, urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


BASE_URL = "https://prod.danawa.com"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)
REQUEST_RETRIES = 6
REQUEST_BACKOFF = 1.0
RETRY_STATUS_CODES = (429, 500, 502, 503, 504)

PRICE_BASE_FIELDS = ["product_code", "product_name"]
PRICE_DATE_FIELD = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DEFAULT_PRICE_HISTORY_DAYS = 8
DEFAULT_HISTORY_FILE_DAYS = 60


@dataclass(frozen=True)
class Category:
    slug: str
    name: str
    url: str
    pages: int | None = None


@dataclass(frozen=True)
class DanawaListContext:
    category_code: str
    list_category_code: str
    physics_cate1: str
    physics_cate2: str
    physics_cate3: str
    physics_cate4: str
    group: str
    depth: str
    power_link_keyword: str
    current_category_code: str
    category_mapping_code: str
    package_type: str
    package_limit: str
    price_unit: str
    price_unit_value: str
    price_unit_class: str
    cm_recommend_sort: str
    cm_recommend_sort_default: str
    bundle_image_preview: str
    maker_display_yn: str
    discount_product_rate: str
    initial_price_display: str
    dpg_zone_category: str
    assembly_gallery_category: str
    quick_delivery_category_yn: str
    quick_delivery_display: str
    price_unit_sort: str
    price_unit_sort_order: str
    simple_description_display_yn: str
    simple_description_open: str
    mall_min_price_display_yn: str
    product_list_api: str
    dnw_switch_yn: str
    add_delivery: str
    coupang_member_sort: str
    coupang_member_sort_layer_type: str
    sort_method: str
    total_count: int | None


@dataclass(frozen=True)
class PriceRange:
    min_price: int
    max_price: int

    def label(self) -> str:
        return f"{self.min_price:,}-{self.max_price:,}"


@dataclass(frozen=True)
class SegmentResult:
    products: list[Product]
    total_count: int | None
    pages: int
    stopped_on_duplicate: bool


@dataclass(frozen=True)
class Product:
    category: str
    product_code: str
    product_name: str
    price: int | None
    price_text: str
    product_url: str
    collected_at: str


class CrawlerError(RuntimeError):
    pass


class SeleniumFetcher:
    def __init__(self, timeout: int = 20) -> None:
        self.timeout = timeout
        self.driver = None

    def get(self, url: str) -> str:
        if self.driver is None:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options

            options = Options()
            options.add_argument("--headless=new")
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--disable-gpu")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("lang=ko-KR")
            options.add_argument(f"user-agent={DEFAULT_USER_AGENT}")
            self.driver = webdriver.Chrome(options=options)

        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait

        self.driver.get(url)
        WebDriverWait(self.driver, self.timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "li[id^='productItem']"))
        )
        time.sleep(1)
        return self.driver.page_source

    def close(self) -> None:
        if self.driver is not None:
            self.driver.quit()
            self.driver = None


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def load_categories(config_path: Path) -> list[Category]:
    categories: list[Category] = []
    with config_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            slug = normalize_space(row.get("slug", ""))
            name = normalize_space(row.get("name", ""))
            url = normalize_space(row.get("url", ""))
            pages_text = normalize_space(row.get("pages", ""))
            if not slug or not name or not url:
                continue
            pages = max(1, int(pages_text)) if pages_text else None
            categories.append(Category(slug=slug, name=name, url=url, pages=pages))
    if not categories:
        raise CrawlerError(f"No categories found in {config_path}")
    return categories


def category_code_from_url(url: str) -> str | None:
    query = parse_qs(urlparse(url).query)
    for key in ("cate", "categoryCode", "listCategoryCode"):
        values = query.get(key)
        if values:
            return values[0]
    return None


def update_query(url: str, updates: dict[str, str | int]) -> str:
    parts = urlparse(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    for key, value in updates.items():
        query[key] = str(value)
    return urlunparse(parts._replace(query=urlencode(query)))


def category_page_url(category: Category, page: int, list_count: int) -> str:
    updates: dict[str, str | int] = {
        "page": page,
        "listCount": list_count,
        "viewMethod": "LIST",
    }
    code = category_code_from_url(category.url)
    if code:
        updates["categoryCode"] = code
        updates["listCategoryCode"] = code
    return update_query(category.url, updates)


def fetch_with_requests(session: requests.Session, url: str, timeout: int) -> str:
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    if not response.encoding:
        response.encoding = response.apparent_encoding
    return response.text


def make_retry_adapter() -> HTTPAdapter:
    retry = Retry(
        total=REQUEST_RETRIES,
        connect=REQUEST_RETRIES,
        read=REQUEST_RETRIES,
        status=REQUEST_RETRIES,
        backoff_factor=REQUEST_BACKOFF,
        status_forcelist=RETRY_STATUS_CODES,
        allowed_methods=frozenset({"GET", "POST"}),
        raise_on_status=False,
        respect_retry_after_header=True,
    )
    return HTTPAdapter(max_retries=retry, pool_connections=16, pool_maxsize=16)


def extract_js_object_body(html: str, variable_name: str) -> str:
    match = re.search(rf"var\s+{re.escape(variable_name)}\s*=\s*\{{(?P<body>.*?)\}};", html, re.S)
    if not match:
        raise CrawlerError(f"Could not find {variable_name} in Danawa list page")
    return match.group("body")


def js_object_value(body: str, key: str, default: str = "") -> str:
    pattern = rf"{re.escape(key)}\s*:\s*(?P<value>\"(?:\\.|[^\"])*\"|'(?:\\.|[^'])*'|[^,\n\r}}]+)"
    match = re.search(pattern, body)
    if not match:
        return default
    value = match.group("value").strip()
    if value.startswith(("'", '"')) and value.endswith(("'", '"')):
        value = value[1:-1]
    return value.strip()


def js_variable_value(html: str, variable_name: str, default: str = "") -> str:
    pattern = rf"(?:var|let|const)\s+{re.escape(variable_name)}\s*=\s*(?P<value>\"(?:\\.|[^\"])*\"|'(?:\\.|[^'])*'|[^;\n\r]+)"
    match = re.search(pattern, html)
    if not match:
        return default
    value = match.group("value").strip()
    if value.startswith(("'", '"')) and value.endswith(("'", '"')):
        value = value[1:-1]
    return value.strip()


def parse_int_text(value: str) -> int | None:
    digits = re.sub(r"\D", "", value)
    return int(digits) if digits else None


def selected_sort_method(soup: BeautifulSoup) -> str:
    selected = soup.select_one(".prod_list_opts .order_opt .order_list .selected")
    if selected and selected.get("data-sort-method"):
        return selected["data-sort-method"]
    selected_tab = soup.select_one(".tab_list > li.selected > a")
    if selected_tab and selected_tab.get("data-sort"):
        return selected_tab["data-sort"]
    return "BEST"


def total_count_from_html(html: str) -> int | None:
    soup = BeautifulSoup(html, "html.parser")
    total_count_input = soup.select_one("input#totalProductCount")
    if total_count_input:
        return parse_int_text(total_count_input.get("value", ""))
    return None


def parse_danawa_context(html: str) -> DanawaListContext:
    soup = BeautifulSoup(html, "html.parser")
    global_body = extract_js_object_body(html, "oGlobalSetting")
    expansion_body = extract_js_object_body(html, "oExpansionContent")
    total_count = total_count_from_html(html)

    return DanawaListContext(
        category_code=js_object_value(global_body, "nCategoryCode"),
        list_category_code=js_object_value(global_body, "nListCategoryCode"),
        physics_cate1=js_object_value(global_body, "sPhysicsCate1", "0"),
        physics_cate2=js_object_value(global_body, "sPhysicsCate2", "0"),
        physics_cate3=js_object_value(global_body, "sPhysicsCate3", "0"),
        physics_cate4=js_object_value(global_body, "sPhysicsCate4", "0"),
        group=js_object_value(global_body, "nListGroup", js_object_value(global_body, "nGroup", "0")),
        depth=js_object_value(global_body, "nListDepth", js_object_value(global_body, "nDepth", "0")),
        power_link_keyword=js_object_value(global_body, "sPowerLinkKeyword"),
        current_category_code=js_variable_value(html, "oCurrentCategoryCode"),
        category_mapping_code=js_object_value(global_body, "sCategoryMappingCode"),
        package_type=js_object_value(expansion_body, "nPriceCompareListPackageType", "1"),
        package_limit=js_object_value(expansion_body, "nPriceCompareListPackageLimit", "5"),
        price_unit=js_object_value(expansion_body, "nPriceUnit", "0"),
        price_unit_value=js_object_value(expansion_body, "nPriceUnitValue", "0"),
        price_unit_class=js_object_value(expansion_body, "sPriceUnitClass"),
        cm_recommend_sort=js_object_value(expansion_body, "sCmRecommendSort", "N"),
        cm_recommend_sort_default=js_object_value(expansion_body, "sCmRecommendSortDefault", "N"),
        bundle_image_preview=js_object_value(expansion_body, "sBundleImagePreview", "Y"),
        maker_display_yn=js_object_value(global_body, "bMakerDisplayYN", "Y"),
        discount_product_rate=js_object_value(expansion_body, "sDiscountProductRate", "0"),
        initial_price_display=js_object_value(expansion_body, "sInitialPriceDisplay", "N"),
        dpg_zone_category=js_object_value(global_body, "bDpgZoneCategory", "N"),
        assembly_gallery_category=js_object_value(global_body, "bAssemblyGalleryCategory", "N"),
        quick_delivery_category_yn=js_object_value(global_body, "sQuickDeliveryCategoryYN", "N"),
        quick_delivery_display=js_object_value(global_body, "sQuickDeliveryDisplay"),
        price_unit_sort=js_object_value(global_body, "sPriceUnitSort", "N"),
        price_unit_sort_order=js_object_value(global_body, "sPriceUnitSortOrder", "A"),
        simple_description_display_yn=js_object_value(global_body, "sSimpleDescriptionDisplayYN", "Y"),
        simple_description_open=js_variable_value(html, "simpleDescriptionOpen", "Y"),
        mall_min_price_display_yn=js_object_value(global_body, "sMallMinPriceDisplayYN"),
        product_list_api=js_variable_value(html, "sProductListApi", "search"),
        dnw_switch_yn=js_variable_value(html, "sDnwSwitchYN"),
        add_delivery=js_variable_value(html, "isAddDelivery", "N"),
        coupang_member_sort=js_variable_value(html, "coupangMemberSort"),
        coupang_member_sort_layer_type=js_variable_value(html, "coupangMemberSortLayerType"),
        sort_method=selected_sort_method(soup),
        total_count=total_count,
    )


def ajax_payload(context: DanawaListContext, page: int, list_count: int) -> dict[str, str | int]:
    return {
        "page": page,
        "listCategoryCode": context.list_category_code,
        "categoryCode": context.category_code,
        "physicsCate1": context.physics_cate1,
        "physicsCate2": context.physics_cate2,
        "physicsCate3": context.physics_cate3,
        "physicsCate4": context.physics_cate4,
        "viewMethod": "LIST",
        "sortMethod": context.sort_method,
        "listCount": list_count,
        "group": context.group,
        "depth": context.depth,
        "brandName": "",
        "makerName": "",
        "searchOptionName": "",
        "sDiscountProductRate": context.discount_product_rate,
        "sInitialPriceDisplay": context.initial_price_display,
        "sPowerLinkKeyword": context.power_link_keyword,
        "oCurrentCategoryCode": context.current_category_code,
        "sMallMinPriceDisplayYN": context.mall_min_price_display_yn,
        "quickDeliveryCategoryYN": context.quick_delivery_category_yn,
        "quickDeliveryDisplay": context.quick_delivery_display,
        "priceUnitSort": context.price_unit_sort,
        "priceUnitSortOrder": context.price_unit_sort_order,
        "simpleDescriptionDisplayYN": context.simple_description_display_yn,
        "simpleDescriptionOpen": context.simple_description_open,
        "sProductListApi": context.product_list_api,
        "listPackageType": context.package_type,
        "categoryMappingCode": context.category_mapping_code,
        "priceUnit": context.price_unit,
        "priceUnitValue": context.price_unit_value,
        "priceUnitClass": context.price_unit_class,
        "cmRecommendSort": context.cm_recommend_sort,
        "cmRecommendSortDefault": context.cm_recommend_sort_default,
        "bundleImagePreview": context.bundle_image_preview,
        "nPackageLimit": context.package_limit,
        "bMakerDisplayYN": context.maker_display_yn,
        "dnwSwitchOn": context.dnw_switch_yn,
        "isDpgZoneUICategory": context.dpg_zone_category,
        "isAssemblyGalleryCategory": context.assembly_gallery_category,
        "addDelivery": context.add_delivery,
        "coupangMemberSort": context.coupang_member_sort,
        "coupangMemberSortLayerType": context.coupang_member_sort_layer_type,
    }


def fetch_ajax_product_list(
    session: requests.Session,
    context: DanawaListContext,
    page: int,
    list_count: int,
    referer: str,
    timeout: int,
    price_min: int | None = None,
    price_max: int | None = None,
    sort_method: str | None = None,
) -> str:
    payload = ajax_payload(context, page, list_count)
    if sort_method:
        payload["sortMethod"] = sort_method
    if price_min is not None:
        payload["priceRangeMinPrice"] = price_min
    if price_max is not None:
        payload["priceRangeMaxPrice"] = price_max

    response = session.post(
        f"{BASE_URL}/list/ajax/getProductList.ajax.php",
        data=payload,
        headers={
            "Referer": referer,
            "X-Requested-With": "XMLHttpRequest",
        },
        timeout=timeout,
    )
    response.raise_for_status()
    if not response.encoding:
        response.encoding = response.apparent_encoding
    return response.text


def product_code_from_node(node) -> str | None:
    node_id = node.get("id", "")
    if node_id.startswith("productItem"):
        code = re.sub(r"\D", "", node_id[len("productItem") :])
        if code:
            return code

    for attr in ("data-pcode", "data-product-code", "data-prod-code"):
        value = node.get(attr)
        if value and str(value).isdigit():
            return str(value)

    for link in node.select("a[href*='pcode=']"):
        href = link.get("href", "")
        values = parse_qs(urlparse(href).query).get("pcode")
        if values and values[0].isdigit():
            return values[0]
    return None


def product_url_from_node(node, product_code: str) -> str:
    for link in node.select("a[href*='pcode=']"):
        href = link.get("href")
        if href:
            return urljoin(BASE_URL, href)
    return f"{BASE_URL}/info/?pcode={product_code}"


def product_name_from_node(node) -> str | None:
    selectors = [
        ".prod_name a",
        "p.prod_name a",
        ".prod_info a[href*='pcode=']",
        "a[href*='pcode=']",
    ]
    ignored = {"이미지보기", "가격정보 더보기", "최저가 구매하기", "자세히보기"}
    for selector in selectors:
        for element in node.select(selector):
            text = normalize_space(element.get_text(" ", strip=True))
            if text and text not in ignored and "가격정보" not in text:
                return text

    image = node.select_one("img[alt]")
    if image:
        text = normalize_space(image.get("alt", ""))
        if text:
            return text
    return None


def parse_price_value(text: str) -> int | None:
    cleaned = re.sub(r"[^\d,]", "", text)
    if not cleaned:
        return None
    value = int(cleaned.replace(",", ""))
    return value if value > 100 else None


def price_candidates_from_node(node) -> list[tuple[int, str]]:
    selectors = [
        ".price_sect strong",
        "p.price_sect strong",
        ".prod_pricelist .price_sect strong",
        ".prod_pricelist strong",
        ".lowest_price strong",
        ".price_info strong",
        ".prod_price strong",
    ]
    candidates: list[tuple[int, str]] = []
    seen: set[tuple[int, str]] = set()

    for selector in selectors:
        for element in node.select(selector):
            text = normalize_space(element.get_text(" ", strip=True))
            value = parse_price_value(text)
            if value is None:
                continue
            price_text = f"{value:,}원"
            key = (value, price_text)
            if key not in seen:
                candidates.append(key)
                seen.add(key)

    if candidates:
        return candidates

    product_text = normalize_space(node.get_text(" ", strip=True))
    for match in re.finditer(r"(\d{1,3}(?:,\d{3})+|\d{4,})\s*원", product_text):
        value = parse_price_value(match.group(1))
        if value is None:
            continue
        price_text = f"{value:,}원"
        key = (value, price_text)
        if key not in seen:
            candidates.append(key)
            seen.add(key)
    return candidates


def extract_price(node) -> tuple[int | None, str]:
    candidates = price_candidates_from_node(node)
    if not candidates:
        product_text = normalize_space(node.get_text(" ", strip=True))
        if any(token in product_text for token in ("가격비교예정", "일시품절", "판매중지")):
            return None, "가격없음"
        return None, ""
    return min(candidates, key=lambda item: item[0])


def parse_products(html: str, category: Category, collected_at: str) -> list[Product]:
    soup = BeautifulSoup(html, "html.parser")
    nodes = soup.select("li[id^='productItem']")
    products: dict[str, Product] = {}

    for node in nodes:
        classes = set(node.get("class", []))
        node_id = node.get("id", "")
        if "prod_ad_item" in classes or node_id.startswith("ad"):
            continue

        product_code = product_code_from_node(node)
        product_name = product_name_from_node(node)
        if not product_code or not product_name:
            continue

        price, price_text = extract_price(node)
        product = Product(
            category=category.slug,
            product_code=product_code,
            product_name=product_name,
            price=price,
            price_text=price_text,
            product_url=product_url_from_node(node, product_code),
            collected_at=collected_at,
        )

        existing = products.get(product_code)
        if existing is None:
            products[product_code] = product
        elif product.price is not None and (existing.price is None or product.price < existing.price):
            products[product_code] = product

    return list(products.values())


def move_page_numbers(html: str) -> list[int]:
    numbers = {int(value) for value in re.findall(r"movePage\((\d+)\)", html)}
    return sorted(numbers)


def has_next_page(html: str, current_page: int) -> bool:
    return any(page > current_page for page in move_page_numbers(html))


def make_session() -> requests.Session:
    session = requests.Session()
    retry_adapter = make_retry_adapter()
    session.mount("https://", retry_adapter)
    session.mount("http://", retry_adapter)
    session.headers.update(
        {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": "https://www.danawa.com/",
        }
    )
    return session


def first_price_for_sort(
    session: requests.Session,
    context: DanawaListContext,
    category: Category,
    referer_url: str,
    sort_method: str,
    timeout: int,
) -> int | None:
    html = fetch_ajax_product_list(
        session=session,
        context=context,
        page=1,
        list_count=30,
        referer=referer_url,
        timeout=timeout,
        sort_method=sort_method,
    )
    products = parse_products(html, category, datetime.now().astimezone().isoformat(timespec="seconds"))
    for product in products:
        if product.price is not None:
            return product.price
    return None


def merge_products(target: dict[str, Product], products: Iterable[Product]) -> int:
    before = len(target)
    for product in products:
        existing = target.get(product.product_code)
        if existing is None:
            target[product.product_code] = product
        elif product.price is not None and (existing.price is None or product.price < existing.price):
            target[product.product_code] = product
    return len(target) - before


def crawl_price_segment(
    category: Category,
    session: requests.Session,
    context: DanawaListContext,
    price_range: PriceRange,
    collected_at: str,
    referer_url: str,
    list_count: int,
    max_pages: int,
    delay: float,
    timeout: int,
) -> SegmentResult:
    segment_products: dict[str, Product] = {}
    page = 1
    total_count: int | None = None
    stopped_on_duplicate = False

    while page <= max_pages:
        html = fetch_ajax_product_list(
            session=session,
            context=context,
            page=page,
            list_count=list_count,
            referer=referer_url,
            timeout=timeout,
            price_min=price_range.min_price,
            price_max=price_range.max_price,
            sort_method="MinPrice",
        )
        if total_count is None:
            total_count = total_count_from_html(html)

        products = parse_products(html, category, collected_at)
        new_count = merge_products(segment_products, products)
        print(
            f"[{category.slug}] price {price_range.label()} page {page}: "
            f"{len(products)} products, {new_count} new, {len(segment_products)} segment total"
        )

        if not products:
            break
        if page > 1 and new_count == 0:
            stopped_on_duplicate = True
            break
        if not has_next_page(html, page):
            break

        page += 1
        if delay > 0:
            time.sleep(delay)

    return SegmentResult(
        products=sorted(segment_products.values(), key=lambda product: product.product_name),
        total_count=total_count,
        pages=page,
        stopped_on_duplicate=stopped_on_duplicate,
    )


def count_price_range(
    session: requests.Session,
    context: DanawaListContext,
    price_range: PriceRange,
    referer_url: str,
    timeout: int,
) -> int | None:
    html = fetch_ajax_product_list(
        session=session,
        context=context,
        page=1,
        list_count=30,
        referer=referer_url,
        timeout=timeout,
        price_min=price_range.min_price,
        price_max=price_range.max_price,
        sort_method="MinPrice",
    )
    return total_count_from_html(html)


def split_price_range(price_range: PriceRange, products: list[Product]) -> tuple[PriceRange, PriceRange] | None:
    prices = [product.price for product in products if product.price is not None]
    if not prices or price_range.min_price >= price_range.max_price:
        return None

    split_at = max(prices)
    if split_at >= price_range.max_price:
        split_at = (price_range.min_price + price_range.max_price) // 2
    if split_at < price_range.min_price or split_at >= price_range.max_price:
        return None

    return (
        PriceRange(price_range.min_price, split_at),
        PriceRange(split_at + 1, price_range.max_price),
    )


def crawl_category_by_price(
    category: Category,
    session: requests.Session,
    collected_at: str,
    list_count: int,
    max_pages: int,
    delay: float,
    timeout: int,
) -> list[Product]:
    referer_url = category_page_url(category, 1, list_count)
    initial_html = fetch_with_requests(session, referer_url, timeout)
    context = parse_danawa_context(initial_html)
    if context.total_count:
        print(f"[{category.slug}] Danawa reports {context.total_count:,} products before price splitting")

    min_price = first_price_for_sort(session, context, category, referer_url, "MinPrice", timeout)
    max_price = first_price_for_sort(session, context, category, referer_url, "MaxPrice", timeout)
    if min_price is None or max_price is None:
        raise CrawlerError(f"Could not determine price bounds for {category.name}")
    if min_price > max_price:
        min_price, max_price = max_price, min_price

    print(f"[{category.slug}] price bounds: {min_price:,} - {max_price:,}")
    pending: list[PriceRange] = [PriceRange(min_price, max_price)]
    completed: set[PriceRange] = set()
    category_products: dict[str, Product] = {}

    while pending:
        price_range = pending.pop(0)
        if price_range in completed:
            continue
        completed.add(price_range)

        result = crawl_price_segment(
            category=category,
            session=session,
            context=context,
            price_range=price_range,
            collected_at=collected_at,
            referer_url=referer_url,
            list_count=list_count,
            max_pages=max_pages,
            delay=delay,
            timeout=timeout,
        )
        merge_products(category_products, result.products)

        expected = result.total_count
        collected = len(result.products)
        if expected is not None and collected < expected:
            split = split_price_range(price_range, result.products)
            if split is None:
                print(
                    f"[{category.slug}] warning: price {price_range.label()} returned "
                    f"{collected:,}/{expected:,} products but cannot be split further"
                )
                continue
            left, right = split
            print(
                f"[{category.slug}] splitting price {price_range.label()} "
                f"because collected {collected:,}/{expected:,}: "
                f"{left.label()} and {right.label()}"
            )
            left_expected = count_price_range(session, context, left, referer_url, timeout)
            left_collected = len(
                {
                    product.product_code
                    for product in result.products
                    if product.price is not None and left.min_price <= product.price <= left.max_price
                }
            )
            if left_expected is None or left_collected < left_expected:
                pending.insert(0, left)
            else:
                print(
                    f"[{category.slug}] price {left.label()} already covered "
                    f"({left_collected:,}/{left_expected:,})"
                )
            pending.insert(0, right)

    print(f"[{category.slug}] collected {len(category_products):,} unique products after price splitting")
    return sorted(category_products.values(), key=lambda product: product.product_name)


def crawl_category(
    category: Category,
    session: requests.Session,
    collected_at: str,
    fetcher: str,
    list_count: int,
    max_pages: int,
    delay: float,
    timeout: int,
    selenium_fetcher: SeleniumFetcher | None,
) -> list[Product]:
    if category.pages is None:
        if fetcher not in {"auto", "requests"}:
            raise CrawlerError("Full category crawling uses Danawa Ajax and requires --fetcher auto or requests")
        return crawl_category_by_price(
            category=category,
            session=session,
            collected_at=collected_at,
            list_count=list_count,
            max_pages=max_pages,
            delay=delay,
            timeout=timeout,
        )

    category_products: dict[str, Product] = {}
    page = 1
    context: DanawaListContext | None = None
    expected_pages: int | None = None
    referer_url = category_page_url(category, 1, list_count)

    while True:
        if category.pages is not None and page > category.pages:
            break
        if category.pages is None and page > max_pages:
            raise CrawlerError(
                f"{category.name} reached --max-pages={max_pages}. "
                "Increase the limit if Danawa has more pages."
            )

        source_url = category_page_url(category, page, list_count)
        print(f"[{category.slug}] page {page}: {source_url}")

        products: list[Product] = []
        html = ""
        request_error: Exception | None = None

        if fetcher in {"auto", "requests"}:
            try:
                if page == 1 or context is None:
                    initial_html = fetch_with_requests(session, source_url, timeout)
                    context = parse_danawa_context(initial_html)
                    if context.total_count:
                        expected_pages = max(1, math.ceil(context.total_count / list_count))
                        print(
                            f"[{category.slug}] Danawa reports "
                            f"{context.total_count:,} products across about {expected_pages} pages"
                        )
                    html = fetch_ajax_product_list(
                        session=session,
                        context=context,
                        page=page,
                        list_count=list_count,
                        referer=referer_url,
                        timeout=timeout,
                    )
                else:
                    html = fetch_ajax_product_list(
                        session=session,
                        context=context,
                        page=page,
                        list_count=list_count,
                        referer=referer_url,
                        timeout=timeout,
                    )
                products = parse_products(html, category, collected_at)
            except Exception as exc:  # noqa: BLE001
                request_error = exc
                if fetcher == "requests":
                    raise

        if fetcher == "selenium" or (fetcher == "auto" and not products):
            if selenium_fetcher is None:
                raise CrawlerError("Selenium fetcher is not available")
            if request_error is not None:
                print(f"[{category.slug}] requests failed, falling back to Selenium: {request_error}")
            elif fetcher == "auto":
                print(f"[{category.slug}] no products parsed from requests, falling back to Selenium")
            html = selenium_fetcher.get(source_url)
            products = parse_products(html, category, collected_at)

        previous_count = len(category_products)
        for product in products:
            existing = category_products.get(product.product_code)
            if existing is None:
                category_products[product.product_code] = product
            elif product.price is not None and (existing.price is None or product.price < existing.price):
                category_products[product.product_code] = product

        new_count = len(category_products) - previous_count
        print(
            f"[{category.slug}] page {page}: "
            f"{len(products)} products, {new_count} new, {len(category_products)} total"
        )

        if not products:
            print(f"[{category.slug}] stopping: no products on page {page}")
            break

        if category.pages is not None:
            if page >= category.pages:
                break
        elif not has_next_page(html, page):
            print(f"[{category.slug}] stopping: no next page after page {page}")
            break

        if page > 1 and new_count == 0:
            raise CrawlerError(
                f"{category.name} page {page} returned no new product codes while Danawa still advertised a next page. "
                "Stopping to avoid silently looping over duplicated pages."
            )

        page += 1
        if delay > 0:
            time.sleep(delay)

    return sorted(category_products.values(), key=lambda product: product.product_name)


def ensure_output_dirs(output_dir: Path) -> tuple[Path, Path]:
    latest_dir = output_dir / "latest"
    history_dir = output_dir / "history"
    latest_dir.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    return latest_dir, history_dir


def write_csv(path: Path, fields: list[str], rows: Iterable[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def price_value(product: Product) -> str:
    return "" if product.price is None else str(product.price)


def read_existing_price_csv(path: Path) -> tuple[list[str], dict[str, dict[str, str]]]:
    if not path.exists():
        return [], {}

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None:
            return [], {}

        date_fields = [field for field in reader.fieldnames if PRICE_DATE_FIELD.match(field)]
        rows_by_code = {
            row.get("product_code", ""): {field: row.get(field, "") for field in date_fields}
            for row in reader
            if row.get("product_code")
        }
        return date_fields, rows_by_code


def recent_date_fields(collected_date: str, history_days: int) -> list[str]:
    end_date = date.fromisoformat(collected_date)
    return [(end_date - timedelta(days=offset)).isoformat() for offset in range(history_days)]


def write_price_csv(path: Path, products: list[Product], collected_date: str, history_days: int) -> None:
    _, existing_rows = read_existing_price_csv(path)
    date_fields = recent_date_fields(collected_date, history_days)

    rows: list[dict[str, str]] = []
    for product in products:
        previous_prices = existing_rows.get(product.product_code, {})
        row = {
            "product_code": product.product_code,
            "product_name": product.product_name,
        }
        for date_field in date_fields:
            row[date_field] = previous_prices.get(date_field, "")
        row[collected_date] = price_value(product)
        rows.append(row)

    write_csv(path, [*PRICE_BASE_FIELDS, *date_fields], rows)


def write_latest(
    output_dir: Path,
    products_by_category: dict[str, list[Product]],
    collected_date: str,
    history_days: int = DEFAULT_PRICE_HISTORY_DAYS,
    write_combined: bool = True,
) -> None:
    latest_dir, _ = ensure_output_dirs(output_dir)
    all_products: list[Product] = []
    for slug, products in products_by_category.items():
        all_products.extend(products)
        write_price_csv(latest_dir / f"{slug}.csv", products, collected_date, history_days)

    if not write_combined:
        return

    all_products.sort(key=lambda product: (product.category, product.product_name))
    write_price_csv(latest_dir / "danawa_products.csv", all_products, collected_date, history_days)


def write_history(
    output_dir: Path,
    products_by_category: dict[str, list[Product]],
    collected_date: str,
    history_file_days: int = DEFAULT_HISTORY_FILE_DAYS,
) -> None:
    _, history_dir = ensure_output_dirs(output_dir)
    for slug, products in products_by_category.items():
        write_price_csv(history_dir / f"{slug}_price_history.csv", products, collected_date, history_file_days)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect Danawa product codes, names, and prices.")
    parser.add_argument("--config", default="config/categories.csv", help="Category CSV path.")
    parser.add_argument("--output", default="data", help="Output directory.")
    parser.add_argument(
        "--category",
        action="append",
        dest="categories",
        help="Category slug to crawl. Can be passed multiple times.",
    )
    parser.add_argument(
        "--pages",
        type=int,
        help="Limit page count for all selected categories. By default, categories crawl until the last page.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=500,
        help="Safety limit used only when crawling until the last page.",
    )
    parser.add_argument("--list-count", type=int, default=90, help="Danawa list count per page.")
    parser.add_argument(
        "--fetcher",
        choices=["auto", "requests", "selenium"],
        default="auto",
        help="Fetch method. auto tries requests first and uses Selenium as a fallback.",
    )
    parser.add_argument("--delay", type=float, default=0.05, help="Delay between category pages.")
    parser.add_argument("--timeout", type=int, default=20, help="HTTP and browser wait timeout in seconds.")
    parser.add_argument(
        "--fail-on-empty",
        action="store_true",
        help="Exit without writing CSV files if any selected category returns zero products.",
    )
    parser.add_argument(
        "--history-days",
        type=int,
        default=DEFAULT_PRICE_HISTORY_DAYS,
        help="Number of daily price columns to keep in each CSV.",
    )
    parser.add_argument(
        "--history-file-days",
        type=int,
        default=DEFAULT_HISTORY_FILE_DAYS,
        help="Number of daily price columns to keep in data/history CSV files.",
    )
    parser.add_argument(
        "--skip-combined",
        action="store_true",
        help="Skip data/latest/danawa_products.csv update.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    config_path = Path(args.config)
    output_dir = Path(args.output)
    categories = load_categories(config_path)

    if args.categories:
        selected = set(args.categories)
        categories = [category for category in categories if category.slug in selected]
        missing = selected - {category.slug for category in categories}
        if missing:
            raise CrawlerError(f"Unknown categories: {', '.join(sorted(missing))}")

    if args.pages is not None:
        categories = [
            Category(slug=category.slug, name=category.name, url=category.url, pages=max(1, args.pages))
            for category in categories
        ]
    if args.max_pages < 1:
        raise CrawlerError("--max-pages must be at least 1")
    if args.history_days < 1:
        raise CrawlerError("--history-days must be at least 1")
    if args.history_file_days < 1:
        raise CrawlerError("--history-file-days must be at least 1")

    collected_at = datetime.now().astimezone().isoformat(timespec="seconds")
    collected_date = collected_at[:10]
    session = make_session()
    selenium_fetcher = SeleniumFetcher(timeout=args.timeout) if args.fetcher in {"auto", "selenium"} else None
    products_by_category: dict[str, list[Product]] = {}

    try:
        for index, category in enumerate(categories):
            products_by_category[category.slug] = crawl_category(
                category=category,
                session=session,
                collected_at=collected_at,
                fetcher=args.fetcher,
                list_count=args.list_count,
                max_pages=args.max_pages,
                delay=args.delay,
                timeout=args.timeout,
                selenium_fetcher=selenium_fetcher,
            )
            if args.delay > 0 and index < len(categories) - 1:
                time.sleep(args.delay)
    finally:
        if selenium_fetcher is not None:
            selenium_fetcher.close()

    empty_categories = [category.name for category in categories if not products_by_category.get(category.slug)]
    if args.fail_on_empty and empty_categories:
        print(f"No products collected for: {', '.join(empty_categories)}", file=sys.stderr)
        return 2

    write_latest(output_dir, products_by_category, collected_date, args.history_days, not args.skip_combined)
    write_history(output_dir, products_by_category, collected_date, args.history_file_days)

    total = sum(len(products) for products in products_by_category.values())
    print(f"Saved {total} products to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
