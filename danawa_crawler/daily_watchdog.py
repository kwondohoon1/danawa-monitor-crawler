"""하루 한 번 도는 수집(모니터 가격·스펙, 키보드, 노트북, TV, PC부품)이 실패하면 그날 안에 다시 돌린다.

2026-11-12 오전 다나와가 GitHub 서버 접속을 몇 시간 동안 403 으로 막아, 그 시간에 돈 하루 수집이
전부 실패하고 다음 날까지 그대로 멈췄다. 24시간 떠 있는 매시 가격 작업(run_hourly_component_prices.py)이
몇 분마다 이 검사를 불러, 오늘 실행됐는데 성공이 없는 수집을 다시 실행시킨다.

하루 수집들은 같은 동시 실행 그룹(danawa-data-updates)이라 '대기 중' 실행은 하나만 남고 나머지는
취소된다. 그래서 그룹에서 도는/대기 중인 실행이 없을 때만, 한 번에 하나씩 다시 실행한다.
오늘 예약 실행이 아직 안 온 수집은 건드리지 않는다(GitHub 예약은 몇 시간씩 늦게 옴).
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
DAILY_WORKFLOWS = [  # 다시 돌릴 우선순위
    "update-danawa-prices.yml",
    "update-monitor-specs.yml",
    "update-keyboard-prices.yml",
    "update-laptop-prices.yml",
    "update-tv-prices.yml",
    "update-extra-prices.yml",
    "update-keyboard-specs.yml",
    "update-tv-specs.yml",
    "update-laptop-specs.yml",
]
ACTIVE = {"queued", "in_progress", "waiting", "pending", "requested"}
MAX_RUNS_PER_DAY = 6                  # 예약 실행 포함, 하루에 이만큼 돌았으면 포기
COOL_DOWN = timedelta(minutes=40)     # 실패 뒤 이만큼 지나야 다시 돌림 (차단이 풀릴 시간)


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def pick_retry(runs_by_workflow: dict[str, list[dict]], now: datetime) -> str | None:
    """다시 돌릴 워크플로 하나 (없으면 None). runs 는 `gh run list --json status,conclusion,createdAt,updatedAt` 결과."""
    if any(run.get("status") in ACTIVE for runs in runs_by_workflow.values() for run in runs):
        return None
    day_start = now.astimezone(KST).replace(hour=0, minute=0, second=0, microsecond=0)
    for workflow in DAILY_WORKFLOWS:
        today = [run for run in runs_by_workflow.get(workflow, []) if _time(run["createdAt"]) >= day_start]
        if not today or any(run.get("conclusion") == "success" for run in today):
            continue
        if len(today) >= MAX_RUNS_PER_DAY:
            continue
        last = max(_time(run.get("updatedAt") or run["createdAt"]) for run in today)
        if now - last < COOL_DOWN:
            continue
        return workflow
    return None


def _gh(args: list[str], cwd: Path) -> str:
    return subprocess.run(["gh", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def retry_failed_daily_runs(cwd: Path, now: datetime | None = None) -> str | None:
    """실패한 하루 수집 하나를 다시 실행하고 그 워크플로 이름을 돌려준다."""
    runs = {}
    for workflow in DAILY_WORKFLOWS:
        runs[workflow] = json.loads(_gh(["run", "list", "--workflow", workflow, "--limit", "15",
                                         "--json", "status,conclusion,createdAt,updatedAt"], cwd))
    workflow = pick_retry(runs, now or datetime.now(timezone.utc))
    if workflow:
        _gh(["workflow", "run", workflow, "--ref", "main"], cwd)
        print(f"daily watchdog: {workflow} has no successful run today -> started it again", flush=True)
    return workflow
