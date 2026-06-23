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
    parse_registration_month,
    value_tokens,
)


SPEC_FIELDS = [
    "collected_at",
    "product_code",
    "product_name",
    "product_url",
    "brand",
    "graphics",
    "cpu",
    "ram",
    "ssd",
    "operating_system",
    "inch",
    "weight",
    "resolution",
    "refresh_rate",
    "panel",
    "cpu_brand",
    "cpu_model",
    "cpu_cores",
    "npu",
    "graphics_type",
    "graphics_model",
    "graphics_memory",
    "ram_type",
    "ram_slots",
    "storage_slot",
    "wireless",
    "battery",
    "ports",
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
        if normalize_label(value) not in labels:
            continue
        collected: list[str] = []
        for token in values[index + 1 :]:
            if normalize_label(token) in stop_labels:
                break
            collected.append(token)
        return " / ".join(clean_spec_value(token) for token in collected if clean_spec_value(token))
    return ""


def normalize_label(value: str) -> str:
    return value.strip().strip("[]")


def laptop_spec_tokens(html: str) -> list[str]:
    match = re.search(
        r'<div[^>]*class=["\'][^"\']*\bspec_list\b[^"\']*["\'][^>]*>\s*'
        r'<div[^>]*class=["\'][^"\']*\bitems\b[^"\']*["\'][^>]*>(.*?)</div>',
        html,
        re.I | re.S,
    )
    if not match:
        soup = BeautifulSoup(html, "html.parser")
        spec = soup.select_one(".spec_list .items") or soup.select_one(".spec_list")
        if not spec:
            return []
        return [normalize_space(token) for token in spec.stripped_strings if normalize_space(token)]
    fragment = BeautifulSoup(match.group(1), "html.parser")
    return [normalize_space(token) for token in fragment.stripped_strings if normalize_space(token)]


def labeled_value(full_spec: str, labels: Iterable[str], value_pattern: str, flags: int = re.I) -> str:
    for label in labels:
        match = re.search(rf"{re.escape(label)}\s*:?\s*({value_pattern})", full_spec, flags)
        if match:
            return clean_spec_value(match.group(1))
    return ""


def extract_operating_system(values: list[str]) -> str:
    return first_matching(values, r"(윈도우|Windows|OS미포함|프리도스|FreeDOS|리눅스|Linux|macOS|크롬OS)", re.I)


def extract_brand(product_name: str) -> str:
    brand_patterns = [
        ("ACER", r"\bACER\b|에이서"),
        ("ASUS", r"\bASUS\b|에이수스"),
        ("DELL", r"\bDELL\b|델"),
        ("GIGABYTE", r"\bGIGABYTE\b|기가바이트"),
        ("MSI", r"\bMSI\b"),
        ("LENOVO", r"\bLENOVO\b|레노버"),
        ("HP", r"\bHP\b"),
        ("삼성", r"삼성전자|삼성"),
        ("LG", r"LG전자|\bLG\b"),
    ]
    for brand, pattern in brand_patterns:
        if re.search(pattern, product_name, re.I):
            return brand
    return ""


def collect_section(values: list[str], label: str) -> list[str]:
    stop_labels = {
        "화면",
        "화면정보",
        "CPU",
        "NPU",
        "그래픽",
        "램",
        "구성",
        "저장장치",
        "네트워크",
        "영상입출력",
        "단자",
        "입력장치",
        "파워",
        "전원",
        "배터리",
        "주요제원",
        "용도",
    }
    for index, value in enumerate(values):
        if normalize_label(value) != label:
            continue
        collected: list[str] = []
        for token in values[index + 1 :]:
            normalized = normalize_label(token)
            if normalized in stop_labels and normalized != label:
                break
            collected.append(token)
        return collected
    return []


def extract_cpu(values: list[str]) -> str:
    stop_labels = {"NPU", "그래픽", "램", "구성", "저장장치", "전원", "배터리", "용도", "화면", "화면정보"}
    return collect_after_label(values, {"CPU"}, stop_labels)


def extract_graphics(values: list[str]) -> str:
    stop_labels = {"TGP", "램", "구성", "저장장치", "전원", "배터리", "용도", "화면", "화면정보", "CPU"}
    return collect_after_label(values, {"그래픽"}, stop_labels)


def first_from_section(values: list[str], label: str, pattern: str, flags: int = re.I) -> str:
    return first_matching(collect_section(values, label), pattern, flags)


def compact_section_values(values: list[str], label: str, pattern: str, flags: int = re.I) -> str:
    matched = [clean_spec_value(value) for value in collect_section(values, label) if re.search(pattern, value, flags)]
    return " / ".join(dict.fromkeys(matched))


def extract_ports(values: list[str]) -> str:
    patterns = r"(USB|썬더볼트|Thunderbolt|HDMI|DP|DisplayPort|LAN|RJ-?45|카드리더|오디오|헤드폰)"
    matched = [
        clean_spec_value(value)
        for value in values
        if re.search(patterns, value, re.I) and not re.search(r"CPU|그래픽|램", value)
    ]
    return " / ".join(dict.fromkeys(matched[:12]))


def parse_laptop_specs(html: str, product_name: str = "") -> dict[str, str]:
    tokens = laptop_spec_tokens(html)
    values = value_tokens(tokens)
    full_spec = join_tokens(tokens)
    cpu = extract_cpu(values)
    graphics = extract_graphics(values)
    cpu_values = collect_section(values, "CPU")
    graphics_values = collect_section(values, "그래픽")

    return {
        "brand": extract_brand(product_name),
        "inch": first_matching(values, r"\d+(?:\.\d+)?\s*cm\s*\(\s*\d+(?:\.\d+)?\s*인치\s*\)|\d+(?:\.\d+)?\s*인치|\d+(?:\.\d+)?\s*cm"),
        "weight": first_matching(values, r"\d+(?:\.\d+)?\s*kg\b", re.I),
        "operating_system": extract_operating_system(values),
        "resolution": first_matching(values, r"[A-Za-z0-9+\- ]*\(?[0-9]{3,5}\s*x\s*[0-9]{3,5}\)?(?:\([A-Za-z0-9+\- ]+\))?", re.I),
        "refresh_rate": first_matching(values, r"\d+(?:\.\d+)?\s*Hz\b", re.I),
        "panel": first_matching(values, r"(OLED|AMOLED|IPS|WVA|TN|VA|미니\s*LED|Mini\s*LED|터치스크린)", re.I),
        "cpu": cpu,
        "cpu_brand": first_matching(cpu_values, r"(인텔|Intel|AMD|애플|Apple|퀄컴|Qualcomm)", re.I),
        "cpu_model": first_matching(cpu_values, r"(코어\s*울트라|코어\s*\d|Core\s*Ultra|Core\s*i[3579]|라이젠\s*\d|Ryzen\s*\d|M[1-9]|스냅드래곤|Snapdragon|\d{3,5}[A-Z]{0,2}|[A-Z0-9]{3,}[- ][A-Z0-9]{2,})", re.I),
        "cpu_cores": labeled_value(full_spec, ["코어", "코어 수"], r"\d+\s*코어"),
        "npu": first_matching(values, r"\d+(?:\.\d+)?\s*TOPS\b", re.I),
        "graphics": graphics,
        "graphics_type": first_matching(graphics_values, r"(외장그래픽|내장그래픽|통합그래픽)", re.I),
        "graphics_model": first_matching(graphics_values, r"(RTX\s*\d{4}|GTX\s*\d{3,4}|Arc\s*[A-Z0-9]+|Radeon\s*[A-Z0-9 ]+|Intel\s*Graphics|Iris\s*Xe|UHD\s*Graphics|Adreno\s*[A-Z0-9]+|Mali\s*[A-Z0-9]+)", re.I),
        "graphics_memory": labeled_value(full_spec, ["VRAM", "그래픽 메모리"], r"\d+(?:\.\d+)?\s*(?:GB|MB)"),
        "ram": labeled_value(full_spec, ["램"], r"\d+(?:\.\d+)?\s*(?:GB|TB)")
        or first_matching(collect_section(values, "구성"), r"\d+(?:\.\d+)?\s*(?:GB|TB)"),
        "ram_type": first_matching(values, r"(LPDDR\dX?|DDR\d|온보드|SO-DIMM)", re.I),
        "ram_slots": first_matching(values, r"(램\s*교체|메모리\s*슬롯|슬롯\s*\d+개|온보드)", re.I),
        "ssd": labeled_value(full_spec, ["SSD", "용량"], r"\d+(?:\.\d+)?\s*(?:TB|GB)"),
        "storage_slot": first_matching(values, r"(M\.2|NVMe|저장\s*슬롯|슬롯\s*\d+개)", re.I),
        "wireless": compact_section_values(values, "네트워크", r"(Wi-?Fi|802\.11|무선랜|블루투스|Bluetooth)", re.I),
        "battery": first_matching(values, r"\d+(?:\.\d+)?\s*(?:Wh|mAh)\b", re.I),
        "ports": extract_ports(values),
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
            specs = parse_laptop_specs(response.text, item.product_name)
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
