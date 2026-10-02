"""시스템 명령을 실행하지 않고 분리한 명령·실행 계층 계약을 확인한다."""

import subprocess

from service_ops import parser
from service_ops.actions import support


def test_foreground_start_passes_confirmation_to_selected_action(monkeypatch):
    called = []
    monkeypatch.setattr(
        parser, "start_agent_foreground", lambda **kwargs: called.append(kwargs) or 7
    )
    args = parser.build_parser().parse_args(["start", "--foreground", "--yes"])
    assert parser.dispatch(args) == 7
    assert called == [{"interactive": False, "assume_yes": True}]


def test_capture_timeout_preserves_error_code(monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("test-command", 1, output="시간 초과 로그")

    monkeypatch.setattr(support.subprocess, "run", timeout)
    assert support._capture(["test-command"], timeout=1) == (124, "시간 초과 로그")


def test_sudo_retry_is_only_used_after_prompt_eligible_failure(monkeypatch):
    calls = []

    def capture(command, **kwargs):
        calls.append(command)
        return (1, "암호 필요") if len(calls) == 1 else (0, "완료")

    monkeypatch.setattr(support, "_capture", capture)
    monkeypatch.setattr(support, "_sudo_can_retry_with_prompt", lambda output: True)
    assert support._sudo_capture(["stat", "file"]) == (0, "완료")
    assert calls == [["sudo", "-n", "stat", "file"], ["sudo", "stat", "file"]]
