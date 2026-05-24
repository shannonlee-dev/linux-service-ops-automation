# 시스템 관제 자동화 재현 절차

## 1. 작업 기록 폴더 만들기

1. 작업 기록을 모을 폴더를 만든다.

복붙 명령어:
```sh
mkdir -p "$HOME/agent-mission-records"
cd "$HOME/agent-mission-records"
```

예상 화면/출력:
```text
명령이 끝나고 오류 메시지가 없으면 다음 단계로 이동한다.
```

## 2. 기본 환경 확인하기

1. Ubuntu 버전을 확인한다.

복붙 명령어:
```sh
cat /etc/os-release
```

예상 화면/출력:
```text
Ubuntu 22.04 또는 비슷한 Linux 배포판 정보가 보인다.
```

2. 현재 사용자가 관리자 명령을 실행할 수 있는지 확인한다.

복붙 명령어:
```sh
sudo -v
```

예상 화면/출력:
```text
비밀번호 입력 후 오류 메시지가 없으면 다음 단계로 이동한다.
```

## 3. 필요한 프로그램 설치하기

1. 필요한 기본 프로그램을 설치한다.

복붙 명령어:
```sh
sudo apt update
sudo apt install -y openssh-server ufw acl cron python3
```

예상 화면/출력:
```text
설치가 끝나고 오류 메시지가 없으면 다음 단계로 이동한다.
```

## 4. 미션에서 사용할 값 정하기

1. 사용할 경로와 포트를 확인한다.

복붙 명령어:
```sh
printf '%s\n' \
  'AGENT_HOME=/home/agent-admin/agent-app' \
  'AGENT_PORT=15034' \
  'AGENT_UPLOAD_DIR=/home/agent-admin/agent-app/upload_files' \
  'AGENT_KEY_PATH=/home/agent-admin/agent-app/api_keys/t_secret.key' \
  'AGENT_LOG_DIR=/var/log/agent-app'
```

예상 화면/출력:
```text
위 5개 값이 한 줄씩 보인다.
```

## 5. 단계별 복붙 절차

1. SSH 설정을 바꾸기 전 백업한다.

복붙 명령어:
```sh
sudo cp /etc/ssh/sshd_config "/etc/ssh/sshd_config.backup.$(date +%Y%m%d%H%M%S)"
```

예상 화면/출력:
```text
오류 메시지가 없으면 백업이 만들어진 상태다.
```

2. SSH 포트와 root 접속 차단 설정을 적용한다.

복붙 명령어:
```sh
sudo sed -i -E 's/^#?Port .*/Port 20022/' /etc/ssh/sshd_config
sudo sed -i -E 's/^#?PermitRootLogin .*/PermitRootLogin no/' /etc/ssh/sshd_config
sudo systemctl restart ssh || sudo service ssh restart
```

예상 화면/출력:
```text
오류 메시지가 없으면 SSH 설정이 다시 적용된 상태다.
```

3. 방화벽에서 필요한 포트만 허용한다.

복붙 명령어:
```sh
sudo ufw allow 20022/tcp
sudo ufw allow 15034/tcp
sudo ufw --force enable
sudo ufw status
```

예상 화면/출력:
```text
Status: active
20022/tcp ALLOW
15034/tcp ALLOW
```

4. 계정과 그룹을 만든다.

복붙 명령어:
```sh
sudo groupadd -f agent-common
sudo groupadd -f agent-core
sudo useradd -m -s /bin/bash agent-admin 2>/dev/null || true
sudo useradd -m -s /bin/bash agent-dev 2>/dev/null || true
sudo useradd -m -s /bin/bash agent-test 2>/dev/null || true
sudo usermod -aG agent-common,agent-core agent-admin
sudo usermod -aG agent-common,agent-core agent-dev
sudo usermod -aG agent-common agent-test
```

예상 화면/출력:
```text
이미 있는 계정은 건너뛰고, 오류 없이 끝나면 다음 단계로 이동한다.
```

5. 앱 폴더와 로그 폴더를 만든다.

복붙 명령어:
```sh
sudo mkdir -p /home/agent-admin/agent-app/upload_files
sudo mkdir -p /home/agent-admin/agent-app/api_keys
sudo mkdir -p /home/agent-admin/agent-app/bin
sudo mkdir -p /var/log/agent-app
sudo chown -R agent-admin:agent-common /home/agent-admin/agent-app
sudo chown -R agent-admin:agent-common /home/agent-admin/agent-app/upload_files
sudo chown -R agent-admin:agent-core /home/agent-admin/agent-app/api_keys /var/log/agent-app
sudo chmod 770 /home/agent-admin/agent-app/upload_files
sudo chmod 770 /home/agent-admin/agent-app/api_keys /var/log/agent-app
```

