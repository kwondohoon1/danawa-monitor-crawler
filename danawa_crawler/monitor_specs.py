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
from bs4 import BeautifulSoup

from danawa_crawler.core import DEFAULT_USER_AGENT, normalize_space


SPEC_FIELDS = [
    "collected_at",
    "product_code",
    "product_name",
    "product_url",
    "inch",
    "resolution",
    "refresh_rate",
    "panel",
    "aspect_ratio",
    "shape",
    "color",
    "special_features",
    "full_spec",
    "registration_month",
    "fetch_status",
    "error",
]

_thread_local = threading.local()


@dataclass(frozen=True)
class MonitorInput:
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


def load_monitor_inputs(path: Path, limit: int | None = None) -> list[MonitorInput]:
    rows: list[MonitorInput] = []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            product_code = normalize_space(row.get("product_code", ""))
            product_name = normalize_space(row.get("product_name", ""))
            product_url = normalize_space(row.get("product_url", ""))
            if not product_code:
                continue
            if not product_url:
                product_url = f"https://prod.danawa.com/info/?pcode={product_code}&cate=112757"
            rows.append(
                MonitorInput(
                    index=len(rows),
                    product_code=product_code,
                    product_name=product_name,
                    product_url=product_url,
                )
            )
            if limit is not None and len(rows) >= limit:
                break
    return rows


