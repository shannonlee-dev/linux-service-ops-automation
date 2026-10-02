"""운영 명령의 실행·권한·출력 보조 함수."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from ..paths import ROOT
from ..style import S
from .settings import (
    AGENT_BINARY,
    AGENT_HOME,
    AGENT_KEY_PATH,
    AGENT_LOG_DIR,
    AGENT_PORT,
    AGENT_UPLOAD_DIR,
)


def _capture(command: list[str], *, timeout: int = 10) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            command,
            cwd=str(ROOT),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return 127, f"명령을 찾을 수 없습니다: {command[0]}"
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout if isinstance(exc.stdout, str) else ""
        return 124, output or "명령 시간이 초과되었습니다."
    return completed.returncode, completed.stdout or ""


def _sudo_capture(args: list[str], *, timeout: int = 10) -> tuple[int, str]:
    code, output = _capture(["sudo", "-n", *args], timeout=timeout)
    if code == 0 or not _sudo_can_retry_with_prompt(output):
        return code, output
    return _capture(["sudo", *args], timeout=timeout)


def _sudo_can_retry_with_prompt(output: str) -> bool:
    lowered = output.lower()
    return (
        "password is required" in lowered
        or "a password is required" in lowered
        or "a terminal is required" in lowered
    )


def _systemd_available() -> bool:
    return (
        shutil.which("systemctl") is not None and Path("/run/systemd/system").exists()
    )


def _check_status(label: str, ok: bool, detail: str = "") -> bool:
    marker = S.ok("OK") if ok else S.bad("MISS")
    suffix = f" - {detail}" if detail else ""
    print(f"{label:<32} {marker}{suffix}")
    return ok


def _ops_status(label: str, ok: bool, detail: str = "") -> bool:
    marker = S.ok("OK") if ok else S.bad("FAIL")
    suffix = f" - {detail}" if detail else ""
    print(f"{label:<24} {marker}{suffix}")
    return ok


def _ops_warn(label: str, detail: str = "") -> None:
    suffix = f" - {detail}" if detail else ""
    print(f"{label:<24} {S.warn('WARN')}{suffix}")


def _warn_status(label: str, detail: str = "") -> None:
    suffix = f" - {detail}" if detail else ""
    print(f"{label:<32} {S.warn('WARN')}{suffix}")


def _file_text(path: Path) -> str:
    try:
        return path.read_text(errors="ignore")
    except OSError:
        return ""


def _installed_path_state(
    path: Path, *, executable: bool = False
) -> tuple[bool | None, str]:
    check = "-x" if executable else "-e"
    try:
        if path.exists():
            return True, ""
        return False, ""
    except PermissionError:
        code, output = _sudo_capture(["test", check, str(path)])
        if code == 0:
            return True, "sudo로 확인됨"
        detail = output.strip()
        if "password" in detail.lower() or "sudo" in detail.lower():
            return None, "현재 사용자로 접근할 수 없어 사전 확인을 건너뜁니다."
        return False, detail or "경로가 없거나 실행 권한이 없습니다."


def _stat_fields(path: Path) -> tuple[bool, str, str, str]:
    code, output = _capture(["stat", "-c", "%U %G %a", str(path)])
    if code != 0:
        return False, "", "", output.strip()
    parts = output.strip().split()
    if len(parts) != 3:
        return False, "", "", output.strip()
    owner, group, mode = parts
    return True, owner, group, mode


def _mode_digit(mode: str, index_from_right: int) -> int:
    try:
        return int(mode[-index_from_right])
    except (ValueError, IndexError):
        return -1


def _group_rw(mode: str) -> bool:
    digit = _mode_digit(mode, 2)
    return digit >= 0 and (digit & 6) == 6


def _group_rx(mode: str) -> bool:
    digit = _mode_digit(mode, 2)
    return digit >= 0 and (digit & 5) == 5


def _other_none(mode: str) -> bool:
    return _mode_digit(mode, 1) == 0


def _process_name_running(*names: str) -> bool:
    code, output = _capture(["ps", "-eo", "comm="])
    if code != 0:
        return False
    wanted = set(names)
    return any(line.strip() in wanted for line in output.splitlines())


def _print_sudo_tail(path: Path, *, lines: int = 20) -> None:
    code, output = _sudo_capture(["tail", "-n", str(lines), str(path)])
    if code == 0 and output.strip():
        print()
        print(S.title(f"{path.name} 최근 {lines}줄"))
        print(output.rstrip())
    elif code != 0:
        detail = _sudo_failure_detail(
            output, f"sudo 권한이 필요해 {path}를 조회하지 못했습니다."
        )
        print(S.dim(f"{path.name} 조회 실패: {detail}"))


def _agent_env_args() -> list[str]:
    return [
        f"AGENT_HOME={AGENT_HOME}",
        f"AGENT_PORT={AGENT_PORT}",
        f"AGENT_UPLOAD_DIR={AGENT_UPLOAD_DIR}",
        f"AGENT_KEY_PATH={AGENT_KEY_PATH}",
        f"AGENT_LOG_DIR={AGENT_LOG_DIR}",
        f"AGENT_BINARY={AGENT_BINARY}",
    ]


def shlex_quote(value: str) -> str:
    import shlex

    return shlex.quote(value)


def _section(title: str) -> None:
    print()
    print(S.title(title))


def _human_bytes(size: int) -> str:
    value = float(size)
    for unit in ["B", "KB", "MB", "GB"]:
        if value < 1024 or unit == "GB":
            return f"{value:.1f}{unit}" if unit != "B" else f"{int(value)}B"
        value /= 1024
    return f"{size}B"


def _sudo_failure_detail(output: str, fallback: str) -> str:
    detail = output.strip()
    lowered = detail.lower()
    if (
        "password" in lowered
        or "no new privileges" in lowered
        or "sudo.conf" in lowered
        or "sudo:" in lowered
    ):
        return fallback
    return detail.splitlines()[0] if detail else fallback
