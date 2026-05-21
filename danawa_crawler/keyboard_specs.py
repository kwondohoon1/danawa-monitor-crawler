from __future__ import annotations

import argparse
import csv
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import requests

from danawa_crawler.core import DEFAULT_USER_AGENT, normalize_space
from danawa_crawler.monitor_specs import join_tokens, parse_registration_month, spec_tokens, value_tokens


SPEC_FIELDS = [
    "collected_at",
    "product_code",
    "product_name",
    "product_url",
    "size",
    "key_layout",
    "connection_type",
    "battery",
    "battery_capacity",
    "switch_contact_type",
    "switch_type",
    "actuation_force",
    "key_switch",
    "polling_rate",
    "response_time",
    "rollover",
    "keycap_material",
    "keycap_printing",
    "extra_features",
    "full_spec",
    "registration_month",
    "fetch_status",
    "error",
]

_thread_local = threading.local()


@dataclass(frozen=True)
class KeyboardInput:
    index: int
    product_code: str
    product_name: str
    product_url: str


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": "https://prod.danawa.com/",
        }
    )
    return session


def get_session() -> requests.Session:
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = make_session()
        _thread_local.session = session
    return session


def load_keyboard_inputs(path: Path, limit: int | None = None) -> list[KeyboardInput]:
    rows: list[KeyboardInput] = []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            product_code = normalize_space(row.get("product_code", ""))
            product_name = normalize_space(row.get("product_name", ""))
            product_url = normalize_space(row.get("product_url", ""))
            if not product_code:
                continue
            if not product_url:
                product_url = f"https://prod.danawa.com/info/?pcode={product_code}&cate=112782"
            rows.append(
                KeyboardInput(
                    index=len(rows),
                    product_code=product_code,
                    product_name=product_name,
                    product_url=product_url,
                )
            )
            if limit is not None and len(rows) >= limit:
                break
    return rows


def first_value(values: Iterable[str], candidates: Iterable[str]) -> str:
    for candidate in candidates:
        for value in values:
            if candidate == value or candidate in value:
                return candidate
    return ""


def first_value_by_appearance(values: Iterable[str], candidates: Iterable[str]) -> str:
    candidate_list = list(candidates)
    for value in values:
        for candidate in candidate_list:
            if candidate == value or candidate in value:
                return candidate
    return ""


def extract_key_layout(values: list[str]) -> str:
    for value in values:
        match = re.search(r"(\d{2,3})\s*키", value)
        if not match:
            continue
        key_count = int(match.group(1))
        if key_count >= 103:
            return "103키 이상"
        if key_count >= 94:
            return "102~94키"
        if key_count >= 84:
            return "93~84키"
        if key_count >= 75:
            return "83~75키"
        return "74키 이하"
    return ""


def extract_battery_capacity(values: list[str]) -> str:
    for value in values:
        match = re.search(r"(\d{3,5})\s*mAh", value, re.I)
        if not match:
            continue
        capacity = int(match.group(1))
        if capacity >= 8000:
            return "8000~mAh"
        if capacity >= 6000:
            return "6000~7999mAh"
        if capacity >= 4000:
            return "4000~5999mAh"
        if capacity >= 2000:
            return "2000~3999mAh"
        return "2000mAh 미만"
    return ""


def extract_switch_contact_type(values: list[str], text: str) -> str:
    if "기계식" in values:
        return "기계식"
    if "자석축" in text or "마그네틱" in text:
        return "무접점(자석축)"
    if "광축" in text:
        return "무접점(광축)"
    if "정전용량" in text:
        return "무접점(정전용량)"
    if "펜타그래프" in values:
        return "펜타그래프"
    if "멤브레인" in values:
        return "멤브레인"
    return ""


def extract_actuation_force(values: list[str]) -> str:
    for index, value in enumerate(values):
        match = re.search(r"키압\s*:?\s*(\d+(?:\.\d+)?)\s*g", value, re.I)
        if match:
            return f"{match.group(1)}g"
        if value == "키압" and index + 1 < len(values):
            next_match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*g", values[index + 1], re.I)
            if next_match:
                return f"{next_match.group(1)}g"
    return ""


def extract_key_switch(values: list[str], product_name: str) -> str:
    switch_names = [
        "저소음 바다축",
        "저소음 솜사탕축",
        "제조사 축",
        "저소음 적축",
        "저소음 갈축",
        "자석축",
        "적축",
        "갈축",
        "청축",
        "황축",
        "흑축",
        "백축",
        "은축",
        "광축",
    ]
    text = " / ".join([product_name, *values])
    for switch_name in switch_names:
        if switch_name in text:
            return switch_name
    return ""


def extract_switch_type(values: list[str], text: str) -> str:
    for switch_type in ["저소음", "넌클릭", "리니어", "클릭"]:
        if switch_type in values or switch_type in text:
            return switch_type
    return ""


def extract_polling_rate(values: list[str]) -> str:
    for value in values:
        match = re.fullmatch(r"(8000|4000|1000|125)\s*Hz", value, re.I)
        if match:
            return f"{match.group(1)}Hz"
    return ""


