"""cron 명령과 자동 로그 증가 검증 흐름."""

from __future__ import annotations

import time

from ..paths import ROOT
from ..runner import run
from ..style import S
from ..ui import finish, header, yes_no
from .cron_runtime import (
    _cron_daemon_running,
    _crontab_text,
    _ensure_cron_daemon,
    _monitor_log_count,
    _restart_cron_daemon,
    _stop_cron_daemon,
)
from .logs import run_monitor
from .process import _agent_summary
from .service import start_agent
from .settings import CRON_COMMAND, CRON_OUTPUT_LOG, MONITOR_SCRIPT
from .support import _check_status, _ops_status, _print_sudo_tail, shlex_quote


def cron_service_status(*, interactive: bool = True) -> int:
    if interactive:
        header()
    print(S.title("cron 데몬 상태"))
    running, detail = _cron_daemon_running()
    _ops_status("cron 데몬", running, detail)
    code, crontab = _crontab_text()
    registered = code == 0 and str(MONITOR_SCRIPT) in crontab
    _ops_status(
        "monitor.sh 등록",
        registered,
        "등록됨" if registered else "미등록 또는 조회 실패",
    )
    finish(interactive)
    return 0 if running and registered else 1


def cron_service_control(
    action: str, *, interactive: bool = True, assume_yes: bool = False
) -> int:
    if interactive:
        header()
    labels = {
        "start": "cron 데몬 시작",
        "stop": "cron 데몬 중지",
        "restart": "cron 데몬 재시작",
    }
    print(S.title(labels.get(action, "cron 데몬 제어")))
    if action not in labels:
        print(S.bad(f"지원하지 않는 작업입니다: {action}"))
        finish(interactive)
        return 2

    if not assume_yes and not yes_no(f"{labels[action]}을 실행할까요?"):
        print("취소했습니다.")
        finish(interactive)
        return 2

    if action == "start":
        ok, detail = _ensure_cron_daemon()
    elif action == "stop":
        ok, detail = _stop_cron_daemon()
    else:
        ok, detail = _restart_cron_daemon()

    _ops_status(labels[action], ok, detail)
    finish(interactive)
    return 0 if ok else 1


def cron_service_menu(*, interactive: bool = True) -> int:
    if interactive:
        header()
    print(S.title("cron 데몬 제어"))
    print("1. 상태 확인")
    print("2. 시작")
    print("3. 중지")
    print("4. 재시작")
    choice = input("\n번호 선택 [1]: ").strip()
    print()

    if choice in {"", "1"}:
        code = cron_service_status(interactive=False)
    elif choice == "2":
        code = cron_service_control("start", interactive=False)
    elif choice == "3":
        code = cron_service_control("stop", interactive=False)
    elif choice == "4":
        code = cron_service_control("restart", interactive=False)
    else:
        print(S.bad("없는 번호입니다."))
        code = 2

    finish(interactive)
    return code


def install_cron(*, interactive: bool = True, assume_yes: bool = False) -> int:
    if interactive:
        header()
    print(S.title("crontab 등록"))
    print("agent-admin crontab에 monitor.sh 매분 실행 줄을 등록합니다.")
    print(S.dim(CRON_COMMAND))
    print()
    if not assume_yes and not yes_no("crontab을 등록/갱신할까요?"):
        print("취소했습니다.")
        finish(interactive)
        return 2

    archive = ROOT / "runtime" / "archive"
    script = (
        "set -u; "
        f"mkdir -p {shlex_quote(str(archive))}; "
        f"backup={shlex_quote(str(archive))}/agent-admin.cron.$(date +%Y%m%dT%H%M%S%z).bak; "
        'crontab -u agent-admin -l > "$backup" 2>/dev/null || :; '
        "tmp=$(mktemp); "
        f'crontab -u agent-admin -l 2>/dev/null | grep -v {shlex_quote(str(MONITOR_SCRIPT))} > "$tmp" || :; '
        f"printf '%s\\n' {shlex_quote(CRON_COMMAND)} >> \"$tmp\"; "
        'crontab -u agent-admin "$tmp"; '
        'rm -f "$tmp"'
    )
    code = run(["sudo", "bash", "-lc", script])
    if code == 0:
        print(S.ok("crontab 등록이 완료되었습니다."))
    else:
        print(S.warn(f"crontab 등록 종료 코드: {code}"))
    finish(interactive)
    return code


