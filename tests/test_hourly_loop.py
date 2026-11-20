"""수집이 다음 정각을 넘겨 끝나면 그 시간 몫을 바로 수집하는지 (2026-11-20 17시 몫이 18:00을 넘겨 18시가 빠졌음)."""

import importlib.util
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_hourly_component_prices.py"
KST = timezone(timedelta(hours=9))


def load_script():
    spec = importlib.util.spec_from_file_location("run_hourly_component_prices_loop", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class HourlyLoopTests(unittest.TestCase):
    def test_hour_that_started_during_a_long_collection_is_collected(self):
        module = load_script()
        clock = [datetime(2026, 11, 20, 17, 55, tzinfo=KST)]
        collected = []

        def fake_collect(day, hour, categories, use_git):
            collected.append(hour)
            clock[0] += timedelta(minutes=6)   # 17:55 시작 -> 18:01 끝

        with mock.patch.object(module, "now_kst", lambda: clock[0]), \
                mock.patch.object(module, "slot_done", lambda *args, **kwargs: False), \
                mock.patch.object(module, "collect", fake_collect), \
                mock.patch.object(module.time, "sleep"), \
                mock.patch.object(sys, "argv", ["run_hourly_component_prices.py", "--no-git"]):
            self.assertEqual(module.main(), 0)
        self.assertEqual(collected, [17, 18])


if __name__ == "__main__":
    unittest.main()
