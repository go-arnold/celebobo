#!/bin/sh
# Nightly pg_dump of the local database; keeps the last BACKUP_DAYS dumps.
#   one now: ./deploy/prod.sh exec backup sh /usr/local/bin/backup.sh once
set -eu

dump() {
    target="/backups/celebobo-$(date -u +%Y-%m-%dT%H%M).dump"
    pg_dump --format=custom --compress=6 --file="$target.part" && mv "$target.part" "$target"
    find /backups -name 'celebobo-*.dump' -mtime +"$BACKUP_DAYS" -delete
    echo "backup: $target ($(du -h "$target" | cut -f1))"
}

if [ "${1:-}" = "once" ]; then
    dump
    exit 0
fi

trap exit TERM
while :; do
    # 03:00 Bukavu time (01:00 UTC), when the shop is quiet
    now=$(date -u +%s)
    next=$(( (now / 86400) * 86400 + 3600 ))
    [ "$next" -le "$now" ] && next=$((next + 86400))
    sleep $((next - now)) & wait $!
    dump || echo "backup: failed" >&2
done
