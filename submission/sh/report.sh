#!/usr/bin/env bash
set -u
set -o pipefail

LOG_FILE="${MONITOR_LOG_FILE:-${AGENT_LOG_DIR:-/var/log/agent-app}/monitor.log}"
START_TIME="${1:-}"
END_TIME="${2:-}"

usage() {
  printf 'Usage: %s [START_TIME] [END_TIME]\n' "$0"
  printf 'Time format: YYYY-MM-DD HH:MM:SS\n'
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  usage
  exit 0
fi

if [ "$#" -gt 2 ]; then
  usage >&2
  exit 2
fi

if [ ! -r "$LOG_FILE" ]; then
  printf '[ERROR] monitor log is not readable: %s\n' "$LOG_FILE" >&2
  exit 1
fi

awk -v start="$START_TIME" -v end="$END_TIME" '
function emit_section(label, avg, max, max_ts, min, min_ts) {
  printf("[%s]\n", label)
  printf("Average : %.1f%%\n", avg)
  printf("Maximum : %.1f%% at %s\n", max, max_ts)
  printf("Minimum : %.1f%% at %s\n", min, min_ts)
}
function parse_metric(field, prefix) {
  sub(prefix, "", field)
  sub(/%$/, "", field)
  return field + 0
}
BEGIN {
  cpu_min = mem_min = disk_min = 1000000
  cpu_max = mem_max = disk_max = -1
}
$0 ~ /^\[[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}\] PID:[0-9]+ CPU:[0-9.]+% MEM:[0-9.]+% DISK_USED:[0-9.]+%$/ {
  ts = substr($0, 2, 19)
  if (start != "" && ts < start) {
    next
  }
  if (end != "" && ts > end) {
    next
  }

  cpu = parse_metric($4, "CPU:")
  mem = parse_metric($5, "MEM:")
  disk = parse_metric($6, "DISK_USED:")

  count++
  cpu_sum += cpu
  mem_sum += mem
  disk_sum += disk

  if (cpu > cpu_max) { cpu_max = cpu; cpu_max_ts = ts }
  if (cpu < cpu_min) { cpu_min = cpu; cpu_min_ts = ts }
  if (mem > mem_max) { mem_max = mem; mem_max_ts = ts }
  if (mem < mem_min) { mem_min = mem; mem_min_ts = ts }
  if (disk > disk_max) { disk_max = disk; disk_max_ts = ts }
  if (disk < disk_min) { disk_min = disk; disk_min_ts = ts }
}
END {
  if (count == 0) {
    print "[WARNING] no monitor samples matched the requested range" > "/dev/stderr"
    exit 1
  }

  print "====== STATISTICS REPORT ======"
  emit_section("CPU", cpu_sum / count, cpu_max, cpu_max_ts, cpu_min, cpu_min_ts)
  emit_section("Memory", mem_sum / count, mem_max, mem_max_ts, mem_min, mem_min_ts)
  emit_section("Disk", disk_sum / count, disk_max, disk_max_ts, disk_min, disk_min_ts)
  print "[Samples]"
  printf("Data Points: %d samples\n", count)
}' "$LOG_FILE"
