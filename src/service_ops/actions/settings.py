"""기존 운영 대상 경로와 로그 정책 상수."""

from __future__ import annotations

import re
from pathlib import Path

LOGROTATE_POLICY = Path("/etc/logrotate.d/agent-app")


SYSTEMD_UNIT = Path("/etc/systemd/system/agent-app.service")


PROFILE_ENV = Path("/etc/profile.d/agent-app.sh")


BASH_BASHRC = Path("/etc/bash.bashrc")


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


LogFile = tuple[str, int, float]


LOGROTATE_SIZE_BYTES = 10 * 1024 * 1024


LOGROTATE_KEEP_COUNT = 10
