from __future__ import annotations

import os
import sys

from .paths import ROOT
from .style import S


def clear() -> None:
    if sys.stdout.isatty():
        os.system("clear")


def pause() -> None:
    input(S.dim("\nEnter를 누르면 메뉴로 돌아갑니다. "))


def header() -> None:
    clear()
    print(S.title("Agent Service Operations"))
    print("agent 서비스 상태, 로그, 모니터링, 보관 정책을 다루는 운영 CLI")
    print(S.dim("자동화용 명령도 지원: python3 main.py --help"))
    print(S.dim(f"repo: {ROOT}"))
    print()


def finish(interactive: bool) -> None:
    if interactive:
        pause()


def yes_no(prompt: str) -> bool:
    answer = input(f"{prompt} [y/N] ").strip().lower()
    return answer in {"y", "yes"}


def status_line(label: str, ok: bool, detail: str = "") -> None:
    marker = S.ok("OK") if ok else S.bad("MISS")
    suffix = f" - {detail}" if detail else ""
    print(f"{label:<28} {marker}{suffix}")
