"""네트워크·권한·서비스·로그의 운영 진단."""

from __future__ import annotations

import re
import shutil
import time
from pathlib import Path

from ..paths import LOGROTATE_TEMPLATE, ROOT
from ..style import S
from ..ui import finish, header
from .cron_runtime import _crontab_text, _monitor_log_count
from .logs import _sudo_logrotate_dry_run
from .process import _agent_process_records, _app_port_listening, _tcp_port_listening
from .settings import (
    AGENT_HOME,
    AGENT_KEY_DIR,
    AGENT_KEY_FILE,
    AGENT_LOG_DIR,
    AGENT_PORT,
    AGENT_UPLOAD_DIR,
    BASH_BASHRC,
    LOGROTATE_POLICY,
    MONITOR_LOG_PATTERN,
    MONITOR_SCRIPT,
    PROFILE_ENV,
    PS_AGENT_COMMAND,
    REPORT_SCRIPT,
)
from .support import (
    _capture,
    _check_status,
    _file_text,
    _group_rw,
    _group_rx,
    _other_none,
    _section,
    _stat_fields,
    _sudo_capture,
    _warn_status,
)


def _verify_ssh() -> list[bool]:
    results: list[bool] = []
    code, sshd_t = _sudo_capture(["sshd", "-T"])
    config_text = _file_text(Path("/etc/ssh/sshd_config"))
    effective_port = "port 20022" in sshd_t.lower()
    effective_root = "permitrootlogin no" in sshd_t.lower()
    configured_port = re.search(r"(?im)^\s*Port\s+20022\s*$", config_text) is not None
    configured_root = (
        re.search(r"(?im)^\s*PermitRootLogin\s+no\s*$", config_text) is not None
    )
    if code != 0:
        _warn_status(
            "sshd -T", "sudo 비밀번호 없이 실행 불가, 설정 파일 기준도 함께 확인"
        )
    results.append(_check_status("SSH Port 20022", effective_port or configured_port))
    results.append(
        _check_status("Root 원격 로그인 차단", effective_root or configured_root)
    )

    listens = _app_port_listening()
    ssh_listens = _tcp_port_listening("20022")
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
        allowed_ports = {
            line.split()[0].lower() for line in allow_lines if line.split()
        }
        expected = {"20022/tcp", "15034/tcp"}
        extra = sorted(
            port
            for port in allowed_ports
            if port not in expected and port != "20022" and port != "15034"
        )
        results.append(_check_status("UFW 활성화", active))
        results.append(
            _check_status(
                "UFW 20022/15034 허용",
                expected.issubset(allowed_ports),
                ", ".join(sorted(allowed_ports)) or "허용 없음",
            )
        )
        results.append(
            _check_status(
                "추가 인바운드 허용 없음",
                active and not extra,
                ", ".join(extra)
                if extra
                else ("OK" if active else "방화벽 비활성/조회 실패"),
            )
        )
        return results

    if shutil.which("firewall-cmd"):
        state_code, state = _sudo_capture(["firewall-cmd", "--state"])
        ports_code, ports = _sudo_capture(["firewall-cmd", "--list-ports"])
        active = state_code == 0 and "running" in state
        allowed_ports = set(ports.split()) if ports_code == 0 else set()
        expected = {"20022/tcp", "15034/tcp"}
        extra = sorted(allowed_ports - expected)
        results.append(_check_status("firewalld 활성화", active))
        results.append(
            _check_status(
                "firewalld 20022/15034 허용",
                expected.issubset(allowed_ports),
                ", ".join(sorted(allowed_ports)) or "허용 없음",
            )
        )
        results.append(
            _check_status(
                "추가 인바운드 허용 없음",
                active and not extra,
                ", ".join(extra)
                if extra
                else ("OK" if active else "방화벽 비활성/조회 실패"),
            )
        )
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
        results.append(
            _check_status(
                f"{user} 그룹",
                groups.issubset(actual),
                " ".join(sorted(actual)) or "없음",
            )
        )

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
        results.append(
            _check_status(
                label, desired, f"{actual_owner}:{actual_group} {mode}" if ok else mode
            )
        )

    ok, owner, group, mode = _stat_fields(AGENT_KEY_FILE)
    content_ok = _file_text(AGENT_KEY_FILE).strip() == "agent_api_key_test"
    key_ok = (
        ok
        and owner == "agent-admin"
        and group == "agent-core"
        and _group_rw(mode)
        and _other_none(mode)
        and content_ok
    )
    results.append(
        _check_status("API 키 파일", key_ok, f"{owner}:{group} {mode}" if ok else mode)
    )
    return results


