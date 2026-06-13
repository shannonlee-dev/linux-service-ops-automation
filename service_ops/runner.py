from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from .paths import ROOT
from .style import S


def run(command: list[str], *, check: bool = False, cwd: Path = ROOT) -> int:
    printable = " ".join(shlex.quote(part) for part in command)
    print(S.dim(f"$ {printable}"))
    try:
        completed = subprocess.run(command, cwd=str(cwd), check=check)
        return completed.returncode
    except KeyboardInterrupt:
        print()
        print(S.dim("사용자 중단(Ctrl-C)"))
        return 130
    except FileNotFoundError:
        print(S.bad(f"명령을 찾을 수 없습니다: {command[0]}"))
        return 127
    except subprocess.CalledProcessError as exc:
        return exc.returncode


def run_shell(command: str, *, check: bool = False) -> int:
    print(S.dim(f"$ {command}"))
    try:
        completed = subprocess.run(["bash", "-lc", command], cwd=str(ROOT), check=check)
        return completed.returncode
    except KeyboardInterrupt:
        print()
        print(S.dim("사용자 중단(Ctrl-C)"))
        return 130
    except subprocess.CalledProcessError as exc:
        return exc.returncode
