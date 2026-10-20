#!/usr/bin/env bash
# Backup MariaDB harian. Kredensial dibaca dari ~/.my.cnf (mode 600), bukan dari
# argumen/command line. Jadwalkan lewat cron, mis.:
#   15 2 * * * /opt/pointse/deploy/backup.sh >> /var/log/pointse-backup.log 2>&1
#
# Status terakhir ditulis sebagai JSON agar halaman Status Sistem bisa
# menampilkan keberhasilan/kegagalan backup. Arahkan BACKUP_STATUS_FILE ke
# folder yang dapat dibaca pengguna service pointse.
set -euo pipefail

TUJUAN="${BACKUP_DIR:-/home/backup}"
DB="${DB_NAME:-pointse}"
MYCNF="${MYSQL_DEFAULTS_FILE:-${HOME}/.my.cnf}"
STATUS_FILE="${BACKUP_STATUS_FILE:-${TUJUAN}/pointse-backup-status.json}"
MULAI="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
BERKAS=""

tulis_status() {
  local status="$1"
  local pesan="$2"
  local selesai ukuran nama aman tmp
  selesai="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  ukuran=0
  if [[ -n "${BERKAS}" && -f "${BERKAS}" ]]; then
    ukuran="$(stat -c%s "${BERKAS}" 2>/dev/null || echo 0)"
  fi
  nama=""
  if [[ -n "${BERKAS}" ]]; then
    nama="$(basename "${BERKAS}")"
  fi
  aman="$(printf '%s' "${pesan}" | tr -d '"\\\n\r' | cut -c1-500)"
  tmp="${STATUS_FILE}.tmp.$$"
  mkdir -p "$(dirname "${STATUS_FILE}")"
  if printf '{"status":"%s","waktu_mulai":"%s","waktu_selesai":"%s","berkas":"%s","ukuran_bytes":%s,"pesan":"%s"}\n' \
      "${status}" "${MULAI}" "${selesai}" "${nama}" "${ukuran}" "${aman}" > "${tmp}"; then
    chmod 0644 "${tmp}"
    mv -f "${tmp}" "${STATUS_FILE}"
  else
    rm -f "${tmp}"
    echo "Status backup tidak dapat ditulis: ${STATUS_FILE}" >&2
  fi
}

if [[ ! -r "${MYCNF}" ]]; then
  echo "File kredensial tidak dapat dibaca: ${MYCNF}" >&2
  tulis_status "gagal" "File kredensial tidak dapat dibaca"
  exit 1
fi

umask 077
mkdir -p "${TUJUAN}"
BERKAS="${TUJUAN}/pointse-$(date +%Y%m%d-%H%M%S).sql.gz"
tulis_status "mulai" "Backup dimulai"

if mysqldump \
  --defaults-extra-file="${MYCNF}" \
  --single-transaction \
  --quick \
  --routines \
  --events \
  --no-tablespaces \
  --databases "${DB}" | gzip -9 > "${BERKAS}"; then
  # Rotasi 14 hari.
  find "${TUJUAN}" -maxdepth 1 -type f -name 'pointse-*.sql.gz' -mtime +14 -delete
  tulis_status "sukses" "Backup selesai"
  echo "Backup selesai: ${BERKAS}"
else
  rm -f "${BERKAS}"
  tulis_status "gagal" "mysqldump atau gzip gagal"
  echo "Backup gagal" >&2
  exit 1
fi
