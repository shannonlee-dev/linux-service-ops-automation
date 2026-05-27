# 98_PROCEDURE_MANUAL

이 문서는 리눅스가 처음인 사람도 새 Ubuntu 환경에서 그대로 따라 하며 미션을 끝낼 수 있도록 만든 단계별 복붙 절차다.

## 1. 작업 기록 폴더 만들기

1. 작업 기록을 모을 폴더를 만든다.

복붙 명령어:
~~~sh
mkdir -p "$HOME/mission1-work/logs" "$HOME/mission1-work/submission"
printf '%s\n' "작업 폴더: $HOME/mission1-work"
~~~

예상 화면/출력:
~~~text
작업 폴더: /home/<현재사용자이름>/mission1-work
~~~

## 2. 기본 환경 확인하기

1. Ubuntu 버전과 현재 사용자를 확인한다.

복붙 명령어:
~~~sh
printf 'USER=%s\n' "$(id -un)"
printf 'UID=%s\n' "$(id -u)"
cat /etc/os-release | grep -E '^(NAME|VERSION)='
~~~

예상 화면/출력:
~~~text
USER=<현재사용자이름>
UID=<숫자>
NAME="Ubuntu"
VERSION="22.04..."
~~~

2. sudo 사용 가능 여부를 확인한다.

복붙 명령어:
~~~sh
sudo -v
printf '%s\n' "sudo 확인 완료"
~~~

예상 화면/출력:
~~~text
sudo 확인 완료
~~~

## 3. 필요한 프로그램 설치하기

1. 필요한 프로그램을 설치한다.

복붙 명령어:
~~~sh
sudo apt update
sudo apt install -y openssh-server ufw acl cron unzip python3 psmisc procps
~~~

예상 화면/출력:
~~~text
패키지 목록을 읽는 중입니다...
openssh-server, ufw, acl, cron, unzip, python3 관련 설치 또는 최신 상태 표시
~~~

2. 서비스가 켜져 있는지 확인한다.

복붙 명령어:
~~~sh
systemctl is-enabled ssh || true
systemctl is-active ssh || true
systemctl is-enabled cron || true
systemctl is-active cron || true
~~~

예상 화면/출력:
~~~text
enabled 또는 disabled
active 또는 inactive
~~~

## 4. 미션에서 사용할 값 정하기

1. 사용할 계정, 포트, 폴더 값을 기록한다.

복붙 명령어:
~~~sh
printf '%s\n' 'AGENT_HOME=/home/agent-admin/agent-app'
printf '%s\n' 'AGENT_PORT=15034'
printf '%s\n' 'AGENT_UPLOAD_DIR=/home/agent-admin/agent-app/upload_files'
printf '%s\n' 'AGENT_KEY_PATH=/home/agent-admin/agent-app/api_keys/t_secret.key'
printf '%s\n' 'AGENT_LOG_DIR=/var/log/agent-app'
printf '%s\n' 'SSH_PORT=20022'
~~~

예상 화면/출력:
~~~text
AGENT_HOME=/home/agent-admin/agent-app
AGENT_PORT=15034
AGENT_UPLOAD_DIR=/home/agent-admin/agent-app/upload_files
AGENT_KEY_PATH=/home/agent-admin/agent-app/api_keys/t_secret.key
AGENT_LOG_DIR=/var/log/agent-app
SSH_PORT=20022
~~~

## 5. 단계별 복붙 절차

1. SSH 포트 변경은 현재 접속이 끊길 수 있으므로 콘솔 접속이나 대체 접속 방법을 먼저 확보한 뒤 실행한다.

복붙 명령어:
~~~sh
sudo cp /etc/ssh/sshd_config "/etc/ssh/sshd_config.backup.$(date +%Y%m%d%H%M%S)"
sudo sed -i -E 's/^#?Port .*/Port 20022/' /etc/ssh/sshd_config
sudo sed -i -E 's/^#?PermitRootLogin .*/PermitRootLogin no/' /etc/ssh/sshd_config
sudo grep -E '^(Port|PermitRootLogin)' /etc/ssh/sshd_config
~~~

예상 화면/출력:
~~~text
Port 20022
PermitRootLogin no
~~~

2. SSH 설정을 검사하고 서비스를 다시 읽는다.

복붙 명령어:
~~~sh
sudo sshd -t
sudo mkdir -p /etc/systemd/system/ssh.socket.d
printf '%s\n' '[Socket]' 'ListenStream=' 'ListenStream=20022' | sudo tee /etc/systemd/system/ssh.socket.d/override.conf >/dev/null
sudo systemctl daemon-reload
sudo systemctl restart ssh.socket
sudo systemctl restart ssh
sudo ss -tulnp | grep ':20022' || true
~~~

예상 화면/출력:
~~~text
LISTEN ... :20022 ... sshd
~~~

3. 방화벽은 필요한 포트만 허용한다.

복붙 명령어:
~~~sh
sudo ufw --force reset
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 20022/tcp
sudo ufw allow 15034/tcp
sudo ufw --force enable
sudo ufw status verbose
~~~

