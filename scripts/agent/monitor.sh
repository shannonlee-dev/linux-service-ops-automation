#!/usr/bin/env bash
set -u
set -o pipefail

AGENT_HOME="${AGENT_HOME:-/home/agent-admin/agent-app}"
AGENT_PORT="${AGENT_PORT:-15034}"
AGENT_LOG_DIR="${AGENT_LOG_DIR:-/var/log/agent-app}"
AGENT_DISK_WARN_MB="${AGENT_DISK_WARN_MB:-1024}"
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

read_cmdline() {
  tr '\0' ' ' <"/proc/$1/cmdline" 2>/dev/null
}

find_agent_pid() {
  for proc_dir in /proc/[0-9]*; do
    pid="${proc_dir##*/}"
    [ -r "${proc_dir}/cmdline" ] || continue
    cmdline="$(read_cmdline "$pid")"
    [ -n "$cmdline" ] || continue
    first_arg="${cmdline%% *}"
    base_name="${first_arg##*/}"
    case "$cmdline" in
      *monitor.sh*|*timeout\ *|*bash\ -lc*|*sh\ -c*) continue ;;
    esac
    if [[ "$cmdline" =~ $PROCESS_PATTERN ]] && [[ "$base_name" == agent-app* || "$cmdline" == *agent_app.py* ]]; then
      printf '%s\n' "$pid"
      return 0
    fi
  done
}

check_process() {
  pid="$(find_agent_pid)"
  if [ -z "${pid:-}" ]; then
    fail "Checking process '${PROCESS_PATTERN}'... [FAIL]"
  fi
  printf "Checking process '%s'... [OK] (PID: %s)\n" "$PROCESS_PATTERN" "$pid"
}

check_port() {
  port_hex="$(printf '%04X' "$AGENT_PORT")"
  if awk -v port="$port_hex" '
    NR > 1 {
      split($2, local_addr, ":")
      if (toupper(local_addr[2]) == port && $4 == "0A") {
        found = 1
      }
    }
    END { exit found ? 0 : 1 }
  ' /proc/net/tcp /proc/net/tcp6 2>/dev/null; then
    printf 'Checking port %s... [OK] (LISTEN)\n' "$AGENT_PORT"
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

cpu_snapshot() {
  awk '/^cpu / {
    total = 0
    for (i = 2; i <= NF; i++) {
      total += $i
    }
    idle = $5 + $6
    printf "%s %s\n", total, idle
    exit
  }' /proc/stat
}

stat_tail() {
  stat_line="$(cat "/proc/$1/stat" 2>/dev/null)" || return 1
  printf '%s\n' "${stat_line##*) }"
}

process_ticks() {
  tail_fields="$(stat_tail "$1")" || return 1
  set -- $tail_fields
  printf '%s\n' "$(( ${12:-0} + ${13:-0} ))"
}

sample_cpu_usage() {
  sample_pid="$1"
  read -r total1 idle1 < <(cpu_snapshot)
  proc1="$(process_ticks "$sample_pid" 2>/dev/null || true)"
  sleep 1
  read -r total2 idle2 < <(cpu_snapshot)
  proc2="$(process_ticks "$sample_pid" 2>/dev/null || true)"
  cores="$(getconf _NPROCESSORS_ONLN 2>/dev/null || printf '1')"

  if [ -z "${total1:-}" ] || [ -z "${total2:-}" ] || [ -z "${proc1:-}" ] || [ -z "${proc2:-}" ]; then
    printf '0.0 0.0\n'
    return 1
  fi

  awk -v p1="$proc1" -v p2="$proc2" -v t1="$total1" -v t2="$total2" \
      -v i1="$idle1" -v i2="$idle2" -v cores="$cores" '
    BEGIN {
      total_delta = t2 - t1
      proc_delta = p2 - p1
      idle_delta = i2 - i1
      if (total_delta <= 0 || proc_delta < 0) {
        printf "0.0 0.0\n"
        exit
      }
      app_cpu = (proc_delta / total_delta) * cores * 100
      system_cpu = ((total_delta - idle_delta) / total_delta) * 100
      printf "%.1f %.1f\n", app_cpu, system_cpu
    }'
}

mem_total_kb() {
  awk '/^MemTotal:/ { print $2; exit }' /proc/meminfo
}

process_rss_kb() {
  awk '/^VmRSS:/ { print $2; found=1; exit } END { if (!found) print 0 }' "/proc/$1/status" 2>/dev/null
}

process_mem_usage() {
  rss_kb="$(process_rss_kb "$1")"
  total_kb="$(mem_total_kb)"
  awk -v rss="$rss_kb" -v total="$total_kb" 'BEGIN {
    if (total <= 0) {
      print "0.0"
    } else {
      printf "%.1f\n", (rss / total) * 100
    }
  }'
}

process_mem_mb() {
  rss_kb="$(process_rss_kb "$1")"
  awk -v rss="$rss_kb" 'BEGIN { printf "%.1f\n", rss / 1024 }'
}

mem_usage() {
  awk '
    /^MemTotal:/ { total = $2 }
    /^MemAvailable:/ { available = $2 }
    END {
      if (total <= 0) {
        print "0.0"
      } else {
        printf "%.1f\n", ((total - available) / total) * 100
      }
    }' /proc/meminfo
}

