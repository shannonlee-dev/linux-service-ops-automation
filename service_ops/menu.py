from __future__ import annotations

from .actions import (
    apply_system,
    crontab_dashboard,
    cron_service_menu,
    logrotate_dashboard,
    restart_agent,
    service_status,
    show_logs,
    show_report,
    start_agent_menu,
    stop_agent,
)
from .style import S
from .ui import header, pause


def menu() -> None:
    actions = {
        "1": ("서비스 상태", service_status),
        "2": ("서비스 시작", start_agent_menu),
        "3": ("서비스 중지", stop_agent),
        "4": ("서비스 재시작", restart_agent),
        "5": ("monitor.log 보기", show_logs),
        "6": ("리소스 리포트", show_report),
        "7": ("monitor.log 보관 현황", logrotate_dashboard),
        "8": ("모니터링 cron 상태", crontab_dashboard),
        "9": ("cron 데몬 제어", cron_service_menu),
        "10": ("설치/수리", apply_system),
    }
    while True:
        header()
        for key, (label, _) in actions.items():
            print(f"{key}. {label}")
        print("0. 종료")
        choice = input("\n번호 선택: ").strip()
        if choice == "0":
            print("좋습니다. 작업을 마칩니다.")
            return
        action = actions.get(choice)
        if action is None:
            print(S.bad("없는 번호입니다."))
            pause()
            continue
        action[1](interactive=True)
