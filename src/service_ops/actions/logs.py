"""모니터 실행·로그 조회·리포트·회전 현황."""

from __future__ import annotations

import subprocess
from fnmatch import fnmatch

from ..paths import ROOT
from ..runner import run
from ..style import S
from ..ui import finish, header
from .settings import (
    AGENT_HOME,
    AGENT_KEY_PATH,
    AGENT_LOG_DIR,
    AGENT_PORT,
    AGENT_UPLOAD_DIR,
    LOGROTATE_KEEP_COUNT,
    LOGROTATE_POLICY,
    LOGROTATE_SIZE_BYTES,
    MONITOR_SCRIPT,
    REPORT_SCRIPT,
    LogFile,
)
from .support import (
    _human_bytes,
    _installed_path_state,
    _sudo_capture,
    _sudo_failure_detail,
)


def run_monitor(*, interactive: bool = True) -> int:
    if interactive:
        header()
    print(S.title("monitor.sh 즉시 실행"))
    monitor_state, monitor_detail = _installed_path_state(
        MONITOR_SCRIPT, executable=True
    )
    if monitor_state is False:
        print(S.warn(f"monitor.sh가 아직 설치되지 않았습니다: {MONITOR_SCRIPT}"))
        if monitor_detail:
            print(S.dim(monitor_detail))
        print("먼저 `uv run service-ops install`로 설치/수리를 완료해야 합니다.")
        finish(interactive)
        return 1
    if monitor_state is None:
        print(S.warn(monitor_detail))
        print(S.dim("실행 단계에서 sudo 인증 후 agent-admin 권한으로 시작합니다."))
    code = run(
        [
            "sudo",
            "-u",
            "agent-admin",
            "env",
            f"AGENT_HOME={AGENT_HOME}",
            f"AGENT_PORT={AGENT_PORT}",
            f"AGENT_UPLOAD_DIR={AGENT_UPLOAD_DIR}",
            f"AGENT_KEY_PATH={AGENT_KEY_PATH}",
            f"AGENT_LOG_DIR={AGENT_LOG_DIR}",
            str(MONITOR_SCRIPT),
        ]
    )
    finish(interactive)
    return code


def show_logs(*, interactive: bool = True) -> int:
    if interactive:
        header()
    print(S.title("monitor.log 보기"))
    print(S.dim("/var/log/agent-app/monitor.log"))
    code = run(["sudo", "tail", "-n", "120", "/var/log/agent-app/monitor.log"])
    finish(interactive)
    return code


def show_report(*, interactive: bool = True) -> int:
    if interactive:
        header()
    print(S.title("report 보기"))
    report_state, report_detail = _installed_path_state(REPORT_SCRIPT, executable=True)
    if report_state is False:
        print(S.warn("report.sh가 아직 설치되지 않았습니다."))
        if report_detail:
            print(S.dim(report_detail))
        print("먼저 `uv run service-ops install`로 설치/수리를 완료해야 합니다.")
        finish(interactive)
        return 1
    if report_state is None:
        print(S.warn(report_detail))
        print(S.dim("실행 단계에서 sudo 인증 후 agent-admin 권한으로 시작합니다."))

    command = [
        "sudo",
        "-u",
        "agent-admin",
        "env",
        f"AGENT_LOG_DIR={AGENT_LOG_DIR}",
        str(REPORT_SCRIPT),
    ]
    try:
        completed = subprocess.run(command, cwd=str(ROOT), check=False)
    except FileNotFoundError:
        print(S.bad("sudo 명령을 찾을 수 없습니다."))
        finish(interactive)
        return 127
    finish(interactive)
    return completed.returncode


def _matches_any(name: str, patterns: list[str]) -> bool:
    return any(fnmatch(name, pattern) for pattern in patterns)


def _sudo_log_file_records(patterns: list[str]) -> tuple[list[LogFile], str]:
    code, output = _sudo_capture(
        [
            "find",
            str(AGENT_LOG_DIR),
            "-maxdepth",
            "1",
            "-type",
            "f",
            "-printf",
            "%T@\t%s\t%f\n",
        ]
    )
    if code != 0:
        return [], _sudo_failure_detail(
            output, "sudo 권한이 필요해 로그 목록을 조회하지 못했습니다."
        )

    records: list[LogFile] = []
    for line in output.splitlines():
        parts = line.split("\t", 2)
        if len(parts) != 3 or not _matches_any(parts[2], patterns):
            continue
        try:
            records.append((parts[2], int(parts[1]), float(parts[0])))
        except ValueError:
            continue
    return sorted(records, key=lambda item: item[2], reverse=True), "sudo로 조회"


