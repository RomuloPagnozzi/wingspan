#!/bin/sh
# Nightly snapshot of the live database, kept per weekday (7 rotating copies). Installed by `make setup`.
# Uses SQLite's backup API inside the container: a plain file copy can miss writes still in the WAL.
set -e
docker exec wingspan python -c "from wingspan.web.store import backup; backup('/data/games.db', '/data/nightly.db')"
cp /srv/wingspan/data/nightly.db "/srv/wingspan/backups/games-$(date +%a).db"