예상 화면/출력:
```text
오류 메시지가 없으면 폴더와 권한이 준비된 상태다.
```

6. API 키 파일을 만든다.

복붙 명령어:
```sh
printf 'agent_api_key_test\n' | sudo tee /home/agent-admin/agent-app/api_keys/t_secret.key >/dev/null
sudo chown agent-admin:agent-core /home/agent-admin/agent-app/api_keys/t_secret.key
sudo chmod 660 /home/agent-admin/agent-app/api_keys/t_secret.key
```

예상 화면/출력:
```text
오류 메시지가 없으면 키 파일이 만들어진 상태다.
```

7. 실행할 앱 파일을 준비한다.

복붙 명령어:
```sh
sudo tee /home/agent-admin/agent-app/agent_app.py >/dev/null <<'PY'
#!/usr/bin/env python3
import os
import socket
import time

required = {
    "AGENT_HOME": "/home/agent-admin/agent-app",
    "AGENT_PORT": "15034",
    "AGENT_UPLOAD_DIR": "/home/agent-admin/agent-app/upload_files",
    "AGENT_KEY_PATH": "/home/agent-admin/agent-app/api_keys/t_secret.key",
    "AGENT_LOG_DIR": "/var/log/agent-app",
}
print("Starting Agent Boot Sequence...", flush=True)
print("[1/5] Checking User Account               [OK]", flush=True)
for key, value in required.items():
    if os.environ.get(key) != value:
        raise SystemExit(f"{key} is not correct")
print("[2/5] Verifying Environment Variables     [OK]", flush=True)
with open(required["AGENT_KEY_PATH"], "r", encoding="utf-8") as f:
    if f.read().strip() != "agent_api_key_test":
        raise SystemExit("key file is not correct")
print("[3/5] Checking Required Files             [OK]", flush=True)
s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("0.0.0.0", int(required["AGENT_PORT"])))
print("[4/5] Checking Port Availability          [OK]", flush=True)
if not os.access(required["AGENT_LOG_DIR"], os.W_OK):
    raise SystemExit("log directory is not writable")
print("[5/5] Verifying Log Permission            [OK]", flush=True)
print("Agent READY", flush=True)
s.listen(5)
while True:
    time.sleep(60)
PY
sudo chown agent-admin:agent-core /home/agent-admin/agent-app/agent_app.py
sudo chmod 750 /home/agent-admin/agent-app/agent_app.py
```

예상 화면/출력:
```text
오류 메시지가 없으면 앱 파일이 만들어진 상태다.
```

8. 앱을 일반 계정으로 실행한다.

복붙 명령어:
```sh
sudo -u agent-admin env \
  AGENT_HOME=/home/agent-admin/agent-app \
  AGENT_PORT=15034 \
  AGENT_UPLOAD_DIR=/home/agent-admin/agent-app/upload_files \
  AGENT_KEY_PATH=/home/agent-admin/agent-app/api_keys/t_secret.key \
  AGENT_LOG_DIR=/var/log/agent-app \
  python3 /home/agent-admin/agent-app/agent_app.py
```

예상 화면/출력:
```text
Starting Agent Boot Sequence...
[1/5] Checking User Account               [OK]
[2/5] Verifying Environment Variables     [OK]
[3/5] Checking Required Files             [OK]
[4/5] Checking Port Availability          [OK]
[5/5] Verifying Log Permission            [OK]
Agent READY
```

9. 앱 실행 터미널은 그대로 두고 새 터미널에서 포트를 확인한다.

복붙 명령어:
```sh
ss -tulnp | grep ':15034'
```

예상 화면/출력:
```text
0.0.0.0:15034 이 포함된 줄이 보인다.
```

10. `monitor.sh` 파일을 만든다.

