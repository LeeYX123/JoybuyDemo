#!/usr/bin/env bash
# WP-39: restore a database dump into a running MySQL container.
set -euo pipefail
DUMP="${1:?usage: restore.sh <dump.sql.gz>}"
docker exec -i "$(basename "$PWD")-mysql-1" sh -c \
  'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" joybuy' < "$DUMP"
echo "Restore complete. Verify: health endpoint + core E2E."
