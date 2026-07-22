from __future__ import annotations

import csv
import re
from pathlib import Path


NEW_PRODUCT_FIELDS = ["product_code", "product_name", "first_collected_date"]
KNOWN_PRODUCT_FIELDS = ["product_code", "product_name"]
MIN_NEW_PRODUCT_CODE = 122_000_000
EXCLUDED_NAME_KEYWORDS = ("중고", "해외구매")

# Categories whose specs CSV carries Danawa's registration month; their
# new-product registry is rebuilt from that field instead of the code threshold.
SPEC_BACKED_CATEGORIES = ("monitor",)
REGISTRATION_WINDOW_MONTHS = 3
_REGISTRATION_MONTH_PATTERN = re.compile(r"^(\d{4})/(\d{2})$")


def _has_excluded_keyword(product_name: str) -> bool:
    compact_name = "".join(product_name.split())
    return any(keyword in compact_name for keyword in EXCLUDED_NAME_KEYWORDS)


def is_new_product_candidate(product_code: str, product_name: str) -> bool:
    if not product_code.isdigit() or int(product_code) < MIN_NEW_PRODUCT_CODE:
        return False
    return not _has_excluded_keyword(product_name)


def _recent_registration_months(collected_date: str) -> set[str]:
    year, month = int(collected_date[:4]), int(collected_date[5:7])
    months = set()
    for offset in range(REGISTRATION_WINDOW_MONTHS):
        y, m = year, month - offset
        while m < 1:
            y, m = y - 1, m + 12
        months.add(f"{y:04d}/{m:02d}")
    return months


def _is_recent_registration(registration_month: str, allowed_months: set[str]) -> bool:
    if not _REGISTRATION_MONTH_PATTERN.match(registration_month):
        return False
    return registration_month in allowed_months


def _read_latest(path: Path) -> tuple[str, dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        date_fields = [
            field
            for field in (reader.fieldnames or [])
            if len(field) == 10 and field[4] == "-" and field[7] == "-"
        ]
        if not date_fields:
            raise ValueError(f"No collection date found in {path}")

        products = {
            row["product_code"].strip(): row.get("product_name", "").strip()
            for row in reader
            if row.get("product_code", "").strip()
        }
    return max(date_fields), products


def _read_registry(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return {
            row["product_code"].strip(): {
                "product_code": row["product_code"].strip(),
                "product_name": row.get("product_name", "").strip(),
                "first_collected_date": row.get("first_collected_date", "").strip(),
            }
            for row in csv.DictReader(file)
            if row.get("product_code", "").strip()
        }


def _read_known_products(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return {
            row["product_code"].strip(): row.get("product_name", "").strip()
            for row in csv.DictReader(file)
            if row.get("product_code", "").strip()
        }


def _read_specs(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return {
            row["product_code"].strip(): {
                "product_name": row.get("product_name", "").strip(),
                "registration_month": row.get("registration_month", "").strip(),
            }
            for row in csv.DictReader(file)
            if row.get("product_code", "").strip()
        }


def rebuild_new_products_from_specs(output_dir: Path, category: str) -> tuple[int, int]:
    latest_path = output_dir / "latest" / f"{category}.csv"
    specs_path = output_dir / "specs" / f"{category}_specs.csv"
    registry_path = output_dir / "new_products" / f"{category}.csv"

    collected_date, _ = _read_latest(latest_path)
    allowed_months = _recent_registration_months(collected_date)
    previous_registry = _read_registry(registry_path)
    specs = _read_specs(specs_path)

    rows = []
    added = 0
    for product_code, spec in sorted(
        specs.items(),
        key=lambda item: (item[1]["registration_month"], item[0]),
        reverse=True,
    ):
        if not _is_recent_registration(spec["registration_month"], allowed_months):
            continue
        if _has_excluded_keyword(spec["product_name"]):
            continue
        previous = previous_registry.get(product_code)
        if previous is None:
            added += 1
        rows.append(
            {
                "product_code": product_code,
                "product_name": spec["product_name"],
                "first_collected_date": previous["first_collected_date"]
                if previous and previous["first_collected_date"]
                else collected_date,
            }
        )

    registry_path.parent.mkdir(parents=True, exist_ok=True)
    with registry_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=NEW_PRODUCT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    return added, len(rows)


def update_new_products(output_dir: Path, category: str) -> tuple[int, int]:
    if category in SPEC_BACKED_CATEGORIES:
        return rebuild_new_products_from_specs(output_dir, category)

    latest_path = output_dir / "latest" / f"{category}.csv"
    registry_path = output_dir / "new_products" / f"{category}.csv"
    known_path = output_dir / "state" / "known_products" / f"{category}.csv"

    collected_date, current_products = _read_latest(latest_path)
    initializing = not known_path.exists()
    known_products = _read_known_products(known_path)
    registry = {} if initializing else _read_registry(registry_path)
    registry = {
        code: row
        for code, row in registry.items()
        if is_new_product_candidate(code, row["product_name"])
    }

    added = 0
    for product_code, product_name in current_products.items():
        eligible = is_new_product_candidate(product_code, product_name)
        if product_code not in known_products and not initializing and eligible:
            registry[product_code] = {
                "product_code": product_code,
                "product_name": product_name,
                "first_collected_date": collected_date,
            }
            added += 1

        known_products[product_code] = product_name
        if product_code in registry:
            if eligible:
                registry[product_code]["product_name"] = product_name
            else:
                del registry[product_code]

    rows = list(registry.values())
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    with registry_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=NEW_PRODUCT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    known_path.parent.mkdir(parents=True, exist_ok=True)
    with known_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=KNOWN_PRODUCT_FIELDS)
        writer.writeheader()
        writer.writerows(
            {"product_code": code, "product_name": name}
            for code, name in sorted(known_products.items())
        )

    return added, len(rows)