def spec_tokens(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    spec = soup.select_one(".spec_list .items") or soup.select_one(".spec_list")
    if not spec:
        return []
    return [normalize_space(token) for token in spec.stripped_strings if normalize_space(token)]


def clean_spec_value(value: str) -> str:
    value = normalize_space(value)
    value = re.sub(r"(?<=\d)\s*x\s*(?=\d)", "x", value, flags=re.I)
    value = re.sub(r"\s*↔\s*", " ↔ ", value)
    value = re.sub(r"\s*:\s*", ": ", value)
    value = re.sub(r"(?<=\d):\s+(?=\d)", ":", value)
    return value


def join_tokens(tokens: Iterable[str]) -> str:
    output: list[str] = []
    for token in tokens:
        if token == "/":
            if output and output[-1] != "/":
                output.append("/")
            continue
        if token == ":":
            if output and output[-1] not in {"/", ":"}:
                output[-1] = output[-1] + ":"
            continue
        if output and output[-1].endswith(":"):
            output[-1] = output[-1] + " " + token
        else:
            output.append(token)
    while output and output[-1] == "/":
        output.pop()
    return clean_spec_value(" ".join(output))


def value_tokens(tokens: list[str]) -> list[str]:
    return [token for token in tokens if token not in {"/", ":"}]


def first_matching(values: Iterable[str], pattern: str, flags: int = 0) -> str:
    for value in values:
        if re.search(pattern, value, flags):
            return clean_spec_value(value)
    return ""


def extract_panel(values: list[str]) -> str:
    panel_keywords = [
        "QD-OLED",
        "OLED",
        "IPS Black",
        "Nano IPS",
        "Nano-IPS",
        "Fast IPS",
        "FAST IPS",
        "Rapid IPS",
        "AH-IPS",
        "IPS",
        "VA",
        "TN",
        "PLS",
        "ADS",
        "AHVA",
    ]
    for value in values:
        normalized = clean_spec_value(value)
        for keyword in panel_keywords:
            if normalized.lower() == keyword.lower():
                return normalized
    for value in values:
        normalized = clean_spec_value(value)
        for keyword in panel_keywords:
            if keyword.lower() in normalized.lower():
                return normalized
    return ""


def extract_shape(values: list[str]) -> str:
    for value in values:
        if re.search(r"(평면|커브드|곡면|벤더블)", value):
            return clean_spec_value(value)
    return ""


def extract_color(tokens: list[str]) -> str:
    for idx, token in enumerate(tokens):
        if token in {"[색상영역]", "색상영역"}:
            continue
        if token in {"색상", "[색상]"}:
            for next_token in tokens[idx + 1 : idx + 4]:
                if next_token not in {"/", ":"}:
                    return clean_spec_value(next_token)
        match = re.search(r"색상\s*:?\s*(.+)", token)
        if match and "색상영역" not in token:
            return clean_spec_value(match.group(1))
    return ""


def extract_color_from_text(text: str) -> str:
    color_words = [
        "스페이스 그레이",
        "다크 그레이",
        "라이트 그레이",
        "매트 블랙",
        "블랙",
        "화이트",
        "실버",
        "그레이",
        "핑크",
        "블루",
        "레드",
        "그린",
        "옐로우",
        "골드",
        "베이지",
        "브라운",
        "민트",
        "퍼플",
        "오렌지",
        "네이비",
        "Black",
        "White",
        "Silver",
        "Gray",
        "Grey",
    ]
    found: list[str] = []
    for word in color_words:
        if re.search(re.escape(word), text, re.I) and word not in found:
            found.append(word)
    return " / ".join(found)


def section_tokens(tokens: list[str], section_name: str) -> list[str]:
    section = f"[{section_name}]"
    if section not in tokens:
        return []
    start = tokens.index(section) + 1
    collected: list[str] = []
    for token in tokens[start:]:
        if token.startswith("[") and token.endswith("]"):
            break
        collected.append(token)
    return collected


def parse_monitor_specs(html: str) -> dict[str, str]:
    tokens = spec_tokens(html)
    values = value_tokens(tokens)
    special = section_tokens(tokens, "게임특화")

    return {
        "inch": first_matching(values, r"\d+(?:\.\d+)?\s*cm\s*\(\s*\d+(?:\.\d+)?\s*인치\s*\)|\d+(?:\.\d+)?\s*인치|\d+(?:\.\d+)?\s*cm"),
        "resolution": first_matching(values, r"[A-Za-z0-9+\- ]*\(?[0-9]{3,5}\s*x\s*[0-9]{3,5}\)?(?:\([A-Za-z0-9+\- ]+\))?", re.I),
        "refresh_rate": first_matching(values, r"\d+(?:\.\d+)?\s*Hz\b", re.I),
        "panel": extract_panel(values),
        "aspect_ratio": first_matching(values, r"\(\s*\d+\s*:\s*\d+\s*\)"),
        "shape": extract_shape(values),
        "color": extract_color(tokens),
        "special_features": join_tokens(special),
        "full_spec": join_tokens(tokens),
        "registration_month": parse_registration_month(html),
    }


def parse_registration_month(html: str) -> str:
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    match = re.search(r"등록월\s*:\s*(\d{4})\s*[./년]\s*(\d{1,2})", text)
    if not match:
        return ""
    return f"{match.group(1)}/{int(match.group(2)):02d}"


def empty_row(item: MonitorInput, collected_at: str, status: str, error: str = "") -> dict[str, str]:
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


def fetch_one(item: MonitorInput, collected_at: str, timeout: int, retries: int) -> dict[str, str]:
    last_error = ""
    for attempt in range(1, retries + 2):
        try:
            response = get_session().get(item.product_url, timeout=timeout)
            response.raise_for_status()
            specs = parse_monitor_specs(response.text)
            if not specs["full_spec"]:
                raise ValueError("spec_list not found")
            if not specs["color"]:
                specs["color"] = extract_color_from_text(item.product_name)
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


def crawl_monitor_specs(
    input_path: Path,
    output_path: Path,
    workers: int,
    timeout: int,
    retries: int,
    limit: int | None,
) -> tuple[int, int]:
    items = load_monitor_inputs(input_path, limit)
    collected_at = datetime.now().astimezone().isoformat(timespec="seconds")
    results: list[dict[str, str] | None] = [None] * len(items)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(fetch_one, item, collected_at, timeout, retries): item
            for item in items
        }
        done = 0
        for future in as_completed(futures):
            item = futures[future]
            results[item.index] = future.result()
            done += 1
            if done % 100 == 0 or done == len(items):
                print(f"monitor specs: {done}/{len(items)}")

    ordered = [row for row in results if row is not None]
    errors = sum(1 for row in ordered if row["fetch_status"] != "ok")
    write_csv(output_path, ordered)
    return len(ordered), errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect monitor specs from Danawa product pages.")
    parser.add_argument("--input", default="data/latest/monitor.csv", help="Input monitor CSV path.")
    parser.add_argument("--output", default="data/specs/monitor_specs.csv", help="Output specs CSV path.")
    parser.add_argument("--workers", type=int, default=24, help="Parallel worker count.")
    parser.add_argument("--timeout", type=int, default=20, help="Request timeout in seconds.")
    parser.add_argument("--retries", type=int, default=2, help="Retries per product.")
    parser.add_argument("--limit", type=int, help="Limit products for testing.")
    parser.add_argument("--fail-on-error", action="store_true", help="Exit with error if any product fails.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    total, errors = crawl_monitor_specs(
        input_path=Path(args.input),
        output_path=Path(args.output),
        workers=max(1, args.workers),
        timeout=args.timeout,
        retries=max(0, args.retries),
        limit=args.limit,
    )
    print(f"saved {total} monitor specs to {args.output} ({errors} errors)")
    if args.fail_on_error and errors:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
