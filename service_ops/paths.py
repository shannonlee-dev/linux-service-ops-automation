from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APPLY = ROOT / "scripts" / "apply_system.sh"
LOGROTATE_TEMPLATE = ROOT / "config" / "logrotate" / "agent-app"
SYSTEMD_UNIT_TEMPLATE = ROOT / "config" / "systemd" / "agent-app.service"
