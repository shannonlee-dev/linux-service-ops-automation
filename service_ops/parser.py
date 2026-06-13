from __future__ import annotations

import argparse

from .actions import (
    apply_system,
    cron_growth_test,
    cron_service_control,
    cron_service_status,
    crontab_dashboard,
    doctor,
    install_cron,
    logrotate_dashboard,
    run_monitor,
    follow_agent_logs,
    restart_agent,
    service_status,
    show_logs,
    show_report,
    start_agent,
    start_agent_foreground,
    stop_agent,
    syntax_check,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Agent service operations CLI. 인자 없이 실행하면 운영 메뉴가 열립니다.",
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("status", help="서비스 상태, 포트, cron, 로그 보관 현황을 봅니다.")

    start_parser = subparsers.add_parser("start", help="agent 서비스를 시작합니다(systemd 우선, 없으면 background fallback).")
    start_parser.add_argument("--yes", "-y", action="store_true", help="확인 질문 없이 실행합니다.")
    start_parser.add_argument("--foreground", action="store_true", help="백그라운드 대신 현재 터미널에서 agent를 실행합니다.")
    start_parser.add_argument("--follow-logs", action="store_true", help="백그라운드 시작 후 agent stdout/stderr 로그를 따라봅니다.")

    stop_parser = subparsers.add_parser("stop", help="실행 중인 agent 프로세스를 종료합니다.")
    stop_parser.add_argument("--yes", "-y", action="store_true", help="확인 질문 없이 종료합니다.")

    restart_parser = subparsers.add_parser("restart", help="agent를 재시작합니다.")
    restart_parser.add_argument("--yes", "-y", action="store_true", help="확인 질문 없이 재시작합니다.")

    install_parser = subparsers.add_parser("install", help="사용자, 권한, 앱, cron, logrotate 구성을 설치/수리합니다.")
    install_parser.add_argument("--yes", "-y", action="store_true", help="확인 질문 없이 적용합니다.")

    subparsers.add_parser("doctor", help="운영 전제와 시스템 구성을 진단합니다.")
    subparsers.add_parser("check", help="로컬 스크립트 문법 검사를 실행합니다.")
    subparsers.add_parser("monitor", help="설치된 monitor.sh를 agent-admin으로 즉시 실행합니다.")
    subparsers.add_parser("logs", help="monitor.log를 tail로 봅니다.")
    subparsers.add_parser("report", help="report.sh 통계 결과를 봅니다.")
    subparsers.add_parser("retention", help="monitor.log 보관 파일과 회전본 현황을 봅니다.")
    cron_install_parser = subparsers.add_parser("cron-enable", help="agent-admin crontab에 monitor.sh 매분 실행을 등록합니다.")
    cron_install_parser.add_argument("--yes", "-y", action="store_true", help="확인 질문 없이 등록합니다.")
    subparsers.add_parser("cron", help="crontab 등록 상태를 확인합니다.")
    cron_service_parser = subparsers.add_parser("cron-service", help="cron 데몬 상태를 확인하거나 시작/중지/재시작합니다.")
    cron_service_parser.add_argument("action", choices=["status", "start", "stop", "restart"], help="cron 데몬 작업")
    cron_service_parser.add_argument("--yes", "-y", action="store_true", help="확인 질문 없이 실행합니다.")
    cron_test_parser = subparsers.add_parser("cron-check", help="cron과 agent를 필요 시 준비하고 monitor.log 자동 증가를 확인합니다.")
    cron_test_parser.add_argument("--wait", type=int, default=75, help="대기 시간(초). 기본값: 75")
    return parser


def dispatch(args: argparse.Namespace) -> int:
    if args.command == "status":
        return service_status(interactive=False)
    if args.command == "start":
        if args.foreground:
            return start_agent_foreground(interactive=False, assume_yes=args.yes)
        if args.follow_logs:
            code = start_agent(interactive=False, assume_yes=args.yes)
            if code == 0:
                return follow_agent_logs(interactive=False)
            return code
        return start_agent(interactive=False, assume_yes=args.yes)
    if args.command == "stop":
        return stop_agent(interactive=False, assume_yes=args.yes)
    if args.command == "restart":
        return restart_agent(interactive=False, assume_yes=args.yes)
    if args.command == "install":
        return apply_system(interactive=False, assume_yes=args.yes)
    if args.command == "doctor":
        return doctor(interactive=False)
    if args.command == "check":
        return syntax_check(interactive=False)
    if args.command == "monitor":
        return run_monitor(interactive=False)
    if args.command == "logs":
        return show_logs(interactive=False)
    if args.command == "report":
        return show_report(interactive=False)
    if args.command == "retention":
        return logrotate_dashboard(interactive=False)
    if args.command == "cron-enable":
        return install_cron(interactive=False, assume_yes=args.yes)
    if args.command == "cron":
        return crontab_dashboard(interactive=False)
    if args.command == "cron-service":
        if args.action == "status":
            return cron_service_status(interactive=False)
        return cron_service_control(args.action, interactive=False, assume_yes=args.yes)
    if args.command == "cron-check":
        return cron_growth_test(interactive=False, wait_seconds=args.wait)
    return 2
