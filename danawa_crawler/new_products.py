from __future__ import annotations

import csv
from pathlib import Path


NEW_PRODUCT_FIELDS = ["product_code", "product_name", "first_collected_date"]
KNOWN_PRODUCT_FIELDS = ["product_code", "product_name"]


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


def update_new_products(output_dir: Path, category: str) -> tuple[int, int]:
    latest_path = output_dir / "latest" / f"{category}.csv"
    registry_path = output_dir / "new_products" / f"{category}.csv"
    known_path = output_dir / "state" / "known_products" / f"{category}.csv"

    collected_date, current_products = _read_latest(latest_path)
    initializing = not known_path.exists()
    known_products = _read_known_products(known_path)
    registry = {} if initializing else _read_registry(registry_path)

    added = 0
    for product_code, product_name in current_products.items():
        if product_code not in known_products and not initializing:
            registry[product_code] = {
                "product_code": product_code,
                "product_name": product_name,
                "first_collected_date": collected_date,
            }
            added += 1

        known_products[product_code] = product_name
        if product_code in registry:
            registry[product_code]["product_name"] = product_name

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

    known_path.parent.mkdir(parents=True, exist_ok=True)
    with known_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=KNOWN_PRODUCT_FIELDS)
        writer.writeheader()
        writer.writerows(
            {"product_code": code, "product_name": name}
            for code, name in sorted(known_products.items())
        )

    return added, len(rows)
