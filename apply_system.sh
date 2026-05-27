#!/usr/bin/env bash
set -u
set -o pipefail
export PATH="/usr/sbin:/usr/bin:/sbin:/bin:${PATH:-}"

RUN_DIR="$(pwd -P)"
RUNTIME_DIR="${RUN_DIR}/runtime"
WORK_LOG="${RUNTIME_DIR}/work.log"
SUBMIT_BIN="${RUN_DIR}/submission/home/agent-admin/agent-app/bin"
MISSION_ZIP="${RUN_DIR}/agent-app.zip"

AGENT_HOME="/home/agent-admin/agent-app"
AGENT_PORT="15034"
AGENT_UPLOAD_DIR="${AGENT_HOME}/upload_files"
AGENT_KEY_PATH="${AGENT_HOME}/api_keys"
AGENT_LOG_DIR="/var/log/agent-app"
AGENT_ARCHIVE_DIR="/var/log/monitor/agent-app/archive"
SSH_PORT="20022"

RUN_EXIT=0
CURRENT_REQ=""
CURRENT_TITLE=""

mkdir -p "$RUNTIME_DIR"

ts() { date -Iseconds; }

log_block_start() {
  CURRENT_REQ="$1"
  CURRENT_TITLE="$2"
  {
    printf '===== apply_system.sh block =====\n'
    printf '[ts] %s\n' "$(ts)"
    printf '[req] %s\n' "$CURRENT_REQ"
    printf '[title] %s\n' "$CURRENT_TITLE"
    printf '[cwd] %s\n' "$RUN_DIR"
  } >> "$WORK_LOG"
}

run_cmd() {
  desc="$1"
  cmd="$2"
  tmp="$(mktemp)"
  {
    printf '[cmd] %s\n' "$cmd"
    printf '[stdout/stderr]\n'
  } >> "$WORK_LOG"
  bash -c "$cmd" >"$tmp" 2>&1
  code=$?
  cat "$tmp" >> "$WORK_LOG"
  {
    printf '[exit] %s\n' "$code"
    if [ "$code" -eq 0 ]; then
      printf '[interpretation] PASS: %s\n\n' "$desc"
      printf '[성공] %s\n' "$desc"
    else
      printf '[interpretation] FAIL: %s\n\n' "$desc"
      printf '[실패] %s\n' "$desc"
      RUN_EXIT=1
    fi
  } >> "$WORK_LOG"
  rm -f "$tmp"
  return "$code"
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    printf '[실패] 필수 명령 없음: %s\n' "$1"
    return 1
  }
}

printf '적용 범위: SSH 20022/root 차단, 방화벽, agent 계정/권한, 앱/monitor/report 배치, cron 등록, 15034 포트 정리\n'
printf '백업: SSH 설정과 crontab/방화벽 상태는 timestamp 파일로 보존합니다.\n'

log_block_start "ENV-001" "Install packages"
printf '[실행] 패키지 설치\n'
if [ "$(id -u)" -eq 0 ] && command -v apt-get >/dev/null 2>&1; then
  run_cmd "필수 패키지 설치" "DEBIAN_FRONTEND=noninteractive apt-get update || true; DEBIAN_FRONTEND=noninteractive apt-get install -y openssh-server ufw acl cron unzip python3 psmisc procps"
else
  run_cmd "apt-get/root 권한 확인" "false"
fi

# 무엇: root 권한, 필수 명령, 제출 소스, 실행 환경을 확인한다.
# 예상여파: 읽기 전용 점검이며 시스템 변경 전 실패 조건을 드러낸다.
# 효과: 필수 전제가 충족되면 이후 적용 블록을 진행한다.
# 실패 시 처리: 필수 전제가 없으면 중단한다.
# 재실행 가능성: 반복 실행해도 상태를 변경하지 않는다.
# 백업/복구: 읽기 전용 점검이므로 백업이 필요 없다.
log_block_start "ENV-001,SEC-001,SEC-002,SEC-003,SEC-004,PERM-001,PERM-002,PERM-003,PERM-004,PERM-005,PERM-006,DATA-001,FUNC-001,FUNC-002,FUNC-003,FUNC-004,FUNC-010,FUNC-012,BONUS-001,BONUS-002,BONUS-003,BONUS-004,BONUS-005" "Preflight"
printf '[실행] preflight\n'
preflight_ok=0
[ "$(id -u)" -eq 0 ] || preflight_ok=1
for cmd in awk bash chmod chown cp date fuser getent grep id mkdir mv pgrep pkill ps sed stat unzip useradd groupadd usermod python3; do
  need_cmd "$cmd" || preflight_ok=1
