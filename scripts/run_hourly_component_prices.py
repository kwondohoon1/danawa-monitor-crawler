"""Stay alive around the clock and crawl GPU/RAM/SSD prices at the top of every hour 07:00-18:00 KST.

GitHub's scheduled runs start hours late (the first morning run often after 09:00), so the runner
never stops: it waits for each hour itself, keeps waiting through the night for tomorrow's 07:00,
and hands over to a fresh run (workflow_dispatch) shortly before the 6-hour job limit.
The schedule is only a watchdog that restarts the chain if it ever breaks.
"""

import argparse
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import timedelta


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from danawa_crawler.hourly_prices import (  # noqa: E402
    HOURLY_CATEGORIES,
    current_slot,
    next_collection,
    now_kst,
    prune_old_days,
    record_hour,
    slot_done,
    update_readme,
)
from danawa_crawler.open_market import collect_open_market  # noqa: E402
from danawa_crawler.price_outliers import fix_price_outliers  # noqa: E402


def run(command: list[str], check: bool = True) -> subprocess.CompletedProcess:
    print("+", " ".join(command), flush=True)
    return subprocess.run(command, cwd=ROOT, check=check)


def crawl(categories: list[str]) -> bool:
    args = [arg for category in categories for arg in ("--category", category)]
    for attempt in range(1, 3):
        result = run(
            [sys.executable, "scripts/crawl_danawa.py", *args, "--fail-on-empty", "--fetcher", "requests",
             "--max-pages", "100", "--delay", "0.1", "--skip-combined"],
            check=False,
        )
        if result.returncode == 0:
            run([sys.executable, "scripts/update_new_products.py", *args])
            return True
        print(f"crawl failed (attempt {attempt}, exit {result.returncode})", flush=True)
        time.sleep(60)
    return False


def commit_and_push(categories: list[str], message: str) -> None:
    paths = ["README.md", "data/hourly"]
    for category in categories:
        paths += [
            f"data/latest/{category}.csv",
            f"data/latest/{category}_open.csv",
            f"data/history/{category}_price_history.csv",
            f"data/new_products/{category}.csv",
            f"data/state/known_products/{category}.csv",
        ]
    run(["git", "add", "-A", "--", *paths])
    if run(["git", "diff", "--cached", "--quiet"], check=False).returncode == 0:
        print("No CSV changes", flush=True)
        return
    run(["git", "commit", "-m", message])
    for attempt in range(1, 6):
        run(["git", "pull", "--rebase", "origin", "main"], check=False)
        if run(["git", "push"], check=False).returncode == 0:
            return
        time.sleep(10 * attempt)
    raise RuntimeError("git push failed")


def collect(day: str, hour: int, categories: list[str], use_git: bool) -> None:
    collected_at = now_kst().isoformat(timespec="seconds")
    if not crawl(categories):
        print(f"{day} {hour:02d}:00 crawl failed; will retry at the next hour", flush=True)
        return
    output_dir = ROOT / "data"
    try:
        # 판매처 한 곳의 비정상 최저가(사기 의심)를 쇼핑몰별 가격으로 바로잡는다. 실패해도 수집은 계속
        fix_price_outliers(output_dir, day, hour, categories)
    except Exception as error:
        print(f"price outlier check failed: {error}", flush=True)
    try:
        # 오픈마켓(11번가·G마켓·옥션·스마트스토어)만의 최저가와 배송비. 실패해도 수집은 계속
        collect_open_market(output_dir, day, hour, categories)
    except Exception as error:
        print(f"open-market prices failed: {error}", flush=True)
    record_hour(output_dir, day, hour, collected_at, categories)
    removed = prune_old_days(output_dir, day)
    if removed:
        print("removed old hourly folders:", ", ".join(removed), flush=True)
    update_readme(ROOT / "README.md", output_dir, day)
    if use_git:
        commit_and_push(categories, f"Update GPU RAM SSD price CSV {day} {hour:02d}:00")


def hand_over() -> None:
    workflow = os.environ.get("HOURLY_WORKFLOW_FILE", "update-component-prices.yml")
    run(["gh", "workflow", "run", workflow, "--ref", "main"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--category", action="append", choices=HOURLY_CATEGORIES)
    parser.add_argument("--max-minutes", type=int, default=330, help="Hand over to a new run after this long.")
    parser.add_argument("--once", action="store_true", help="Collect the current hour (if due) and exit.")
    parser.add_argument("--no-git", action="store_true", help="Do not pull, commit, push or hand over.")
    args = parser.parse_args()

    categories = args.category or list(HOURLY_CATEGORIES)
    use_git = not args.no_git
    deadline = now_kst() + timedelta(minutes=args.max_minutes)

    while True:
        now = now_kst()
        day, hour = now.date().isoformat(), current_slot(now)
        if hour is not None:
            if use_git:
                run(["git", "pull", "--rebase", "origin", "main"], check=False)
            if slot_done(ROOT / "data", day, hour, categories):
                print(f"{day} {hour:02d}:00 already collected", flush=True)
            else:
                collect(day, hour, categories, use_git)

        if args.once:
            return 0
        upcoming = next_collection(now_kst())
        if not use_git and upcoming.date() != now_kst().date():
            print("Today's 07:00-18:00 window is finished", flush=True)
            return 0
        if upcoming + timedelta(minutes=10) > deadline:
            # 다음 수집이 이 실행의 시간 안에 안 들어오면, 시간 한도 직전까지 기다렸다가 새 실행에 넘긴다
            # (밤새 체인을 이어 다음 날 07:00 에 이미 떠 있도록 — GitHub 예약 실행은 몇 시간씩 늦게 옴)
            hand_at = deadline - timedelta(minutes=5)
            wait = (hand_at - now_kst()).total_seconds()
            if wait > 0:
                print(f"Next collection {upcoming:%m-%d %H:%M}; waiting {wait / 60:.0f} min, then handing over", flush=True)
                time.sleep(wait)
            print(f"Handing over before {upcoming:%m-%d %H:%M} (job time limit)", flush=True)
            if use_git:
                hand_over()
            return 0
        wait = (upcoming - now_kst()).total_seconds()
        print(f"Sleeping {wait / 60:.1f} min until {upcoming:%Y-%m-%d %H:%M} KST", flush=True)
        time.sleep(max(0, wait) + 5)


if __name__ == "__main__":
    raise SystemExit(main())
