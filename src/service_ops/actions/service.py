"""agent 서비스 시작·중지·재시작과 상태 화면."""

from __future__ import annotations

import time

from ..runner import run
from ..style import S
from ..ui import finish, header, yes_no
from .cron_runtime import _crontab_text, _monitor_log_count
from .logs import logrotate_dashboard
from .process import _agent_summary, _app_port_listening, _systemd_state
from .settings import (
    AGENT_BINARY,
    AGENT_LOG_DIR,
    AGENT_PID_FILE,
    AGENT_PORT,
    MONITOR_SCRIPT,
    SYSTEMD_UNIT,
)
from .support import (
    _agent_env_args,
    _installed_path_state,
    _ops_status,
    _ops_warn,
    _systemd_available,
)


def start_agent(*, interactive: bool = True, assume_yes: bool = False) -> int:
    if interactive:
        header()
    print(S.title("서비스 시작"))
    if _systemd_available() and SYSTEMD_UNIT.exists():
        if not assume_yes and not yes_no("agent 서비스를 시작할까요?"):
            print("취소했습니다.")
            finish(interactive)
            return 2
        code = run(["sudo", "systemctl", "start", "agent-app.service"])
        if code == 0:
            print(S.ok("agent-app.service 시작 요청을 보냈습니다."))
        finish(interactive)
        return code

    records, agent_admin_records, ready = _agent_summary()
    if ready:
        print(S.ok("agent가 이미 실행 중입니다."))
        for user, pid, args in agent_admin_records[:3]:
            print(f"{user:<12} pid={pid:<8} {args}")
        finish(interactive)
        return 0
    if records:
        print(S.warn("agent로 보이는 프로세스가 있지만 READY 상태는 아닙니다."))
        for user, pid, args in records:
            print(f"{user:<12} pid={pid:<8} {args}")
        print()

    binary_state, binary_detail = _installed_path_state(AGENT_BINARY, executable=True)
    if binary_state is False:
        print(S.warn(f"agent 실행 파일이 없습니다: {AGENT_BINARY}"))
        if binary_detail:
            print(S.dim(binary_detail))
        print("먼저 `uv run service-ops install`로 설치/수리를 완료해야 합니다.")
        finish(interactive)
        return 1
    if binary_state is None:
        print(S.warn(binary_detail))
        print(S.dim("실행 단계에서 sudo 인증 후 agent-admin 권한으로 시작합니다."))
    print("agent를 agent-admin 계정으로 백그라운드 실행합니다.")
    print(S.dim(f"stdout: {AGENT_LOG_DIR}/agent-app.out"))
    print(S.dim(f"stderr: {AGENT_LOG_DIR}/agent-app.err"))
    print(S.dim(f"pid:    {AGENT_PID_FILE}"))
    print()
    if not assume_yes and not yes_no("agent를 실행할까요?"):
        print("취소했습니다.")
        finish(interactive)
        return 2
    code = run(
        [
            "sudo",
            "-u",
            "agent-admin",
            "env",
            *_agent_env_args(),
            "bash",
            "-lc",
            'nohup "$AGENT_BINARY" >> "$AGENT_LOG_DIR/agent-app.out" 2>> "$AGENT_LOG_DIR/agent-app.err" & echo $! > "$AGENT_LOG_DIR/agent-app.pid"',
        ]
    )
    if code == 0:
        time.sleep(1)
        _, _, started = _agent_summary()
        if started:
            print(S.ok("agent가 백그라운드에서 실행 중입니다."))
        else:
            print(
                S.warn(
                    "시작 명령은 성공했지만 READY 상태는 아직 확인되지 않았습니다. `uv run service-ops status`로 확인하세요."
                )
            )
    finish(interactive)
    return code


