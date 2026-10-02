"""서비스 제어의 실패·설치 전제·취소 경로를 격리한다."""

import pytest

from service_ops.actions import service


@pytest.mark.parametrize("code", [0, 9])
def test_systemd_start_preserves_service_manager_result(tmp_path, monkeypatch, code):
    unit = tmp_path / "agent-app.service"
    unit.touch()
    monkeypatch.setattr(service, "SYSTEMD_UNIT", unit)
    monkeypatch.setattr(service, "_systemd_available", lambda: True)

    def execute(args):
        assert args == ["sudo", "systemctl", "start", "agent-app.service"]
        return code

    monkeypatch.setattr(service, "run", execute)
    assert service.start_agent(interactive=False, assume_yes=True) == code


def test_background_start_requires_installed_executable(monkeypatch):
    monkeypatch.setattr(service, "_systemd_available", lambda: False)
    monkeypatch.setattr(service, "_agent_summary", lambda: ([], [], False))
    monkeypatch.setattr(
        service, "_installed_path_state", lambda *args, **kwargs: (False, "missing")
    )
    monkeypatch.setattr(
        service, "run", lambda args: pytest.fail("Started a missing binary")
    )
    assert service.start_agent(interactive=False, assume_yes=True) == 1


def test_stop_declined_never_signals_process(monkeypatch):
    record = ("agent-admin", "123", "/home/agent-admin/agent-app/bin/agent-app")
    monkeypatch.setattr(service, "_agent_summary", lambda: ([record], [record], True))
    monkeypatch.setattr(service, "yes_no", lambda prompt: False)
    monkeypatch.setattr(
        service, "run", lambda args: pytest.fail("Signaled after cancellation")
    )
    assert service.stop_agent(interactive=False) == 2
