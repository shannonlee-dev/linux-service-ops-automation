"""운영 환경 설치와 저장소 스크립트 문법 검사."""

from __future__ import annotations

from ..paths import APPLY
from ..runner import run
from ..style import S
from ..ui import finish, header, status_line, yes_no


def apply_system(*, interactive: bool = True, assume_yes: bool = False) -> int:
    if interactive:
        header()
    print(S.warn("이 작업은 실제 시스템 설정을 변경합니다."))
    print("- SSH 포트/root 로그인 정책")
    print("- 방화벽 규칙")
    print("- 로컬 계정/그룹/권한")
    print("- /home/agent-admin, /var/log/agent-app")
    print("- crontab")
    print()
    if not assume_yes and not yes_no("계속 적용할까요?"):
        print("취소했습니다.")
        finish(interactive)
        return 2
    code = run(["sudo", str(APPLY)])
    print()
    if code == 0:
        print(S.ok("적용 스크립트가 종료 코드 0으로 끝났습니다."))
    else:
        print(S.warn(f"적용 스크립트 종료 코드: {code}"))
    print(
        S.dim(
            "다음 단계: `uv run service-ops start --yes` 또는 메뉴의 서비스 시작을 실행하세요."
        )
    )
    finish(interactive)
    return code


def syntax_check(*, interactive: bool = True) -> int:
    if interactive:
        header()
    print(S.title("스크립트 문법 검사"))
    files = [
        "scripts/apply_system.sh",
        "scripts/agent/monitor.sh",
        "scripts/agent/report.sh",
    ]
    ok = True
    for file_name in files:
        code = run(["bash", "-n", file_name])
        ok = ok and code == 0
        status_line(file_name, code == 0)
    finish(interactive)
    return 0 if ok else 1
