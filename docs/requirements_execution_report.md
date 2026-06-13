# 요구사항 수행 내역서

## 1. 수행 환경

| 항목 | 값 |
|---|---|
| OS | Ubuntu 24.04 LTS, Ubuntu 22.04 LTS 동등 Linux 환경 |
| SSH 포트 | `20022/tcp` |
| 앱 포트 | `15034/tcp` |
| 방화벽 | UFW |
| 앱 실행 계정 | `agent-admin` |
| monitor.sh 소유자/그룹/권한 | `agent-dev:agent-core`, `750` |

## 2. 설정/명령어 기록

### SSH 포트와 root 접속 차단

- `/etc/ssh/sshd_config`를 백업한 뒤 `Port 20022`, `PermitRootLogin no`를 적용했다.
- `sshd -t`로 문법을 확인하고 sshd를 재시작 또는 직접 기동했다.
- 확인 명령:

```sh
sudo sshd -T | awk '/^port / || /^permitrootlogin /'
sudo ss -tulnp | awk '$5 ~ /:20022$/ && /sshd/ {print}'
```

### 방화벽 규칙

- UFW를 선택했다.
- 기존 UFW 상태를 백업한 뒤 inbound 기본 정책을 deny로 두고 `20022/tcp`, `15034/tcp`만 허용했다.
- 확인 명령:

```sh
sudo ufw status verbose
```

### 계정/그룹/ACL

- 계정: `agent-admin`, `agent-dev`, `agent-test`
- 그룹: `agent-common`, `agent-core`
- 멤버십:
  - `agent-common`: `agent-admin`, `agent-dev`, `agent-test`
  - `agent-core`: `agent-admin`, `agent-dev`
- 확인 명령:

```sh
id agent-admin
id agent-dev
id agent-test
getfacl -p /home/agent-admin/agent-app/upload_files /home/agent-admin/agent-app/api_keys /var/log/agent-app
```

### 디렉터리와 권한

| 경로 | 소유자:그룹 | 권한 정책 |
|---|---|---|
| `/home/agent-admin/agent-app` | `agent-admin:agent-common` | 앱 홈 |
| `/home/agent-admin/agent-app/upload_files` | `agent-admin:agent-common` | group rwx, default ACL |
| `/home/agent-admin/agent-app/api_keys` | `agent-admin:agent-core` | group rwx, other none |
| `/home/agent-admin/agent-app/bin` | `agent-admin:agent-core` | 실행 스크립트 배치 |
| `/var/log/agent-app` | `agent-admin:agent-core` | group rwx, other none |

### 환경 변수

```sh
AGENT_HOME=/home/agent-admin/agent-app
AGENT_PORT=15034
AGENT_UPLOAD_DIR=/home/agent-admin/agent-app/upload_files
AGENT_KEY_PATH=/home/agent-admin/agent-app/api_keys/t_secret.key
AGENT_LOG_DIR=/var/log/agent-app
```

### 키 파일

- 경로: `/home/agent-admin/agent-app/api_keys/t_secret.key`
- 내용: `<MASKED_API_KEY>`
- 검증 기준: 1줄, 18자, `agent-admin:agent-core`, mode `660`

### 앱 실행

- 제공 앱 다운로드 오류 상황에 따라 대체 Python 앱을 `/home/agent-admin/agent-app/agent_app.py`로 작성했다.
- root가 아닌 `agent-admin`으로 실행했다.
- Boot Sequence 5단계 `[OK]`와 `Agent READY`를 확인했다.
- `0.0.0.0:15034` LISTEN 상태를 확인했다.

### monitor.sh

- 위치: `/home/agent-admin/agent-app/bin/monitor.sh`
- 소유자/그룹/권한: `agent-dev:agent-core`, `750`
- 기능:
  - `agent_app.py` 프로세스 확인, 실패 시 `exit 1`
  - TCP `15034` LISTEN 확인, 실패 시 `exit 1`
  - UFW/firewalld 활성 상태 점검, 비활성 시 `[WARNING]`만 출력
  - CPU, MEM, 루트 파티션 DISK_USED 수집
  - CPU `>20%`, MEM `>10%`, DISK_USED `>80%` 경고 출력
  - `/var/log/agent-app/monitor.log` 누적 기록
  - `monitor.log` 최대 `10MB/10개` 회전 보존

### cron 등록

- `agent-admin` crontab에 매분 실행을 등록했다.

```sh
* * * * * /home/agent-admin/agent-app/bin/monitor.sh >/tmp/agent-monitor-cron.out 2>/tmp/agent-monitor-cron.err
```

### 보너스 산출물

- `report.sh`는 `monitor.log`를 분석해 CPU, Memory, Disk의 평균/최대/최소와 샘플 수를 출력한다.
- `report.sh`는 선택적으로 시작/종료 시간을 인자로 받아 해당 구간의 로그만 분석한다.
- `log_retention.sh`는 7일 이상 경과한 `/var/log/agent-app/*.log` 파일을 gzip으로 압축해 `/var/log/monitor/agent-app/archive/`로 이동하고, 30일 이상 경과한 아카이브를 삭제한다.
- 두 스크립트 모두 Bash로 작성했고, 디렉터리 미존재, 권한 부족, 대상 파일 없음 상황에서 오류를 숨기지 않고 안전하게 종료하거나 경고를 출력하도록 작성했다.

## 3. 필수 증거 자료 체크리스트

| 증거 항목 | 확인 방법 | 상태 |
|---|---|---|
| SSH 포트 변경(20022) 및 Root 원격 접속 차단 설정 확인 내역 | `sshd -T`, `ss -tulnp` | 최신 검증 로그 참조 |
| 방화벽(UFW 또는 firewalld) 활성화 및 20022/tcp, 15034/tcp만 허용 내역 | `ufw status verbose` | 최신 검증 로그 참조 |
| 계정/그룹(agent-admin/dev/test, agent-common/core) 생성 확인 내역 | `id` | 최신 검증 로그 참조 |
| 디렉토리 구조 및 권한(ACL 포함) 확인 내역 | `ls -ld`, `getfacl` | 최신 검증 로그 참조 |
| 앱 Boot Sequence 5단계 `[OK]` 및 `Agent READY` 확인 내역 | 앱 boot log | 최신 검증 로그 참조 |
| monitor.sh 실행 결과(프로세스/포트/리소스/경고) 내역 | `monitor.sh` 실행 | 최신 검증 로그 참조 |
| `/var/log/agent-app/monitor.log` 누적 기록 확인(최근 라인) 내역 | `tail -n 5` | 최신 검증 로그 참조 |
| crontab 매분 실행 등록 및 자동 실행 확인(1분 후 로그 증가) 내역 | `crontab -u`, 라인 수 비교 | 최신 검증 로그 참조 |
| 보너스 report.sh 통계 출력 확인 | 임시 `monitor.log` 샘플 기반 실행 | 최신 검증 로그 참조 |
| 보너스 로그 보존 정책 확인 | 임시 로그/아카이브 디렉터리 기반 실행 | 최신 검증 로그 참조 |

## 4. 제출 산출물

| 산출물 | 경로 |
|---|---|
| 요구사항 수행 내역서 | `submission/docs/requirements_execution_report.md` |
| 자동화 스크립트 소스코드 | `submission/home/agent-admin/agent-app/bin/monitor.sh` |
| 보너스 리포트 스크립트 | `submission/home/agent-admin/agent-app/bin/report.sh` |
| 보너스 로그 보존 스크립트 | `submission/home/agent-admin/agent-app/bin/log_retention.sh` |
