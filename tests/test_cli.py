"""시스템을 변경하지 않는 운영 CLI 진입점을 검증한다."""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.smoke
@pytest.mark.parametrize("args", [["--help"], ["check"]], ids=["help", "syntax"])
def test_read_only_cli_commands(args):
    result = subprocess.run(
        [sys.executable, "-m", "service_ops", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout
