#!/usr/bin/env bash
set -u
set -o pipefail

AGENT_HOME="${AGENT_HOME:-/home/agent-admin/agent-app}"
AGENT_PORT="${AGENT_PORT:-15034}"
AGENT_LOG_DIR="${AGENT_LOG_DIR:-/var/log/agent-app}"
PROCESS_PATTERN="${AGENT_PROCESS_PATTERN:-agent-app-linux|agent_app.py|agent-app}"
LOG_FILE="${AGENT_LOG_DIR}/monitor.log"
MAX_BYTES="${MONITOR_MAX_BYTES:-10485760}"
MAX_FILES="${MONITOR_MAX_FILES:-10}"

warn_count=0

print_section() {
  printf '\n%s\n' "$1"
}

warn() {
  warn_count=$((warn_count + 1))
  printf '[WARNING] %s\n' "$*"
}

fail() {
  printf '[ERROR] %s\n' "$*" >&2
  exit 1
}

first_number() {
  awk 'match($0, /[0-9]+([.][0-9]+)?/) { print substr($0, RSTART, RLENGTH); exit }'
}

rotate_logs() {
  mkdir -p "$AGENT_LOG_DIR" || fail "cannot create log directory: $AGENT_LOG_DIR"

  if [ -f "$LOG_FILE" ]; then
    size=$(wc -c < "$LOG_FILE" 2>/dev/null || printf '0')
    if [ "${size:-0}" -ge "$MAX_BYTES" ]; then
      i=$((MAX_FILES - 1))
      while [ "$i" -ge 1 ]; do
        if [ -f "${LOG_FILE}.${i}" ]; then
          if [ "$i" -eq $((MAX_FILES - 1)) ]; then
            rm -f "${LOG_FILE}.${MAX_FILES}" 2>/dev/null || true
          fi
          mv -f "${LOG_FILE}.${i}" "${LOG_FILE}.$((i + 1))"
        fi
        i=$((i - 1))
      done
      mv -f "$LOG_FILE" "${LOG_FILE}.1"
    fi
  fi

  keep_index=$((MAX_FILES + 1))
  while [ "$keep_index" -le 99 ]; do
    rm -f "${LOG_FILE}.${keep_index}" 2>/dev/null || true
    keep_index=$((keep_index + 1))
  done
}

find_agent_pid() {
  if command -v pgrep >/dev/null 2>&1; then
    pgrep -f "$PROCESS_PATTERN" | awk 'NR == 1 { print; exit }'
    return 0
  fi
  ps -eo pid=,args= | awk -v pat="$PROCESS_PATTERN" '$0 ~ pat { print $1; exit }'
}

check_process() {
  pid="$(find_agent_pid)"
  if [ -z "${pid:-}" ]; then
    fail "Checking process '${PROCESS_PATTERN}'... [FAIL]"
  fi
  printf "Checking process '%s'... [OK] (PID: %s)\n" "$PROCESS_PATTERN" "$pid"
}

check_port() {
  if command -v ss >/dev/null 2>&1; then
    if ss -H -tuln | awk -v port=":${AGENT_PORT}" '$0 ~ port { found=1 } END { exit found ? 0 : 1 }'; then
      printf 'Checking port %s... [OK]\n' "$AGENT_PORT"
      return 0
    fi
  elif command -v netstat >/dev/null 2>&1; then
    if netstat -tuln | awk -v port=":${AGENT_PORT}" '$0 ~ port { found=1 } END { exit found ? 0 : 1 }'; then
      printf 'Checking port %s... [OK]\n' "$AGENT_PORT"
      return 0
    fi
  fi
  fail "Checking port ${AGENT_PORT}... [FAIL]"
}

check_firewall() {
  if command -v ufw >/dev/null 2>&1; then
    status="$(ufw status 2>/dev/null | head -n 1 || true)"
    if printf '%s\n' "$status" | grep -qi 'active'; then
      printf 'Firewall status: [OK] UFW active\n'
    else
      warn "UFW is not active"
    fi
  elif command -v firewall-cmd >/dev/null 2>&1; then
    if firewall-cmd --state >/dev/null 2>&1; then
      printf 'Firewall status: [OK] firewalld active\n'
    else
      warn "firewalld is not active"
    fi
  else
    warn "No supported firewall command found"
  fi
}

cpu_usage() {
  if command -v top >/dev/null 2>&1; then
    top -bn1 | awk -F'[, ]+' '/Cpu\(s\)|%Cpu/ {
      for (i=1; i<=NF; i++) {
        if ($i == "id") {
          printf "%.1f\n", 100 - $(i-1)
          exit
        }
      }
    }'
  fi
}

mem_usage() {
  free | awk '/^Mem:/ { printf "%.1f\n", ($3 / $2) * 100 }'
}

disk_usage() {
  df -P / | awk 'NR == 2 { gsub(/%/, "", $5); print $5 }'
}

gt_threshold() {
  awk -v value="$1" -v limit="$2" 'BEGIN { exit (value > limit) ? 0 : 1 }'
}

main() {
  print_section '====== SYSTEM MONITOR RESULT ======'
  print_section '[HEALTH CHECK]'
  check_process
  check_port

  print_section '[STATUS CHECK]'
  check_firewall

  print_section '[RESOURCE MONITORING]'
  cpu="$(cpu_usage | first_number)"
  mem="$(mem_usage | first_number)"
  disk="$(disk_usage | first_number)"
  [ -n "${cpu:-}" ] || cpu="0.0"
  [ -n "${mem:-}" ] || mem="0.0"
  [ -n "${disk:-}" ] || disk="0"

  printf 'CPU Usage : %.1f%%\n' "$cpu"
  printf 'MEM Usage : %.1f%%\n' "$mem"
  printf 'DISK Used  : %s%%\n' "$disk"

  gt_threshold "$cpu" 20 && warn "CPU threshold exceeded (${cpu}% > 20%)"
  gt_threshold "$mem" 10 && warn "MEM threshold exceeded (${mem}% > 10%)"
  gt_threshold "$disk" 80 && warn "DISK_USED threshold exceeded (${disk}% > 80%)"

  rotate_logs
  timestamp="$(date '+%Y-%m-%d %H:%M:%S')"
  log_pid="$(find_agent_pid)"
  printf '[%s] PID:%s CPU:%.1f%% MEM:%.1f%% DISK_USED:%s%%\n' \
    "$timestamp" "${log_pid:-unknown}" "$cpu" "$mem" "$disk" >> "$LOG_FILE" || fail "cannot append log"
  printf '\n[INFO] Log appended: %s\n' "$LOG_FILE"
  printf '[INFO] Warning count: %s\n' "$warn_count"
}

main "$@"
