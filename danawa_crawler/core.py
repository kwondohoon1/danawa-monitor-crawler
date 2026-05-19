from __future__ import annotations

import argparse
import csv
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, parse_qsl, urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://prod.danawa.com"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)

LATEST_FIELDS = [
    "collected_at",
    "category",
    "category_name",
    "product_code",
    "product_name",
    "price",
    "price_text",
    "product_url",
    "source_url",
]

HISTORY_FIELDS = [
    "collected_date",
    "collected_at",
    "category",
    "category_name",
    "product_code",
    "product_name",
    "price",
    "price_text",
    "product_url",
]


@dataclass(frozen=True)
class Category:
    slug: str
    name: str
    url: str
    pages: int = 1


@dataclass(frozen=True)
class Product:
    category: str
    category_name: str
    product_code: str
    product_name: str
    price: int | None
    price_text: str
    product_url: str
    source_url: str
    collected_at: str

    def latest_row(self) -> dict[str, str]:
        return {
            "collected_at": self.collected_at,
            "category": self.category,
            "category_name": self.category_name,
            "product_code": self.product_code,
            "product_name": self.product_name,
            "price": "" if self.price is None else str(self.price),
            "price_text": self.price_text,
            "product_url": self.product_url,
            "source_url": self.source_url,
        }

    def history_row(self, collected_date: str) -> dict[str, str]:
        row = self.latest_row()
        row.pop("source_url", None)
        return {"collected_date": collected_date, **row}


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
            pages_text = normalize_space(row.get("pages", "")) or "1"
            if not slug or not name or not url:
                continue
            categories.append(Category(slug=slug, name=name, url=url, pages=max(1, int(pages_text))))
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


def parse_products(html: str, category: Category, source_url: str, collected_at: str) -> list[Product]:
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
            category_name=category.name,
            product_code=product_code,
            product_name=product_name,
            price=price,
            price_text=price_text,
            product_url=product_url_from_node(node, product_code),
            source_url=source_url,
            collected_at=collected_at,
        )

        existing = products.get(product_code)
        if existing is None:
            products[product_code] = product
        elif product.price is not None and (existing.price is None or product.price < existing.price):
            products[product_code] = product

    return list(products.values())


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": "https://www.danawa.com/",
        }
    )
    return session


def crawl_category(
    category: Category,
    session: requests.Session,
    collected_at: str,
    fetcher: str,
    list_count: int,
    delay: float,
    timeout: int,
    selenium_fetcher: SeleniumFetcher | None,
) -> list[Product]:
    category_products: dict[str, Product] = {}

    for page in range(1, category.pages + 1):
        source_url = category_page_url(category, page, list_count)
        print(f"[{category.slug}] page {page}: {source_url}")

        products: list[Product] = []
        request_error: Exception | None = None

        if fetcher in {"auto", "requests"}:
            try:
                html = fetch_with_requests(session, source_url, timeout)
                products = parse_products(html, category, source_url, collected_at)
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
            products = parse_products(html, category, source_url, collected_at)

        print(f"[{category.slug}] page {page}: {len(products)} products")
        for product in products:
            existing = category_products.get(product.product_code)
            if existing is None:
                category_products[product.product_code] = product
            elif product.price is not None and (existing.price is None or product.price < existing.price):
                category_products[product.product_code] = product

        if delay > 0 and page < category.pages:
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


def write_latest(output_dir: Path, products_by_category: dict[str, list[Product]]) -> None:
    latest_dir, _ = ensure_output_dirs(output_dir)
    all_products: list[Product] = []
    for slug, products in products_by_category.items():
        all_products.extend(products)
        rows = [product.latest_row() for product in products]
        write_csv(latest_dir / f"{slug}.csv", LATEST_FIELDS, rows)

    all_products.sort(key=lambda product: (product.category, product.product_name))
    write_csv(latest_dir / "danawa_products.csv", LATEST_FIELDS, [product.latest_row() for product in all_products])


def update_history(output_dir: Path, products_by_category: dict[str, list[Product]], collected_date: str) -> None:
    _, history_dir = ensure_output_dirs(output_dir)
    history_path = history_dir / "danawa_price_history.csv"
    selected_categories = set(products_by_category)
    rows: list[dict[str, str]] = []

    if history_path.exists():
        with history_path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            for row in reader:
                if row.get("collected_date") == collected_date and row.get("category") in selected_categories:
                    continue
                rows.append({field: row.get(field, "") for field in HISTORY_FIELDS})

    for products in products_by_category.values():
        rows.extend(product.history_row(collected_date) for product in products)

    rows.sort(key=lambda row: (row["collected_date"], row["category"], row["product_code"]))
    write_csv(history_path, HISTORY_FIELDS, rows)


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
    parser.add_argument("--pages", type=int, help="Override page count for all selected categories.")
    parser.add_argument("--list-count", type=int, default=90, help="Danawa list count per page.")
    parser.add_argument(
        "--fetcher",
        choices=["auto", "requests", "selenium"],
        default="auto",
        help="Fetch method. auto tries requests first and uses Selenium as a fallback.",
    )
    parser.add_argument("--delay", type=float, default=1.5, help="Delay between category pages.")
    parser.add_argument("--timeout", type=int, default=20, help="HTTP and browser wait timeout in seconds.")
    parser.add_argument(
        "--fail-on-empty",
        action="store_true",
        help="Exit without writing CSV files if any selected category returns zero products.",
    )
    parser.add_argument(
        "--no-history",
        action="store_true",
        help="Skip data/history/danawa_price_history.csv update.",
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

    write_latest(output_dir, products_by_category)
    if not args.no_history:
        update_history(output_dir, products_by_category, collected_date)

    total = sum(len(products) for products in products_by_category.values())
    print(f"Saved {total} products to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

