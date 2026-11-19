import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from danawa_crawler.daily_watchdog import DAILY_WORKFLOWS, due_times, pick_retry

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 12, 11, 30, tzinfo=KST)  # 11-12 오전, 다나와가 GitHub 서버를 막았던 날


def run(minutes_ago: int, conclusion: str | None = "failure", status: str = "completed", length: int = 2) -> dict:
    created = NOW - timedelta(minutes=minutes_ago)
    return {
        "status": status,
        "conclusion": conclusion,
        "createdAt": created.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "updatedAt": (created + timedelta(minutes=length)).astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


class DailyWatchdogTests(unittest.TestCase):
    def test_failed_today_is_retried(self):
        runs = {"update-danawa-prices.yml": [run(90)]}
        self.assertEqual(pick_retry(runs, NOW), "update-danawa-prices.yml")

    def test_nothing_while_any_daily_run_is_queued_or_running(self):
        # 같은 동시 실행 그룹이라 대기 중인 실행이 새 실행에 밀려 취소된다 -> 그룹이 빌 때까지 기다림
        runs = {"update-danawa-prices.yml": [run(90)],
                "update-keyboard-specs.yml": [run(5, conclusion=None, status="in_progress")]}
        self.assertIsNone(pick_retry(runs, NOW))

    def test_success_today_is_left_alone(self):
        runs = {"update-danawa-prices.yml": [run(120), run(60, conclusion="success")]}
        self.assertIsNone(pick_retry(runs, NOW))

    def test_waits_after_a_recent_failure(self):
        runs = {"update-danawa-prices.yml": [run(20)]}
        self.assertIsNone(pick_retry(runs, NOW))

    def test_gives_up_after_too_many_runs(self):
        runs = {"update-danawa-prices.yml": [run(400 - i * 60) for i in range(6)]}
        self.assertIsNone(pick_retry(runs, NOW))

    def test_yesterdays_failure_is_not_retried(self):
        # 오늘 예약 실행이 아직 안 왔으면 손대지 않는다 (예약이 몇 시간씩 늦게 옴)
        runs = {"update-danawa-prices.yml": [run(13 * 60)]}
        self.assertIsNone(pick_retry(runs, NOW))

    def test_cancelled_run_counts_as_failed(self):
        runs = {"update-tv-prices.yml": [run(90, conclusion="cancelled")]}
        self.assertEqual(pick_retry(runs, NOW), "update-tv-prices.yml")

    def test_one_at_a_time_in_priority_order(self):
        runs = {wf: [run(90)] for wf in DAILY_WORKFLOWS}
        self.assertEqual(pick_retry(runs, NOW), DAILY_WORKFLOWS[0])
        self.assertEqual(DAILY_WORKFLOWS[0], "update-danawa-prices.yml")


DUE = {"update-danawa-prices.yml": (6, 0), "update-keyboard-prices.yml": (7, 0)}


class LateScheduleTests(unittest.TestCase):
    """GitHub 예약이 몇 시간씩 늦으므로, 예약 시각 + 2시간까지 안 돌았으면 직접 시작한다 (11-20 요청)."""

    def at(self, hour: int, minute: int = 0) -> datetime:
        return datetime(2026, 11, 20, hour, minute, tzinfo=KST)

    def test_not_started_two_hours_after_schedule_is_started(self):
        self.assertEqual(pick_retry({}, self.at(8, 1), DUE), "update-danawa-prices.yml")

    def test_waits_until_two_hours_after_schedule(self):
        self.assertIsNone(pick_retry({}, self.at(7, 59), DUE))

    def test_each_workflow_has_its_own_time(self):
        runs = {"update-danawa-prices.yml": [{"status": "completed", "conclusion": "success",
                                              "createdAt": "2026-11-19T23:00:00Z", "updatedAt": "2026-11-19T23:20:00Z"}]}
        self.assertIsNone(pick_retry(runs, self.at(8, 30), DUE))
        self.assertEqual(pick_retry(runs, self.at(9, 1), DUE), "update-keyboard-prices.yml")

    def test_not_started_while_group_is_busy(self):
        runs = {"update-tv-prices.yml": [{"status": "in_progress", "conclusion": None,
                                          "createdAt": "2026-11-19T23:50:00Z", "updatedAt": "2026-11-19T23:50:00Z"}]}
        self.assertIsNone(pick_retry(runs, self.at(8, 30), DUE))

    def test_due_times_are_read_from_workflow_crons(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "update-danawa-prices.yml").write_text(
                'on:\n  schedule:\n    # 21:00 UTC = 06:00 KST\n    - cron: "0 21 * * *"\n', encoding="utf-8")
            (Path(tmp) / "update-monitor-miniled-prices.yml").write_text(
                'on:\n  schedule:\n    - cron: "5 21 * * *"\n', encoding="utf-8")
            self.assertEqual(due_times(Path(tmp)), {"update-danawa-prices.yml": (6, 0),
                                                    "update-monitor-miniled-prices.yml": (6, 5)})

    def test_monitor_miniled_is_watched(self):
        self.assertIn("update-monitor-miniled-prices.yml", DAILY_WORKFLOWS)


if __name__ == "__main__":
    unittest.main()