def extract_response_time(values: list[str]) -> str:
    for value in values:
        match = re.search(r"(0\.1|0\.125|0\.2|0\.25|1)\s*ms\s*응답속도", value, re.I)
        if match:
            return f"{match.group(1)}ms 응답속도"
    return ""


def extract_rollover(values: list[str]) -> str:
    text = " / ".join(values)
    if re.search(r"동시입력\s*:?\s*무한|무한\s*동시입력", text):
        return "무한"
    match = re.search(r"동시입력\s*:?\s*(\d+)\s*키", text)
    if match:
        return "5키 이상" if int(match.group(1)) >= 5 else "5키 미만"
    return ""


def extract_keyboard_specs(html: str, product_name: str = "") -> dict[str, str]:
    tokens = spec_tokens(html)
    values = value_tokens(tokens)
    full_spec = join_tokens(tokens)
    text = " / ".join([product_name, *values])

    return {
        "size": first_value(values, ["컴팩트 풀배열", "텐키리스", "풀배열", "미니"]),
        "key_layout": extract_key_layout(values),
        "connection_type": first_value(values, ["유선+무선", "유선", "무선"]),
        "battery": first_value_by_appearance(
            values, ["내장 배터리", "AAA형 1개", "AAA형 2개", "AAA형 3개", "AA형 1개", "AA형 2개"]
        ),
        "battery_capacity": extract_battery_capacity(values),
        "switch_contact_type": extract_switch_contact_type(values, text),
        "switch_type": extract_switch_type(values, text),
        "actuation_force": extract_actuation_force(values),
        "key_switch": extract_key_switch(values, product_name),
        "polling_rate": extract_polling_rate(values),
        "response_time": extract_response_time(values),
        "rollover": extract_rollover(values),
        "keycap_material": first_value(values, ["PBT", "ABS"]),
        "keycap_printing": first_value(values, ["이중사출 키캡", "염료승화 방식", "레이저각인 키캡"]),
        "extra_features": " / ".join(feature for feature in ["멀티페어링", "멀티미디어", "래피드 트리거"] if feature in text),
        "full_spec": full_spec,
        "registration_month": parse_registration_month(html),
    }


def empty_row(item: KeyboardInput, collected_at: str, status: str, error: str = "") -> dict[str, str]:
    row = {field: "" for field in SPEC_FIELDS}
    row.update(
        {
            "collected_at": collected_at,
            "product_code": item.product_code,
            "product_name": item.product_name,
            "product_url": item.product_url,
            "fetch_status": status,
            "error": error,
        }
    )
    return row


def fetch_one(item: KeyboardInput, collected_at: str, timeout: int, retries: int) -> dict[str, str]:
    last_error = ""
    for attempt in range(1, retries + 2):
        try:
            response = get_session().get(item.product_url, timeout=timeout)
            response.raise_for_status()
            specs = extract_keyboard_specs(response.text, item.product_name)
            if not specs["full_spec"]:
                raise ValueError("spec_list not found")
            row = empty_row(item, collected_at, "ok")
            row.update(specs)
            return row
        except Exception as exc:  # noqa: BLE001
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt <= retries:
                time.sleep(min(2.0, 0.25 * attempt))
    return empty_row(item, collected_at, "error", last_error)


def write_csv(path: Path, rows: Iterable[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=SPEC_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def crawl_keyboard_specs(
    input_path: Path,
    output_path: Path,
    workers: int,
    timeout: int,
    retries: int,
    limit: int | None,
) -> tuple[int, int]:
    items = load_keyboard_inputs(input_path, limit)
    collected_at = datetime.now().astimezone().isoformat(timespec="seconds")
    results: list[dict[str, str] | None] = [None] * len(items)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(fetch_one, item, collected_at, timeout, retries): item for item in items}
        done = 0
        for future in as_completed(futures):
            item = futures[future]
            results[item.index] = future.result()
            done += 1
            if done % 100 == 0 or done == len(items):
                print(f"keyboard specs: {done}/{len(items)}")

    ordered = [row for row in results if row is not None]
    errors = sum(1 for row in ordered if row["fetch_status"] != "ok")
    write_csv(output_path, ordered)
    return len(ordered), errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect keyboard specs from Danawa product pages.")
    parser.add_argument("--input", default="data/latest/keyboard.csv", help="Input keyboard CSV path.")
    parser.add_argument("--output", default="data/specs/keyboard_specs.csv", help="Output specs CSV path.")
    parser.add_argument("--workers", type=int, default=24, help="Parallel worker count.")
    parser.add_argument("--timeout", type=int, default=20, help="Request timeout in seconds.")
    parser.add_argument("--retries", type=int, default=2, help="Retries per product.")
    parser.add_argument("--limit", type=int, help="Limit products for testing.")
    parser.add_argument("--fail-on-error", action="store_true", help="Exit with error if any product fails.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    total, errors = crawl_keyboard_specs(
        input_path=Path(args.input),
        output_path=Path(args.output),
        workers=max(1, args.workers),
        timeout=args.timeout,
        retries=max(0, args.retries),
        limit=args.limit,
    )
    print(f"saved {total} keyboard specs to {args.output} ({errors} errors)")
    if args.fail_on_error and errors:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
