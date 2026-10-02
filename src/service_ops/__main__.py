"""설치된 패키지의 모듈 실행 진입점."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