done
[ -s "$MISSION_ZIP" ] || preflight_ok=1
[ -s "${SUBMIT_BIN}/monitor.sh" ] || preflight_ok=1
[ -s "${SUBMIT_BIN}/report.sh" ] || preflight_ok=1
if [ "$preflight_ok" -ne 0 ]; then
  {
    printf '[cmd] preflight checks\n'
    printf '[stdout/stderr]\n'
    printf 'root_uid=%s mission_zip=%s monitor=%s report=%s\n' "$(id -u)" "$MISSION_ZIP" "${SUBMIT_BIN}/monitor.sh" "${SUBMIT_BIN}/report.sh"
    printf '[exit] 2\n'
    printf '[interpretation] BLOCKED: root 권한 또는 필수 명령/소스 파일이 부족해 시스템 적용을 중단한다.\n\n'
  } >> "$WORK_LOG"
  printf '[실패] preflight: root 권한 또는 필수 파일/명령 부족\n최종 종료 코드: 2\n전체 로그: runtime/work.log\n'
  exit 2
fi
{
  printf '[cmd] preflight checks\n'
  printf '[stdout/stderr]\n'
  printf 'root_uid=0 mission_zip=%s monitor=%s report=%s\n' "$MISSION_ZIP" "${SUBMIT_BIN}/monitor.sh" "${SUBMIT_BIN}/report.sh"
  printf '[exit] 0\n'
  printf '[interpretation] PASS: root 권한과 필수 소스/명령을 확인했다.\n\n'
} >> "$WORK_LOG"
printf '[성공] preflight\n'

# 무엇: SSH 포트를 20022로 고정하고 Root 원격 접속을 차단한다.
# 예상여파: SSH 서비스 설정이 변경되며 현재 원격 접속 정책에 영향을 줄 수 있다.
# 효과: sshd 설정에 Port 20022와 PermitRootLogin no가 적용된다.
# 실패 시 처리: 설정 문법 검사 실패 시 reload를 실패로 기록한다.
# 재실행 가능성: 기존 mission block을 교체해 같은 설정을 유지한다.
# 백업/복구: 변경 전 sshd_config를 timestamp 백업으로 보존한다.
log_block_start "SEC-001,SEC-002" "Configure OpenSSH"
printf '[실행] SSH 설정\n'
if [ -f /etc/ssh/sshd_config ]; then
  backup="/etc/ssh/sshd_config.agent-mission.$(date +%Y%m%dT%H%M%S%z).bak"
  run_cmd "SSH 설정 백업" "cp /etc/ssh/sshd_config '$backup'"
  run_cmd "SSH Port/PermitRootLogin 설정 적용" "sed -i '/^# BEGIN agent mission$/,/^# END agent mission$/d' /etc/ssh/sshd_config && sed -i -E 's/^([[:space:]]*Port[[:space:]]+)/# agent mission disabled: \\1/' /etc/ssh/sshd_config && sed -i -E 's/^([[:space:]]*PermitRootLogin[[:space:]]+)/# agent mission disabled: \\1/' /etc/ssh/sshd_config && printf '\\n# BEGIN agent mission\\nPort ${SSH_PORT}\\nPermitRootLogin no\\n# END agent mission\\n' >> /etc/ssh/sshd_config"
  if command -v sshd >/dev/null 2>&1 || [ -x /usr/sbin/sshd ]; then
    sshd_bin="$(command -v sshd || printf /usr/sbin/sshd)"
    run_cmd "sshd 설정 문법 검사" "'$sshd_bin' -t"
    if command -v systemctl >/dev/null 2>&1; then
      run_cmd "ssh.socket 20022 override 설정" "mkdir -p /etc/systemd/system/ssh.socket.d && printf '%s\\n' '[Socket]' 'ListenStream=' 'ListenStream=${SSH_PORT}' > /etc/systemd/system/ssh.socket.d/override.conf && systemctl daemon-reload"
      run_cmd "ssh 서비스 reload/start" "systemctl restart ssh.socket 2>/dev/null || :; systemctl restart ssh || systemctl restart sshd || systemctl start ssh || systemctl start sshd"
    elif command -v service >/dev/null 2>&1; then
      run_cmd "ssh 서비스 reload" "service ssh reload || service sshd reload"
    else
      run_cmd "ssh 서비스 reload 도구 확인" "false"
    fi
  else
    run_cmd "sshd 실행 파일 확인" "false"
  fi
