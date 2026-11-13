import unittest
from datetime import datetime, timedelta, timezone

from danawa_crawler.daily_watchdog import DAILY_WORKFLOWS, pick_retry

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


if __name__ == "__main__":
    unittest.main()