def _list_log_files(patterns: list[str]) -> tuple[list[LogFile], str]:
    sudo_records, sudo_detail = _sudo_log_file_records(patterns)
    if sudo_records or not sudo_detail.startswith("sudo 권한"):
        return sudo_records, sudo_detail

    try:
        entries = list(AGENT_LOG_DIR.iterdir())
    except FileNotFoundError:
        return [], "로그 디렉터리가 없습니다."
    except PermissionError:
        return _sudo_log_file_records(patterns)

    records: list[LogFile] = []
    for path in entries:
        if not _matches_any(path.name, patterns):
            continue
        try:
            stat_result = path.stat()
        except PermissionError:
            return [], sudo_detail
        if path.is_file():
            records.append((path.name, stat_result.st_size, stat_result.st_mtime))
    return sorted(records, key=lambda item: item[2], reverse=True), ""


def _detail_is_error(detail: str) -> bool:
    return bool(detail) and detail != "sudo로 조회"


def _find_log_record(files: list[LogFile], name: str) -> LogFile | None:
    return next((record for record in files if record[0] == name), None)


def _monitor_rotation_records(rotated_logs: list[LogFile]) -> list[LogFile]:
    return [record for record in rotated_logs if record[0].startswith("monitor.log.")]


def _summarize_monitor_rotation(
    active_logs: list[LogFile], rotated_logs: list[LogFile], detail: str = ""
) -> None:
    print(S.title("monitor.log 보관 현황"))
    if _detail_is_error(detail):
        print(f"{'보관 파일':<18} {S.warn('권한 필요')} - {detail}")
        return

    monitor_log = _find_log_record(active_logs, "monitor.log")
    current_size = monitor_log[1] if monitor_log else 0
    monitor_rotated = _monitor_rotation_records(rotated_logs)
    monitor_files = ([monitor_log] if monitor_log else []) + monitor_rotated
    total_size = sum(size for _, size, _ in monitor_files)
    rotated_size = sum(size for _, size, _ in monitor_rotated)
    print(
        f"{'현재 크기':<18} {_human_bytes(current_size)} / {_human_bytes(LOGROTATE_SIZE_BYTES)}"
    )
    print(f"{'전체 보관 파일':<18} {len(monitor_files)}개, {_human_bytes(total_size)}")
    if monitor_log:
        print(f"{'현재 파일':<18} {_human_bytes(monitor_log[1])}  {monitor_log[0]}")
    else:
        print(f"{'현재 파일':<18} 없음")
    print(
        f"{'회전/압축본':<18} {len(monitor_rotated)}/{LOGROTATE_KEEP_COUNT}개, "
        f"{_human_bytes(rotated_size)}"
    )
    for name, size, _ in monitor_rotated[:5]:
        print(S.dim(f"  {_human_bytes(size):>8}  {name}"))
    if len(monitor_rotated) > 5:
        print(S.dim(f"  ... 외 {len(monitor_rotated) - 5}개"))


def _sudo_logrotate_dry_run() -> tuple[bool, str]:
    if not LOGROTATE_POLICY.exists():
        return False, "정책 파일이 아직 설치되지 않았습니다."
    try:
        completed = subprocess.run(
            ["sudo", "-n", "logrotate", "-d", str(LOGROTATE_POLICY)],
            cwd=str(ROOT),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False, "sudo/logrotate 실행 상태를 확인하지 못했습니다."

    output = completed.stdout or ""
    if completed.returncode == 0:
        if "No logs found" in output:
            return True, "정책 파싱 OK, 현재 회전 대상 로그 없음"
        return True, "정책 파싱 OK"
    if (
        "no new privileges" in output
        or "password is required" in output
        or "a password is required" in output
    ):
        return False, "sudo 권한이 필요해 dry-run은 건너뜀"
    for line in output.splitlines():
        if "error:" in line:
            return False, line.strip()
    return False, "dry-run 실패"


def logrotate_dashboard(*, interactive: bool = True) -> int:
    if interactive:
        header()

    active_logs, active_detail = _list_log_files(["*.log", "*.out"])
    rotated_logs, rotated_detail = _list_log_files(
        ["*.log.[0-9]*", "*.log.*.gz", "*.out.[0-9]*", "*.out.*.gz"]
    )
    detail = active_detail if _detail_is_error(active_detail) else rotated_detail

    _summarize_monitor_rotation(active_logs, rotated_logs, detail)

    if not LOGROTATE_POLICY.exists():
        print()
        print(S.warn("아직 시스템에 logrotate 정책이 설치되지 않았습니다."))
        print("`uv run service-ops install`을 먼저 실행하면 설치됩니다.")

    finish(interactive)
    return 0
