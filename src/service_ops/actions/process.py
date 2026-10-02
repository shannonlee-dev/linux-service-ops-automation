"""agent 프로세스·포트·systemd 상태 조회."""

from __future__ import annotations

import re

from .settings import AGENT_PORT, PS_AGENT_COMMAND
from .support import _capture, _sudo_capture, _systemd_available


def _app_port_listening() -> bool:
    code, ss_output = _capture(["ss", "-H", "-tuln"])
    return code == 0 and f":{AGENT_PORT}" in ss_output


def _agent_process_records(ps_output: str) -> list[tuple[str, str, str]]:
    records: list[tuple[str, str, str]] = []
    for line in ps_output.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) < 3:
            continue
        user, pid, args = parts
        if "monitor.sh" in args:
            continue
        if re.search(
            r"(^|/)(agent-app-linux[^/ ]*|agent_app[.]py|agent-app)([ ]|$)", args
        ):
            records.append((user, pid, args))
    wrappers = ("sudo ", "env ", "bash ", "sh ", "tee ")
    actual = [
        record
        for record in records
        if not record[2].startswith(wrappers)
        and " tee " not in record[2]
        and " bash -lc " not in record[2]
        and " sh -c " not in record[2]
    ]
    return actual or records


def _agent_processes() -> list[tuple[str, str, str]]:
    code, ps_output = _capture(PS_AGENT_COMMAND)
    return _agent_process_records(ps_output) if code == 0 else []


def _agent_summary() -> tuple[
    list[tuple[str, str, str]], list[tuple[str, str, str]], bool
]:
    records = _agent_processes()
    agent_admin_records = [record for record in records if record[0] == "agent-admin"]
    return (
        records,
        agent_admin_records,
        bool(agent_admin_records) and _app_port_listening(),
    )


def _systemd_state() -> tuple[bool, str]:
    if not _systemd_available():
        return False, "systemd 없음"
    code, output = _sudo_capture(["systemctl", "is-active", "agent-app.service"])
    state = output.strip() or "unknown"
    return code == 0 and state == "active", state