format_duration() {
  awk -v seconds="$1" 'BEGIN {
    if (seconds < 0) {
      print "unknown"
      exit
    }
    days = int(seconds / 86400)
    seconds %= 86400
    hours = int(seconds / 3600)
    seconds %= 3600
    minutes = int(seconds / 60)
    seconds = int(seconds % 60)
    if (days > 0) {
      printf "%d-%02d:%02d:%02d\n", days, hours, minutes, seconds
    } else {
      printf "%02d:%02d:%02d\n", hours, minutes, seconds
    }
  }'
}

process_elapsed() {
  tail_fields="$(stat_tail "$1")" || {
    printf 'unknown\n'
    return 1
  }
  set -- $tail_fields
  start_ticks="${20:-0}"
  uptime_seconds="$(awk '{ print $1 }' /proc/uptime)"
  ticks_per_second="$(getconf CLK_TCK 2>/dev/null || printf '100')"
  elapsed="$(awk -v uptime="$uptime_seconds" -v start="$start_ticks" -v hz="$ticks_per_second" 'BEGIN {
    printf "%.0f\n", uptime - (start / hz)
  }')"
  format_duration "$elapsed"
}

dir_usage_mb() {
  if [ -d "$1" ]; then
    du -sk "$1" 2>/dev/null | awk 'NR == 1 { printf "%.1f\n", ($1 + 0) / 1024 }'
  fi
}

agent_disk_usage_mb() {
  du -sk "$AGENT_HOME" "$AGENT_LOG_DIR" 2>/dev/null | awk '{
    total += $1
  } END {
    printf "%.1f\n", total / 1024
  }'
}

agent_disk_usage_pct() {
  awk -v used_mb="$1" -v limit_mb="$AGENT_DISK_WARN_MB" 'BEGIN {
    if (limit_mb <= 0) {
      print "0.0"
    } else {
      printf "%.1f\n", (used_mb / limit_mb) * 100
    }
  }'
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
  read -r app_cpu system_cpu < <(sample_cpu_usage "$pid")
  app_mem="$(process_mem_usage "$pid")"
  app_mem_mb="$(process_mem_mb "$pid")"
  app_elapsed="$(process_elapsed "$pid")"
  system_mem="$(mem_usage)"
  agent_home_mb="$(dir_usage_mb "$AGENT_HOME")"
  agent_log_mb="$(dir_usage_mb "$AGENT_LOG_DIR")"
  agent_disk_mb="$(agent_disk_usage_mb)"
  agent_disk_pct="$(agent_disk_usage_pct "$agent_disk_mb")"
  [ -n "${app_cpu:-}" ] || app_cpu="0.0"
  [ -n "${system_cpu:-}" ] || system_cpu="0.0"
  [ -n "${app_mem:-}" ] || app_mem="0.0"
  [ -n "${app_mem_mb:-}" ] || app_mem_mb="0.0"
  [ -n "${app_elapsed:-}" ] || app_elapsed="unknown"
  [ -n "${system_mem:-}" ] || system_mem="0.0"
  [ -n "${agent_home_mb:-}" ] || agent_home_mb="0.0"
  [ -n "${agent_log_mb:-}" ] || agent_log_mb="0.0"
  [ -n "${agent_disk_mb:-}" ] || agent_disk_mb="0.0"
  [ -n "${agent_disk_pct:-}" ] || agent_disk_pct="0.0"

  printf 'Agent CPU recent           : %.1f%%\n' "$app_cpu"
  printf 'Agent MEM RSS              : %.1f%% (RSS %.1fMB)\n' "$app_mem" "$app_mem_mb"
  printf 'Agent Runtime              : %s\n' "$app_elapsed"
  printf 'System CPU recent          : %.1f%%\n' "$system_cpu"
  printf 'System MEM used            : %.1f%%\n' "$system_mem"
  printf 'Agent Home                 : %.1fMB\n' "$agent_home_mb"
  printf 'Agent Log Dir              : %.1fMB\n' "$agent_log_mb"
  printf 'Agent Disk Budget          : %.1f%% (%.1fMB / %sMB)\n' "$agent_disk_pct" "$agent_disk_mb" "$AGENT_DISK_WARN_MB"

  gt_threshold "$app_cpu" 20 && warn "Agent CPU threshold exceeded (${app_cpu}% > 20%)"
  gt_threshold "$app_mem" 10 && warn "Agent MEM threshold exceeded (${app_mem}% > 10%)"
  gt_threshold "$agent_disk_pct" 100 && warn "Agent disk budget exceeded (${agent_disk_mb}MB > ${AGENT_DISK_WARN_MB}MB)"

  mkdir -p "$AGENT_LOG_DIR" || fail "cannot create log directory: $AGENT_LOG_DIR"
  timestamp="$(date '+%Y-%m-%d %H:%M:%S')"
  log_pid="$(find_agent_pid)"
  printf '[%s] PID:%s CPU:%.1f%% MEM:%.1f%% DISK_USED:%.1f%%\n' \
    "$timestamp" "${log_pid:-unknown}" "$app_cpu" "$app_mem" "$agent_disk_pct" >> "$LOG_FILE" || fail "cannot append log"
  printf '\n[INFO] Log appended: %s\n' "$LOG_FILE"
  printf '[INFO] Warning count: %s\n' "$warn_count"
}

main "$@"
