from __future__ import annotations

import csv
import re
from pathlib import Path


DATE_FIELD = re.compile(r"^\d{4}-\d{2}-\d{2}$")
NEW_PRODUCT_FIELDS = ["product_code", "product_name", "first_collected_date"]


def _read_latest(path: Path) -> tuple[str, dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        date_fields = [field for field in (reader.fieldnames or []) if DATE_FIELD.match(field)]
        if not date_fields:
            raise ValueError(f"No collection date found in {path}")

        products = {
            row["product_code"].strip(): row.get("product_name", "").strip()
            for row in reader
            if row.get("product_code", "").strip()
        }
    return max(date_fields), products


def _read_first_seen_from_history(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        date_fields = sorted(field for field in (reader.fieldnames or []) if DATE_FIELD.match(field))
        first_seen: dict[str, str] = {}
        for row in reader:
            product_code = row.get("product_code", "").strip()
            if not product_code:
                continue
            for date_field in date_fields:
                value = row.get(date_field, "").strip().replace(",", "")
                if value.isdigit() and int(value) > 0:
                    first_seen[product_code] = date_field
                    break
        return first_seen


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


def update_new_products(output_dir: Path, category: str) -> tuple[int, int]:
    latest_path = output_dir / "latest" / f"{category}.csv"
    history_path = output_dir / "history" / f"{category}_price_history.csv"
    registry_path = output_dir / "new_products" / f"{category}.csv"

    collected_date, current_products = _read_latest(latest_path)
    registry = _read_registry(registry_path)
    history_first_seen = _read_first_seen_from_history(history_path) if not registry else {}

    added = 0
    for product_code, product_name in current_products.items():
        if product_code in registry:
            registry[product_code]["product_name"] = product_name
            continue

        registry[product_code] = {
            "product_code": product_code,
            "product_name": product_name,
            "first_collected_date": history_first_seen.get(product_code, collected_date),
        }
        added += 1

    rows = sorted(
        registry.values(),
        key=lambda row: (row["first_collected_date"], row["product_code"]),
        reverse=True,
    )
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    with registry_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=NEW_PRODUCT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    return added, len(rows)
