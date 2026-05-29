from __future__ import annotations

import argparse
import csv
from pathlib import Path

from danawa_crawler.core import PRICE_DATE_FIELD, Product, write_history, write_latest


def parse_price(value: str) -> int | None:
    cleaned = (value or "").strip().replace(",", "")
    if not cleaned:
        return None
    return int(cleaned) if cleaned.isdigit() else None


def read_part(path: Path, category: str) -> tuple[str, list[Product]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        date_fields = [field for field in (reader.fieldnames or []) if PRICE_DATE_FIELD.match(field)]
        if not date_fields:
            return "", []
        collected_date = date_fields[0]
        products: list[Product] = []
        for row in reader:
            product_code = (row.get("product_code") or "").strip()
            product_name = (row.get("product_name") or "").strip()
            if not product_code or not product_name:
                continue
            price = parse_price(row.get(collected_date, ""))
            products.append(
                Product(
                    category=category,
                    product_code=product_code,
                    product_name=product_name,
                    price=price,
                    price_text="" if price is None else f"{price:,}원",
                    product_url="",
                    collected_at=f"{collected_date}T00:00:00+09:00",
                )
            )
        return collected_date, products


def merge_products(parts: list[Product]) -> list[Product]:
    products_by_code: dict[str, Product] = {}
    for product in parts:
        existing = products_by_code.get(product.product_code)
        if existing is None:
            products_by_code[product.product_code] = product
            continue
        if product.price is not None and (existing.price is None or product.price < existing.price):
            products_by_code[product.product_code] = product
    return sorted(products_by_code.values(), key=lambda product: product.product_name)


def merge_price_parts(
    category: str,
    input_dir: Path,
    output_dir: Path,
    history_days: int,
    history_file_days: int,
) -> tuple[str, int]:
    part_paths = sorted(input_dir.glob(f"**/{category}.csv"))
    if not part_paths:
        raise FileNotFoundError(f"No {category}.csv files found under {input_dir}")

    collected_dates: list[str] = []
    all_products: list[Product] = []
    for path in part_paths:
        collected_date, products = read_part(path, category)
        if not collected_date:
            continue
        collected_dates.append(collected_date)
        all_products.extend(products)

    if not collected_dates or not all_products:
        raise ValueError(f"No products found in {len(part_paths)} part files")

    collected_date = max(collected_dates)
    products = merge_products(all_products)
    write_latest(output_dir, {category: products}, collected_date, history_days, write_combined=False)
    write_history(output_dir, {category: products}, collected_date, history_file_days)
    return collected_date, len(products)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Merge split Danawa price CSV parts.")
    parser.add_argument("--category", required=True, help="Category slug to merge.")
    parser.add_argument("--input-dir", required=True, help="Directory containing part CSV artifacts.")
    parser.add_argument("--output", default="data", help="Output data directory.")
    parser.add_argument("--history-days", type=int, default=8, help="Date columns for latest CSV.")
    parser.add_argument("--history-file-days", type=int, default=60, help="Date columns for history CSV.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    collected_date, count = merge_price_parts(
        category=args.category,
        input_dir=Path(args.input_dir),
        output_dir=Path(args.output),
        history_days=args.history_days,
        history_file_days=args.history_file_days,
    )
    print(f"merged {count} {args.category} products for {collected_date}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
