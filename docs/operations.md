# 운영 절차

## 준비와 진단

전용 Linux 실습 호스트에서 Python 3.10 이상, Bash, 대상 아키텍처에 맞는 바이너리, 시스템 관리 권한을 준비합니다. 저장소 루트에서 실행합니다.

```bash
uv run --frozen service-ops --help
uv run --frozen service-ops check
uv run --frozen service-ops doctor
```

## 설치

`scripts/apply_system.sh`와 systemd·logrotate 설정을 검토한 뒤 대화형 확인을 거쳐 적용합니다. 설치는 사용자·그룹·디렉토리 권한·cron·SSH·방화벽 정책을 변경합니다.

```bash
uv run --frozen service-ops install
```

운영 SSH 세션을 유지하며 적용 후 별도 세션에서 접속 상태를 확인합니다. `--yes` 옵션은 도구의 확인 질문을 생략하므로 자동 실행 환경에서 변경 범위를 이미 확인한 경우에만 사용합니다.

## 서비스와 로그

```bash
uv run --frozen service-ops status
uv run --frozen service-ops start
uv run --frozen service-ops logs
uv run --frozen service-ops report
uv run --frozen service-ops retention
uv run --frozen service-ops cron
```

`start --foreground`는 현재 터미널에서 실행하고 `start --follow-logs`는 백그라운드 시작 후 로그를 따라갑니다. `stop`과 `restart`는 실제 서비스 프로세스를 변경합니다.

## 모니터링

모니터링은 `/proc`의 CPU·메모리 정보를 읽고 앱과 로그 디렉토리의 디스크 사용량을 계산합니다. cron은 매분 `/var/log/agent-app/monitor.log`에 결과를 누적합니다. logrotate는 10MB 기준으로 회전하고 최대 10개 회전본을 유지합니다.

`cron-enable`, `cron-service start`, `cron-check`는 cron 또는 앱을 준비·변경할 수 있습니다. 이 명령은 CI에서 실행하지 않습니다.

## 확인 범위

`make check`는 Python·Bash 문법과 문서 링크를 확인합니다. `make smoke`는 도움말과 기존 문법 검사 명령을 확인합니다. 실제 호스트에서는 `doctor`로 계정·권한·설치 전제를, `status`로 서비스·포트를 확인합니다. `cron`과 `retention`으로 스케줄과 로그 보관 상태를 확인하고, `report`로 수집 결과를 점검합니다. 검증한 호스트와 시각을 함께 기록합니다.
