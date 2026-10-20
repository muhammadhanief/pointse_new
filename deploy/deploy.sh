#!/usr/bin/env bash
# Deploy backend di server AlmaLinux/aaPanel. Jalankan sebagai root atau dengan
# sudo. Tidak menyimpan kredensial; nilai rahasia ada di /etc/pointse/pointse.env.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/pointse}"
ENV_FILE="${ENV_FILE:-/etc/pointse/pointse.env}"
VENV="${APP_DIR}/backend/.venv"
PY="${VENV}/bin/python"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "File environment tidak ditemukan: ${ENV_FILE}" >&2
  echo "Salin deploy/.env.example ke sana dan isi nilainya lebih dulu." >&2
  exit 1
fi

cd "${APP_DIR}"

if [[ -d .git ]]; then
  git pull --ff-only
fi

if [[ ! -x "${PY}" ]]; then
  python3 -m venv "${VENV}"
fi

"${PY}" -m pip install --upgrade pip
"${PY}" -m pip install -r backend/requirements.txt

cd "${APP_DIR}/backend"
"${PY}" -m alembic upgrade head

systemctl daemon-reload
systemctl enable pointse-api.service pointse-worker.service
systemctl restart pointse-api.service pointse-worker.service

echo "Deploy selesai. Periksa: systemctl status pointse-api pointse-worker"
echo "Log: journalctl -u pointse-api -u pointse-worker -f"
