"""cron 실패를 임시 파일과 가짜 crontab으로 재현한다."""

import os
import subprocess
from pathlib import Path

import pytest

from service_ops.actions import cron

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("entrypoint", ["cli", "installer"])
@pytest.mark.parametrize("exit_code", [0, 7])
def test_registration_preserves_crontab_exit_code(
    tmp_path, monkeypatch, entrypoint, exit_code
):
    fake = tmp_path / "crontab"
    fake.write_text(
        "#!/bin/bash\n"
        'if [[ "$*" == *" -l" ]]; then exit 1; fi\n'
        'cat "${@: -1}" > "$REGISTERED_FILE"\n'
        'exit "$REGISTER_EXIT"\n'
    )
    fake.chmod(0o750)
    env = dict(
        os.environ,
        PATH=f"{tmp_path}:{os.environ['PATH']}",
        REGISTERED_FILE=str(tmp_path / "registered"),
        REGISTER_EXIT=str(exit_code),
    )
    monkeypatch.setattr(cron, "ROOT", tmp_path)
    if entrypoint == "cli":

        def execute(args):
            assert args[:3] == ["sudo", "bash", "-lc"]
            return subprocess.run(
                ["bash", "-c", args[3]], env=env, check=False
            ).returncode

        monkeypatch.setattr(cron, "run", execute)
        actual = cron.install_cron(interactive=False, assume_yes=True)
    else:
        # Execute only the installer cron block, never the system installer.
        block = next(
            line
            for line in (ROOT / "scripts/apply_system.sh").read_text().splitlines()
            if line.startswith('run_cmd "매분 monitor 등록"')
        )
        command = (
            'run_cmd() { bash -c "$2"; }; '
            "AGENT_HOME=/home/agent-admin/agent-app; AGENT_PORT=15034; "
            "AGENT_UPLOAD_DIR=/tmp/uploads; AGENT_KEY_PATH=/tmp/keys; "
            "AGENT_LOG_DIR=/tmp/logs; " + block
        )
        actual = subprocess.run(
            ["bash", "-c", command], env=env, check=False
        ).returncode
    assert actual == exit_code
    assert (tmp_path / "registered").read_text().count("* * * * *") == 1


def test_declined_registration_does_not_execute(monkeypatch):
    monkeypatch.setattr(cron, "yes_no", lambda prompt: False)

    def unexpected(*args):
        pytest.fail("Declined registration executed a system command")

    monkeypatch.setattr(cron, "run", unexpected)
    assert cron.install_cron(interactive=False) == 2
