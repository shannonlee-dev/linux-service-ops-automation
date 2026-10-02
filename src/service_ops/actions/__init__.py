"""CLI・메뉴에서 사용하는 운영 명령의 공개 인터페이스."""

from .cron import (
    cron_growth_test,
    cron_service_control,
    cron_service_menu,
    cron_service_status,
    crontab_dashboard,
    install_cron,
)
from .diagnostics import doctor
from .installation import apply_system, syntax_check
from .logs import logrotate_dashboard, run_monitor, show_logs, show_report
from .service import (
    follow_agent_logs,
    restart_agent,
    service_status,
    start_agent,
    start_agent_foreground,
    start_agent_menu,
    stop_agent,
)
from .support import shlex_quote

__all__ = [
    "apply_system",
    "cron_growth_test",
    "cron_service_control",
    "cron_service_menu",
    "cron_service_status",
    "crontab_dashboard",
    "doctor",
    "follow_agent_logs",
    "install_cron",
    "logrotate_dashboard",
    "restart_agent",
    "run_monitor",
    "service_status",
    "shlex_quote",
    "show_logs",
    "show_report",
    "start_agent",
    "start_agent_foreground",
    "start_agent_menu",
    "stop_agent",
    "syntax_check",
]
