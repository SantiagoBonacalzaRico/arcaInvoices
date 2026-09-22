#!/usr/bin/env bash
# Nightly consistent backup of the app's SQLite DB to S3.
# Installed at /opt/arcainvoices/backup-db.sh and run by the
# arcainvoices-backup.timer systemd timer (see deploy/ for the unit files).
#
# The DB is a few MB; objects expire after 30 days (S3 lifecycle rule), so the
# ongoing cost is a few cents/month — negligible against the $15 budget.
set -euo pipefail

REGION="sa-east-1"
BUCKET="arcainvoices-db-backups-879366471813"
DATA="/opt/arcainvoices/data"
TS="$(date -u +%Y%m%d-%H%M%S)"

APP="$(docker ps --format '{{.Names}}' | grep -m1 app)"
if [ -z "$APP" ]; then
  echo "app container not running; skipping backup" >&2
  exit 0
fi

# WAL-safe online backup via the container's stdlib sqlite3 (consistent snapshot
# even while the app is writing). Output lands on the shared /app/data volume.
docker exec "$APP" python -c "import sqlite3; s=sqlite3.connect('/app/data/app.db'); d=sqlite3.connect('/app/data/backup-$TS.db'); s.backup(d); d.close(); s.close()"

gzip -f "$DATA/backup-$TS.db"
aws s3 cp "$DATA/backup-$TS.db.gz" "s3://$BUCKET/backups/app-$TS.db.gz" \
  --region "$REGION" --only-show-errors
rm -f "$DATA/backup-$TS.db.gz"
logger -t arcainvoices-backup "uploaded app-$TS.db.gz to s3://$BUCKET"
echo "backed up app-$TS.db.gz"
