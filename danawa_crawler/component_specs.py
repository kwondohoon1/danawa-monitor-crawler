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
from typing import Callable, Iterable

import requests

from danawa_crawler.core import DEFAULT_USER_AGENT, normalize_space
from danawa_crawler.monitor_specs import (
    has_spec_container,
    join_tokens,
    parse_registration_month,
    spec_tokens,
)


BASE_FIELDS = ["collected_at", "product_code", "product_name", "product_url"]
TAIL_FIELDS = ["full_spec", "registration_month", "fetch_status", "error"]

_thread_local = threading.local()


@dataclass(frozen=True)
class ComponentInput:
    index: int
    product_code: str
    product_name: str
    product_url: str


def spec_items(full_spec: str) -> list[str]:
    """Split a joined Danawa spec string into items, dropping [section] prefixes."""
    items = []
    for item in full_spec.split(" / "):
        item = normalize_space(re.sub(r"^(?:\[[^\]]*\]\s*)+", "", item))
        if item:
            items.append(item)
    return items


def labeled(items: Iterable[str], *labels: str) -> str:
    for label in labels:
        prefix = f"{label}:"
        for item in items:
            if item.startswith(prefix):
                return normalize_space(item[len(prefix) :])
    return ""


def matching(items: Iterable[str], pattern: str, flags: int = re.I) -> str:
    for item in items:
        if ":" in item:
            continue
        match = re.search(pattern, item, flags)
        if match:
            return match.group(0)
    return ""


def one_of(items: Iterable[str], candidates: Iterable[str]) -> str:
    item_list = list(items)
    for candidate in candidates:
        if candidate in item_list:
            return candidate
    return ""


def capacity_from_name(product_name: str) -> str:
    """Read the variant capacity Danawa appends to names, e.g. "(32GB(16Gx2))" or "(1TB)"."""
    match = re.search(r"\((\d+(?:\.\d+)?\s*[GT]B(?:\([^)]*\))?)\)\s*$", product_name, re.I)
    return match.group(1) if match else ""


def parse_gpu_specs(items: list[str], product_name: str) -> dict[str, str]:
    memory = re.search(r"\b(\d+)\s*GB\b", product_name, re.I)
    return {
        "chipset": items[0] if items and ":" not in items[0] and not items[0].startswith("PCIe") else "",
        "interface": matching(items, r"^PCIe[\d.]+x\d+(?:\(at x\d+\))?"),
        "memory_type": matching(items, r"^G?DDR\d+X?$|^HBM\d*e?$"),
        "memory_size": f"{memory.group(1)}GB" if memory else "",
        "base_clock": labeled(items, "베이스클럭"),
        "boost_clock": labeled(items, "부스트클럭"),
        "stream_processors": labeled(items, "스트림 프로세서", "쿠다 프로세서"),
        "memory_bandwidth": labeled(items, "VRAM 대역폭", "메모리 대역폭"),
        "outputs": labeled(items, "출력단자"),
        "power_consumption": labeled(items, "사용전력"),
        "recommended_psu": matching(items, r"^\d+W 이상$"),
        "power_connector": labeled(items, "전원 포트"),
        "length": labeled(items, "가로(길이)"),
        "thickness": labeled(items, "두께"),
        "fans": matching(items, r"^\d팬$"),
    }


def parse_ram_specs(items: list[str], product_name: str) -> dict[str, str]:
    features = [feature for feature in ["XMP3.0", "XMP", "EXPO", "온다이ECC", "ECC", "PMIC 언락"] if feature in items]
    return {
        "usage": one_of(items, ["데스크탑용", "노트북용", "서버용"]),
        "generation": matching(items, r"^DDR\d$"),
        "capacity": capacity_from_name(product_name),
        "speed": matching(items, r"^\d+\s*MHz.*$|^\d+\s*MT/s.*$"),
        "timing": labeled(items, "램타이밍"),
        "voltage": matching(items, r"^\d+(?:\.\d+)?V$"),
        "module_count": labeled(items, "램개수"),
        "heatsink": labeled(items, "히트싱크"),
        "led_color": labeled(items, "LED색상") or ("LED" if "LED 라이트" in items else ""),
        "height": labeled(items, "높이"),
        "features": " / ".join(features),
    }


def parse_ssd_specs(items: list[str], product_name: str) -> dict[str, str]:
    return {
        "form_factor": items[0] if items and ":" not in items[0] else "",
        "interface": matching(items, r"^(?:PCIe|SATA|NVMe|USB)[^:]*$"),
        "capacity": capacity_from_name(product_name),
        "nand": matching(items, r"^(?:SLC|MLC|TLC|QLC)(?:\s.*)?$"),
        "dram": one_of(items, ["DRAM 탑재", "DRAM 미탑재", "HMB 지원"]),
        "controller": labeled(items, "컨트롤러"),
        "seq_read": labeled(items, "순차읽기"),
        "seq_write": labeled(items, "순차쓰기"),
        "read_iops": labeled(items, "읽기IOPS"),
        "write_iops": labeled(items, "쓰기IOPS"),
        "tbw": labeled(items, "TBW"),
        "mtbf": labeled(items, "MTBF"),
        "warranty": labeled(items, "A/S기간"),
        "heatsink": one_of(items, ["방열판 포함", "방열판 미포함"]),
    }


