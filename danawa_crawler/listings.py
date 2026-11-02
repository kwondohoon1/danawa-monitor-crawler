"""Tell brand-new G마켓·옥션 listings (the scam pattern) from established ones, plus a hand-kept block list.

2026-11-01 (빅스마일데이 전날) 한 판매자가 G마켓에 그래픽카드 수백 개를 시세보다 20~35% 싸게 한꺼번에 올렸다
(상품번호 48942xxxxx, 통신판매업 신고 2026년, 상품평 0, 금성몰스토어 등). 다나와는 그 가격을 그대로 보여 주므로
동일스펙 최저가 비교가 전부 틀어졌다. 그렇다고 혼자 싼 가격을 다 빼면 오래된 판매자의 실제 행사 쿠폰가까지 빠진다.

G마켓·옥션 상품 페이지는 봇 차단(403)이라 판매자 정보를 읽을 수 없다. 대신 다나와 판매 목록에 있는
상품번호(link_pcode)를 쓴다:
  - 상품번호를 처음 본 날을 data/state/listings_seen.csv 에 기록해 '새 상품'(NEW_DAYS 안)을 가려낸다.
    처음 도입한 날 이미 있던 상품은 상품번호 크기(KNOWN_OLD)로 오래된 상품인지 판단한다.
  - 새 G마켓·옥션 상품이 믿을 만한 가격(새 상품이 아닌 판매들 중 최저가, 같은 스펙 시세)보다 NEW_RATIO 넘게
    싸면 사기로 보고 뺀다. 여러 개가 같이 싸도(계정 여러 개) 마찬가지.
  - 오래된 G마켓·옥션 상품은 혼자 싸도 빼지 않는다 (trusted).
  - data/blocked_listings.csv 에 적은 상품번호(또는 다나와 상품코드)는 무조건 뺀다.
"""

from __future__ import annotations

import csv
import re
import threading
from datetime import date
from pathlib import Path

from .core import write_csv


ESM = {"EE128": "G마켓", "EE715": "옥션"}
# 처음 도입할 때(2026-11-02) 이미 있던 상품: 상품번호가 이보다 작으면 오래된 상품으로 본다.
# G마켓 48942xxxxx 가 2026-11-01 등록이고 자사 2026-09~10월 등록 상품이 4839~4854xxxxxx.
KNOWN_OLD = {"EE128": 4890000000, "EE715": 7000000000}
OLD_DAY = "2026-09-01"       # 오래된 상품으로 볼 때 적는 처음 본 날
NEW_DAYS = 14                # 처음 본 지 이만큼 안 되면 '새 상품'
NEW_RATIO = 0.9              # 새 G마켓·옥션 상품이 믿을 만한 가격보다 10% 넘게 싸면 사기로 본다
STATE_FIELDS = ["mall", "link_pcode", "first_seen"]
BLOCK_FIELDS = ["product_code", "mall", "link_pcode", "note"]

_DIGITS = re.compile(r"\d+")


def _number(code: str) -> int:
    digits = "".join(_DIGITS.findall(str(code)))
    return int(digits) if digits else 0


def _days(later: str, earlier: str) -> int:
    try:
        return (date.fromisoformat(later) - date.fromisoformat(earlier)).days
    except ValueError:
        return 0


class Listings:
    """처음 본 날 기록(data/state/listings_seen.csv) + 수동 제외 목록(data/blocked_listings.csv)."""

    def __init__(self, output_dir: Path):
        self.path = output_dir / "state" / "listings_seen.csv"
        self.seen: dict[tuple[str, str], str] = {}
        self.block_listings: set[tuple[str, str]] = set()
        self.block_products: set[str] = set()
        self._lock = threading.Lock()
        self._dirty = False
        if self.path.exists():
            with self.path.open("r", encoding="utf-8-sig", newline="") as file:
                for row in csv.DictReader(file):
                    self.seen[(row["mall"], row["link_pcode"])] = row["first_seen"]
        block = output_dir / "blocked_listings.csv"
        if block.exists():
            with block.open("r", encoding="utf-8-sig", newline="") as file:
                for row in csv.DictReader(file):
                    code, mall, link = (row.get("product_code") or "").strip(), (row.get("mall") or "").strip(), (row.get("link_pcode") or "").strip()
                    if link:
                        self.block_listings.add((mall, link))
                    elif code:
                        self.block_products.add(code)

    def first_seen(self, mall: str, link_pcode: str, day: str) -> str:
        key = (mall, link_pcode)
        with self._lock:
            if key not in self.seen:
                old = mall in KNOWN_OLD and 0 < _number(link_pcode) < KNOWN_OLD[mall]
                self.seen[key] = OLD_DAY if old else day
                self._dirty = True
            return self.seen[key]

    def is_new(self, mall: str, link_pcode: str, day: str) -> bool:
        """G마켓·옥션 상품인데 처음 본 지 NEW_DAYS 가 안 됐으면 True."""
        if mall not in ESM or not link_pcode:
            return False
        return _days(day, self.first_seen(mall, link_pcode, day)) < NEW_DAYS

    def is_blocked(self, mall: str, link_pcode: str) -> bool:
        return (mall, link_pcode) in self.block_listings or ("", link_pcode) in self.block_listings

    def save(self) -> None:
        if not self._dirty:
            return
        rows = [{"mall": mall, "link_pcode": code, "first_seen": day} for (mall, code), day in sorted(self.seen.items())]
        write_csv(self.path, STATE_FIELDS, rows)
        self._dirty = False


def split(offers: list[dict], day: str, listings: Listings | None, market: int | None = None) -> tuple[list[dict], list[tuple[dict, str]]]:
    """판매 목록(가격순, 각 항목에 price·mall(코드)·code(상품번호)) -> (남긴 판매, [(뺀 판매, 이유)]).

    오래된 G마켓·옥션 판매에는 trusted=True 를 달아 준다 (뒤의 시세·합의 규칙에서도 빼지 않도록).
    """
    if listings is None:
        return offers, []
    removed: list[tuple[dict, str]] = []
    kept: list[dict] = []
    fresh: list[dict] = []
    for offer in offers:
        mall, code = offer.get("mall", ""), offer.get("code", "")
        if listings.is_blocked(mall, code):
            removed.append((offer, "수동 제외"))
        elif listings.is_new(mall, code, day):
            fresh.append(offer)
        else:
            if mall in ESM and code:
                offer["trusted"] = True
            kept.append(offer)
    if fresh:
        # 믿을 만한 가격: 새 상품이 아닌 판매 중 최저가와 같은 스펙 시세 중 작은 값
        refs = [o["price"] for o in kept] + ([market] if market else [])
        ref = min(refs) if refs else None
        for offer in fresh:
            if ref and offer["price"] < ref * NEW_RATIO:
                removed.append((offer, f"새 {ESM[offer['mall']]} 상품 {offer['code']}, 믿을 만한 가격 {ref:,}"))
            else:
                kept.append(offer)
        kept.sort(key=lambda o: o["price"])
    return kept, removed