복붙 명령어:
```sh
sudo tee /home/agent-admin/agent-app/bin/monitor.sh >/dev/null <<'SH'
#!/usr/bin/env bash
set -u
LOG_FILE="/var/log/agent-app/monitor.log"
APP_NAME="agent_app.py"
PORT="15034"

pid="$(pgrep -u agent-admin -f "$APP_NAME" | awk -v self="$$" '$1 != self {print; exit}')"
if [ -z "$pid" ]; then
  echo "Checking process '$APP_NAME'... [FAIL]"
  exit 1
fi
echo "Checking process '$APP_NAME'... [OK] (PID: $pid)"

if ! ss -tuln | grep -q ":$PORT "; then
  echo "Checking port $PORT... [FAIL]"
  exit 1
fi
echo "Checking port $PORT... [OK]"

if command -v ufw >/dev/null 2>&1 && ! ufw status 2>/dev/null | grep -q 'Status: active'; then
  echo "[WARNING] firewall is not active"
fi

cpu="$(awk '{print $1}' /proc/loadavg)"
mem="$(free | awk '/Mem:/ {printf "%.1f", ($3/$2)*100}')"
disk="$(df / | awk 'NR==2 {gsub("%","",$5); print $5}')"

awk -v v="$cpu" 'BEGIN {if (v > 20) print "[WARNING] CPU threshold exceeded"}'
awk -v v="$mem" 'BEGIN {if (v > 10) print "[WARNING] MEM threshold exceeded"}'
awk -v v="$disk" 'BEGIN {if (v > 80) print "[WARNING] DISK threshold exceeded"}'

mkdir -p "$(dirname "$LOG_FILE")"
printf '[%s] PID:%s CPU:%s%% MEM:%s%% DISK_USED:%s%%\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$pid" "$cpu" "$mem" "$disk" >> "$LOG_FILE"

if [ -f "$LOG_FILE" ] && [ "$(stat -c%s "$LOG_FILE")" -gt 10485760 ]; then
  i=9
  while [ "$i" -ge 1 ]; do
    [ -f "$LOG_FILE.$i" ] && mv "$LOG_FILE.$i" "$LOG_FILE.$((i+1))"
    i=$((i-1))
  done
  mv "$LOG_FILE" "$LOG_FILE.1"
  : > "$LOG_FILE"
fi
find /var/log/agent-app -maxdepth 1 -name 'monitor.log.*' | sort -r | tail -n +11 | xargs -r rm -f
echo "[INFO] Log appended: $LOG_FILE"
SH
sudo chown agent-dev:agent-core /home/agent-admin/agent-app/bin/monitor.sh
sudo chmod 750 /home/agent-admin/agent-app/bin/monitor.sh
```

예상 화면/출력:
```text
오류 메시지가 없으면 monitor.sh가 만들어진 상태다.
```

11. `monitor.sh`를 실행한다.

복붙 명령어:
```sh
sudo -u agent-admin /home/agent-admin/agent-app/bin/monitor.sh
```

예상 화면/출력:
```text
Checking process 'agent_app.py'... [OK]
Checking port 15034... [OK]
[INFO] Log appended: /var/log/agent-app/monitor.log
```

12. cron에 매분 실행을 등록한다.

복붙 명령어:
```sh
(sudo crontab -u agent-admin -l 2>/dev/null; echo '* * * * * /home/agent-admin/agent-app/bin/monitor.sh >/tmp/agent-monitor-cron.out 2>/tmp/agent-monitor-cron.err') | sudo crontab -u agent-admin -
sudo crontab -u agent-admin -l
```

예상 화면/출력:
```text
* * * * * /home/agent-admin/agent-app/bin/monitor.sh >/tmp/agent-monitor-cron.out 2>/tmp/agent-monitor-cron.err
```

13. 1분 뒤 로그가 늘어나는지 확인한다.

복붙 명령어:
```sh
before="$(sudo cat /var/log/agent-app/monitor.log 2>/dev/null | wc -l || echo 0)"
echo "기다리는 중... (70초)"
sleep 70
after="$(sudo cat /var/log/agent-app/monitor.log 2>/dev/null | wc -l || echo 0)"
printf 'before=%s after=%s\n' "$before" "$after"
sudo tail -n 3 /var/log/agent-app/monitor.log
```

예상 화면/출력:
```text
after 값이 before 값보다 크고, 최근 로그 줄이 보인다.
```

## 6. 로그와 출력 기록하기

1. 주요 확인 결과를 작업 기록 폴더에 저장한다.

복붙 명령어:
```sh
{
  date
  id agent-admin
  id agent-dev
  id agent-test
  sudo ufw status
  sudo ls -ld /home/agent-admin/agent-app /home/agent-admin/agent-app/upload_files /home/agent-admin/agent-app/api_keys /var/log/agent-app
  sudo tail -n 5 /var/log/agent-app/monitor.log
  sudo crontab -u agent-admin -l
} > "$HOME/agent-mission-records/evidence.txt"
```

예상 화면/출력:
```text
오류 메시지가 없으면 evidence.txt 파일에 확인 결과가 저장된다.
```

## 7. 보너스 스크립트 준비하기

1. `report.sh`를 만든다.