@dataclass(frozen=True)
class ComponentSpec:
    slug: str
    category_code: str
    fields: list[str]
    parse: Callable[[list[str], str], dict[str, str]]

    @property
    def spec_fields(self) -> list[str]:
        return [*BASE_FIELDS, *self.fields, *TAIL_FIELDS]


def _fields(parser: Callable[[list[str], str], dict[str, str]]) -> list[str]:
    return list(parser([], "").keys())


COMPONENTS = {
    "gpu": ComponentSpec("gpu", "112753", _fields(parse_gpu_specs), parse_gpu_specs),
    "ram": ComponentSpec("ram", "112752", _fields(parse_ram_specs), parse_ram_specs),
    "ssd": ComponentSpec("ssd", "11229608", _fields(parse_ssd_specs), parse_ssd_specs),
}


def extract_component_specs(component: ComponentSpec, html: str, product_name: str = "") -> dict[str, str]:
    full_spec = join_tokens(spec_tokens(html))
    specs = component.parse(spec_items(full_spec), product_name)
    specs["full_spec"] = full_spec
    specs["registration_month"] = parse_registration_month(html)
    return specs


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


def load_component_inputs(component: ComponentSpec, path: Path, limit: int | None = None) -> list[ComponentInput]:
    rows: list[ComponentInput] = []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            product_code = normalize_space(row.get("product_code", ""))
            if not product_code:
                continue
            product_url = normalize_space(row.get("product_url", "")) or (
                f"https://prod.danawa.com/info/?pcode={product_code}&cate={component.category_code}"
            )
            rows.append(
                ComponentInput(
                    index=len(rows),
                    product_code=product_code,
                    product_name=normalize_space(row.get("product_name", "")),
                    product_url=product_url,
                )
            )
            if limit is not None and len(rows) >= limit:
                break
    return rows


def empty_row(
    component: ComponentSpec, item: ComponentInput, collected_at: str, status: str, error: str = ""
) -> dict[str, str]:
    row = {field: "" for field in component.spec_fields}
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


def fetch_one(
    component: ComponentSpec, item: ComponentInput, collected_at: str, timeout: int, retries: int
) -> dict[str, str]:
    last_error = ""
    for attempt in range(1, retries + 2):
        try:
            response = get_session().get(item.product_url, timeout=timeout)
            response.raise_for_status()
            specs = extract_component_specs(component, response.text, item.product_name)
            if not specs["full_spec"]:
                if has_spec_container(response.text):
                    # The page loaded but Danawa lists no specs for this product.
                    row = empty_row(component, item, collected_at, "no_spec")
                    row.update(specs)
                    return row
                raise ValueError("spec_list not found")
            row = empty_row(component, item, collected_at, "ok")
            row.update(specs)
            return row
        except Exception as exc:  # noqa: BLE001
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt <= retries:
                time.sleep(min(2.0, 0.25 * attempt))
    return empty_row(component, item, collected_at, "error", last_error)


def write_csv(path: Path, fields: list[str], rows: Iterable[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def crawl_component_specs(
    component: ComponentSpec,
    input_path: Path,
    output_path: Path,
    workers: int,
    timeout: int,
    retries: int,
    limit: int | None,
) -> tuple[int, int]:
    items = load_component_inputs(component, input_path, limit)
    collected_at = datetime.now().astimezone().isoformat(timespec="seconds")
    results: list[dict[str, str] | None] = [None] * len(items)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(fetch_one, component, item, collected_at, timeout, retries): item for item in items
        }
        done = 0
        for future in as_completed(futures):
            item = futures[future]
            results[item.index] = future.result()
            done += 1
            if done % 100 == 0 or done == len(items):
                print(f"{component.slug} specs: {done}/{len(items)}")

    ordered = [row for row in results if row is not None]
    errors = sum(1 for row in ordered if row["fetch_status"] == "error")
    write_csv(output_path, component.spec_fields, ordered)
    return len(ordered), errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect PC component (GPU/RAM/SSD) specs from Danawa product pages.")
    parser.add_argument("--category", required=True, choices=sorted(COMPONENTS), help="Component category.")
    parser.add_argument("--input", help="Input price CSV path. Defaults to data/latest/<category>.csv.")
    parser.add_argument("--output", help="Output specs CSV path. Defaults to data/specs/<category>_specs.csv.")
    parser.add_argument("--workers", type=int, default=24, help="Parallel worker count.")
    parser.add_argument("--timeout", type=int, default=20, help="Request timeout in seconds.")
    parser.add_argument("--retries", type=int, default=2, help="Retries per product.")
    parser.add_argument("--limit", type=int, help="Limit products for testing.")
    parser.add_argument("--fail-on-error", action="store_true", help="Exit with error if any product fails.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    component = COMPONENTS[args.category]
    output = args.output or f"data/specs/{component.slug}_specs.csv"
    total, errors = crawl_component_specs(
        component=component,
        input_path=Path(args.input or f"data/latest/{component.slug}.csv"),
        output_path=Path(output),
        workers=max(1, args.workers),
        timeout=args.timeout,
        retries=max(0, args.retries),
        limit=args.limit,
    )
    print(f"saved {total} {component.slug} specs to {output} ({errors} errors)")
    if args.fail_on_error and errors:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
