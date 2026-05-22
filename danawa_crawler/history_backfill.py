from __future__ import annotations

import argparse
import csv
import re
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from urllib.request import urlopen

from danawa_crawler.core import PRICE_DATE_FIELD, write_csv


SAMMY_MONITOR_URL = "https://raw.githubusercontent.com/sammy310/Danawa-Crawler/master/crawl_data/Monitor.csv"
LEGACY_DATE_FIELD = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:\s|$)")


@dataclass(frozen=True)
class BackfillResult:
    path: Path
    rows: int
    date_fields: int
    filled_from_legacy: int
    filled_with_zero: int


def price_text(value: str | None) -> str:
    cleaned = (value or "").strip().replace(",", "")
    return cleaned or "0"


def read_sammy_monitor_prices(csv_text: str) -> dict[str, dict[str, str]]:
    reader = csv.DictReader(StringIO(csv_text.lstrip("\ufeff")))
    date_columns = {
        field: match.group(1)
        for field in (reader.fieldnames or [])
        if (match := LEGACY_DATE_FIELD.match(field))
    }

    prices: dict[str, dict[str, str]] = {}
    for row in reader:
        product_code = (row.get("Id") or "").strip()
        if not product_code:
            continue
        prices[product_code] = {
            date_field: price_text(row.get(source_field))
            for source_field, date_field in date_columns.items()
        }
    return prices


def load_source_text(source: str) -> str:
    if source.startswith(("https://", "http://")):
        with urlopen(source, timeout=30) as response:  # noqa: S310
            return response.read().decode("utf-8-sig")
    return Path(source).read_text(encoding="utf-8-sig")


def backfill_price_csv(path: Path, legacy_prices: dict[str, dict[str, str]]) -> BackfillResult:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    date_fields = [field for field in fieldnames if PRICE_DATE_FIELD.match(field)]
    filled_from_legacy = 0
    filled_with_zero = 0

    for row in rows:
        legacy_row = legacy_prices.get(row.get("product_code", ""), {})
        for date_field in date_fields:
            if row.get(date_field):
                continue
            if date_field in legacy_row:
                row[date_field] = legacy_row[date_field]
                filled_from_legacy += 1
            else:
                row[date_field] = "0"
                filled_with_zero += 1

    write_csv(path, fieldnames, rows)
    return BackfillResult(path, len(rows), len(date_fields), filled_from_legacy, filled_with_zero)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backfill monitor price dates from sammy310/Danawa-Crawler.")
    parser.add_argument("--source", default=SAMMY_MONITOR_URL, help="Legacy Monitor.csv path or raw URL.")
    parser.add_argument("--latest", default="data/latest/monitor.csv", help="Current monitor latest CSV path.")
    parser.add_argument(
        "--history",
        default="data/history/monitor_price_history.csv",
        help="Current monitor history CSV path.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    legacy_prices = read_sammy_monitor_prices(load_source_text(args.source))
    for path in [Path(args.latest), Path(args.history)]:
        result = backfill_price_csv(path, legacy_prices)
        print(
            f"{result.path}: {result.rows} rows, {result.date_fields} dates, "
            f"{result.filled_from_legacy} legacy cells, {result.filled_with_zero} zero cells"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
