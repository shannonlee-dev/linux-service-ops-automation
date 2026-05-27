# 2026 Main 1-1

이 디렉토리는 2026 Main 1-1 제출용 산출물과 시스템 적용 스크립트를 함께 보관합니다.

## 매우 중요한 주의

`apply_system.sh`는 반드시 `sudo` 권한으로 실행되는 시스템 변경 스크립트입니다. 이 스크립트는 단순 테스트 스크립트가 아니며, 실행하면 실제 서버의 SSH 설정, 방화벽, 사용자/그룹, 파일 권한, cron, `/etc` 설정, `/var/log` 경로를 변경합니다.

리눅스 사용자/권한/SSH/방화벽/cron 동작을 정확히 이해하지 못한다면 실행하지 마십시오. 이해가 부족한 상태에서 실행하면 SSH 접속이 막히거나, 방화벽 정책이 바뀌거나, 시스템 서비스 상태가 달라질 수 있습니다. 실행 전 반드시 내용을 읽고, 현재 서버에 적용해도 되는지 확인해야 합니다.

## Directory Structure

```text
2026-main-1-1/
├── 98_PROCEDURE_MANUAL.md
├── README.md
├── agent-app.zip
├── agent-app/
│   ├── agent-app-linux-arm64
│   └── agent-app-linux-x86
├── apply_system.sh
├── runtime/
│   ├── archive/
│   └── work.log
└── submission/
    ├── docs/
    │   └── requirements_execution_report.md
    └── home/
        └── agent-admin/
            └── agent-app/
                └── bin/
                    ├── log_retention.sh
                    ├── monitor.sh
                    └── report.sh
```

## Files

| Path | Description |
| --- | --- |
| `apply_system.sh` | 시스템 적용 스크립트. `sudo`로만 정상 실행됩니다. |
| `agent-app.zip` | 제공된 agent 앱 바이너리 압축 파일입니다. |
| `agent-app/` | `agent-app.zip`을 풀어 둔 바이너리 확인용 디렉토리입니다. |
| `submission/home/agent-admin/agent-app/bin/` | 실제 배치 대상이 되는 제출 스크립트 위치입니다. |
| `submission/docs/requirements_execution_report.md` | 요구사항 실행 보고서입니다. |
| `runtime/work.log` | `apply_system.sh` 실행 로그입니다. |
| `runtime/archive/` | 방화벽/crontab 등 적용 전 백업 파일이 저장됩니다. |
| `98_PROCEDURE_MANUAL.md` | 작업 절차와 운영 기준 문서입니다. |

## Apply

`apply_system.sh`는 현재 디렉토리 기준으로 파일을 찾습니다. 반드시 `2026-main-1-1` 디렉토리에서 실행하십시오.

```bash
cd /home/shh921shh4393/.dev/codyssey-mission/2026-main-1-1
sudo ./apply_system.sh
```

스크립트는 다음 항목을 적용합니다.

- 필수 패키지 설치: `openssh-server`, `ufw`, `acl`, `cron`, `unzip`, `python3`, `psmisc`, `procps`
- SSH 포트 `20022` 설정 및 root SSH 접속 차단
- 방화벽에서 `20022/tcp`, `15034/tcp` 허용
- `agent-admin`, `agent-dev`, `agent-test` 사용자와 관련 그룹 구성
- `/home/agent-admin/agent-app` 및 `/var/log/agent-app` 권한 구성
- `/home/agent-admin/agent-app/api_keys/secret.key` 생성
- agent 앱과 `monitor.sh`, `report.sh` 배치
- monitor cron 등록
- 사용자가 직접 agent 앱을 실행할 수 있도록 기존 `15034/tcp` 점유 프로세스 종료

## Check

agent-admin 로그인 쉘로 들어가 직접 실행:

```bash
sudo -iu agent-admin
/home/agent-admin/agent-app/bin/agent-app
```

실행 로그 확인:

```bash
sudo tail -n 120 runtime/work.log
```

agent 앱 실행 여부:

```bash
pgrep -a -u agent-admin -f 'agent-app-linux|agent-app'
```

15034 포트 확인:

```bash
ss -ltn | grep ':15034' && echo open || echo closed
```

앱 부팅 로그 확인:

```bash
sudo tail -n 120 /var/log/agent-app/agent-app.boot.log
```

## Notes

- `sudo ./apply_system.sh`는 root 권한으로 시스템을 변경합니다.
- agent 앱은 root로 직접 실행하면 실패합니다.
- `apply_system.sh`는 agent 앱을 자동 실행하지 않습니다.
- agent 앱은 `agent-admin` 계정과 필요한 환경변수로 직접 실행해야 합니다.
- 제출/적용 기준 경로는 `pwd -P`, 즉 현재 실행 디렉토리입니다.
