"""Hourly GPU/RAM/SSD price snapshots (07:00-18:00 KST) and the README index for them."""

from __future__ import annotations

import csv
import re
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

from .core import KST, write_csv


HOURLY_CATEGORIES = ("gpu", "ram", "ssd")
CATEGORY_LABELS = {"gpu": "그래픽카드", "ram": "RAM", "ssd": "SSD"}
FIRST_HOUR = 7
LAST_HOUR = 18
SNAPSHOT_RETENTION_DAYS = 7
MANIFEST_FIELDS = ["hour", "category", "collected_at", "products"]
REPO_BLOB_URL = "https://github.com/kwondohoon1/danawa-monitor-crawler/blob/main"
README_START = "<!-- hourly-prices:start -->"
README_END = "<!-- hourly-prices:end -->"
_DATE_DIR = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def hour_label(hour: int) -> str:
    return f"{hour:02d}:00"


def day_dir(output_dir: Path, day: str) -> Path:
    return output_dir / "hourly" / day


def snapshot_path(output_dir: Path, day: str, category: str, hour: int) -> Path:
    return day_dir(output_dir, day) / f"{category}_{hour:02d}.csv"


def next_slot(now: datetime) -> datetime | None:
    """Start of the next collection hour after ``now``, or None when today's window is over."""
    candidate = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    if candidate.date() == now.date() and candidate.hour < FIRST_HOUR:
        candidate = candidate.replace(hour=FIRST_HOUR)
    if candidate.date() != now.date() or candidate.hour > LAST_HOUR:
        return None
    return candidate


def current_slot(now: datetime) -> int | None:
    return now.hour if FIRST_HOUR <= now.hour <= LAST_HOUR else None


def read_manifest(output_dir: Path, day: str) -> list[dict[str, str]]:
    path = day_dir(output_dir, day) / "collected.csv"
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def slot_done(output_dir: Path, day: str, hour: int, categories=HOURLY_CATEGORIES) -> bool:
    done = {row["category"] for row in read_manifest(output_dir, day) if row.get("hour") == f"{hour:02d}"}
    return set(categories) <= done


def _today_prices(latest_csv: Path, day: str) -> list[tuple[str, str, str]]:
    with latest_csv.open("r", encoding="utf-8-sig", newline="") as file:
        return [(row["product_code"], row["product_name"], row.get(day, "")) for row in csv.DictReader(file)]


def record_hour(output_dir: Path, day: str, hour: int, collected_at: str, categories=HOURLY_CATEGORIES) -> None:
    """Copy today's column of data/latest/<category>.csv into the hourly snapshot and day table."""
    target = day_dir(output_dir, day)
    manifest = [row for row in read_manifest(output_dir, day) if not (row["hour"] == f"{hour:02d}" and row["category"] in categories)]

    for category in categories:
        rows = _today_prices(output_dir / "latest" / f"{category}.csv", day)
        write_csv(
            snapshot_path(output_dir, day, category, hour),
            ["product_code", "product_name", "price"],
            ({"product_code": code, "product_name": name, "price": price} for code, name, price in rows),
        )
        manifest.append({"hour": f"{hour:02d}", "category": category, "collected_at": collected_at, "products": str(len(rows))})
        _write_day_table(output_dir, day, category)

    manifest.sort(key=lambda row: (row["hour"], HOURLY_CATEGORIES.index(row["category"]) if row["category"] in HOURLY_CATEGORIES else 99))
    write_csv(target / "collected.csv", MANIFEST_FIELDS, manifest)


def _write_day_table(output_dir: Path, day: str, category: str) -> None:
    """One row per product, one column per collected hour (07:00 ... 18:00)."""
    names: dict[str, str] = {}
    prices: dict[str, dict[str, str]] = {}
    hours: list[str] = []
    for hour in range(FIRST_HOUR, LAST_HOUR + 1):
        path = snapshot_path(output_dir, day, category, hour)
        if not path.exists():
            continue
        label = hour_label(hour)
        hours.append(label)
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            for row in csv.DictReader(file):
                names[row["product_code"]] = row["product_name"]
                prices.setdefault(row["product_code"], {})[label] = row["price"]

    rows = [{"product_code": code, "product_name": name, **prices[code]} for code, name in names.items()]
    rows.sort(key=lambda row: row["product_name"])
    write_csv(day_dir(output_dir, day) / f"{category}.csv", ["product_code", "product_name", *hours], rows)


