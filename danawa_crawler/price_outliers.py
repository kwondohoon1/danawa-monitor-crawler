"""Drop one-seller fake low prices from the hourly GPU/RAM/SSD prices.

A list page only shows each product's lowest price. When one seller lists many products far below
every other mall (a scam seller), that fake price becomes the product's "lowest price". For products
whose price suddenly dropped (or that are new), open the product page, read the per-mall price list,
remove prices that sit far below the other malls, and keep the cheapest remaining price instead.

Every change is written to data/hourly/<day>/price_fixes.csv so the fake prices can still be found.
"""

from __future__ import annotations

import csv
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from .core import make_session, write_csv


CATE_CODES = {"gpu": "112753", "ram": "112752", "ssd": "112760"}
DROP_RATIO = 0.85        # 직전 가격보다 15% 넘게 떨어지면 쇼핑몰 목록 확인
OUTLIER_RATIO = 0.85     # 싼 쇼핑몰 5곳 중간값보다 15% 넘게 싸면 '혼자 튀는 가격'으로 제외
MAX_CHECKS = 600         # 카테고리당 한 번에 확인하는 상품 수 상한
WORKERS = 6
FIX_FIELDS = ["hour", "category", "product_code", "product_name", "crawled_price", "fixed_price", "baseline", "removed"]

_LIST = re.compile(r'class="list__mall-price"(.*?)</ul>', re.S)
_ITEM = re.compile(r"<li(.*?)</li>", re.S)
_MALL = re.compile(r"cmpnyc=(\w+)")
_PRICE = re.compile(r'class="text__num">([\d,]+)<')


def parse_mall_prices(html: str) -> list[tuple[int, str]]:
    """(price, mall code) of the '쇼핑몰별 최저가' list, cash-only prices excluded."""
    block = _LIST.search(html)
    if not block:
        return []
    rows = []
    for item in _ITEM.findall(block.group(1)):
        if "badge__cash" in item:
            continue
        mall, price = _MALL.search(item), _PRICE.search(item)
        if mall and price:
            rows.append((int(price.group(1).replace(",", "")), mall.group(1)))
    return sorted(rows)


def clean_lowest(prices: list[tuple[int, str]], baseline: int | None = None) -> tuple[int | None, list[tuple[int, str]]]:
    """Cheapest price after removing prices far below the other malls -> (price, removed).

    A price close to the product's previous price (baseline) is never removed, so a real
    cheap mall that was already the lowest before stays in.
    """
    if not prices:
        return None, []
    if len(prices) == 1:
        return prices[0][0], []
    if len(prices) == 2:
        ref = prices[1][0]
    else:
        head = [price for price, _ in prices[:5]]
        ref = sorted(head)[len(head) // 2]

    def odd(price: int) -> bool:
        return price < ref * OUTLIER_RATIO and not (baseline and price >= baseline * DROP_RATIO)

    kept = [row for row in prices if not odd(row[0])]
    removed = [row for row in prices if odd(row[0])]
    return kept[0][0], removed


def _int(value: str | None) -> int | None:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _baselines(output_dir: Path, day: str, hour: int, category: str, header: list[str], rows: list[list[str]]) -> dict[str, int]:
    """Most recent earlier price per product: today's earlier hour if collected, else an earlier day."""
    base: dict[str, int] = {}
    day_index = header.index(day)
    for row in rows:
        for value in row[day_index + 1:]:
            price = _int(value)
            if price:
                base[row[0]] = price
                break
    for earlier in range(hour - 1, 6, -1):
        path = output_dir / "hourly" / day / f"{category}_{earlier:02d}.csv"
        if path.exists():
            with path.open("r", encoding="utf-8-sig", newline="") as file:
                for snap in csv.DictReader(file):
                    price = _int(snap.get("price"))
                    if price:
                        base[snap["product_code"]] = price
            break
    return base


def _read(path: Path) -> tuple[list[str], list[list[str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.reader(file)
        header = next(reader)
        return header, [row for row in reader]


def _write(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(header)
        writer.writerows(rows)


def _set_today(path: Path, day: str, fixes: dict[str, int]) -> None:
    if not path.exists():
        return
    header, rows = _read(path)
    if day not in header:
        return
    col = header.index(day)
    for row in rows:
        if row and row[0] in fixes and col < len(row):
            row[col] = str(fixes[row[0]])
    _write(path, header, rows)


def default_fetch(category: str) -> Callable[[str], str]:
    session = make_session()

    def fetch(code: str) -> str:
        url = f"https://prod.danawa.com/info/?pcode={code}&cate={CATE_CODES[category]}"
        response = session.get(url, timeout=15)
        response.raise_for_status()
        return response.text

    return fetch


def fix_category(output_dir: Path, day: str, hour: int, category: str, fetch: Callable[[str], str] | None = None) -> list[dict[str, str]]:
    latest = output_dir / "latest" / f"{category}.csv"
    if not latest.exists():
        return []
    header, rows = _read(latest)
    if day not in header:
        return []
    col = header.index(day)
    base = _baselines(output_dir, day, hour, category, header, rows)

    candidates = []
    for row in rows:
        price = _int(row[col]) if col < len(row) else None
        if not price:
            continue
        before = base.get(row[0])
        if before is None or price < before * DROP_RATIO:
            drop = 1.0 if before is None else price / before
            candidates.append((drop, row[0], row[1], price, before))
    candidates.sort()
    candidates = candidates[:MAX_CHECKS]
    if not candidates:
        return []

    fetch = fetch or default_fetch(category)

    def check(item):
        _, code, name, price, before = item
        try:
            mall_prices = parse_mall_prices(fetch(code))
        except Exception as error:  # 페이지를 못 읽으면 그대로 둔다
            print(f"  {category} {code}: mall list failed ({error})", flush=True)
            return None
        clean, removed = clean_lowest(mall_prices, before)
        if not clean or clean <= price:
            return None
        return {"hour": f"{hour:02d}", "category": category, "product_code": code, "product_name": name,
                "crawled_price": str(price), "fixed_price": str(clean), "baseline": "" if before is None else str(before),
                "removed": " ".join(f"{mall}:{value}" for value, mall in removed)}

    started = time.time()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = [result for result in pool.map(check, candidates) if result]
    fixes = {result["product_code"]: int(result["fixed_price"]) for result in results}
    if fixes:
        _set_today(latest, day, fixes)
        _set_today(output_dir / "history" / f"{category}_price_history.csv", day, fixes)
    print(f"{category}: checked {len(candidates)} suspicious prices in {time.time() - started:.0f}s, fixed {len(fixes)}", flush=True)
    return results


def fix_price_outliers(output_dir: Path, day: str, hour: int, categories, fetch_factory=None) -> list[dict[str, str]]:
    """Fix today's prices in data/latest (and history) and log the changes for this hour."""
    results = []
    for category in categories:
        fetch = fetch_factory(category) if fetch_factory else None
        results += fix_category(output_dir, day, hour, category, fetch)

    log = output_dir / "hourly" / day / "price_fixes.csv"
    kept = []
    if log.exists():
        with log.open("r", encoding="utf-8-sig", newline="") as file:
            kept = [row for row in csv.DictReader(file) if not (row["hour"] == f"{hour:02d}" and row["category"] in categories)]
    if results or kept or log.exists():
        write_csv(log, FIX_FIELDS, kept + results)
    return results