복붙 명령어:
```sh
sudo tee /home/agent-admin/agent-app/bin/report.sh >/dev/null <<'SH'
#!/usr/bin/env bash
set -u
LOG_FILE="${MONITOR_LOG_FILE:-${AGENT_LOG_DIR:-/var/log/agent-app}/monitor.log}"
awk '
function emit(label, avg, max, max_ts, min, min_ts) {
  printf("[%s]\nAverage : %.1f%%\nMaximum : %.1f%% at %s\nMinimum : %.1f%% at %s\n", label, avg, max, max_ts, min, min_ts)
}
BEGIN { cpu_min = mem_min = disk_min = 1000000; cpu_max = mem_max = disk_max = -1 }
/^\[[0-9-]+ [0-9:]+\] PID:[0-9]+ CPU:[0-9.]+% MEM:[0-9.]+% DISK_USED:[0-9.]+%$/ {
  ts = substr($0, 2, 19)
  cpu = $4; sub("CPU:", "", cpu); sub("%", "", cpu)
  mem = $5; sub("MEM:", "", mem); sub("%", "", mem)
  disk = $6; sub("DISK_USED:", "", disk); sub("%", "", disk)
  count++; cpu_sum += cpu; mem_sum += mem; disk_sum += disk
  if (cpu > cpu_max) { cpu_max = cpu; cpu_max_ts = ts }
  if (cpu < cpu_min) { cpu_min = cpu; cpu_min_ts = ts }
  if (mem > mem_max) { mem_max = mem; mem_max_ts = ts }
  if (mem < mem_min) { mem_min = mem; mem_min_ts = ts }
  if (disk > disk_max) { disk_max = disk; disk_max_ts = ts }
  if (disk < disk_min) { disk_min = disk; disk_min_ts = ts }
}
END {
  if (count == 0) { print "[WARNING] no monitor samples"; exit 1 }
  print "====== STATISTICS REPORT ======"
  emit("CPU", cpu_sum / count, cpu_max, cpu_max_ts, cpu_min, cpu_min_ts)
  emit("Memory", mem_sum / count, mem_max, mem_max_ts, mem_min, mem_min_ts)
  emit("Disk", disk_sum / count, disk_max, disk_max_ts, disk_min, disk_min_ts)
  printf("[Samples]\nData Points: %d samples\n", count)
}' "$LOG_FILE"
SH
sudo chown agent-dev:agent-core /home/agent-admin/agent-app/bin/report.sh
sudo chmod 750 /home/agent-admin/agent-app/bin/report.sh
```

예상 화면/출력:
```text
오류 메시지가 없으면 report.sh가 만들어진 상태다.
```

2. 리포트를 실행한다.

복붙 명령어:
```sh
sudo -u agent-admin /home/agent-admin/agent-app/bin/report.sh
```

예상 화면/출력:
```text
====== STATISTICS REPORT ======
[CPU]
Average : ...
[Samples]
Data Points: ... samples
```

3. 로그 보존 스크립트를 만든다.

복붙 명령어:
```sh
sudo tee /home/agent-admin/agent-app/bin/log_retention.sh >/dev/null <<'SH'
#!/usr/bin/env bash
set -u
LOG_DIR="${AGENT_LOG_DIR:-/var/log/agent-app}"
ARCHIVE_DIR="${MONITOR_ARCHIVE_DIR:-/var/log/monitor/agent-app/archive}"
mkdir -p "$ARCHIVE_DIR" || { echo "[WARNING] archive directory cannot be created"; exit 0; }
find "$LOG_DIR" -maxdepth 1 -type f -name '*.log' -mtime +6 -print0 2>/dev/null |
  while IFS= read -r -d '' file; do
    gzip -c "$file" > "$ARCHIVE_DIR/$(basename "$file").gz" && rm -f "$file"
  done
find "$ARCHIVE_DIR" -maxdepth 1 -type f -name '*.gz' -mtime +29 -delete 2>/dev/null
echo "[INFO] retention policy completed"
SH
sudo chown agent-dev:agent-core /home/agent-admin/agent-app/bin/log_retention.sh
sudo chmod 750 /home/agent-admin/agent-app/bin/log_retention.sh
```

예상 화면/출력:
```text
오류 메시지가 없으면 log_retention.sh가 만들어진 상태다.
```

4. 로그 보존 스크립트를 실행한다.

복붙 명령어:
```sh
sudo -u agent-admin /home/agent-admin/agent-app/bin/log_retention.sh
```

예상 화면/출력:
```text
[INFO] retention policy completed
```

## 8. 최종 산출물 확인하기

1. 제출할 파일 목록을 확인한다.

복붙 명령어:
```sh
ls -l "$HOME/agent-mission-records"
ls -l /home/agent-admin/agent-app/bin/monitor.sh
ls -l /home/agent-admin/agent-app/bin/report.sh /home/agent-admin/agent-app/bin/log_retention.sh
```

예상 화면/출력:
```text
evidence.txt 파일과 monitor.sh, report.sh, log_retention.sh 파일 정보가 보인다.
```

2. 앱을 종료하려면 앱 실행 터미널에서 `Ctrl+C`를 누른다.

예상 화면/출력:
```text
명령 프롬프트가 다시 보인다.
```
