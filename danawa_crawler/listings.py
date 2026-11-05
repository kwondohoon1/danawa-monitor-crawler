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
  - data/blocked_listings.csv 에 적은 상품번호·쇼핑몰 전체(예: 판매를 안 하는데 가격만 남은 스마트스토어)·다나와 상품코드는 무조건 뺀다.
  - 11번가는 상품 페이지를 읽을 수 있어 판매자(스토어 이름·번호)로도 뺀다 (예: 이비즈 ebiz). 가장 싼 11번가 판매만 확인하고
    결과는 data/state/eleven_stores.csv 에 남겨 다시 읽지 않는다.
"""

from __future__ import annotations

import csv
import re
import threading
from datetime import date
from pathlib import Path
from typing import Callable

import requests

from .core import DEFAULT_USER_AGENT, write_csv


ESM = {"EE128": "G마켓", "EE715": "옥션"}
# 처음 도입할 때(2026-11-02) 이미 있던 상품: 상품번호가 이보다 작으면 오래된 상품으로 본다.
# G마켓 48942xxxxx 가 2026-11-01 등록이고 자사 2026-09~10월 등록 상품이 G마켓 4839~4854xxxxxx, 옥션 F647~F662xxxxxx.
KNOWN_OLD = {"EE128": 4890000000, "EE715": 690000000}
OLD_DAY = "2026-09-01"       # 오래된 상품으로 볼 때 적는 처음 본 날
NEW_DAYS = 14                # 처음 본 지 이만큼 안 되면 '새 상품'
NEW_RATIO = 0.9              # 새 G마켓·옥션 상품이 믿을 만한 가격보다 10% 넘게 싸면 사기로 본다
STATE_FIELDS = ["mall", "link_pcode", "first_seen"]
BLOCK_FIELDS = ["product_code", "mall", "link_pcode", "store", "note"]
ELEVEN = {"TH201", "TY618D"}                 # 다나와의 11번가 쇼핑몰 코드
STORE_FIELDS = ["link_pcode", "store_no", "store_name"]
_STORE = re.compile(r'storeNo:\s*(\d+),\s*storeName:\s*"([^"]*)"')
STORE_FAIL_LIMIT = 5         # 한 번 확인하는 동안 이만큼 실패하면 11번가가 막은 것으로 보고 남은 확인은 건너뛴다


def fetch_store(link_pcode: str) -> tuple[str, str]:
    """11번가 상품 페이지에서 (스토어 번호, 스토어 이름). 못 읽으면 ('', '').

    한 번만 시도한다. 재시도 세션(make_session)은 502 한 번에 약 80초를 기다리는데, 11번가가 GitHub 서버를
    502로 막아서 2026-11-03부터 매시 가격 수집이 몇 시간씩 늘어져 한 회차도 저장하지 못했다.
    """
    response = requests.get(f"https://www.11st.co.kr/products/{link_pcode}",
                            headers={"User-Agent": DEFAULT_USER_AGENT}, timeout=10)
    response.raise_for_status()
    match = _STORE.search(response.text)
    return (match.group(1), match.group(2)) if match else ("", "")

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

    def __init__(self, output_dir: Path, fetch_store: Callable[[str], tuple[str, str]] = fetch_store):
        self.path = output_dir / "state" / "listings_seen.csv"
        self.store_path = output_dir / "state" / "eleven_stores.csv"
        self.seen: dict[tuple[str, str], str] = {}
        self.stores: dict[str, tuple[str, str]] = {}          # 11번가 상품번호 -> (스토어 번호, 스토어 이름)
        self.block_listings: set[tuple[str, str]] = set()
        self.block_products: set[str] = set()
        self.block_malls: set[str] = set()
        self.block_stores: set[str] = set()                     # 11번가 스토어 이름 또는 번호
        self._fetch_store = fetch_store
        self._store_failed: set[str] = set()                    # 이번에 못 읽은 11번가 상품 (다시 안 읽음)
        self._lock = threading.Lock()
        self._dirty = False
        if self.path.exists():
            with self.path.open("r", encoding="utf-8-sig", newline="") as file:
                for row in csv.DictReader(file):
                    self.seen[(row["mall"], row["link_pcode"])] = row["first_seen"]
        if self.store_path.exists():
            with self.store_path.open("r", encoding="utf-8-sig", newline="") as file:
                for row in csv.DictReader(file):
                    self.stores[row["link_pcode"]] = (row["store_no"], row["store_name"])
        block = output_dir / "blocked_listings.csv"
        if block.exists():
            with block.open("r", encoding="utf-8-sig", newline="") as file:
                for row in csv.DictReader(file):
                    code, mall, link = (row.get("product_code") or "").strip(), (row.get("mall") or "").strip(), (row.get("link_pcode") or "").strip()
                    store = (row.get("store") or "").strip()
                    if store:
                        self.block_stores.add(store)        # 11번가 스토어
                    elif link:
                        self.block_listings.add((mall, link))
                    elif code:
                        self.block_products.add(code)
                    elif mall:
                        self.block_malls.add(mall)          # 쇼핑몰 전체

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
        return mall in self.block_malls or (mall, link_pcode) in self.block_listings or ("", link_pcode) in self.block_listings

    def store_of(self, link_pcode: str) -> tuple[str, str]:
        """11번가 상품의 (스토어 번호, 이름). 처음 보는 상품만 페이지를 읽고 기록한다."""
        with self._lock:
            if link_pcode in self.stores:
                return self.stores[link_pcode]
            if link_pcode in self._store_failed or len(self._store_failed) >= STORE_FAIL_LIMIT:
                return ("", "")                                 # 이번엔 모름 (같은 상품·막힌 11번가를 또 기다리지 않음)
        try:
            store = self._fetch_store(link_pcode)
        except Exception as error:                              # 못 읽으면 이번엔 모름(파일에 기록 안 함)
            with self._lock:
                self._store_failed.add(link_pcode)
                stop = len(self._store_failed) == STORE_FAIL_LIMIT
            print(f"  11st store lookup failed {link_pcode}: {error}", flush=True)
            if stop:
                print(f"  11st store lookup: {STORE_FAIL_LIMIT} failures, skipping the rest of this check", flush=True)
            return ("", "")
        with self._lock:
            self.stores[link_pcode] = store
            self._dirty = True
        return store

    def store_blocked(self, mall: str, link_pcode: str) -> str:
        """막아 둔 11번가 스토어의 판매면 스토어 이름, 아니면 ''."""
        if mall not in ELEVEN or not link_pcode or not self.block_stores:
            return ""
        number, name = self.store_of(link_pcode)
        return name or number if (name in self.block_stores or number in self.block_stores) else ""

    def save(self) -> None:
        if not self._dirty:
            return
        rows = [{"mall": mall, "link_pcode": code, "first_seen": day} for (mall, code), day in sorted(self.seen.items())]
        write_csv(self.path, STATE_FIELDS, rows)
        write_csv(self.store_path, STORE_FIELDS,
                  [{"link_pcode": code, "store_no": no, "store_name": name} for code, (no, name) in sorted(self.stores.items())])
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
    # 가장 싼 11번가 판매가 막아 둔 스토어 것이면 뺀다 (스토어 확인은 페이지를 읽어야 해서 가장 싼 것만 본다)
    while kept and kept[0].get("mall") in ELEVEN:
        store = listings.store_blocked(kept[0]["mall"], kept[0].get("code", ""))
        if not store:
            break
        removed.append((kept.pop(0), f"막아 둔 11번가 스토어 {store}"))
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
