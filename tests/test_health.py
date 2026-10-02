"""방화벽·TCP 서비스 상태를 시스템 변경 없이 검증한다."""

import subprocess
from pathlib import Path

import pytest

from service_ops.actions import process

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("state,healthy", [("active", True), ("inactive", False)])
def test_monitor_firewall_does_not_accept_inactive(state, healthy):
    script = (ROOT / "scripts/agent/monitor.sh").read_text()
    begin = script.index("check_firewall() {")
    end = script.index("\n}", begin) + 2
    command = (
        f"ufw() {{ printf 'Status: {state}\\n'; }}; "
        "warn() { printf 'WARNING:%s\\n' \"$*\"; }; "
        + script[begin:end]
        + "; check_firewall"
    )
    output = subprocess.check_output(["bash", "-c", command], text=True)
    assert ("[OK] UFW active" in output) is healthy


@pytest.mark.parametrize(
    "output,healthy",
    [
        ("tcp LISTEN 0 128 0.0.0.0:15034 0.0.0.0:*", True),
        ("tcp LISTEN 0 128 [::]:15034 [::]:*", True),
        ("udp UNCONN 0 0 0.0.0.0:15034 0.0.0.0:*", False),
        ("tcp LISTEN 0 128 0.0.0.0:22 0.0.0.0:15034", False),
        ("tcp LISTEN 0 128 0.0.0.0:1503 0.0.0.0:*", False),
    ],
)
def test_service_requires_local_tcp_listener(monkeypatch, output, healthy):
    monkeypatch.setattr(process, "_capture", lambda args: (0, output))
    assert process._app_port_listening() is healthy


def test_listener_query_failure_is_unhealthy(monkeypatch):
    monkeypatch.setattr(process, "_capture", lambda args: (1, "permission denied"))
    assert not process._app_port_listening()