def start_agent_foreground(
    *, interactive: bool = True, assume_yes: bool = False
) -> int:
    if interactive:
        header()
    print(S.title("서비스 foreground 실행"))

    records, agent_admin_records, ready = _agent_summary()
    if ready:
        print(
            S.warn(
                "agent가 이미 READY 상태입니다. foreground를 추가 실행하면 포트 충돌이 납니다."
            )
        )
        for user, pid, args in agent_admin_records[:3]:
            print(f"{user:<12} pid={pid:<8} {args}")
        print("기존 실행 로그는 로그 따라보기를 사용하세요.")
        finish(interactive)
        return 1
    if records:
        print(S.warn("agent로 보이는 프로세스가 있지만 READY 상태는 아닙니다."))
        for user, pid, args in records:
            print(f"{user:<12} pid={pid:<8} {args}")
        print()

    binary_state, binary_detail = _installed_path_state(AGENT_BINARY, executable=True)
    if binary_state is False:
        print(S.warn(f"agent 실행 파일이 없습니다: {AGENT_BINARY}"))
        if binary_detail:
            print(S.dim(binary_detail))
        print("먼저 `uv run service-ops install`로 설치/수리를 완료해야 합니다.")
        finish(interactive)
        return 1
    if binary_state is None:
        print(S.warn(binary_detail))
        print(S.dim("실행 단계에서 sudo 인증 후 agent-admin 권한으로 시작합니다."))

    print("현재 터미널에서 agent를 실행합니다. 종료하려면 Ctrl-C를 누르세요.")
    print(S.dim("foreground 실행 중에는 메뉴로 돌아오지 않습니다."))
    print()
    if not assume_yes and not yes_no("foreground로 agent를 실행할까요?"):
        print("취소했습니다.")
        finish(interactive)
        return 2

    code = run(
        [
            "sudo",
            "-u",
            "agent-admin",
            "env",
            *_agent_env_args(),
            str(AGENT_BINARY),
        ]
    )
    finish(interactive)
    return code


def follow_agent_logs(*, interactive: bool = True) -> int:
    if interactive:
        header()
    print(S.title("agent 로그 따라보기"))
    print(S.dim("Ctrl-C로 종료하면 메뉴로 돌아갑니다."))
    print(S.dim(f"{AGENT_LOG_DIR}/agent-app.out"))
    print(S.dim(f"{AGENT_LOG_DIR}/agent-app.err"))
    print()

    run(
        [
            "sudo",
            "-u",
            "agent-admin",
            "env",
            *_agent_env_args(),
            "bash",
            "-lc",
            'touch "$AGENT_LOG_DIR/agent-app.out" "$AGENT_LOG_DIR/agent-app.err"',
        ]
    )
    code = run(
        [
            "sudo",
            "tail",
            "-n",
            "80",
            "-F",
            str(AGENT_LOG_DIR / "agent-app.out"),
            str(AGENT_LOG_DIR / "agent-app.err"),
        ]
    )
    finish(interactive)
    return code


def start_agent_menu(*, interactive: bool = True) -> int:
    if interactive:
        header()
    print(S.title("서비스 시작"))
    print("1. 백그라운드 시작 (기본)")
    print("2. foreground 실행")
    print("3. 백그라운드 시작 후 로그 따라보기")
    print("4. 실행 중인 로그만 따라보기")
    choice = input("\n실행 방식 선택 [1]: ").strip()
    print()

    if choice in {"", "1"}:
        code = start_agent(interactive=False)
    elif choice == "2":
        code = start_agent_foreground(interactive=False)
    elif choice == "3":
        code = start_agent(interactive=False, assume_yes=True)
        if code == 0:
            code = follow_agent_logs(interactive=False)
    elif choice == "4":
        code = follow_agent_logs(interactive=False)
    else:
        print(S.bad("없는 번호입니다."))
        code = 2

    finish(interactive)
    return code


