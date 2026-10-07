"""Lowest price without cash-only malls (with shipping fee) for every GPU/RAM/SSD product.

The list-page price is the lowest of *all* malls, including cash-only specialist shops
(일반 전문몰, 카드/현금 동일 전문몰 such as 컴오아시스) that we do not compete with. Danawa's product
page groups offers by mall type; its '오픈마켓' group (11번가, G마켓, 옥션, 네이버 스마트스토어 ...) and
'백화점/홈쇼핑/종합몰' group (SSG, 롯데ON, 하이마트 ...) are fetched per product here, and the
offer with the lowest price + shipping fee among believable offers is written to

    data/latest/<category>_open.csv
    data/hourly/<day>/<category>_open_<HH>.csv

Fake low prices (one scam seller inside 11번가 listing everything far below the market) are skipped:
price_outliers has already replaced them in the all-mall price, and an open-market offer far below
that price can only be the same fake listing.
"""

from __future__ import annotations

import csv
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from .core import make_session, write_csv
from .price_outliers import CONSENSUS_MALLS, OUTLIER_RATIO, _SKIP_NAME, _int


OPEN_FIELDS = ["product_code", "product_name", "price", "shipping", "mall", "offers", "removed"]
OPEN_URL = "https://prod.danawa.com/info/ajax/getPartPriceCompareMallList.ajax.php"
OFFERS = 10              # 상품당 묶음별로 받는 판매 수 (가격순)
WORKERS = 8

_ITEM = re.compile(r'<div class="diff_item[^"]*"[^>]*>(.*?)(?=<div class="diff_item|\Z)', re.S)
_MALL = re.compile(r"cmpnyc=(\w+)")
_NAME = re.compile(r'<img[^>]*alt="([^"]*)"|class="txt_logo">([^<]*)<')
_PRICE = re.compile(r'class="prc_c">([\d,]+)<')
_SHIP = re.compile(r'class="ship">\(([^)]*)\)')


def shipping_fee(text: str) -> int | None:
    """'무료배송' -> 0, '배송비 3,000원' -> 3000, 알 수 없음(유/무료 등) -> None."""
    if "무료" in text and "유/무료" not in text:
        return 0
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


def parse_offers(html: str) -> list[dict]:
    """오픈마켓·종합몰 판매 목록 -> [{price, mall, name, shipping}] 가격순."""
    offers = []
    for item in _ITEM.findall(html):
        mall, price, name = _MALL.search(item), _PRICE.search(item), _NAME.search(item)
        if not (mall and price):
            continue
        ship = _SHIP.search(item)
        label = (name.group(1) or name.group(2)).strip() if name else mall.group(1)
        if 'class="npay"' in item:
            label += "(스마트스토어)"
        offers.append({"price": int(price.group(1).replace(",", "")), "mall": mall.group(1), "name": label,
                       "shipping": shipping_fee(ship.group(1)) if ship else None})
    return sorted(offers, key=lambda o: o["price"])


def default_fetch() -> Callable[[str], str]:
    session = make_session()

    def part(code: str, mall_type: str, count_field: str) -> str:
        response = session.post(
            OPEN_URL,
            data={"pcode": code, "sMallType": mall_type, "nPage": 1, "sSortType": "minPrice", count_field: OFFERS},
            headers={"Referer": f"https://prod.danawa.com/info/?pcode={code}", "X-Requested-With": "XMLHttpRequest"},
            timeout=15,
        )
        response.raise_for_status()
        return response.content.decode("utf-8", "replace")

    def fetch(code: str) -> str:
        # 오픈마켓 + 백화점/홈쇼핑/종합몰 (현금몰인 '카드/현금 동일 전문몰'·'일반 전문몰'은 받지 않음)
        return part(code, "OpenMarket", "nOpenMarketMoreCount") + part(code, "Affiliate", "nAffiliateMoreCount")

    return fetch


def _read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def _products(output_dir: Path, day: str, category: str) -> list[tuple[str, str, int]]:
    """(코드, 이름, 오늘 전체 쇼핑몰 최저가) — 오늘 가격이 있는 상품만, 중고·해외구매·리퍼·벌크 제외."""
    rows = _read_rows(output_dir / "latest" / f"{category}.csv")
    return [(row["product_code"], row["product_name"], _int(row.get(day))) for row in rows
            if _int(row.get(day)) and not _SKIP_NAME.search(row["product_name"])]


def pick(offers: list[dict], floor: float) -> tuple[dict | None, list[dict]]:
    """믿을 만한 판매(floor 이상이거나 여러 판매처가 같은 값, 10% 이내) 중 상품가+배송비가 가장 싼 판매
    -> (offer, 믿을 수 없어 뺀 판매들)."""
    for i, offer in enumerate(offers):
        near = {o["name"] for o in offers[i:] if o["price"] <= offer["price"] * 1.1}
        if offer["price"] >= floor or len(near) >= CONSENSUS_MALLS:
            return min(offers[i:], key=lambda o: (o["price"] + (o["shipping"] or 0), o["price"])), offers[:i]
    return None, offers


def collect_category(output_dir: Path, day: str, hour: int, category: str, fetch: Callable[[str], str] | None = None) -> list[dict[str, str]]:
    products = _products(output_dir, day, category)
    if not products:
        return []
    latest = output_dir / "latest" / f"{category}_open.csv"
    previous = {row["product_code"]: row for row in _read_rows(latest)}
    fetch = fetch or default_fetch()

    def get(item):
        code, name, _ = item
        try:
            return parse_offers(fetch(code))
        except Exception as error:  # 못 읽은 상품은 직전 값을 쓴다
            print(f"  {category} {code}: open-market list failed ({error})", flush=True)
            return None

    started = time.time()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        fetched = list(pool.map(get, products))

    rows, failed, skipped = [], 0, 0
    for (code, name, all_mall), offers in zip(products, fetched):
        if offers is None:
            failed += 1
            if code in previous:
                rows.append({**previous[code], "product_name": name})
            continue
        # 전체 쇼핑몰 최저가는 price_outliers 가 사기 가격을 이미 걸러낸 값.
        # 오픈마켓 가격은 그보다 싸게 나올 수 없으므로, 크게 싸면 같은 사기 판매로 보고 건너뛴다.
        offer, removed = pick(offers, all_mall * OUTLIER_RATIO)
        if offer is None:
            continue                                           # 오픈마켓 판매 없음
        skipped += bool(removed)
        rows.append({
            "product_code": code, "product_name": name, "price": str(offer["price"]),
            "shipping": "" if offer["shipping"] is None else str(offer["shipping"]), "mall": offer["name"],
            "offers": str(len(offers)), "removed": " ".join(f"{o['name']}:{o['price']}" for o in removed),
        })

    write_csv(latest, OPEN_FIELDS, rows)
    write_csv(output_dir / "hourly" / day / f"{category}_open_{hour:02d}.csv", OPEN_FIELDS, rows)
    print(f"{category}: open-market prices for {len(rows)}/{len(products)} products in {time.time() - started:.0f}s"
          f" (skipped fake low {skipped}, failed {failed})", flush=True)
    return rows


def collect_open_market(output_dir: Path, day: str, hour: int, categories, fetch_factory=None) -> dict[str, list[dict[str, str]]]:
    return {category: collect_category(output_dir, day, hour, category, fetch_factory(category) if fetch_factory else None)
            for category in categories}
