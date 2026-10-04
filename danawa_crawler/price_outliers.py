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
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from .core import make_session, write_csv


CATE_CODES = {"gpu": "112753", "ram": "112752", "ssd": "112760"}
DROP_RATIO = 0.85        # 직전 가격보다 15% 넘게 떨어지면 쇼핑몰 목록 확인
OUTLIER_RATIO = 0.85     # 싼 쇼핑몰 5곳 중간값보다 15% 넘게 싸면 '혼자 튀는 가격'으로 제외
SUSPECT_MIN = 5          # 한 번 수집에서 이만큼 '혼자 튀는 가격'으로 빠진 쇼핑몰은 사기 의심
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


_DIGITS = re.compile(r"(\d{4,5})")


def _norm(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).upper()


def spec_keys(output_dir: Path, category: str) -> dict[str, str]:
    """product_code -> 같은 스펙 묶음 키 (그래픽카드: 칩셋+VRAM, SSD: 폼팩터+인터페이스+용량, RAM: 세대+클럭+용량)."""
    path = output_dir / "specs" / f"{category}_specs.csv"
    if not path.exists():
        return {}
    keys = {}
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            if category == "gpu":
                parts = [row.get("chipset"), row.get("memory_size")]
            elif category == "ssd":
                parts = [row.get("form_factor"), row.get("interface"), row.get("capacity")]
            else:
                speed = _DIGITS.search(row.get("speed") or "")
                parts = [row.get("generation"), speed.group(1) if speed else "", row.get("capacity")]
            if all(_norm(part) for part in parts):
                keys[row["product_code"]] = "|".join(_norm(part) for part in parts)
    return keys


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


def _set_today(path: Path, day: str, fixes: dict[str, str]) -> None:
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
        kept_malls = {mall for value, mall in mall_prices if (value, mall) not in removed}
        return {"code": code, "name": name, "price": price, "before": before, "clean": clean, "removed": removed, "kept": kept_malls}

    started = time.time()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        checked = [result for result in pool.map(check, candidates) if result]

    def log_row(c, fixed: str, removed: str) -> dict[str, str]:
        return {"hour": f"{hour:02d}", "category": category, "product_code": c["code"], "product_name": c["name"],
                "crawled_price": str(c["price"]), "fixed_price": fixed, "baseline": "" if c["before"] is None else str(c["before"]),
                "removed": removed}

    # 1차: 같은 상품 안에서 다른 쇼핑몰보다 혼자 튀는 가격을 빼고 다음 최저가로
    fixes: dict[str, str] = {}
    results = []
    for c in checked:
        if c["clean"] and c["clean"] > c["price"]:
            fixes[c["code"]] = str(c["clean"])
            results.append(log_row(c, str(c["clean"]), " ".join(f"{mall}:{value}" for value, mall in c["removed"])))

    # 2차: 이번에 '혼자 튀는 가격'으로 여러 번 빠진 쇼핑몰(사기 의심)에서만 파는 상품은 비교할 다른 쇼핑몰이 없다.
    # 이전 가격이 없는(새로 나타난) 상품이면 뺀다 — 사기 업체가 직접 올린 상품의 전형.
    # 이전 가격이 있으면 같은 스펙 상품 중간값보다 15% 넘게 쌀 때만 뺀다.
    counts = Counter(mall for c in checked for _, mall in c["removed"])
    suspects = {mall for mall, n in counts.items() if n >= SUSPECT_MIN}
    if suspects:
        keys = spec_keys(output_dir, category)
        today = {row[0]: _int(fixes.get(row[0], row[col] if col < len(row) else "")) for row in rows}
        groups: dict[str, list[tuple[str, int]]] = {}
        for code, price in today.items():
            if price and keys.get(code):
                groups.setdefault(keys[code], []).append((code, price))
        for c in checked:
            key = keys.get(c["code"])
            if c["code"] in fixes or not c["kept"] or not c["kept"] <= suspects:
                continue
            malls = " ".join(f"{mall}:{c['price']}" for mall in sorted(c["kept"]))
            if c["before"] is None:
                fixes[c["code"]] = ""
                results.append(log_row(c, "", f"{malls} (의심 쇼핑몰 단독 신규 상품)"))
                continue
            peers = sorted(price for code, price in groups.get(key, []) if code != c["code"]) if key else []
            if len(peers) < 5:
                continue
            median = peers[len(peers) // 2]
            if c["price"] < median * OUTLIER_RATIO:
                fixes[c["code"]] = ""
                results.append(log_row(c, "", f"{malls} (의심 쇼핑몰 단독, 같은 스펙 중간값 {median})"))

    if fixes:
        _set_today(latest, day, fixes)
        _set_today(output_dir / "history" / f"{category}_price_history.csv", day, fixes)
    print(f"{category}: checked {len(checked)} suspicious prices in {time.time() - started:.0f}s, fixed {len(fixes)}"
          f"{' (suspect malls ' + ', '.join(sorted(suspects)) + ')' if suspects else ''}", flush=True)
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
