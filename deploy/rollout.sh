#!/bin/sh
# Run as root with a release archive prepared from backend sources and frontend/dist.
set -eu
umask 022

archive=${1:?expected release archive}
app=/opt/neartalk
db=/var/lib/neartalk/neartalk.sqlite3
python=$app/backend/.venv/bin/python
install -d -m 700 /var/backups/neartalk
backup=$(mktemp -d /var/backups/neartalk/release.XXXXXXXX)
stage=$(mktemp -d "$app/staging.XXXXXXXX")
trap 'test ! -d "$stage" || rmdir "$stage" 2>/dev/null || true' EXIT

tar -xzf "$archive" --no-same-owner --no-same-permissions -C "$stage"
find "$stage" -type d -exec chmod 755 {} +
find "$stage" -type f -exec chmod 644 {} +
test -f "$stage/frontend/dist/index.html"
"$python" -m pip --isolated install --index-url https://pypi.org/simple -r "$stage/backend/requirements.txt"
(cd "$stage/backend" && PYTHONDONTWRITEBYTECODE=1 "$python" -m pytest -q -p no:cacheprovider)

"$python" - "$db" "$backup/neartalk.sqlite3" <<'PY'
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

source, target = sys.argv[1:]
with closing(sqlite3.connect(Path(source).as_uri() + "?mode=ro", uri=True)) as live:
    with closing(sqlite3.connect(target)) as snapshot:
        live.backup(snapshot)
        if snapshot.execute("PRAGMA quick_check").fetchone() != ("ok",):
            raise SystemExit("SQLite backup verification failed")
PY

# Keep previous hashed assets available to currently open browser tabs.
cp -an "$app/frontend/dist/assets/." "$stage/frontend/dist/assets/"

restore_on_failure() {
    status=$?
    if [ "$status" -ne 0 ]; then
        echo "Release failed; restoring previous code and frontend." >&2
        if [ -d "$backup/app" ]; then
            if [ -d "$app/backend/app" ]; then mv "$app/backend/app" "$backup/failed-app"; fi
            mv "$backup/app" "$app/backend/app"
        fi
        if [ -d "$backup/dist" ]; then
            if [ -d "$app/frontend/dist" ]; then mv "$app/frontend/dist" "$backup/failed-dist"; fi
            mv "$backup/dist" "$app/frontend/dist"
        fi
        systemctl restart neartalk
    fi
    echo "Backup: $backup"
}
trap restore_on_failure EXIT

mv "$app/backend/app" "$backup/app"
mv "$stage/backend/app" "$app/backend/app"
mv "$app/frontend/dist" "$backup/dist"
mv "$stage/frontend/dist" "$app/frontend/dist"
systemctl restart neartalk
for attempt in 1 2 3 4 5 6 7 8 9 10; do
    if curl -fsS http://127.0.0.1:8010/api/health >/dev/null; then break; fi
    sleep 1
done
curl -fsS http://127.0.0.1:8010/api/health
curl -fsS 'http://127.0.0.1:8010/api/regions/topics?lat=22.34&lon=114.17&scope=5' -o /dev/null
systemctl is-active neartalk
trap - EXIT
rm -f "$stage/backend/requirements.txt" "$stage/backend/tests/"test_*.py
find "$stage/backend" -depth -type d -empty -delete
rmdir "$stage/frontend" 2>/dev/null || true
rmdir "$stage" 2>/dev/null || true
echo "Backup: $backup"