def _verify_environment_and_app() -> list[bool]:
    results: list[bool] = []
    profile_clean = not PROFILE_ENV.exists()
    bashrc_clean = "# BEGIN agent-app env" not in _file_text(BASH_BASHRC)
    results.append(
        _check_status(
            "환경 변수 전역 미등록",
            profile_clean and bashrc_clean,
            "profile.d/bash.bashrc에 남지 않음"
            if profile_clean and bashrc_clean
            else "전역 shell 설정에 agent env 흔적 있음",
        )
    )

    code, ps_output = _capture(PS_AGENT_COMMAND)
    agent_records = _agent_process_records(ps_output) if code == 0 else []
    agent_admin_records = [
        record for record in agent_records if record[0] == "agent-admin"
    ]
    selected_records = agent_admin_records or agent_records
    agent_user = selected_records[0][0] if selected_records else ""
    agent_detail = (
        f"{selected_records[0][0]} {selected_records[0][1]} {selected_records[0][2]}"
        if selected_records
        else "없음"
    )
    process_ready = bool(agent_admin_records) and _app_port_listening()

    ready_detail = (
        "agent-admin 프로세스와 포트 LISTEN으로 확인" if process_ready else ""
    )
    results.append(_check_status("Boot Sequence 5단계 OK", process_ready, ready_detail))
    results.append(_check_status("Agent READY", process_ready, ready_detail))

    results.append(
        _check_status("agent 프로세스 실행", bool(agent_records), agent_detail)
    )
    results.append(
        _check_status(
            "agent 실행 계정", agent_user == "agent-admin", agent_user or "없음"
        )
    )
    return results


def _verify_monitor_and_logs() -> list[bool]:
    results: list[bool] = []
    for path, owner, group, mode_want, label in [
        (MONITOR_SCRIPT, "agent-dev", "agent-core", "750", "monitor.sh 설치/권한"),
        (REPORT_SCRIPT, "agent-dev", "agent-core", "750", "report.sh 설치/권한"),
    ]:
        ok, actual_owner, actual_group, mode = _stat_fields(path)
        results.append(
            _check_status(
                label,
                ok
                and actual_owner == owner
                and actual_group == group
                and mode == mode_want,
                f"{actual_owner}:{actual_group} {mode}" if ok else mode,
            )
        )

    code, _ = _capture(["bash", "-n", str(ROOT / "scripts" / "agent" / "monitor.sh")])
    results.append(_check_status("monitor.sh 문법", code == 0))

    log_path = AGENT_LOG_DIR / "monitor.log"
    code, output = _sudo_capture(["tail", "-n", "1", str(log_path)])
    latest = output.strip().splitlines()[-1] if output.strip() else ""
    results.append(
        _check_status(
            "monitor.log 최근 라인",
            code == 0 and MONITOR_LOG_PATTERN.match(latest) is not None,
            latest or "없음",
        )
    )
    return results


def _verify_cron() -> list[bool]:
    results: list[bool] = []
    code, output = _crontab_text()
    registered = (
        code == 0
        and str(MONITOR_SCRIPT) in output
        and any(
            line.strip().startswith("* * * * *") and str(MONITOR_SCRIPT) in line
            for line in output.splitlines()
        )
    )
    results.append(_check_status("crontab 매분 등록", registered))
    ok, count, detail = _monitor_log_count()
    results.append(
        _check_status(
            "monitor.log 누적", ok and count > 0, f"{count} lines" if ok else detail
        )
    )
    return results


def _verify_logrotate() -> list[bool]:
    results: list[bool] = []
    policy_text = _file_text(LOGROTATE_POLICY)
    template_text = _file_text(LOGROTATE_TEMPLATE)
    active_text = policy_text or template_text
    results.append(
        _check_status(
            "logrotate 정책 설치", LOGROTATE_POLICY.exists(), str(LOGROTATE_POLICY)
        )
    )
    results.append(
        _check_status(
            "logrotate repo 템플릿",
            LOGROTATE_TEMPLATE.exists(),
            str(LOGROTATE_TEMPLATE.relative_to(ROOT)),
        )
    )
    results.append(_check_status("10MB 기준", "size 10M" in active_text))
    results.append(_check_status("10개 보관", "rotate 10" in active_text))
    results.append(_check_status("gzip 압축", "compress" in active_text))
    dry_ok, dry_detail = _sudo_logrotate_dry_run()
    results.append(_check_status("logrotate dry-run", dry_ok, dry_detail))
    return results


def doctor(
    *, interactive: bool = True, cron_wait: bool = False, wait_seconds: int = 75
) -> int:
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
            all_results.append(
                _check_status(
                    "cron 1분 자동 누적",
                    after_ok and after_count > before_count,
                    f"{before_count} -> {after_count}" if after_ok else detail,
                )
            )
        else:
            all_results.append(
                _check_status(
                    "cron 1분 자동 누적", False, "monitor.log 라인 수 확인 실패"
                )
            )
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
