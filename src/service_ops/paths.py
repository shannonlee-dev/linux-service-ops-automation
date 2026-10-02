from __future__ import annotations

from pathlib import Path

_CHECKOUT_DIR = Path(__file__).resolve().parents[2]
ROOT = _CHECKOUT_DIR if (_CHECKOUT_DIR / "pyproject.toml").is_file() else Path.cwd()
APPLY = ROOT / "scripts" / "apply_system.sh"
LOGROTATE_TEMPLATE = ROOT / "config" / "logrotate" / "agent-app"
SYSTEMD_UNIT_TEMPLATE = ROOT / "config" / "systemd" / "agent-app.service"