def crontab_dashboard(*, interactive: bool = True) -> int:
    if interactive:
        header()
    print(S.title("crontab 현황"))
    code, output = _crontab_text()
    if code != 0:
        _check_status("agent-admin crontab 조회", False, output.strip() or "조회 실패")
        finish(interactive)
        return 1

    has_monitor = str(MONITOR_SCRIPT) in output
    has_schedule = any(
        line.strip().startswith("* * * * *") and str(MONITOR_SCRIPT) in line
        for line in output.splitlines()
    )
    _check_status("monitor.sh 매분 등록", has_monitor and has_schedule)
    print()
    print(S.title("등록 내용"))
    print(output.rstrip() or S.dim("(비어 있음)"))

    print()
    ok, count, detail = _monitor_log_count()
    if ok:
        _check_status("monitor.log 현재 라인 수", True, f"{count} lines")
    else:
        _check_status("monitor.log 현재 라인 수", False, detail or "읽기 실패")
    print()
    print(
        "자동 누적 확인은 `uv run service-ops cron-check`로 1분 정도 대기하며 확인합니다."
    )
    finish(interactive)
    return 0 if has_monitor and has_schedule else 1


def cron_growth_test(*, interactive: bool = True, wait_seconds: int = 75) -> int:
    if interactive:
        header()
    print(S.title("cron 자동 실행 검증"))
    code, crontab = _crontab_text()
    if code != 0:
        _check_status("agent-admin crontab 조회", False, crontab.strip() or "조회 실패")
        finish(interactive)
        return 1

    has_monitor = str(MONITOR_SCRIPT) in crontab
    if not has_monitor:
        print(S.warn("monitor.sh crontab이 없어서 먼저 등록합니다."))
        cron_code = install_cron(interactive=False, assume_yes=True)
        if cron_code != 0:
            _check_status("monitor.sh crontab 등록", False, f"종료 코드 {cron_code}")
            finish(interactive)
            return cron_code
        code, crontab = _crontab_text()
        has_monitor = code == 0 and str(MONITOR_SCRIPT) in crontab
        if not has_monitor:
            _check_status(
                "monitor.sh crontab 등록",
                False,
                "등록 후에도 crontab에서 monitor.sh를 확인하지 못했습니다.",
            )
            finish(interactive)
            return 1
        _check_status("monitor.sh crontab 등록", True, "자동 등록 완료")

    _, _, ready = _agent_summary()
    if not ready:
        print(S.warn("agent가 READY 상태가 아니어서 먼저 서비스를 시작합니다."))
        start_code = start_agent(interactive=False, assume_yes=True)
        if start_code != 0:
            _check_status("agent 자동 시작", False, f"종료 코드 {start_code}")
            finish(interactive)
            return start_code
        for _ in range(10):
            _, _, ready = _agent_summary()
            if ready:
                break
            time.sleep(1)
        if not ready:
            _check_status(
                "agent READY",
                False,
                "서비스 시작 후에도 15034 LISTEN을 확인하지 못했습니다.",
            )
            finish(interactive)
            return 1
        _check_status("agent READY", True, "cron 확인 전 자동 시작 완료")

    cron_running, cron_detail = _ensure_cron_daemon()
    if not cron_running:
        _check_status("cron 데몬", False, cron_detail)
        finish(interactive)
        return 1
    _check_status("cron 데몬", True, cron_detail)

    before_ok, before_count, before_detail = _monitor_log_count()
    if not before_ok:
        _check_status("검증 전 monitor.log", False, before_detail or "읽기 실패")
        finish(interactive)
        return 1

    print(f"현재 monitor.log 라인 수: {before_count}")
    print(f"{wait_seconds}초 동안 crontab 실행을 기다립니다.")
    time.sleep(wait_seconds)

    after_ok, after_count, after_detail = _monitor_log_count()
    if not after_ok:
        _check_status("검증 후 monitor.log", False, after_detail or "읽기 실패")
        finish(interactive)
        return 1

    grew = after_count > before_count
    _check_status("1분 내 로그 자동 누적", grew, f"{before_count} -> {after_count}")
    if grew:
        finish(interactive)
        return 0

    print()
    print(
        S.warn(
            "cron 자동 누적이 확인되지 않아 monitor.sh를 즉시 실행해 원인을 분리합니다."
        )
    )
    manual_before = after_count
    manual_code = run_monitor(interactive=False)
    manual_ok, manual_after, manual_detail = _monitor_log_count()
    manual_grew = manual_ok and manual_after > manual_before
    if manual_code == 0 and manual_grew:
        _check_status(
            "monitor.sh 수동 실행", True, f"{manual_before} -> {manual_after}"
        )
        print(
            S.warn(
                "monitor.sh는 정상입니다. cron 데몬/스케줄 실행 경로를 확인해야 합니다."
            )
        )
    else:
        detail = f"종료 코드 {manual_code}"
        if manual_ok:
            detail = f"{detail}, {manual_before} -> {manual_after}"
        elif manual_detail:
            detail = f"{detail}, {manual_detail}"
        _check_status("monitor.sh 수동 실행", False, detail)

    _print_sudo_tail(CRON_OUTPUT_LOG)
    finish(interactive)
    return 1
