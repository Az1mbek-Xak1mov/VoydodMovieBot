#!/usr/bin/env bash
# Nightly Postgres backup. Production runs it from the deploy user's crontab:
#
#   20 2 * * * /opt/voydodmoviebot/scripts/backup_db.sh >> /var/backups/voydodmoviebot/backup.log 2>&1
#
# Each dump is checked with `pg_restore --list` before it is kept, so a
# truncated file never pushes out a good one; the newest $KEEP are kept. The
# dumps sit on the same disk as the database: copy them off the server too, or
# losing the server loses both.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/voydodmoviebot}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/voydodmoviebot}"
KEEP="${KEEP:-14}"

log() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*"; }

cd "$APP_DIR"
mkdir -p "$BACKUP_DIR"

# The disk is shared with other projects: never fill it.
avail_kb=$(df -Pk "$BACKUP_DIR" | awk 'NR==2 {print $4}')
if [ "$avail_kb" -lt 1048576 ]; then
    log "ERROR: less than 1 GB free in $BACKUP_DIR, not backing up"
    exit 1
fi

stamp=$(date -u +%Y%m%dT%H%M%SZ)
out="$BACKUP_DIR/voydod-$stamp.dump"
tmp="$out.partial"
trap 'rm -f "$tmp"' EXIT

# POSTGRES_USER / POSTGRES_DB come from the db container's own environment.
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$tmp"
docker compose exec -T db pg_restore --list < "$tmp" > /dev/null
mv "$tmp" "$out"

ls -1t "$BACKUP_DIR"/voydod-*.dump | tail -n +"$((KEEP + 1))" | xargs -r rm --
log "ok $(du -h "$out" | cut -f1) $out"
