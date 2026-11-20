"""매시 작업의 커밋·푸시가 다른 수집이 먼저 올린 날에도 성공하는지 (2026-11-20 실제 실패 재현).

매시 작업은 수집하면서 data/state/listings_seen.csv·eleven_stores.csv 를 고치는데 커밋하지 않아,
'git pull --rebase' 가 '커밋 안 된 변경' 때문에 거부되고, 그사이 하루 수집이 먼저 푸시한 날엔
푸시 5번이 모두 실패해 작업이 죽었다(하루 12번 중 2~7번만 저장).
"""

import importlib.util
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_hourly_component_prices.py"


def load_script():
    spec = importlib.util.spec_from_file_location("run_hourly_component_prices", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@unittest.skipUnless(shutil.which("git"), "git 필요")
class HourlyCommitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.origin = self.tmp / "origin.git"
        git(self.tmp, "init", "--bare", "-b", "main", str(self.origin))
        seed = self.tmp / "seed"
        git(self.tmp, "clone", str(self.origin), str(seed))
        self.configure(seed)
        write(seed / "README.md", "readme\n")
        write(seed / "data/latest/gpu.csv", "product_code,product_name,2026-11-20\n1,a,100\n")
        write(seed / "data/latest/monitor.csv", "product_code,product_name,2026-11-20\n2,b,200\n")
        write(seed / "data/state/listings_seen.csv", "link_pcode,first_seen\nx,2026-11-02\n")
        write(seed / "data/state/eleven_stores.csv", "code,store\n")
        for name in ("data/hourly/2026-11-20/collected.csv", "data/latest/gpu_open.csv",  # 실제 저장소에 있는 파일들
                     "data/specs/gpu_specs_new.csv", "data/history/gpu_price_history.csv",
                     "data/new_products/gpu.csv", "data/state/known_products/gpu.csv"):
            write(seed / name, "x\n")
        git(seed, "add", "-A")
        git(seed, "commit", "-m", "seed")
        git(seed, "push", "origin", "main")
        self.job = self.tmp / "job"      # 매시 작업의 체크아웃
        git(self.tmp, "clone", str(self.origin), str(self.job))
        self.configure(self.job)
        self.other = self.tmp / "other"  # 하루 수집(모니터 가격 등)
        git(self.tmp, "clone", str(self.origin), str(self.other))
        self.configure(self.other)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    @staticmethod
    def configure(repo: Path) -> None:
        git(repo, "config", "user.name", "test")
        git(repo, "config", "user.email", "test@example.com")
        git(repo, "config", "core.autocrlf", "false")

    def test_push_succeeds_after_another_crawl_pushed_first(self):
        # 하루 수집이 먼저 푸시
        write(self.other / "data/latest/monitor.csv", "product_code,product_name,2026-11-20\n2,b,199\n")
        git(self.other, "commit", "-am", "Update monitor price CSV")
        git(self.other, "push", "origin", "main")
        # 매시 작업: 가격과 '처음 본 날' 기록을 고친 상태
        write(self.job / "data/latest/gpu.csv", "product_code,product_name,2026-11-20\n1,a,99\n")
        write(self.job / "data/state/listings_seen.csv", "link_pcode,first_seen\nx,2026-11-02\ny,2026-11-20\n")
        write(self.job / "data/state/eleven_stores.csv", "code,store\nTH1,abc\n")

        module = load_script()
        with mock.patch.object(module, "ROOT", self.job), mock.patch.object(module.time, "sleep"):
            module.commit_and_push(["gpu"], "Update GPU RAM SSD price CSV 2026-11-20 09:00")

        verify = self.tmp / "verify"
        git(self.tmp, "clone", str(self.origin), str(verify))
        self.assertIn("1,a,99", (verify / "data/latest/gpu.csv").read_text(encoding="utf-8"))
        self.assertIn("2,b,199", (verify / "data/latest/monitor.csv").read_text(encoding="utf-8"))
        self.assertIn("y,2026-11-20", (verify / "data/state/listings_seen.csv").read_text(encoding="utf-8"))
        self.assertIn("TH1,abc", (verify / "data/state/eleven_stores.csv").read_text(encoding="utf-8"))
        self.assertEqual(git(self.job, "status", "--porcelain").strip(), "")


if __name__ == "__main__":
    unittest.main()