예상 화면/출력:
~~~text
Status: active
20022/tcp                  ALLOW IN
15034/tcp                  ALLOW IN
~~~

4. 계정과 그룹을 만든다.

복붙 명령어:
~~~sh
sudo groupadd -f agent-common
sudo groupadd -f agent-core
sudo id agent-admin >/dev/null 2>&1 || sudo useradd -m -s /bin/bash agent-admin
sudo id agent-dev >/dev/null 2>&1 || sudo useradd -m -s /bin/bash agent-dev
sudo id agent-test >/dev/null 2>&1 || sudo useradd -m -s /bin/bash agent-test
sudo usermod -aG agent-common,agent-core agent-admin
sudo usermod -aG agent-common,agent-core agent-dev
sudo usermod -aG agent-common agent-test
id agent-admin
id agent-dev
id agent-test
~~~

예상 화면/출력:
~~~text
uid=... agent-admin ... groups=... agent-common,agent-core
uid=... agent-dev ... groups=... agent-common,agent-core
uid=... agent-test ... groups=... agent-common
~~~

5. 앱 폴더, 업로드 폴더, 키 폴더, 로그 폴더를 만든다.

복붙 명령어:
~~~sh
sudo mkdir -p /home/agent-admin/agent-app/upload_files
sudo mkdir -p /home/agent-admin/agent-app/api_keys
sudo mkdir -p /home/agent-admin/agent-app/bin
sudo mkdir -p /var/log/agent-app
sudo chown -R agent-admin:agent-core /home/agent-admin/agent-app
sudo chown -R agent-admin:agent-core /var/log/agent-app
sudo chgrp agent-common /home/agent-admin/agent-app/upload_files
sudo chmod 2770 /home/agent-admin/agent-app/upload_files
sudo chmod 2770 /home/agent-admin/agent-app/api_keys
sudo chmod 2770 /var/log/agent-app
ls -ld /home/agent-admin/agent-app /home/agent-admin/agent-app/upload_files /home/agent-admin/agent-app/api_keys /var/log/agent-app
~~~

예상 화면/출력:
~~~text
drwx... agent-admin agent-core   /home/agent-admin/agent-app
drwx... agent-admin agent-common /home/agent-admin/agent-app/upload_files
drwx... agent-admin agent-core   /home/agent-admin/agent-app/api_keys
drwx... agent-admin agent-core   /var/log/agent-app
~~~

6. 키 파일을 만든다.

복붙 명령어:
~~~sh
printf '%s\n' 'agent_api_key_test' | sudo tee /home/agent-admin/agent-app/api_keys/t_secret.key >/dev/null
printf '%s\n' 'agent_api_key_test' | sudo tee /home/agent-admin/agent-app/api_keys/secret.key >/dev/null
sudo chown agent-admin:agent-core /home/agent-admin/agent-app/api_keys/t_secret.key /home/agent-admin/agent-app/api_keys/secret.key
sudo chmod 660 /home/agent-admin/agent-app/api_keys/t_secret.key /home/agent-admin/agent-app/api_keys/secret.key
sudo wc -c /home/agent-admin/agent-app/api_keys/t_secret.key
~~~

예상 화면/출력:
~~~text
19 /home/agent-admin/agent-app/api_keys/t_secret.key
~~~

7. 제공 앱 압축 파일을 앱 폴더로 풀고 파일명을 확인한다.

복붙 명령어:
~~~sh
python3 -c 'import os,sys,zipfile; z="/home/"+os.environ["USER"]+"/mission1-work/agent-app.zip"; m="agent-app-linux-x86"; t="/tmp/agent-app-linux-x86"; data=zipfile.ZipFile(z).read(m); open(t,"wb").write(data)'
sudo install -o agent-admin -g agent-core -m 750 /tmp/agent-app-linux-x86 /home/agent-admin/agent-app/bin/agent-app-linux-x86
sudo ln -sfn /home/agent-admin/agent-app/bin/agent-app-linux-x86 /home/agent-admin/agent-app/bin/agent-app
find /home/agent-admin/agent-app -maxdepth 2 -type f | sort
~~~

예상 화면/출력:
~~~text
/home/agent-admin/agent-app/...agent_app...
/home/agent-admin/agent-app/bin 또는 실행 파일 목록
~~~

8. 앱을 일반 계정으로 실행한다.

복붙 명령어:
~~~sh
sudo -u agent-admin env \
  AGENT_HOME=/home/agent-admin/agent-app \
  AGENT_PORT=15034 \
  AGENT_UPLOAD_DIR=/home/agent-admin/agent-app/upload_files \
  AGENT_KEY_PATH=/home/agent-admin/agent-app/api_keys \
  AGENT_LOG_DIR=/var/log/agent-app \
  /home/agent-admin/agent-app/bin/agent-app-linux-x86
~~~

예상 화면/출력:
~~~text
Starting Agent Boot Sequence...
[1/5] ... [OK]
[2/5] ... [OK]
[3/5] ... [OK]
[4/5] ... [OK]
[5/5] ... [OK]
Agent READY
~~~