else
  run_cmd "sshd_config 존재 확인" "false"
fi

# 무엇: UFW 또는 firewalld를 활성화하고 20022/tcp, 15034/tcp만 허용한다.
# 예상여파: 인바운드 방화벽 정책이 제한되어 기존 허용 규칙이 바뀔 수 있다.
# 효과: 선택된 방화벽이 활성화되고 필요한 두 포트만 허용된다.
# 실패 시 처리: 사용 가능한 방화벽 도구가 없으면 실패로 기록한다.
# 재실행 가능성: UFW는 reset 후 같은 규칙을 재적용한다.
# 백업/복구: 적용 전 현재 ruleset/status를 runtime archive에 저장한다.
log_block_start "SEC-003,SEC-004" "Configure firewall"
printf '[실행] 방화벽 설정\n'
mkdir -p "${RUNTIME_DIR}/archive"
if command -v ufw >/dev/null 2>&1; then
  run_cmd "UFW 현재 상태 백업" "ufw status verbose > '${RUNTIME_DIR}/archive/ufw_before_$(date +%Y%m%dT%H%M%S%z).txt' 2>&1"
  run_cmd "UFW 20022/15034 허용 정책 적용" "ufw --force reset && ufw default deny incoming && ufw default allow outgoing && ufw allow ${SSH_PORT}/tcp && ufw allow ${AGENT_PORT}/tcp && ufw --force enable"
elif command -v firewall-cmd >/dev/null 2>&1; then
  run_cmd "firewalld 현재 상태 백업" "firewall-cmd --list-all > '${RUNTIME_DIR}/archive/firewalld_before_$(date +%Y%m%dT%H%M%S%z).txt' 2>&1"
  run_cmd "firewalld 20022/15034 허용 정책 적용" "firewall-cmd --permanent --remove-service=ssh >/dev/null 2>&1 || :; firewall-cmd --permanent --add-port=${SSH_PORT}/tcp && firewall-cmd --permanent --add-port=${AGENT_PORT}/tcp && firewall-cmd --reload"
else
  run_cmd "방화벽 도구 확인" "false"
fi

# 무엇: agent 계정과 그룹을 생성하고 역할별 멤버십을 설정한다.
# 예상여파: 로컬 사용자와 그룹 데이터베이스에 agent 계정/그룹이 추가 또는 갱신된다.
# 효과: agent-admin/dev/test와 agent-common/core 멤버십이 존재한다.
# 실패 시 처리: user/group 명령 실패를 기록하고 이후 검증에서 FAIL로 남긴다.
# 재실행 가능성: 이미 있으면 보존하고 필요한 멤버십만 추가한다.
# 백업/복구: 기존 계정은 삭제하지 않으며 변경 전 존재 여부는 로그에 남긴다.
log_block_start "PERM-001,PERM-002,PERM-003" "Configure users and groups"
printf '[실행] 계정/그룹 설정\n'
run_cmd "그룹 생성" "groupadd -f agent-common && groupadd -f agent-core"
run_cmd "계정 생성" "id agent-admin >/dev/null 2>&1 || useradd -m -s /bin/bash agent-admin; id agent-dev >/dev/null 2>&1 || useradd -m -s /bin/bash agent-dev; id agent-test >/dev/null 2>&1 || useradd -m -s /bin/bash agent-test"
run_cmd "그룹 멤버십 설정" "usermod -aG agent-common,agent-core agent-admin && usermod -aG agent-common,agent-core agent-dev && usermod -aG agent-common agent-test"

