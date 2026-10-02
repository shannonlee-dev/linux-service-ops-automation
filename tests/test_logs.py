"""회전본 개수와 저장된 모니터 로그의 통계를 검증한다."""

import os
import subprocess
from pathlib import Path

from service_ops.actions import logs

ROOT = Path(__file__).resolve().parents[1]


def test_rotation_limit_counts_archives_separately_from_current_log(capsys):
    archives = [(f"monitor.log.{index}", 100, 0) for index in range(1, 11)]
    logs._summarize_monitor_rotation([("monitor.log", 10, 0)], archives)
    output = capsys.readouterr().out
    assert "10/10개" in output
    assert "11/10개" not in output


def test_report_uses_time_range_and_real_metric_values(tmp_path):
    source = tmp_path / "monitor.log"
    source.write_text(
        "[2026-10-02 12:00:00] PID:123 CPU:90.0% MEM:9.0% DISK_USED:99.0%\n"
        "[2026-10-02 12:00:01] PID:123 CPU:10.0% MEM:2.0% DISK_USED:4.0%\n"
        "[2026-10-02 12:00:02] PID:123 CPU:20.0% MEM:4.0% DISK_USED:6.0%\n"
    )
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/agent/report.sh"), "2026-10-02 12:00:01"],
        env=dict(os.environ, MONITOR_LOG_FILE=str(source)),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "Average : 15.0%" in result.stdout
    assert "Average : 3.0%" in result.stdout
    assert "Average : 5.0%" in result.stdout
    assert "Data Points: 2 samples" in result.stdout