9. 다른 터미널에서 앱 포트를 확인한다.

복붙 명령어:
~~~sh
sudo ss -tulnp | grep ':15034' || true
~~~

예상 화면/출력:
~~~text
LISTEN ... 0.0.0.0:15034 ...
~~~

10. `monitor.sh`를 만든 뒤 소유자, 그룹, 권한을 맞춘다.

복붙 명령어:
~~~sh
sudo install -o agent-dev -g agent-core -m 750 "$HOME/mission1-work/monitor.sh" /home/agent-admin/agent-app/bin/monitor.sh
sudo stat -c '%U %G %a %n' /home/agent-admin/agent-app/bin/monitor.sh
~~~

예상 화면/출력:
~~~text
agent-dev agent-core 750 /home/agent-admin/agent-app/bin/monitor.sh
~~~

11. `monitor.sh`를 실행해 콘솔 출력과 로그 기록을 확인한다.

복붙 명령어:
~~~sh
sudo -u agent-admin env \
  AGENT_HOME=/home/agent-admin/agent-app \
  AGENT_PORT=15034 \
  AGENT_LOG_DIR=/var/log/agent-app \
  /home/agent-admin/agent-app/bin/monitor.sh
sudo tail -n 5 /var/log/agent-app/monitor.log
~~~

예상 화면/출력:
~~~text
====== SYSTEM MONITOR RESULT ======
[HEALTH CHECK]
Checking process ... [OK]
Checking port 15034... [OK]
[INFO] Log appended: /var/log/agent-app/monitor.log
[YYYY-MM-DD HH:MM:SS] PID:... CPU:..% MEM:..% DISK_USED:..%
~~~

12. agent-admin 계정의 crontab에 매분 실행을 등록한다.

복붙 명령어:
~~~sh
sudo -u agent-admin crontab -l 2>/dev/null | grep -v '/home/agent-admin/agent-app/bin/monitor.sh' | sudo tee /tmp/agent-admin.cron >/dev/null
printf '* * * * * AGENT_HOME=/home/agent-admin/agent-app AGENT_PORT=15034 AGENT_LOG_DIR=/var/log/agent-app /home/agent-admin/agent-app/bin/monitor.sh >> /var/log/agent-app/monitor-cron.out 2>&1\n' | sudo tee -a /tmp/agent-admin.cron >/dev/null
sudo -u agent-admin crontab /tmp/agent-admin.cron
sudo -u agent-admin crontab -l
~~~

예상 화면/출력:
~~~text
* * * * * AGENT_HOME=/home/agent-admin/agent-app ...
~~~

13. 1~2분 뒤 로그가 늘어났는지 확인한다.

복붙 명령어:
~~~sh
sudo wc -l /var/log/agent-app/monitor.log
sleep 70
sudo wc -l /var/log/agent-app/monitor.log
sudo tail -n 5 /var/log/agent-app/monitor.log
~~~

예상 화면/출력:
~~~text
<이전 줄 수> /var/log/agent-app/monitor.log
<더 큰 줄 수> /var/log/agent-app/monitor.log
[YYYY-MM-DD HH:MM:SS] PID:... CPU:..% MEM:..% DISK_USED:..%
~~~

## 6. 로그와 출력 기록하기

1. 수행 내역서에 붙일 확인 출력을 저장한다.

복붙 명령어:
~~~sh
mkdir -p "$HOME/mission1-work/logs"
{
  date --iso-8601=seconds
  grep -E '^(Port|PermitRootLogin)' /etc/ssh/sshd_config
  sudo ufw status verbose
  id agent-admin
  id agent-dev
  id agent-test
  ls -ld /home/agent-admin/agent-app /home/agent-admin/agent-app/upload_files /home/agent-admin/agent-app/api_keys /var/log/agent-app
  sudo stat -c '%U %G %a %n' /home/agent-admin/agent-app/bin/monitor.sh
  sudo tail -n 10 /var/log/agent-app/monitor.log
  sudo -u agent-admin crontab -l
} > "$HOME/mission1-work/logs/final-check.txt"
printf '%s\n' "$HOME/mission1-work/logs/final-check.txt"
~~~

예상 화면/출력:
~~~text
/home/<현재사용자이름>/mission1-work/logs/final-check.txt
~~~

## 7. 최종 산출물 확인하기

1. 제출할 파일이 있는지 확인한다.

복붙 명령어:
~~~sh
find "$HOME/mission1-work/submission" -maxdepth 4 -type f | sort
~~~

예상 화면/출력:
~~~text
/home/<현재사용자이름>/mission1-work/submission/.../monitor.sh
/home/<현재사용자이름>/mission1-work/submission/.../mission1_report.md
~~~

2. `monitor.sh` 문법을 확인한다.

복붙 명령어:
~~~sh
bash -n "$HOME/mission1-work/submission/home/agent-admin/agent-app/bin/monitor.sh"
printf '%s\n' "monitor.sh 문법 확인 완료"
~~~

예상 화면/출력:
~~~text
monitor.sh 문법 확인 완료
~~~