# 무엇: AGENT_HOME, 로그/업로드/키/아카이브 디렉토리와 키 파일을 만든다.
# 예상여파: /home/agent-admin 및 /var/log 아래 agent 관련 디렉토리 권한이 설정된다.
# 효과: 명세의 그룹 R/W 정책과 키 파일이 구성된다.
# 실패 시 처리: 권한 설정 실패를 기록하고 이후 증거 수집에서 FAIL로 남긴다.
# 재실행 가능성: mkdir/chown/chmod는 같은 상태로 수렴한다.
# 백업/복구: 기존 파일은 삭제하지 않고 필요한 권한만 조정한다.
log_block_start "ENV-002,PERM-004,PERM-005,PERM-006,DATA-001,BONUS-003,BONUS-004,BONUS-005" "Configure directories, env, key"
printf '[실행] 디렉토리/환경/키 설정\n'
run_cmd "디렉토리 생성" "mkdir -p '${AGENT_HOME}/bin' '${AGENT_UPLOAD_DIR}' '${AGENT_KEY_PATH}' '${AGENT_LOG_DIR}' '${AGENT_ARCHIVE_DIR}' /etc/profile.d"
run_cmd "디렉토리 소유권/권한 설정" "chown -R agent-admin:agent-core '${AGENT_HOME}' '${AGENT_LOG_DIR}' '${AGENT_ARCHIVE_DIR%/archive}' && chgrp agent-common '${AGENT_UPLOAD_DIR}' && chmod 2770 '${AGENT_UPLOAD_DIR}' '${AGENT_KEY_PATH}' '${AGENT_LOG_DIR}' '${AGENT_ARCHIVE_DIR}' && chmod 2750 '${AGENT_HOME}' '${AGENT_HOME}/bin'"
run_cmd "환경 변수 전역 설정" "printf '%s\\n' 'export AGENT_HOME=${AGENT_HOME}' 'export AGENT_PORT=${AGENT_PORT}' 'export AGENT_UPLOAD_DIR=${AGENT_UPLOAD_DIR}' 'export AGENT_KEY_PATH=${AGENT_KEY_PATH}' 'export AGENT_LOG_DIR=${AGENT_LOG_DIR}' > /etc/profile.d/agent-app.sh && chmod 644 /etc/profile.d/agent-app.sh && touch /etc/bash.bashrc && sed -i '/^# BEGIN agent-app env$/,/^# END agent-app env$/d' /etc/bash.bashrc && printf '\\n# BEGIN agent-app env\\nexport AGENT_HOME=${AGENT_HOME}\\nexport AGENT_PORT=${AGENT_PORT}\\nexport AGENT_UPLOAD_DIR=${AGENT_UPLOAD_DIR}\\nexport AGENT_KEY_PATH=${AGENT_KEY_PATH}\\nexport AGENT_LOG_DIR=${AGENT_LOG_DIR}\\n# END agent-app env\\n' >> /etc/bash.bashrc"
run_cmd "키 파일 생성" "printf '%s\\n' 'agent_api_key_test' > '${AGENT_KEY_PATH}/secret.key' && chown agent-admin:agent-core '${AGENT_KEY_PATH}/secret.key' && chmod 660 '${AGENT_KEY_PATH}/secret.key'"

log_block_start "FUNC-001,FUNC-002,FUNC-003" "Stop existing agent"
printf '[실행] 기존 agent 종료\n'
run_cmd "기존 15034 포트/agent 프로세스 종료" "fuser -k -TERM ${AGENT_PORT}/tcp >/dev/null 2>&1 || :; pkill -TERM -u agent-admin -f 'agent-app-linux|/home/agent-admin/agent-app/bin/agent-app' >/dev/null 2>&1 || :; sleep 1; fuser -k -KILL ${AGENT_PORT}/tcp >/dev/null 2>&1 || :; pkill -KILL -u agent-admin -f 'agent-app-linux|/home/agent-admin/agent-app/bin/agent-app' >/dev/null 2>&1 || :; true"

