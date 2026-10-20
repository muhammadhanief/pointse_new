#!/usr/bin/env bash
# Backup MariaDB harian. Kredensial dibaca dari ~/.my.cnf (mode 600), bukan dari
# argumen/command line. Jadwalkan lewat cron, mis.:
#   15 2 * * * /opt/pointse/deploy/backup.sh >> /var/log/pointse-backup.log 2>&1
set -euo pipefail

TUJUAN="${BACKUP_DIR:-/home/backup}"
DB="${DB_NAME:-pointse}"
MYCNF="${MYSQL_DEFAULTS_FILE:-${HOME}/.my.cnf}"

if [[ ! -r "${MYCNF}" ]]; then
  echo "File kredensial tidak dapat dibaca: ${MYCNF}" >&2
  exit 1
fi

umask 077
mkdir -p "${TUJUAN}"
BERKAS="${TUJUAN}/pointse-$(date +%Y%m%d-%H%M%S).sql.gz"

mysqldump \
  --defaults-extra-file="${MYCNF}" \
  --single-transaction \
  --quick \
  --routines \
  --events \
  --no-tablespaces \
  --databases "${DB}" | gzip -9 > "${BERKAS}"

# Rotasi 14 hari.
find "${TUJUAN}" -maxdepth 1 -type f -name 'pointse-*.sql.gz' -mtime +14 -delete

echo "Backup selesai: ${BERKAS}"