def service_status(*, interactive: bool = True) -> int:
    if interactive:
        header()
    print(S.title("서비스 상태"))
    records, agent_admin_records, ready = _agent_summary()
    selected = agent_admin_records or records
    process_detail = (
        f"{selected[0][0]} pid={selected[0][1]} {selected[0][2]}"
        if selected
        else "프로세스 없음"
    )
    ok = True
    ok = _ops_status("agent 프로세스", bool(records), process_detail) and ok
    ok = (
        _ops_status(
            "실행 계정",
            bool(agent_admin_records),
            "agent-admin" if agent_admin_records else "agent-admin 아님",
        )
        and ok
    )
    ok = (
        _ops_status(
            f"포트 {AGENT_PORT}",
            _app_port_listening(),
            "LISTEN" if _app_port_listening() else "닫힘",
        )
        and ok
    )
    ok = (
        _ops_status(
            "서비스 READY",
            ready,
            "agent-admin 프로세스 + 포트 LISTEN" if ready else "대기 중",
        )
        and ok
    )
    if _systemd_available():
        active, state = _systemd_state()
        _ops_status("systemd unit", active, state)
    else:
        _ops_warn("systemd unit", "사용 불가, 프로세스 직접 제어 모드")

    cron_code, cron_text = _crontab_text()
    cron_ok = cron_code == 0 and str(MONITOR_SCRIPT) in cron_text
    _ops_status(
        "모니터링 cron", cron_ok, "등록됨" if cron_ok else "미등록 또는 조회 실패"
    )

    log_ok, log_count, log_detail = _monitor_log_count()
    _ops_status(
        "monitor.log",
        log_ok and log_count > 0,
        f"{log_count} lines" if log_ok else log_detail,
    )

    print()
    logrotate_dashboard(interactive=False)
    finish(interactive)
    return 0 if ok else 1


def stop_agent(*, interactive: bool = True, assume_yes: bool = False) -> int:
    if interactive:
        header()
    print(S.title("서비스 중지"))
    records, _, _ = _agent_summary()
    if not records:
        print("agent 프로세스가 실행 중이 아닙니다.")
        finish(interactive)
        return 0
    for user, pid, args in records:
        print(f"{user:<12} pid={pid:<8} {args}")
    print()
    if not assume_yes and not yes_no("agent 프로세스를 종료할까요?"):
        print("취소했습니다.")
        finish(interactive)
        return 2
    if _systemd_available() and SYSTEMD_UNIT.exists():
        code = run(["sudo", "systemctl", "stop", "agent-app.service"])
        if code == 0:
            run(["sudo", "rm", "-f", str(AGENT_PID_FILE)])
        finish(interactive)
        return code
    code = run(
        [
            "sudo",
            "pkill",
            "-TERM",
            "-u",
            "agent-admin",
            "-f",
            "agent-app-linux|/home/agent-admin/agent-app/bin/agent-app",
        ]
    )
    time.sleep(1)
    still_running, _, _ = _agent_summary()
    if still_running:
        print(S.warn("TERM 후에도 프로세스가 남아 있어 KILL을 시도합니다."))
        code = run(
            [
                "sudo",
                "pkill",
                "-KILL",
                "-u",
                "agent-admin",
                "-f",
                "agent-app-linux|/home/agent-admin/agent-app/bin/agent-app",
            ]
        )
    if code == 0:
        run(["sudo", "rm", "-f", str(AGENT_PID_FILE)])
    finish(interactive)
    return code


def restart_agent(*, interactive: bool = True, assume_yes: bool = False) -> int:
    if interactive:
        header()
    print(S.title("서비스 재시작"))
    if _systemd_available() and SYSTEMD_UNIT.exists():
        if not assume_yes and not yes_no("agent 서비스를 재시작할까요?"):
            print("취소했습니다.")
            finish(interactive)
            return 2
        code = run(["sudo", "systemctl", "restart", "agent-app.service"])
        finish(interactive)
        return code
    stop_code = stop_agent(interactive=False, assume_yes=True)
    if stop_code not in {0, 1}:
        finish(interactive)
        return stop_code
    print()
    start_code = start_agent(interactive=False, assume_yes=assume_yes)
    finish(interactive)
    return start_code
