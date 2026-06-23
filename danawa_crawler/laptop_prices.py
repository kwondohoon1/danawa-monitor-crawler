from __future__ import annotations

import argparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import requests

from danawa_crawler.core import (
    BASE_URL,
    Category,
    Product,
    ajax_payload,
    category_page_url,
    fetch_with_requests,
    has_next_page,
    make_session,
    merge_products,
    now_kst_iso,
    parse_danawa_context,
    parse_products,
    write_history,
    write_latest,
)


LAPTOP_CATEGORY = Category(
    slug="laptop",
    name="노트북",
    url="https://prod.danawa.com/list/?cate=112758",
)


@dataclass(frozen=True)
class LaptopMaker:
    label: str
    maker_name: str


LAPTOP_MAKERS = [
    LaptopMaker("ACER", "에이서"),
    LaptopMaker("ASUS", "ASUS"),
    LaptopMaker("DELL", "DELL"),
    LaptopMaker("GIGABYTE", "GIGABYTE"),
    LaptopMaker("MSI", "MSI"),
    LaptopMaker("LENOVO", "레노버"),
    LaptopMaker("HP", "HP"),
    LaptopMaker("삼성", "삼성전자"),
    LaptopMaker("LG", "LG전자"),
]


def fetch_laptop_maker_page(
    session: requests.Session,
    context,
    referer_url: str,
    maker_name: str,
    page: int,
    list_count: int,
    timeout: int,
) -> str:
    payload = ajax_payload(context, page, list_count)
    payload["makerName"] = maker_name
    response = session.post(
        f"{BASE_URL}/list/ajax/getProductList.ajax.php",
        data=payload,
        headers={
            "Referer": referer_url,
            "X-Requested-With": "XMLHttpRequest",
        },
        timeout=timeout,
    )
    response.raise_for_status()
    if not response.encoding or response.encoding.lower() == "iso-8859-1":
        response.encoding = response.apparent_encoding
    return response.text


def crawl_laptop_maker(
    session: requests.Session,
    context,
    referer_url: str,
    maker: LaptopMaker,
    collected_at: str,
    list_count: int,
    max_pages: int,
    delay: float,
    timeout: int,
) -> list[Product]:
    products_by_code: dict[str, Product] = {}

    for page in range(1, max_pages + 1):
        html = fetch_laptop_maker_page(
            session=session,
            context=context,
            referer_url=referer_url,
            maker_name=maker.maker_name,
            page=page,
            list_count=list_count,
            timeout=timeout,
        )
        products = parse_products(html, LAPTOP_CATEGORY, collected_at)
        new_count = merge_products(products_by_code, products)
        print(
            f"[laptop] {maker.label} page {page}: "
            f"{len(products)} products, {new_count} new, {len(products_by_code)} maker total"
        )

        if not products:
            break
        if page > 1 and new_count == 0:
            print(f"[laptop] {maker.label} stopping: duplicated page {page}")
            break
        if delay > 0:
            time.sleep(delay)

    return sorted(products_by_code.values(), key=lambda product: product.product_name)


def crawl_laptop_maker_parallel(
    context,
    referer_url: str,
    maker: LaptopMaker,
    collected_at: str,
    list_count: int,
    max_pages: int,
    timeout: int,
    workers: int,
) -> list[Product]:
    products_by_code: dict[str, Product] = {}

    def fetch_page(page: int) -> tuple[int, list[Product], bool]:
        session = make_session()
        html = fetch_laptop_maker_page(
            session=session,
            context=context,
            referer_url=referer_url,
            maker_name=maker.maker_name,
            page=page,
            list_count=list_count,
            timeout=timeout,
        )
        return page, parse_products(html, LAPTOP_CATEGORY, collected_at), has_next_page(html, page)

    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {executor.submit(fetch_page, page): page for page in range(1, max_pages + 1)}
        for future in as_completed(futures):
            page, products, has_next = future.result()
            new_count = merge_products(products_by_code, products)
            print(
                f"[laptop] {maker.label} page {page}: "
                f"{len(products)} products, {new_count} new, {len(products_by_code)} maker total"
            )
            if not has_next and page < max_pages:
                print(f"[laptop] {maker.label} page {page}: no next page advertised")

    return sorted(products_by_code.values(), key=lambda product: product.product_name)


def crawl_laptop_prices(
    output_dir: Path,
    history_days: int,
    history_file_days: int,
    list_count: int,
    max_pages_per_maker: int,
    delay: float,
    timeout: int,
    workers: int,
) -> int:
    collected_at = now_kst_iso()
    collected_date = collected_at[:10]
    session = make_session()
    referer_url = category_page_url(LAPTOP_CATEGORY, 1, list_count)
    context = parse_danawa_context(fetch_with_requests(session, referer_url, timeout))

    products_by_code: dict[str, Product] = {}

    def fetch_maker_page(maker: LaptopMaker, page: int) -> tuple[LaptopMaker, int, list[Product], bool]:
        page_session = make_session()
        html = fetch_laptop_maker_page(
            session=page_session,
            context=context,
            referer_url=referer_url,
            maker_name=maker.maker_name,
            page=page,
            list_count=list_count,
            timeout=timeout,
        )
        return maker, page, parse_products(html, LAPTOP_CATEGORY, collected_at), has_next_page(html, page)

    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {
            executor.submit(fetch_maker_page, maker, page): (maker, page)
            for maker in LAPTOP_MAKERS
            for page in range(1, max_pages_per_maker + 1)
        }
        for future in as_completed(futures):
            maker, page, products, next_page = future.result()
            added = merge_products(products_by_code, products)
            print(
                f"[laptop] {maker.label} page {page}: "
                f"{len(products)} products, {added} new, {len(products_by_code)} total"
            )
            if not next_page and page < max_pages_per_maker:
                print(f"[laptop] {maker.label} page {page}: no next page advertised")
            if delay > 0:
                time.sleep(delay)

    products = sorted(products_by_code.values(), key=lambda product: product.product_name)
    write_latest(output_dir, {"laptop": products}, collected_date, history_days, write_combined=False)
    write_history(output_dir, {"laptop": products}, collected_date, history_file_days)
    return len(products)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect laptop prices for selected Danawa makers.")
    parser.add_argument("--output", default="data", help="Output data directory.")
    parser.add_argument("--history-days", type=int, default=8, help="Date columns for latest CSV.")
    parser.add_argument("--history-file-days", type=int, default=60, help="Date columns for history CSV.")
    parser.add_argument("--list-count", type=int, default=90, help="Danawa list count per page.")
    parser.add_argument("--max-pages-per-maker", type=int, default=2, help="Safety page limit per maker.")
    parser.add_argument("--workers", type=int, default=24, help="Parallel maker page fetches.")
    parser.add_argument("--delay", type=float, default=0.05, help="Delay between maker pages.")
    parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout in seconds.")
    parser.add_argument("--fail-on-empty", action="store_true", help="Exit with error if no laptop products are saved.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    total = crawl_laptop_prices(
        output_dir=Path(args.output),
        history_days=args.history_days,
        history_file_days=args.history_file_days,
        list_count=args.list_count,
        max_pages_per_maker=args.max_pages_per_maker,
        delay=args.delay,
        timeout=args.timeout,
        workers=args.workers,
    )
    print(f"Saved {total} laptop products to {args.output}")
    if args.fail_on_empty and total == 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
