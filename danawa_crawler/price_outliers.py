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
MARKET_CATEGORIES = ("gpu",)  # 같은 스펙 시세로 판단하는 카테고리
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
_SKIP_NAME = re.compile(r"중고|해외구매|리퍼|벌크")   # 원래 싼 상품 — 시세 계산·확인에서 제외 (사이트도 비교에 안 씀)
CONSENSUS_MALLS = 3      # 상품 안에서 이만큼의 쇼핑몰이 최저가 근처(10% 이내)면 시세보다 싸도 진짜 가격


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
    keys = spec_keys(output_dir, category)

    # 같은 스펙 상품들의 오늘 시세(중간값). 판매처가 적은 상품은 자기 쇼핑몰 목록만으로는 기준을 못 잡으므로
    # (비싼 판매처 한두 곳이 기준이 돼 정상가를 빼던 문제) 시세를 기준으로 판단한다.
    today = {row[0]: _int(row[col]) if col < len(row) else None for row in rows if not _SKIP_NAME.search(row[1])}
    group_prices: dict[str, list[int]] = {}
    for code, price in today.items():
        if price and keys.get(code):
            group_prices.setdefault(keys[code], []).append(price)
    # 시세 기준은 그래픽카드만 (칩셋+VRAM 이 같으면 가격대가 좁음). RAM·SSD 는 같은 묶음 안에서도
    # 저가형·고급형 차이가 커서 시세로 판단하면 정상가를 대량으로 잘못 뺀다 → 상품 안 쇼핑몰 비교만.
    market = ({key: sorted(v)[len(v) // 2] for key, v in group_prices.items() if len(v) >= 5}
              if category in MARKET_CATEGORIES else {})

    candidates = []
    for row in rows:
        price = today.get(row[0])
        if not price:
            continue
        before = base.get(row[0])
        median = market.get(keys.get(row[0], ""))
        if median:
            # 시세보다 15% 넘게 싸면 확인. 새 상품은 사기 의심 쇼핑몰 단독인지 보려고 확인(가격은 안 바꿈)
            if price < median * OUTLIER_RATIO or before is None:
                candidates.append((price / median, row[0], row[1], price, before, median))
        elif before is None or price < before * DROP_RATIO:
            # 스펙 묶음이 없으면 예전 방식: 직전 가격 대비 급락·새 상품을 상품 안 쇼핑몰끼리 비교
            candidates.append((1.0 if before is None else price / before, row[0], row[1], price, before, None))
    candidates.sort()
    candidates = candidates[:MAX_CHECKS]
    if not candidates:
        return []

    fetch = fetch or default_fetch(category)

    def check(item):
        _, code, name, price, before, median = item
        try:
            mall_prices = parse_mall_prices(fetch(code))
        except Exception as error:  # 페이지를 못 읽으면 그대로 둔다
            print(f"  {category} {code}: mall list failed ({error})", flush=True)
            return None
        if median:
            floor = median * OUTLIER_RATIO
            removed = [row for row in mall_prices if row[0] < floor]
            ok = [row for row in mall_prices if row[0] >= floor]
            near = [row for row in mall_prices if row[0] <= price * 1.1]
            if price >= floor or len(near) >= CONSENSUS_MALLS:
                clean = price                                  # 시세 범위, 또는 여러 쇼핑몰이 같은 값 → 그대로
                removed = []
            else:
                clean = ok[0][0] if ok else 0                  # 시세 범위의 가장 싼 쇼핑몰, 없으면 0(사기 의심 쇼핑몰 단독일 때만 빼기)
        else:
            clean, removed = clean_lowest(mall_prices, before)
        kept_malls = {mall for value, mall in mall_prices if (value, mall) not in removed}
        return {"code": code, "name": name, "price": price, "before": before, "clean": clean, "removed": removed,
                "kept": kept_malls, "median": median}

    started = time.time()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        checked = [result for result in pool.map(check, candidates) if result]

    def log_row(c, fixed: str, removed: str) -> dict[str, str]:
        return {"hour": f"{hour:02d}", "category": category, "product_code": c["code"], "product_name": c["name"],
                "crawled_price": str(c["price"]), "fixed_price": fixed, "baseline": "" if c["before"] is None else str(c["before"]),
                "removed": removed}

    def removed_text(c) -> str:
        text = " ".join(f"{mall}:{value}" for value, mall in c["removed"])
        return f"{text} (같은 스펙 시세 {c['median']})" if c["median"] else text

    # 1차: 시세(또는 상품 안 다른 쇼핑몰)보다 크게 싼 가격을 빼고 다음 최저가로, 남는 쇼핑몰이 없으면 빼기
    fixes: dict[str, str] = {}
    results = []
    for c in checked:
        if c["clean"] and c["clean"] > c["price"]:
            fixes[c["code"]] = str(c["clean"])
            results.append(log_row(c, str(c["clean"]), removed_text(c)))

    # 2차: 이번에 여러 번 빠진 쇼핑몰(사기 의심)에서만 파는 '새로 나타난' 상품은 뺀다
    # — 사기 업체가 직접 올린 상품의 전형(예: ASUS RTX 5080 NOCTUA 2,180,000원, TH201 단독)
    # 실제로 상품 최저가를 만들었다가 빠진 쇼핑몰만 센다 (목록에 섞인 다른 싼 판매처는 세지 않음)
    counts = Counter(mall for c in checked if c["code"] in fixes for value, mall in c["removed"] if value == c["price"])
    suspects = {mall for mall, n in counts.items() if n >= SUSPECT_MIN}
    if suspects:
        for c in checked:
            if c["code"] in fixes:
                continue
            sellers = {mall for _, mall in c["removed"]} | c["kept"] if c["clean"] == 0 else c["kept"]
            if not sellers or not sellers <= suspects:
                continue                                       # 일반 판매처(G마켓·옥션 등)도 팔면 그대로 둔다
            if c["clean"] == 0:                                # 시세보다 크게 싼데 의심 쇼핑몰에서만 판다
                why = f"(의심 쇼핑몰 단독, 같은 스펙 시세 {c['median']})"
            elif c["before"] is None:                          # 의심 쇼핑몰에서만 파는 새 상품
                why = "(의심 쇼핑몰 단독 신규 상품)"
            else:
                continue
            fixes[c["code"]] = ""
            results.append(log_row(c, "", " ".join(f"{mall}:{c['price']}" for mall in sorted(sellers)) + f" {why}"))

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
