#!/usr/bin/env bash
set -u
set -o pipefail

APP_PATTERN="${AGENT_APP_PROCESS_NAME:-agent_app.py}"
PORT="${AGENT_PORT:-15034}"
LOG_FILE="${AGENT_LOG_DIR:-/var/log/agent-app}/monitor.log"
MAX_LOG_SIZE="${MONITOR_MAX_LOG_SIZE:-10485760}"
MAX_ROTATED_FILES="${MONITOR_MAX_ROTATED_FILES:-10}"

fail() {
  printf '%s\n' "$1"
  exit 1
}

warn_if_gt() {
  label="$1"
  value="$2"
  threshold="$3"
  awk -v label="$label" -v value="$value" -v threshold="$threshold" '
    BEGIN {
      if ((value + 0) > (threshold + 0)) {
        printf("[WARNING] %s threshold exceeded (%s%% > %s%%)\n", label, value, threshold)
      }
    }'
}

sample_cpu_percent() {
  if [ -n "${MONITOR_CPU_OVERRIDE:-}" ]; then
    printf '%s\n' "$MONITOR_CPU_OVERRIDE"
    return 0
  fi

  read -r _ user1 nice1 system1 idle1 iowait1 irq1 softirq1 steal1 _ < /proc/stat
  total1=$((user1 + nice1 + system1 + idle1 + iowait1 + irq1 + softirq1 + steal1))
  idle_all1=$((idle1 + iowait1))
  sleep 1
  read -r _ user2 nice2 system2 idle2 iowait2 irq2 softirq2 steal2 _ < /proc/stat
  total2=$((user2 + nice2 + system2 + idle2 + iowait2 + irq2 + softirq2 + steal2))
  idle_all2=$((idle2 + iowait2))
  total_delta=$((total2 - total1))
  idle_delta=$((idle_all2 - idle_all1))

  awk -v total="$total_delta" -v idle="$idle_delta" 'BEGIN {
    if (total <= 0) {
      printf "0.0"
    } else {
      printf "%.1f", ((total - idle) / total) * 100
    }
  }'
}

sample_mem_percent() {
  if [ -n "${MONITOR_MEM_OVERRIDE:-}" ]; then
    printf '%s\n' "$MONITOR_MEM_OVERRIDE"
    return 0
  fi

  free | awk '/Mem:/ {printf "%.1f", ($3 / $2) * 100}'
}

sample_disk_percent() {
  if [ -n "${MONITOR_DISK_OVERRIDE:-}" ]; then
    printf '%s\n' "$MONITOR_DISK_OVERRIDE"
    return 0
  fi

  df / | awk 'NR == 2 {gsub("%", "", $5); print $5}'
}

rotate_logs_if_needed() {
  [ -f "$LOG_FILE" ] || return 0

  current_size="$(stat -c '%s' "$LOG_FILE" 2>/dev/null || printf '0')"
  [ "$current_size" -le "$MAX_LOG_SIZE" ] && return 0

  i=$((MAX_ROTATED_FILES - 1))
  while [ "$i" -ge 1 ]; do
    if [ -f "$LOG_FILE.$i" ]; then
      mv "$LOG_FILE.$i" "$LOG_FILE.$((i + 1))"
    fi
    i=$((i - 1))
  done
  mv "$LOG_FILE" "$LOG_FILE.1"
  : > "$LOG_FILE"

  find "$(dirname "$LOG_FILE")" -maxdepth 1 -type f -name 'monitor.log.*' \
    | sort -Vr \
    | awk -v keep="$MAX_ROTATED_FILES" 'NR > keep {print}' \
    | xargs -r rm -f
}

find_app_pid() {
  pgrep -u "$(id -u)" -f "$APP_PATTERN" \
    | awk -v self="$$" '$1 != self {print; exit}'
}

printf '%s\n' '====== SYSTEM MONITOR RESULT ======'
printf '\n%s\n' '[HEALTH CHECK]'

pid="$(find_app_pid)"
if [ -z "$pid" ]; then
  fail "Checking process '$APP_PATTERN'... [FAIL]"
fi
printf "Checking process '%s'... [OK] (PID: %s)\n" "$APP_PATTERN" "$pid"

if ! ss -tuln | awk -v port=":$PORT" '$5 ~ port "$" {found = 1} END {exit found ? 0 : 1}'; then
  fail "Checking port $PORT... [FAIL]"
fi
printf 'Checking port %s... [OK]\n' "$PORT"

if command -v ufw >/dev/null 2>&1; then
  firewall_status="$(ufw status 2>/dev/null | awk -F': ' '/^Status:/ {print $2; exit}')"
  if [ "$firewall_status" != "active" ]; then
    printf '%s\n' '[WARNING] firewall is not active'
  fi
elif command -v firewall-cmd >/dev/null 2>&1; then
  firewall_state="$(firewall-cmd --state 2>/dev/null || printf 'unknown')"
  if [ "$firewall_state" != "running" ]; then
    printf '%s\n' '[WARNING] firewall is not active'
  fi
else
  printf '%s\n' '[WARNING] firewall command is not available'
fi

printf '\n%s\n' '[RESOURCE MONITORING]'
cpu="$(sample_cpu_percent)"
mem="$(sample_mem_percent)"
disk="$(sample_disk_percent)"
printf 'CPU Usage : %s%%\n' "$cpu"
printf 'MEM Usage : %s%%\n' "$mem"
printf 'DISK Used : %s%%\n' "$disk"

warn_if_gt "CPU" "$cpu" "20"
warn_if_gt "MEM" "$mem" "10"
warn_if_gt "DISK_USED" "$disk" "80"

log_dir="$(dirname "$LOG_FILE")"
if [ ! -d "$log_dir" ]; then
  fail "Log directory does not exist: $log_dir"
fi
if [ ! -w "$log_dir" ]; then
  fail "Log directory is not writable: $log_dir"
fi

rotate_logs_if_needed
printf '[%s] PID:%s CPU:%s%% MEM:%s%% DISK_USED:%s%%\n' \
  "$(date '+%Y-%m-%d %H:%M:%S')" "$pid" "$cpu" "$mem" "$disk" >> "$LOG_FILE" \
  || fail "Failed to append log: $LOG_FILE"

printf '\n[INFO] Log appended: %s\n' "$LOG_FILE"
