#!/usr/bin/env bash
# WP-39: nightly MySQL dump + media snapshot. Run via cron on the app server.
# Restore: infra/scripts/restore.sh <dump.sql.gz>
set -euo pipefail

BACKUP_ROOT="${BACKUP_ROOT:-/srv/joybuy/backups}"
STAMP="$(date +%Y%m%d-%H%M%S)"
KEEP_DAYS="${KEEP_DAYS:-14}"

mkdir -p "$BACKUP_ROOT"

# MySQL logical backup (all Joybuy schemas; binlog enables PITR between dumps).
docker exec "$(basename "$PWD")-mysql-1" sh -c \
  'exec mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --routines --triggers joybuy' \
  | gzip > "$BACKUP_ROOT/joybuy-db-$STAMP.sql.gz"

# Media snapshot (rsync hard-link incrementals would reduce cost at scale).
tar -czf "$BACKUP_ROOT/joybuy-media-$STAMP.tar.gz" -C /srv/joybuy/data media 2>/dev/null || true

# Retention.
find "$BACKUP_ROOT" -name 'joybuy-*' -mtime +"$KEEP_DAYS" -delete

echo "Backup complete: $BACKUP_ROOT/joybuy-{db,media}-$STAMP.*"