# 무엇: 제공 앱 바이너리와 monitor/report 스크립트를 실제 경로에 배치한다.
# 예상여파: AGENT_HOME/bin 아래 실행 파일이 생성 또는 갱신된다.
# 효과: 앱 실행 파일과 monitor/report가 명세 경로와 권한으로 배치된다.
# 실패 시 처리: 배치 실패를 기록하고 앱 시작을 실패로 남긴다.
# 재실행 가능성: 같은 소스 파일을 install로 덮어쓴다.
# 백업/복구: 기존 파일은 같은 목적 파일로 갱신되며 별도 사용자 파일은 삭제하지 않는다.
log_block_start "ENV-001,FUNC-004,NONFUNC-001,SUB-002,BONUS-001,BONUS-002" "Install app and scripts"
printf '[실행] 앱/스크립트 배치\n'
arch="$(uname -m)"
case "$arch" in
  x86_64|amd64) app_member="agent-app-linux-x86" ;;
  aarch64|arm64) app_member="agent-app-linux-arm64" ;;
  *) app_member="agent-app-linux-x86" ;;
esac
run_cmd "제공 앱 바이너리 추출" "python3 -c 'import os,sys,zipfile; z,m,t=sys.argv[1:4]; data=zipfile.ZipFile(z).read(m); os.makedirs(os.path.dirname(t), exist_ok=True); open(t, \"wb\").write(data); os.chmod(t, 0o750)' '$MISSION_ZIP' '$app_member' '${AGENT_HOME}/bin/$app_member'"
run_cmd "제공 앱 바이너리 권한 설정" "chown agent-admin:agent-core '${AGENT_HOME}/bin/$app_member' && chmod 750 '${AGENT_HOME}/bin/$app_member' && ln -sfn '${AGENT_HOME}/bin/$app_member' '${AGENT_HOME}/bin/agent-app'"
run_cmd "monitor/report 설치" "install -o agent-dev -g agent-core -m 750 '${SUBMIT_BIN}/monitor.sh' '${AGENT_HOME}/bin/monitor.sh' && install -o agent-dev -g agent-core -m 750 '${SUBMIT_BIN}/report.sh' '${AGENT_HOME}/bin/report.sh'"

# 무엇: agent-admin crontab에 monitor.sh 매분 실행을 등록한다.
# 예상여파: agent-admin 사용자 crontab이 생성 또는 갱신된다.
# 효과: monitor.sh가 매분 실행되도록 예약된다.
# 실패 시 처리: crontab 명령 부재 또는 등록 실패를 기록한다.
# 재실행 가능성: 기존 monitor.sh 줄을 제거하고 한 줄만 재등록한다.
# 백업/복구: 기존 crontab은 runtime/archive에 저장한다.
log_block_start "FUNC-012" "Configure cron"
printf '[실행] cron 등록\n'
if command -v crontab >/dev/null 2>&1; then
  cron_backup="${RUNTIME_DIR}/archive/agent-admin.cron.$(date +%Y%m%dT%H%M%S%z).bak"
  run_cmd "기존 crontab 백업" "crontab -u agent-admin -l > '$cron_backup' 2>/dev/null || :"
  run_cmd "매분 monitor 등록" "tmp=\$(mktemp); crontab -u agent-admin -l 2>/dev/null | grep -v '/home/agent-admin/agent-app/bin/monitor.sh' > \$tmp || :; printf '* * * * * AGENT_HOME=${AGENT_HOME} AGENT_PORT=${AGENT_PORT} AGENT_LOG_DIR=${AGENT_LOG_DIR} ${AGENT_HOME}/bin/monitor.sh >> ${AGENT_LOG_DIR}/monitor-cron.out 2>&1\\n' >> \$tmp; crontab -u agent-admin \$tmp; rm -f \$tmp"
else
  run_cmd "crontab 명령 확인" "false"
fi

log_block_start "FUNC-001,FUNC-002,FUNC-003" "Free agent port"
printf '[실행] 15034 포트 정리\n'
run_cmd "15034 포트/agent 프로세스 종료" "fuser -k -TERM ${AGENT_PORT}/tcp >/dev/null 2>&1 || :; pkill -TERM -u agent-admin -f 'agent-app-linux|/home/agent-admin/agent-app/bin/agent-app' >/dev/null 2>&1 || :; sleep 1; fuser -k -KILL ${AGENT_PORT}/tcp >/dev/null 2>&1 || :; pkill -KILL -u agent-admin -f 'agent-app-linux|/home/agent-admin/agent-app/bin/agent-app' >/dev/null 2>&1 || :; true"

printf '최종 종료 코드: %s\n전체 로그: runtime/work.log\n' "$RUN_EXIT"
exit "$RUN_EXIT"
