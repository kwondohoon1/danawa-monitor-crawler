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

from danawa_crawler.core import DEFAULT_USER_AGENT, normalize_space, now_kst_iso
from danawa_crawler.monitor_specs import (
    clean_spec_value,
    first_matching,
    join_tokens,
    parse_registration_month,
    spec_tokens,
    value_tokens,
)


SPEC_FIELDS = [
    "collected_at",
    "product_code",
    "product_name",
    "product_url",
    "inch",
    "weight",
    "operating_system",
    "resolution",
    "refresh_rate",
    "cpu",
    "graphics",
    "ram",
    "ssd",
    "full_spec",
    "registration_month",
    "fetch_status",
    "error",
]

_thread_local = threading.local()


@dataclass(frozen=True)
class LaptopInput:
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


def load_laptop_inputs(path: Path, limit: int | None = None) -> list[LaptopInput]:
    rows: list[LaptopInput] = []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            product_code = normalize_space(row.get("product_code", ""))
            product_name = normalize_space(row.get("product_name", ""))
            product_url = normalize_space(row.get("product_url", ""))
            if not product_code:
                continue
            if not product_url:
                product_url = f"https://prod.danawa.com/info/?pcode={product_code}&cate=112758"
            rows.append(
                LaptopInput(
                    index=len(rows),
                    product_code=product_code,
                    product_name=product_name,
                    product_url=product_url,
                )
            )
            if limit is not None and len(rows) >= limit:
                break
    return rows


def collect_after_label(values: list[str], labels: set[str], stop_labels: set[str]) -> str:
    for index, value in enumerate(values):
        if value not in labels:
            continue
        collected: list[str] = []
        for token in values[index + 1 :]:
            if token in stop_labels:
                break
            collected.append(token)
        return " / ".join(clean_spec_value(token) for token in collected if clean_spec_value(token))
    return ""


def labeled_value(full_spec: str, labels: Iterable[str], value_pattern: str, flags: int = re.I) -> str:
    for label in labels:
        match = re.search(rf"{re.escape(label)}\s*:?\s*({value_pattern})", full_spec, flags)
        if match:
            return clean_spec_value(match.group(1))
    return ""


def extract_operating_system(values: list[str]) -> str:
    return first_matching(values, r"(윈도우|Windows|OS미포함|프리도스|FreeDOS|리눅스|Linux|macOS|크롬OS)", re.I)


def extract_cpu(values: list[str]) -> str:
    stop_labels = {"NPU", "그래픽", "램", "구성", "저장장치", "전원", "배터리", "용도", "화면", "화면정보"}
    return collect_after_label(values, {"CPU"}, stop_labels)


def extract_graphics(values: list[str]) -> str:
    stop_labels = {"TGP", "램", "구성", "저장장치", "전원", "배터리", "용도", "화면", "화면정보", "CPU"}
    return collect_after_label(values, {"그래픽"}, stop_labels)


def parse_laptop_specs(html: str) -> dict[str, str]:
    tokens = spec_tokens(html)
    values = value_tokens(tokens)
    full_spec = join_tokens(tokens)

    return {
        "inch": first_matching(values, r"\d+(?:\.\d+)?\s*cm\s*\(\s*\d+(?:\.\d+)?\s*인치\s*\)|\d+(?:\.\d+)?\s*인치|\d+(?:\.\d+)?\s*cm"),
        "weight": first_matching(values, r"\d+(?:\.\d+)?\s*kg\b", re.I),
        "operating_system": extract_operating_system(values),
        "resolution": first_matching(values, r"[A-Za-z0-9+\- ]*\(?[0-9]{3,5}\s*x\s*[0-9]{3,5}\)?(?:\([A-Za-z0-9+\- ]+\))?", re.I),
        "refresh_rate": first_matching(values, r"\d+(?:\.\d+)?\s*Hz\b", re.I),
        "cpu": extract_cpu(values),
        "graphics": extract_graphics(values),
        "ram": labeled_value(full_spec, ["램"], r"\d+(?:\.\d+)?\s*(?:GB|TB)"),
        "ssd": labeled_value(full_spec, ["SSD", "용량"], r"\d+(?:\.\d+)?\s*(?:TB|GB)"),
        "full_spec": full_spec,
        "registration_month": parse_registration_month(html),
    }


def empty_row(item: LaptopInput, collected_at: str, status: str, error: str = "") -> dict[str, str]:
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


def fetch_one(item: LaptopInput, collected_at: str, timeout: int, retries: int) -> dict[str, str]:
    last_error = ""
    for attempt in range(1, retries + 2):
        try:
            response = get_session().get(item.product_url, timeout=timeout)
            response.raise_for_status()
            specs = parse_laptop_specs(response.text)
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


def crawl_laptop_specs(
    input_path: Path,
    output_path: Path,
    workers: int,
    timeout: int,
    retries: int,
    limit: int | None,
) -> tuple[int, int]:
    items = load_laptop_inputs(input_path, limit)
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
                print(f"laptop specs: {done}/{len(items)}")

    ordered = [row for row in results if row is not None]
    errors = sum(1 for row in ordered if row["fetch_status"] != "ok")
    write_csv(output_path, ordered)
    return len(ordered), errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect laptop specs from Danawa product pages.")
    parser.add_argument("--input", default="data/latest/laptop.csv", help="Input laptop CSV path.")
    parser.add_argument("--output", default="data/specs/laptop_specs.csv", help="Output specs CSV path.")
    parser.add_argument("--workers", type=int, default=32, help="Parallel worker count.")
    parser.add_argument("--timeout", type=int, default=20, help="Request timeout in seconds.")
    parser.add_argument("--retries", type=int, default=2, help="Retries per product.")
    parser.add_argument("--limit", type=int, help="Limit products for testing.")
    parser.add_argument("--fail-on-error", action="store_true", help="Exit with error if any product fails.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    total, errors = crawl_laptop_specs(
        input_path=Path(args.input),
        output_path=Path(args.output),
        workers=max(1, args.workers),
        timeout=args.timeout,
        retries=max(0, args.retries),
        limit=args.limit,
    )
    print(f"saved {total} laptop specs to {args.output} ({errors} errors)")
    if args.fail_on_error and errors:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