def prune_old_days(output_dir: Path, today: str, keep_days: int = SNAPSHOT_RETENTION_DAYS) -> list[str]:
    root = output_dir / "hourly"
    if not root.exists():
        return []
    oldest = date.fromisoformat(today) - timedelta(days=keep_days - 1)
    removed = []
    for child in root.iterdir():
        if child.is_dir() and _DATE_DIR.match(child.name) and date.fromisoformat(child.name) < oldest:
            shutil.rmtree(child)
            removed.append(child.name)
    return sorted(removed)


def _link(path: Path, output_dir: Path, text: str) -> str:
    relative = path.relative_to(output_dir.parent).as_posix()
    return f"[{text}]({REPO_BLOB_URL}/{relative})"


def render_readme_section(output_dir: Path, today: str) -> str:
    manifest = {(row["hour"], row["category"]): row for row in read_manifest(output_dir, today)}
    lines = [
        README_START,
        f"## 그래픽카드 · RAM · SSD 시간대별 가격 (오늘: {today})",
        "",
        "07:00~18:00 KST 매시 정각에 다나와 최저가를 수집합니다. 링크를 누르면 그 시간에 수집한 가격 CSV가 열립니다.",
        "",
    ]

    day_links = [
        _link(day_dir(output_dir, today) / f"{category}.csv", output_dir, f"{CATEGORY_LABELS[category]} 오늘 시간대별 모아보기")
        for category in HOURLY_CATEGORIES
        if (day_dir(output_dir, today) / f"{category}.csv").exists()
    ]
    if day_links:
        lines += [" · ".join(day_links), ""]

    lines += ["| 시간 | 수집 시각 | " + " | ".join(CATEGORY_LABELS[c] for c in HOURLY_CATEGORIES) + " |"]
    lines += ["|---|---|" + "---|" * len(HOURLY_CATEGORIES)]
    for hour in range(FIRST_HOUR, LAST_HOUR + 1):
        key = f"{hour:02d}"
        collected = [manifest[(key, c)]["collected_at"] for c in HOURLY_CATEGORIES if (key, c) in manifest]
        when = collected[0][11:16] if collected else "대기"
        cells = []
        for category in HOURLY_CATEGORIES:
            row = manifest.get((key, category))
            cells.append(
                _link(snapshot_path(output_dir, today, category, hour), output_dir, f"{int(row['products']):,}개")
                if row
                else "—"
            )
        lines.append(f"| {hour_label(hour)} | {when} | " + " | ".join(cells) + " |")

    root = output_dir / "hourly"
    past_days = sorted(
        (child.name for child in root.iterdir() if child.is_dir() and _DATE_DIR.match(child.name) and child.name < today),
        reverse=True,
    ) if root.exists() else []
    if past_days:
        lines += ["", f"지난 {SNAPSHOT_RETENTION_DAYS}일 시간대별 기록:", ""]
        for day in past_days:
            links = [
                _link(day_dir(output_dir, day) / f"{category}.csv", output_dir, CATEGORY_LABELS[category])
                for category in HOURLY_CATEGORIES
                if (day_dir(output_dir, day) / f"{category}.csv").exists()
            ]
            lines.append(f"- {day}: " + " · ".join(links))

    lines.append(README_END)
    return "\n".join(lines)


def update_readme(readme: Path, output_dir: Path, today: str, insert_before: str = "## 가격정보 바로가기") -> None:
    text = readme.read_text(encoding="utf-8")
    section = render_readme_section(output_dir, today)
    if README_START in text and README_END in text:
        start = text.index(README_START)
        end = text.index(README_END) + len(README_END)
        text = text[:start] + section + text[end:]
    elif insert_before in text:
        index = text.index(insert_before)
        text = text[:index] + section + "\n\n" + text[index:]
    else:
        text = text.rstrip("\n") + "\n\n" + section + "\n"
    readme.write_text(text, encoding="utf-8")


def now_kst() -> datetime:
    return datetime.now(KST)
