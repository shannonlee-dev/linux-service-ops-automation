from __future__ import annotations

from fnmatch import fnmatch
import re
import shutil
import subprocess
import time
from pathlib import Path

from .paths import APPLY, LOGROTATE_TEMPLATE, ROOT, SYSTEMD_UNIT_TEMPLATE
from .runner import run
from .style import S
from .ui import finish, header, status_line, yes_no


LOGROTATE_POLICY = Path("/etc/logrotate.d/agent-app")
SYSTEMD_UNIT = Path("/etc/systemd/system/agent-app.service")
AGENT_HOME = Path("/home/agent-admin/agent-app")
AGENT_PORT = "15034"
AGENT_UPLOAD_DIR = AGENT_HOME / "upload_files"
AGENT_KEY_DIR = AGENT_HOME / "api_keys"
AGENT_KEY_PATH = AGENT_KEY_DIR
AGENT_KEY_FILE = AGENT_KEY_DIR / "secret.key"
AGENT_LOG_DIR = Path("/var/log/agent-app")
AGENT_PID_FILE = AGENT_LOG_DIR / "agent-app.pid"
CRON_OUTPUT_LOG = AGENT_LOG_DIR / "monitor-cron.out"
MONITOR_SCRIPT = AGENT_HOME / "bin" / "monitor.sh"
REPORT_SCRIPT = AGENT_HOME / "bin" / "report.sh"
AGENT_BINARY = AGENT_HOME / "bin" / "agent-app"
PS_AGENT_COMMAND = ["ps", "-eo", "euser:32=,pid=,args="]
CRON_COMMAND = (
    f"* * * * * AGENT_HOME={AGENT_HOME} AGENT_PORT={AGENT_PORT} "
    f"AGENT_UPLOAD_DIR={AGENT_UPLOAD_DIR} AGENT_KEY_PATH={AGENT_KEY_PATH} "
    f"AGENT_LOG_DIR={AGENT_LOG_DIR} {MONITOR_SCRIPT} >> {AGENT_LOG_DIR}/monitor-cron.out 2>&1"
)
MONITOR_LOG_PATTERN = re.compile(
    r"^\[[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}\] "
    r"PID:[^ ]+ CPU:[0-9.]+% MEM:[0-9.]+% DISK_USED:[0-9.]+%$"
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
    return shutil.which("systemctl") is not None and Path("/run/systemd/system").exists()


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


def _installed_path_state(path: Path, *, executable: bool = False) -> tuple[bool | None, str]:
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


def _crontab_text() -> tuple[int, str]:
    code, output = _sudo_capture(["crontab", "-u", "agent-admin", "-l"])
    if code != 0:
        return code, _sudo_failure_detail(output, "sudo 권한이 필요해 agent-admin crontab을 조회하지 못했습니다.")
    return code, output


def _monitor_log_count() -> tuple[bool, int, str]:
    code, output = _sudo_capture(["wc", "-l", str(AGENT_LOG_DIR / "monitor.log")])
    if code != 0:
        return False, 0, _sudo_failure_detail(output, "sudo 권한이 필요해 monitor.log를 조회하지 못했습니다.")
    try:
        return True, int(output.split()[0]), output.strip()
    except (IndexError, ValueError):
        return False, 0, output.strip()


def _process_name_running(*names: str) -> bool:
    code, output = _capture(["ps", "-eo", "comm="])
    if code != 0:
        return False
    wanted = set(names)
    return any(line.strip() in wanted for line in output.splitlines())


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


def _print_sudo_tail(path: Path, *, lines: int = 20) -> None:
    code, output = _sudo_capture(["tail", "-n", str(lines), str(path)])
    if code == 0 and output.strip():
        print()
        print(S.title(f"{path.name} 최근 {lines}줄"))
        print(output.rstrip())
    elif code != 0:
        detail = _sudo_failure_detail(output, f"sudo 권한이 필요해 {path}를 조회하지 못했습니다.")
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


def apply_system(*, interactive: bool = True, assume_yes: bool = False) -> int:
    if interactive:
        header()
    print(S.warn("이 작업은 실제 시스템 설정을 변경합니다."))
    print("- SSH 포트/root 로그인 정책")
    print("- 방화벽 규칙")
    print("- 로컬 계정/그룹/권한")
    print("- /home/agent-admin, /var/log/agent-app")
    print("- crontab")
    print()
    if not assume_yes and not yes_no("계속 적용할까요?"):
        print("취소했습니다.")
        finish(interactive)
        return 2
    code = run(["sudo", str(APPLY)])
    print()
    if code == 0:
        print(S.ok("적용 스크립트가 종료 코드 0으로 끝났습니다."))
    else:
        print(S.warn(f"적용 스크립트 종료 코드: {code}"))
    print(S.dim("다음 단계: `python3 main.py start --yes` 또는 메뉴의 서비스 시작을 실행하세요."))
    finish(interactive)
    return code


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
        print("먼저 `python3 main.py install`로 설치/수리를 완료해야 합니다.")
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
    code = run([
        "sudo",
        "-u",
        "agent-admin",
        "env",
        *_agent_env_args(),
        "bash",
        "-lc",
        'nohup "$AGENT_BINARY" >> "$AGENT_LOG_DIR/agent-app.out" 2>> "$AGENT_LOG_DIR/agent-app.err" & echo $! > "$AGENT_LOG_DIR/agent-app.pid"',
    ])
    if code == 0:
        time.sleep(1)
        _, _, started = _agent_summary()
        if started:
            print(S.ok("agent가 백그라운드에서 실행 중입니다."))
        else:
            print(S.warn("시작 명령은 성공했지만 READY 상태는 아직 확인되지 않았습니다. `python3 main.py status`로 확인하세요."))
    finish(interactive)
    return code


def start_agent_foreground(*, interactive: bool = True, assume_yes: bool = False) -> int:
    if interactive:
        header()
    print(S.title("서비스 foreground 실행"))

    records, agent_admin_records, ready = _agent_summary()
    if ready:
        print(S.warn("agent가 이미 READY 상태입니다. foreground를 추가 실행하면 포트 충돌이 납니다."))
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
        print("먼저 `python3 main.py install`로 설치/수리를 완료해야 합니다.")
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

    code = run([
        "sudo",
        "-u",
        "agent-admin",
        "env",
        *_agent_env_args(),
        str(AGENT_BINARY),
    ])
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

    run([
        "sudo",
        "-u",
        "agent-admin",
        "env",
        *_agent_env_args(),
        "bash",
        "-lc",
        'touch "$AGENT_LOG_DIR/agent-app.out" "$AGENT_LOG_DIR/agent-app.err"',
    ])
    code = run([
        "sudo",
        "tail",
        "-n",
        "80",
        "-F",
        str(AGENT_LOG_DIR / "agent-app.out"),
        str(AGENT_LOG_DIR / "agent-app.err"),
    ])
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


def cron_service_status(*, interactive: bool = True) -> int:
    if interactive:
        header()
    print(S.title("cron 데몬 상태"))
    running, detail = _cron_daemon_running()
    _ops_status("cron 데몬", running, detail)
    code, crontab = _crontab_text()
    registered = code == 0 and str(MONITOR_SCRIPT) in crontab
    _ops_status("monitor.sh 등록", registered, "등록됨" if registered else "미등록 또는 조회 실패")
    finish(interactive)
    return 0 if running and registered else 1


def cron_service_control(action: str, *, interactive: bool = True, assume_yes: bool = False) -> int:
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


def run_monitor(*, interactive: bool = True) -> int:
    if interactive:
        header()
    print(S.title("monitor.sh 즉시 실행"))
    monitor_state, monitor_detail = _installed_path_state(MONITOR_SCRIPT, executable=True)
    if monitor_state is False:
        print(S.warn(f"monitor.sh가 아직 설치되지 않았습니다: {MONITOR_SCRIPT}"))
        if monitor_detail:
            print(S.dim(monitor_detail))
        print("먼저 `python3 main.py install`로 설치/수리를 완료해야 합니다.")
        finish(interactive)
        return 1
    if monitor_state is None:
        print(S.warn(monitor_detail))
        print(S.dim("실행 단계에서 sudo 인증 후 agent-admin 권한으로 시작합니다."))
    code = run([
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
    ])
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
        print("먼저 `python3 main.py install`로 설치/수리를 완료해야 합니다.")
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
        "crontab -u agent-admin -l > \"$backup\" 2>/dev/null || :; "
        "tmp=$(mktemp); "
        f"crontab -u agent-admin -l 2>/dev/null | grep -v {shlex_quote(str(MONITOR_SCRIPT))} > \"$tmp\" || :; "
        f"printf '%s\\n' {shlex_quote(CRON_COMMAND)} >> \"$tmp\"; "
        "crontab -u agent-admin \"$tmp\"; "
        "rm -f \"$tmp\""
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
    has_schedule = any(line.strip().startswith("* * * * *") and str(MONITOR_SCRIPT) in line for line in output.splitlines())
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
    print("자동 누적 확인은 `python3 main.py cron-check`로 1분 정도 대기하며 확인합니다.")
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
            _check_status("monitor.sh crontab 등록", False, "등록 후에도 crontab에서 monitor.sh를 확인하지 못했습니다.")
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
            _check_status("agent READY", False, "서비스 시작 후에도 15034 LISTEN을 확인하지 못했습니다.")
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
    print(S.warn("cron 자동 누적이 확인되지 않아 monitor.sh를 즉시 실행해 원인을 분리합니다."))
    manual_before = after_count
    manual_code = run_monitor(interactive=False)
    manual_ok, manual_after, manual_detail = _monitor_log_count()
    manual_grew = manual_ok and manual_after > manual_before
    if manual_code == 0 and manual_grew:
        _check_status("monitor.sh 수동 실행", True, f"{manual_before} -> {manual_after}")
        print(S.warn("monitor.sh는 정상입니다. cron 데몬/스케줄 실행 경로를 확인해야 합니다."))
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


def shlex_quote(value: str) -> str:
    import shlex

    return shlex.quote(value)


def _section(title: str) -> None:
    print()
    print(S.title(title))


def _verify_ssh() -> list[bool]:
    results: list[bool] = []
    code, sshd_t = _sudo_capture(["sshd", "-T"])
    config_text = _file_text(Path("/etc/ssh/sshd_config"))
    effective_port = "port 20022" in sshd_t.lower()
    effective_root = "permitrootlogin no" in sshd_t.lower()
    configured_port = re.search(r"(?im)^\s*Port\s+20022\s*$", config_text) is not None
    configured_root = re.search(r"(?im)^\s*PermitRootLogin\s+no\s*$", config_text) is not None
    if code != 0:
        _warn_status("sshd -T", "sudo 비밀번호 없이 실행 불가, 설정 파일 기준도 함께 확인")
    results.append(_check_status("SSH Port 20022", effective_port or configured_port))
    results.append(_check_status("Root 원격 로그인 차단", effective_root or configured_root))

    code, ss_output = _capture(["ss", "-H", "-tuln"])
    listens = code == 0 and f":{AGENT_PORT}" in ss_output
    ssh_listens = code == 0 and ":20022" in ss_output
    results.append(_check_status("SSH 20022 LISTEN", ssh_listens))
    results.append(_check_status("APP 15034 LISTEN", listens))
    return results


def _verify_firewall() -> list[bool]:
    results: list[bool] = []
    if shutil.which("ufw"):
        code, output = _sudo_capture(["ufw", "status"])
        active = code == 0 and "Status: active" in output
        allow_lines = [
            line.strip()
            for line in output.splitlines()
            if "ALLOW" in line and ("Anywhere" in line or "IN" in line)
        ]
        allowed_ports = {line.split()[0].lower() for line in allow_lines if line.split()}
        expected = {"20022/tcp", "15034/tcp"}
        extra = sorted(port for port in allowed_ports if port not in expected and port != "20022" and port != "15034")
        results.append(_check_status("UFW 활성화", active))
        results.append(_check_status("UFW 20022/15034 허용", expected.issubset(allowed_ports), ", ".join(sorted(allowed_ports)) or "허용 없음"))
        results.append(_check_status("추가 인바운드 허용 없음", active and not extra, ", ".join(extra) if extra else ("OK" if active else "방화벽 비활성/조회 실패")))
        return results

    if shutil.which("firewall-cmd"):
        state_code, state = _sudo_capture(["firewall-cmd", "--state"])
        ports_code, ports = _sudo_capture(["firewall-cmd", "--list-ports"])
        active = state_code == 0 and "running" in state
        allowed_ports = set(ports.split()) if ports_code == 0 else set()
        expected = {"20022/tcp", "15034/tcp"}
        extra = sorted(allowed_ports - expected)
        results.append(_check_status("firewalld 활성화", active))
        results.append(_check_status("firewalld 20022/15034 허용", expected.issubset(allowed_ports), ", ".join(sorted(allowed_ports)) or "허용 없음"))
        results.append(_check_status("추가 인바운드 허용 없음", active and not extra, ", ".join(extra) if extra else ("OK" if active else "방화벽 비활성/조회 실패")))
        return results

    results.append(_check_status("방화벽 도구", False, "ufw/firewalld 없음"))
    return results


def _verify_users_and_permissions() -> list[bool]:
    results: list[bool] = []
    expected_groups = {
        "agent-admin": {"agent-common", "agent-core"},
        "agent-dev": {"agent-common", "agent-core"},
        "agent-test": {"agent-common"},
    }
    for user, groups in expected_groups.items():
        code, output = _capture(["id", "-nG", user])
        actual = set(output.split()) if code == 0 else set()
        results.append(_check_status(f"{user} 그룹", groups.issubset(actual), " ".join(sorted(actual)) or "없음"))

    directory_checks = [
        (AGENT_HOME, "agent-admin", "agent-core", "AGENT_HOME"),
        (AGENT_UPLOAD_DIR, "agent-admin", "agent-common", "upload_files"),
        (AGENT_KEY_DIR, "agent-admin", "agent-core", "api_keys"),
        (AGENT_LOG_DIR, "agent-admin", "agent-core", "agent 로그 디렉터리"),
    ]
    for path, owner, group, label in directory_checks:
        ok, actual_owner, actual_group, mode = _stat_fields(path)
        desired = ok and actual_owner == owner and actual_group == group
        if path == AGENT_HOME:
            desired = desired and _group_rx(mode) and _other_none(mode)
        else:
            desired = desired and _group_rw(mode)
        if path in {AGENT_KEY_DIR, AGENT_LOG_DIR}:
            desired = desired and _other_none(mode)
        results.append(_check_status(label, desired, f"{actual_owner}:{actual_group} {mode}" if ok else mode))

    ok, owner, group, mode = _stat_fields(AGENT_KEY_FILE)
    content_ok = _file_text(AGENT_KEY_FILE).strip() == "agent_api_key_test"
    key_ok = ok and owner == "agent-admin" and group == "agent-core" and _group_rw(mode) and _other_none(mode) and content_ok
    results.append(_check_status("API 키 파일", key_ok, f"{owner}:{group} {mode}" if ok else mode))
    return results


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
        if re.search(r"(^|/)(agent-app-linux[^/ ]*|agent_app[.]py|agent-app)([ ]|$)", args):
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


def _agent_summary() -> tuple[list[tuple[str, str, str]], list[tuple[str, str, str]], bool]:
    records = _agent_processes()
    agent_admin_records = [record for record in records if record[0] == "agent-admin"]
    return records, agent_admin_records, bool(agent_admin_records) and _app_port_listening()


def _systemd_state() -> tuple[bool, str]:
    if not _systemd_available():
        return False, "systemd 없음"
    code, output = _sudo_capture(["systemctl", "is-active", "agent-app.service"])
    state = output.strip() or "unknown"
    return code == 0 and state == "active", state


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
    ok = _ops_status("실행 계정", bool(agent_admin_records), "agent-admin" if agent_admin_records else "agent-admin 아님") and ok
    ok = _ops_status(f"포트 {AGENT_PORT}", _app_port_listening(), "LISTEN" if _app_port_listening() else "닫힘") and ok
    ok = _ops_status("서비스 READY", ready, "agent-admin 프로세스 + 포트 LISTEN" if ready else "대기 중") and ok
    if _systemd_available():
        active, state = _systemd_state()
        _ops_status("systemd unit", active, state)
    else:
        _ops_warn("systemd unit", "사용 불가, 프로세스 직접 제어 모드")

    cron_code, cron_text = _crontab_text()
    cron_ok = cron_code == 0 and str(MONITOR_SCRIPT) in cron_text
    _ops_status("모니터링 cron", cron_ok, "등록됨" if cron_ok else "미등록 또는 조회 실패")

    log_ok, log_count, log_detail = _monitor_log_count()
    _ops_status("monitor.log", log_ok and log_count > 0, f"{log_count} lines" if log_ok else log_detail)

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
    code = run(["sudo", "pkill", "-TERM", "-u", "agent-admin", "-f", "agent-app-linux|/home/agent-admin/agent-app/bin/agent-app"])
    time.sleep(1)
    still_running, _, _ = _agent_summary()
    if still_running:
        print(S.warn("TERM 후에도 프로세스가 남아 있어 KILL을 시도합니다."))
        code = run(["sudo", "pkill", "-KILL", "-u", "agent-admin", "-f", "agent-app-linux|/home/agent-admin/agent-app/bin/agent-app"])
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


def _verify_environment_and_app() -> list[bool]:
    results: list[bool] = []
    profile = _file_text(Path("/etc/profile.d/agent-app.sh"))
    expected_exports = [
        f"export AGENT_HOME={AGENT_HOME}",
        f"export AGENT_PORT={AGENT_PORT}",
        f"export AGENT_UPLOAD_DIR={AGENT_UPLOAD_DIR}",
        f"export AGENT_KEY_PATH={AGENT_KEY_PATH}",
        f"export AGENT_LOG_DIR={AGENT_LOG_DIR}",
    ]
    results.append(_check_status("환경 변수 profile", all(item in profile for item in expected_exports)))

    code, ps_output = _capture(PS_AGENT_COMMAND)
    agent_records = _agent_process_records(ps_output) if code == 0 else []
    agent_admin_records = [record for record in agent_records if record[0] == "agent-admin"]
    selected_records = agent_admin_records or agent_records
    agent_user = selected_records[0][0] if selected_records else ""
    agent_detail = (
        f"{selected_records[0][0]} {selected_records[0][1]} {selected_records[0][2]}"
        if selected_records
        else "없음"
    )
    process_ready = bool(agent_admin_records) and _app_port_listening()

    ready_detail = "agent-admin 프로세스와 포트 LISTEN으로 확인" if process_ready else ""
    results.append(_check_status("Boot Sequence 5단계 OK", process_ready, ready_detail))
    results.append(_check_status("Agent READY", process_ready, ready_detail))

    results.append(_check_status("agent 프로세스 실행", bool(agent_records), agent_detail))
    results.append(_check_status("agent 실행 계정", agent_user == "agent-admin", agent_user or "없음"))
    return results


def _verify_monitor_and_logs() -> list[bool]:
    results: list[bool] = []
    for path, owner, group, mode_want, label in [
        (MONITOR_SCRIPT, "agent-dev", "agent-core", "750", "monitor.sh 설치/권한"),
        (REPORT_SCRIPT, "agent-dev", "agent-core", "750", "report.sh 설치/권한"),
    ]:
        ok, actual_owner, actual_group, mode = _stat_fields(path)
        results.append(_check_status(label, ok and actual_owner == owner and actual_group == group and mode == mode_want, f"{actual_owner}:{actual_group} {mode}" if ok else mode))

    code, _ = _capture(["bash", "-n", str(ROOT / "scripts" / "agent" / "monitor.sh")])
    results.append(_check_status("monitor.sh 문법", code == 0))

    log_path = AGENT_LOG_DIR / "monitor.log"
    code, output = _sudo_capture(["tail", "-n", "1", str(log_path)])
    latest = output.strip().splitlines()[-1] if output.strip() else ""
    results.append(_check_status("monitor.log 최근 라인", code == 0 and MONITOR_LOG_PATTERN.match(latest) is not None, latest or "없음"))
    return results


def _verify_cron() -> list[bool]:
    results: list[bool] = []
    code, output = _crontab_text()
    registered = code == 0 and str(MONITOR_SCRIPT) in output and any(
        line.strip().startswith("* * * * *") and str(MONITOR_SCRIPT) in line for line in output.splitlines()
    )
    results.append(_check_status("crontab 매분 등록", registered))
    ok, count, detail = _monitor_log_count()
    results.append(_check_status("monitor.log 누적", ok and count > 0, f"{count} lines" if ok else detail))
    return results


def _verify_logrotate() -> list[bool]:
    results: list[bool] = []
    policy_text = _file_text(LOGROTATE_POLICY)
    template_text = _file_text(LOGROTATE_TEMPLATE)
    active_text = policy_text or template_text
    results.append(_check_status("logrotate 정책 설치", LOGROTATE_POLICY.exists(), str(LOGROTATE_POLICY)))
    results.append(_check_status("logrotate repo 템플릿", LOGROTATE_TEMPLATE.exists(), str(LOGROTATE_TEMPLATE.relative_to(ROOT))))
    results.append(_check_status("10MB 기준", "size 10M" in active_text))
    results.append(_check_status("10개 보관", "rotate 10" in active_text))
    results.append(_check_status("gzip 압축", "compress" in active_text))
    dry_ok, dry_detail = _sudo_logrotate_dry_run()
    results.append(_check_status("logrotate dry-run", dry_ok, dry_detail))
    return results


def doctor(*, interactive: bool = True, cron_wait: bool = False, wait_seconds: int = 75) -> int:
    if interactive:
        header()
    print(S.title("운영 진단"))
    print(S.dim("서비스 실행, 접근 통제, 로그, cron, logrotate 구성을 점검합니다."))

    all_results: list[bool] = []
    _section("SSH / 포트")
    all_results.extend(_verify_ssh())
    _section("방화벽")
    all_results.extend(_verify_firewall())
    _section("계정 / 권한")
    all_results.extend(_verify_users_and_permissions())
    _section("환경 / 앱")
    all_results.extend(_verify_environment_and_app())
    _section("monitor / 로그")
    all_results.extend(_verify_monitor_and_logs())
    _section("cron")
    all_results.extend(_verify_cron())
    if cron_wait:
        before_ok, before_count, _ = _monitor_log_count()
        if before_ok:
            print(f"cron 자동 누적 확인을 위해 {wait_seconds}초 대기합니다.")
            time.sleep(wait_seconds)
            after_ok, after_count, detail = _monitor_log_count()
            all_results.append(_check_status("cron 1분 자동 누적", after_ok and after_count > before_count, f"{before_count} -> {after_count}" if after_ok else detail))
        else:
            all_results.append(_check_status("cron 1분 자동 누적", False, "monitor.log 라인 수 확인 실패"))
    _section("logrotate")
    all_results.extend(_verify_logrotate())

    print()
    passed = sum(1 for item in all_results if item)
    total = len(all_results)
    if passed == total:
        print(S.ok(f"운영 진단 통과: {passed}/{total}"))
    else:
        print(S.bad(f"점검 필요 항목 있음: {passed}/{total}"))
    finish(interactive)
    return 0 if passed == total else 1


def _human_bytes(size: int) -> str:
    value = float(size)
    for unit in ["B", "KB", "MB", "GB"]:
        if value < 1024 or unit == "GB":
            return f"{value:.1f}{unit}" if unit != "B" else f"{int(value)}B"
        value /= 1024
    return f"{size}B"


LogFile = tuple[str, int, float]
LOGROTATE_SIZE_BYTES = 10 * 1024 * 1024
LOGROTATE_KEEP_COUNT = 10


def _matches_any(name: str, patterns: list[str]) -> bool:
    return any(fnmatch(name, pattern) for pattern in patterns)


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


def _sudo_log_file_records(patterns: list[str]) -> tuple[list[LogFile], str]:
    code, output = _sudo_capture([
        "find",
        str(AGENT_LOG_DIR),
        "-maxdepth",
        "1",
        "-type",
        "f",
        "-printf",
        "%T@\t%s\t%f\n",
    ])
    if code != 0:
        return [], _sudo_failure_detail(output, "sudo 권한이 필요해 로그 목록을 조회하지 못했습니다.")

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
    return [
        record
        for record in rotated_logs
        if record[0].startswith("monitor.log.")
    ]


def _summarize_monitor_rotation(active_logs: list[LogFile], rotated_logs: list[LogFile], detail: str = "") -> None:
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
    print(f"{'현재 크기':<18} {_human_bytes(current_size)} / {_human_bytes(LOGROTATE_SIZE_BYTES)}")
    print(f"{'보관 파일':<18} {len(monitor_files)}/{LOGROTATE_KEEP_COUNT}개, {_human_bytes(total_size)}")
    if monitor_log:
        print(f"{'현재 파일':<18} {_human_bytes(monitor_log[1])}  {monitor_log[0]}")
    else:
        print(f"{'현재 파일':<18} 없음")
    print(f"{'회전/압축본':<18} {len(monitor_rotated)}개, {_human_bytes(rotated_size)}")
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
    if "no new privileges" in output or "password is required" in output or "a password is required" in output:
        return False, "sudo 권한이 필요해 dry-run은 건너뜀"
    for line in output.splitlines():
        if "error:" in line:
            return False, line.strip()
    return False, "dry-run 실패"


def logrotate_dashboard(*, interactive: bool = True) -> int:
    if interactive:
        header()

    active_logs, active_detail = _list_log_files(["*.log", "*.out"])
    rotated_logs, rotated_detail = _list_log_files(["*.log.[0-9]*", "*.log.*.gz", "*.out.[0-9]*", "*.out.*.gz"])
    detail = active_detail if _detail_is_error(active_detail) else rotated_detail

    _summarize_monitor_rotation(active_logs, rotated_logs, detail)

    if not LOGROTATE_POLICY.exists():
        print()
        print(S.warn("아직 시스템에 logrotate 정책이 설치되지 않았습니다."))
        print("`python3 main.py install`을 먼저 실행하면 설치됩니다.")

    finish(interactive)
    return 0


def syntax_check(*, interactive: bool = True) -> int:
    if interactive:
        header()
    print(S.title("스크립트 문법 검사"))
    files = [
        "scripts/apply_system.sh",
        "scripts/agent/monitor.sh",
        "scripts/agent/report.sh",
    ]
    ok = True
    for file_name in files:
        code = run(["bash", "-n", file_name])
        ok = ok and code == 0
        status_line(file_name, code == 0)
    finish(interactive)
    return 0 if ok else 1
