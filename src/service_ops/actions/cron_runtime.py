"""cron 데몬과 설치된 로그의 상태 확인·제어."""

from __future__ import annotations

import shutil
import time

from ..runner import run
from .settings import AGENT_LOG_DIR
from .support import (
    _process_name_running,
    _sudo_capture,
    _sudo_failure_detail,
    _systemd_available,
)


def _crontab_text() -> tuple[int, str]:
    code, output = _sudo_capture(["crontab", "-u", "agent-admin", "-l"])
    if code != 0:
        return code, _sudo_failure_detail(
            output, "sudo 권한이 필요해 agent-admin crontab을 조회하지 못했습니다."
        )
    return code, output


def _monitor_log_count() -> tuple[bool, int, str]:
    code, output = _sudo_capture(["wc", "-l", str(AGENT_LOG_DIR / "monitor.log")])
    if code != 0:
        return (
            False,
            0,
            _sudo_failure_detail(
                output, "sudo 권한이 필요해 monitor.log를 조회하지 못했습니다."
            ),
        )
    try:
        return True, int(output.split()[0]), output.strip()
    except (IndexError, ValueError):
        return False, 0, output.strip()


def _cron_daemon_running() -> tuple[bool, str]:
    if _process_name_running("cron", "crond"):
        return True, "cron/crond 프로세스 실행 중"
    if _systemd_available():
        for unit in ["cron.service", "crond.service"]:
            code, output = _sudo_capture(["systemctl", "is-active", unit])
            if code == 0 and output.strip() == "active":
                return True, f"{unit} active"
    return False, "실행 중인 cron/crond 프로세스 없음"


def _ensure_cron_daemon() -> tuple[bool, str]:
    running, detail = _cron_daemon_running()
    if running:
        return True, detail

    attempts: list[str] = []
    if _systemd_available():
        for unit in ["cron.service", "crond.service"]:
            code = run(["sudo", "systemctl", "start", unit])
            attempts.append(f"{unit}={code}")
            time.sleep(1)
            running, detail = _cron_daemon_running()
            if running:
                return True, detail

    if shutil.which("service") is not None:
        for service_name in ["cron", "crond"]:
            code = run(["sudo", "service", service_name, "start"])
            attempts.append(f"service {service_name}={code}")
            time.sleep(1)
            running, detail = _cron_daemon_running()
            if running:
                return True, detail

    for executable in ["cron", "crond"]:
        if shutil.which(executable) is None:
            continue
        code = run(["sudo", executable])
        attempts.append(f"{executable}={code}")
        time.sleep(1)
        running, detail = _cron_daemon_running()
        if running:
            return True, detail

    suffix = f" ({', '.join(attempts)})" if attempts else ""
    return False, f"cron 데몬 시작 실패{suffix}"


def _stop_cron_daemon() -> tuple[bool, str]:
    running, detail = _cron_daemon_running()
    if not running:
        return True, detail

    attempts: list[str] = []
    if _systemd_available():
        for unit in ["cron.service", "crond.service"]:
            code = run(["sudo", "systemctl", "stop", unit])
            attempts.append(f"{unit}={code}")
            time.sleep(1)
            still_running, stop_detail = _cron_daemon_running()
            if not still_running:
                return True, stop_detail

    if shutil.which("service") is not None:
        for service_name in ["cron", "crond"]:
            code = run(["sudo", "service", service_name, "stop"])
            attempts.append(f"service {service_name}={code}")
            time.sleep(1)
            still_running, stop_detail = _cron_daemon_running()
            if not still_running:
                return True, stop_detail

    for process_name in ["cron", "crond"]:
        code = run(["sudo", "pkill", "-x", process_name])
        attempts.append(f"pkill {process_name}={code}")
        time.sleep(1)
        still_running, stop_detail = _cron_daemon_running()
        if not still_running:
            return True, stop_detail

    return False, f"cron 데몬 중지 실패 ({', '.join(attempts)})"


def _restart_cron_daemon() -> tuple[bool, str]:
    stopped, stop_detail = _stop_cron_daemon()
    if not stopped:
        return False, stop_detail
    return _ensure_cron_daemon()
