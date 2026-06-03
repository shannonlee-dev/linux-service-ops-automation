# Linux Service Ops Automation

Linux 서버에 agent 애플리케이션을 배치하고, 운영에 필요한 사용자, 권한, SSH, 방화벽, cron, 로그 경로를 재현 가능한 스크립트로 구성한 프로젝트입니다.

목표는 단순히 명령을 실행하는 것이 아니라, 시스템 변경이 어떤 순서로 적용되고 어떤 증거로 확인되는지 남기는 것입니다. 운영 환경에서 중요한 접근 통제, 서비스 실행 권한, 로그 보존, 사전 백업을 하나의 절차로 묶었습니다.

## What It Covers

- SSH 포트 변경과 root 접속 차단
- `agent-admin`, `agent-dev`, `agent-test` 사용자와 그룹 구성
- 서비스 디렉터리와 로그 디렉터리 권한 설정
- agent 앱 배치와 실행 보조 스크립트 설치
- cron 기반 모니터링 등록
- 방화벽 규칙 적용
- 적용 전 설정 백업과 실행 로그 기록

## Why It Matters

운영 자동화는 결과만큼 과정이 중요합니다. 이 프로젝트는 시스템 상태를 바꾸는 작업을 스크립트화하면서도, 변경 전 백업과 실행 로그를 남겨 사후 확인이 가능하도록 구성했습니다.

서버 접근, 권한 분리, 로그 보존 같은 항목은 장애나 감사 상황에서 바로 확인되어야 하므로, 실행 흐름을 문서와 코드 양쪽에 남기는 데 초점을 맞췄습니다.

## Files

| Path | Description |
| --- | --- |
| `apply_system.sh` | 시스템 적용 스크립트. `sudo` 권한으로 실행됩니다. |
| `98_PROCEDURE_MANUAL.md` | 적용 절차와 운영 기준 문서 |
| `agent-app.zip` | 제공된 agent 앱 바이너리 압축 파일 |
| `agent-app/` | 바이너리 확인용 디렉터리 |
| `submission/home/agent-admin/agent-app/bin/` | 배치 대상 스크립트 |
| `submission/docs/requirements_execution_report.md` | 요구사항 실행 보고서 |
| `runtime/work.log` | 적용 실행 로그 |
| `runtime/archive/` | 적용 전 백업 파일 |

## Run

> Warning: `apply_system.sh` changes real system settings including SSH, firewall, users, groups, cron, file permissions, and log paths. Read the script and procedure manual before running it.

```bash
sudo ./apply_system.sh
```

## Verification

```bash
sudo tail -n 120 runtime/work.log
pgrep -a -u agent-admin -f 'agent-app-linux|agent-app'
ss -ltn | grep ':15034' && echo open || echo closed
sudo tail -n 120 /var/log/agent-app/agent-app.boot.log
```

To run the agent manually:

```bash
sudo -iu agent-admin
/home/agent-admin/agent-app/bin/agent-app
```

## Design Notes

- The script separates service ownership from administrative execution.
- Runtime logs and backups are kept so that each system change can be reviewed after execution.
- The agent app is not started as root; it is executed under the intended service account.
- The script assumes the current repository root as its working directory.
