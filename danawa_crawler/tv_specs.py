from __future__ import annotations

import argparse
import csv
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import requests
from bs4 import BeautifulSoup

from danawa_crawler.core import DEFAULT_USER_AGENT, normalize_space, now_kst_iso
from danawa_crawler.monitor_specs import (
    clean_spec_value,
    first_matching,
    join_tokens,
    section_tokens,
    value_tokens,
)


SPEC_FIELDS = [
    "collected_at",
    "product_code",
    "product_name",
    "product_url",
    "screen_size",
    "display_type",
    "resolution",
    "refresh_rate",
    "hdr",
    "smart_features",
    "full_spec",
    "registration_month",
    "fetch_status",
    "error",
]

_thread_local = threading.local()


@dataclass(frozen=True)
class TvInput:
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


def load_tv_inputs(path: Path, limit: int | None = None) -> list[TvInput]:
    rows: list[TvInput] = []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            product_code = normalize_space(row.get("product_code", ""))
            product_name = normalize_space(row.get("product_name", ""))
            product_url = normalize_space(row.get("product_url", ""))
            if not product_code:
                continue
            if not product_url:
                product_url = f"https://prod.danawa.com/info/?pcode={product_code}&cate=10248425"
            rows.append(
                TvInput(
                    index=len(rows),
                    product_code=product_code,
                    product_name=product_name,
                    product_url=product_url,
                )
            )
            if limit is not None and len(rows) >= limit:
                break
    return rows


def extract_display_type(values: list[str]) -> str:
    return first_matching(
        values,
        r"(?:OLED|QLED|QNED|미니\s*LED|Mini\s*LED|Micro\s*RGB|LED|LCD|상업용디스플레이)"
        r"(?:\s+(?:TV|모니터|디스플레이))?",
        re.I,
    )


def extract_resolution(values: list[str]) -> str:
    return first_matching(
        values,
        r"(?:8K\s*UHD|4K\s*UHD|UHD|QHD|FHD|HD)"
        r"(?:\s*\(\s*[0-9]{3,5}\s*x\s*[0-9]{3,5}\s*\))?"
        r"|[0-9]{3,5}\s*x\s*[0-9]{3,5}(?:\s*\([A-Za-z0-9+\- ]+\))?",
        re.I,
    )


def extract_hdr(tokens: list[str]) -> str:
    quality = value_tokens(section_tokens(tokens, "화질"))
    matched = [
        clean_spec_value(value)
        for value in quality
        if re.search(r"(HDR|HLG|Dolby\s*Vision|돌비\s*비전)", value, re.I)
    ]
    return " / ".join(dict.fromkeys(matched))


def tv_spec_tokens(html: str) -> list[str]:
    match = re.search(
        r'<div[^>]*class=["\'][^"\']*\bspec_list\b[^"\']*["\'][^>]*>\s*'
        r'<div[^>]*class=["\'][^"\']*\bitems\b[^"\']*["\'][^>]*>(.*?)</div>',
        html,
        re.I | re.S,
    )
    if not match:
        return []
    fragment = BeautifulSoup(match.group(1), "html.parser")
    return [normalize_space(token) for token in fragment.stripped_strings if normalize_space(token)]


def parse_tv_registration_month(html: str) -> str:
    start = html.find("등록월")
    if start < 0:
        return ""
    text = BeautifulSoup(html[start : start + 500], "html.parser").get_text(" ", strip=True)
    match = re.search(r"등록월\s*:\s*(\d{4})\s*[./년]\s*(\d{1,2})", text)
    if not match:
        return ""
    return f"{match.group(1)}/{int(match.group(2)):02d}"


def parse_tv_specs(html: str) -> dict[str, str]:
    tokens = tv_spec_tokens(html)
    values = value_tokens(tokens)

    return {
        "screen_size": first_matching(
            values,
            r"\d+(?:\.\d+)?\s*인치\s*\(\s*\d+(?:\.\d+)?\s*cm\s*\)"
            r"|\d+(?:\.\d+)?\s*cm\s*\(\s*\d+(?:\.\d+)?\s*인치\s*\)"
            r"|\d+(?:\.\d+)?\s*인치",
        ),
        "display_type": extract_display_type(values),
        "resolution": extract_resolution(values),
        "refresh_rate": first_matching(values, r"\d+(?:\.\d+)?\s*Hz\b", re.I),
        "hdr": extract_hdr(tokens),
        "smart_features": join_tokens(section_tokens(tokens, "스마트")),
        "full_spec": join_tokens(tokens),
        "registration_month": parse_tv_registration_month(html),
    }


def empty_row(item: TvInput, collected_at: str, status: str, error: str = "") -> dict[str, str]:
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


def fetch_one(item: TvInput, collected_at: str, timeout: int, retries: int) -> dict[str, str]:
    last_error = ""
    for attempt in range(1, retries + 2):
        try:
            response = get_session().get(item.product_url, timeout=timeout)
            response.raise_for_status()
            specs = parse_tv_specs(response.text)
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


def crawl_tv_specs(
    input_path: Path,
    output_path: Path,
    workers: int,
    timeout: int,
    retries: int,
    limit: int | None,
) -> tuple[int, int]:
    items = load_tv_inputs(input_path, limit)
    collected_at = now_kst_iso()
    results: list[dict[str, str] | None] = [None] * len(items)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(fetch_one, item, collected_at, timeout, retries): item for item in items}
        done = 0
        for future in as_completed(futures):
            item = futures[future]
            results[item.index] = future.result()
            done += 1
            if done % 100 == 0 or done == len(items):
                print(f"tv specs: {done}/{len(items)}")

    ordered = [row for row in results if row is not None]
    errors = sum(1 for row in ordered if row["fetch_status"] != "ok")
    write_csv(output_path, ordered)
    return len(ordered), errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect TV specs from Danawa product pages.")
    parser.add_argument("--input", default="data/latest/tv.csv", help="Input TV CSV path.")
    parser.add_argument("--output", default="data/specs/tv_specs.csv", help="Output specs CSV path.")
    parser.add_argument("--workers", type=int, default=32, help="Parallel worker count.")
    parser.add_argument("--timeout", type=int, default=20, help="Request timeout in seconds.")
    parser.add_argument("--retries", type=int, default=3, help="Retries per product.")
    parser.add_argument("--limit", type=int, help="Limit products for testing.")
    parser.add_argument("--fail-on-error", action="store_true", help="Exit with error if any product fails.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    total, errors = crawl_tv_specs(
        input_path=Path(args.input),
        output_path=Path(args.output),
        workers=max(1, args.workers),
        timeout=args.timeout,
        retries=max(0, args.retries),
        limit=args.limit,
    )
    print(f"saved {total} TV specs to {args.output} ({errors} errors)")
    if args.fail_on_error and errors:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
