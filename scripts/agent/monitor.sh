#!/usr/bin/env bash
set -u
set -o pipefail

AGENT_HOME="${AGENT_HOME:-/home/agent-admin/agent-app}"
AGENT_PORT="${AGENT_PORT:-15034}"
AGENT_LOG_DIR="${AGENT_LOG_DIR:-/var/log/agent-app}"
PROCESS_PATTERN="${AGENT_PROCESS_PATTERN:-agent-app-linux|agent_app.py|agent-app}"
LOG_FILE="${AGENT_LOG_DIR}/monitor.log"

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

find_agent_pid() {
  ps -eo pid=,pcpu=,args= 2>/dev/null | awk -v pat="$PROCESS_PATTERN" '
    $0 ~ pat &&
    $0 !~ /(^|[[:space:]])timeout[[:space:]][0-9]+s?[[:space:]]/ &&
    $0 !~ /[[:space:]]bash[[:space:]].*monitor[.]sh/ {
      cpu = $2 + 0
      if (!found || cpu > best_cpu) {
        best_pid = $1
        best_cpu = cpu
        found = 1
      }
    }
    END {
      if (found) {
        print best_pid
      }
    }'
}

check_process() {
  pid="$(find_agent_pid)"
  if [ -z "${pid:-}" ]; then
    fail "Checking process '${PROCESS_PATTERN}'... [FAIL]"
  fi
  printf "Checking process '%s'... [OK] (PID: %s)\n" "$PROCESS_PATTERN" "$pid"
}

check_port() {
  listen_ok=1

  if command -v ss >/dev/null 2>&1; then
    if ss -H -tuln | awk -v port=":${AGENT_PORT}" '$0 ~ port { found=1 } END { exit found ? 0 : 1 }'; then
      listen_ok=0
    fi
  elif command -v netstat >/dev/null 2>&1; then
    if netstat -tuln | awk -v port=":${AGENT_PORT}" '$0 ~ port { found=1 } END { exit found ? 0 : 1 }'; then
      listen_ok=0
    fi
  fi

  if command -v nc >/dev/null 2>&1; then
    if nc -z 127.0.0.1 "$AGENT_PORT" >/dev/null 2>&1; then
      printf 'Checking port %s... [OK] (LISTEN + TCP connect)\n' "$AGENT_PORT"
      return 0
    fi
    fail "Checking port ${AGENT_PORT} with nc -z 127.0.0.1 ${AGENT_PORT}... [FAIL]"
  fi

  if [ "$listen_ok" -eq 0 ]; then
    printf 'Checking port %s... [OK] (LISTEN; nc unavailable)\n' "$AGENT_PORT"
    return 0
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

process_cpu_usage() {
  ps -p "$1" -o %cpu= 2>/dev/null | awk 'NR == 1 { printf "%.1f\n", $1 + 0 }'
}

process_mem_usage() {
  ps -p "$1" -o %mem= 2>/dev/null | awk 'NR == 1 { printf "%.1f\n", $1 + 0 }'
}

process_mem_mb() {
  ps -p "$1" -o rss= 2>/dev/null | awk 'NR == 1 { printf "%.1f\n", ($1 + 0) / 1024 }'
}

process_elapsed() {
  ps -p "$1" -o etime= 2>/dev/null | awk 'NR == 1 { gsub(/^[[:space:]]+|[[:space:]]+$/, ""); print }'
}

dir_usage_mb() {
  if [ -d "$1" ]; then
    du -sk "$1" 2>/dev/null | awk 'NR == 1 { printf "%.1f\n", ($1 + 0) / 1024 }'
  fi
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
  app_cpu="$(process_cpu_usage "$pid" | first_number)"
  app_mem="$(process_mem_usage "$pid" | first_number)"
  app_mem_mb="$(process_mem_mb "$pid" | first_number)"
  app_elapsed="$(process_elapsed "$pid")"
  system_cpu="$(cpu_usage | first_number)"
  system_mem="$(mem_usage | first_number)"
  root_disk="$(disk_usage | first_number)"
  agent_home_mb="$(dir_usage_mb "$AGENT_HOME" | first_number)"
  agent_log_mb="$(dir_usage_mb "$AGENT_LOG_DIR" | first_number)"
  [ -n "${app_cpu:-}" ] || app_cpu="0.0"
  [ -n "${app_mem:-}" ] || app_mem="0.0"
  [ -n "${app_mem_mb:-}" ] || app_mem_mb="0.0"
  [ -n "${app_elapsed:-}" ] || app_elapsed="unknown"
  [ -n "${system_cpu:-}" ] || system_cpu="0.0"
  [ -n "${system_mem:-}" ] || system_mem="0.0"
  [ -n "${root_disk:-}" ] || root_disk="0"
  [ -n "${agent_home_mb:-}" ] || agent_home_mb="0.0"
  [ -n "${agent_log_mb:-}" ] || agent_log_mb="0.0"

  printf 'Agent CPU (ps %%CPU)        : %.1f%%\n' "$app_cpu"
  printf 'Agent MEM (ps %%MEM/RSS)    : %.1f%% (RSS %.1fMB)\n' "$app_mem" "$app_mem_mb"
  printf 'Agent Runtime               : %s\n' "$app_elapsed"
  printf 'System CPU (top non-idle)   : %.1f%%\n' "$system_cpu"
  printf 'System MEM (free used/total): %.1f%%\n' "$system_mem"
  printf 'Root Disk (df /)            : %s%%\n' "$root_disk"
  printf 'Agent Home (du)             : %.1fMB\n' "$agent_home_mb"
  printf 'Agent Log Dir (du)          : %.1fMB\n' "$agent_log_mb"

  gt_threshold "$app_cpu" 20 && warn "Agent CPU threshold exceeded (${app_cpu}% > 20%)"
  gt_threshold "$app_mem" 10 && warn "Agent MEM threshold exceeded (${app_mem}% > 10%)"
  gt_threshold "$root_disk" 80 && warn "Root DISK_USED threshold exceeded (${root_disk}% > 80%)"

  mkdir -p "$AGENT_LOG_DIR" || fail "cannot create log directory: $AGENT_LOG_DIR"
  timestamp="$(date '+%Y-%m-%d %H:%M:%S')"
  log_pid="$(find_agent_pid)"
  printf '[%s] PID:%s CPU:%.1f%% MEM:%.1f%% DISK_USED:%s%%\n' \
    "$timestamp" "${log_pid:-unknown}" "$app_cpu" "$app_mem" "$root_disk" >> "$LOG_FILE" || fail "cannot append log"
  printf '\n[INFO] Log appended: %s\n' "$LOG_FILE"
  printf '[INFO] Warning count: %s\n' "$warn_count"
}

main "$@"
