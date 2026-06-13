# Agent Service Operations

`agent-app`을 설치, 실행, 관제하기 위한 운영 CLI입니다. 서비스 계정, 권한, 로그, cron 모니터링, logrotate 보관 정책을 한 곳에서 다룹니다.

## 핵심 명령

```bash
python3 main.py status        # 서비스 상태 대시보드
python3 main.py start --yes   # agent 서비스 시작
python3 main.py start --foreground # 현재 터미널에서 agent 실행
python3 main.py start --follow-logs # 시작 후 stdout/stderr 로그 따라보기
python3 main.py stop --yes    # agent 프로세스 종료
python3 main.py restart --yes # 재시작
python3 main.py logs          # monitor.log tail
python3 main.py report        # monitor.log 통계 리포트
python3 main.py retention     # monitor.log 보관/회전 현황
python3 main.py cron          # monitor.sh cron 등록 상태
python3 main.py cron-service status # cron 데몬 상태
python3 main.py cron-service start --yes # cron 데몬 시작
python3 main.py cron-service stop --yes # cron 데몬 중지
python3 main.py cron-enable --yes
python3 main.py cron-check    # cron/agent를 필요 시 준비하고 자동 누적 확인
python3 main.py doctor        # 운영 구성 진단
python3 main.py install --yes # 시스템 설치/수리
```

인자 없이 실행하면 운영 메뉴가 열립니다.

```bash
python3 main.py
```

## 운영 모델

- 앱은 systemd가 있는 환경에서는 `agent-app.service`로 실행하고, 서비스 프로세스는 `agent-admin` 계정으로 동작합니다.
- systemd가 없는 컨테이너/실습 환경에서는 CLI가 background 실행으로 fallback합니다.
- 업로드 디렉터리는 `agent-common`, 키와 로그는 `agent-core` 중심 권한으로 분리합니다.
- `monitor.sh`는 cron으로 매분 실행되어 `/var/log/agent-app/monitor.log`에 상태를 누적합니다.
- `monitor.log`는 logrotate로 10MB 기준 회전하며 최대 10개까지 보관합니다.
- `report.sh`는 monitor 로그에서 CPU, 메모리, 디스크 사용률 통계를 계산합니다.

## 설치/수리

`install`은 실제 시스템 설정을 변경합니다.

- 로컬 사용자/그룹 생성 및 멤버십 설정
- `/home/agent-admin/agent-app`와 `/var/log/agent-app` 권한 정리
- agent 바이너리, monitor/report 스크립트 설치
- cron 등록
- logrotate 정책 설치
- SSH와 방화벽 정책 적용

실행 전 변경 범위를 확인하고, 운영 중인 접속 세션을 유지한 상태에서 실행하세요.

```bash
python3 main.py install
```

## 파일 구조

| Path | Description |
| --- | --- |
| `main.py` | CLI 진입점 |
| `service_ops/` | 운영 CLI 구현 |
| `scripts/apply_system.sh` | 시스템 설치/수리 스크립트 |
| `scripts/agent/monitor.sh` | 서비스/리소스 샘플 수집 |
| `scripts/agent/report.sh` | monitor.log 통계 리포트 |
| `config/logrotate/agent-app` | 로그 보관 정책 |
| `config/systemd/agent-app.service` | systemd 서비스 유닛 |
| `assets/agent-app/` | agent 바이너리 배포 자산 |
