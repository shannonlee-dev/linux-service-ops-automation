#!/usr/bin/env bash
set -u
set -o pipefail

LOG_DIR="${AGENT_LOG_DIR:-/var/log/agent-app}"
ARCHIVE_DIR="${MONITOR_ARCHIVE_DIR:-/var/log/monitor/agent-app/archive}"
COMPRESS_DAYS="${MONITOR_COMPRESS_DAYS:-7}"
DELETE_DAYS="${MONITOR_DELETE_DAYS:-30}"

warn() {
  printf '[WARNING] %s\n' "$1"
}

info() {
  printf '[INFO] %s\n' "$1"
}

if [ ! -d "$LOG_DIR" ]; then
  warn "log directory does not exist: $LOG_DIR"
  exit 0
fi

if [ ! -r "$LOG_DIR" ]; then
  warn "log directory is not readable: $LOG_DIR"
  exit 0
fi

if ! mkdir -p "$ARCHIVE_DIR" 2>/dev/null; then
  warn "archive directory cannot be created: $ARCHIVE_DIR"
  exit 0
fi

if [ ! -w "$ARCHIVE_DIR" ]; then
  warn "archive directory is not writable: $ARCHIVE_DIR"
  exit 0
fi

compressed_count=0
while IFS= read -r -d '' log_file; do
  base_name="$(basename "$log_file")"
  archive_file="$ARCHIVE_DIR/$base_name.gz"

  if gzip -c "$log_file" > "$archive_file.tmp" 2>/dev/null; then
    mv "$archive_file.tmp" "$archive_file"
    rm -f "$log_file"
    compressed_count=$((compressed_count + 1))
    info "archived $base_name"
  else
    rm -f "$archive_file.tmp"
    warn "failed to archive $log_file"
  fi
done < <(find "$LOG_DIR" -maxdepth 1 -type f -name '*.log' -mtime +"$((COMPRESS_DAYS - 1))" -print0 2>/dev/null)

deleted_count=0
while IFS= read -r -d '' archive_file; do
  if rm -f "$archive_file"; then
    deleted_count=$((deleted_count + 1))
    info "deleted $(basename "$archive_file")"
  else
    warn "failed to delete $archive_file"
  fi
done < <(find "$ARCHIVE_DIR" -maxdepth 1 -type f -name '*.gz' -mtime +"$((DELETE_DAYS - 1))" -print0 2>/dev/null)

if [ "$compressed_count" -eq 0 ]; then
  info "no log files older than ${COMPRESS_DAYS} days"
fi
if [ "$deleted_count" -eq 0 ]; then
  info "no archives older than ${DELETE_DAYS} days"
fi
