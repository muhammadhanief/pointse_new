# Deploy backend — AlmaLinux 8 / aaPanel

Panduan ini hanya untuk backend. Frontend statis tetap dilayani cPanel dan
memanggil API lintas origin memakai `NEXT_PUBLIC_API_BASE`.

## Prasyarat server

- AlmaLinux 8, 4 core (i5), RAM 7,6 GB (sekitar 2,8 GB tersedia untuk aplikasi),
  disk HDD, swap 8 GB (lambat; jangan diandalkan untuk beban puncak).
- Python **3.11+** (Python 3.6 bawaan sistem tidak cukup), `venv`, `gcc`,
  header pengembangan, dan MariaDB **10.11**.
- systemd 239, nginx dari aaPanel, dan akses root/SSH.

## 1. Pengguna dan direktori

```bash
useradd --system --home-dir /opt/pointse --shell /sbin/nologin pointse
install -d -o pointse -g pointse /opt/pointse
install -d -o root -g pointse -m 0750 /etc/pointse
install -d -o pointse -g pointse -m 0750 /home/pointse-data
install -d -o pointse -g pointse \
  /home/pointse-data/unggahan \
  /home/pointse-data/master
```

`/opt/pointse` hanya untuk kode dan virtualenv. Berkas besar (GPKG/GeoJSON,
potongan unggahan, cache ekspor, dan geotag master) disimpan di
`/home/pointse-data` karena partisi `/home` lebih besar. Jangan menaruh data di
`/www/wwwroot` karena dapat diakses langsung dari browser.

Letakkan checkout proyek di `/opt/pointse`, lalu:

```bash
cd /opt/pointse
python3.11 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
```

## 2. Environment

```bash
cp deploy/.env.example /etc/pointse/pointse.env
chown root:pointse /etc/pointse/pointse.env
chmod 0640 /etc/pointse/pointse.env
```

Isi `AUTH_SECRET` dan kredensial DB dari pengelola rahasia. Jangan menyalin
nilai rahasia ke dokumen, commit, atau log. `ENV=production` mewajibkan
`AUTH_MODE=jwt` dan `AUTH_SECRET` minimal 32 karakter.

## 3. MariaDB 10.11

Edit konfigurasi server MariaDB (biasanya `/etc/my.cnf.d/mariadb-server.cnf`):

```ini
[mysqld]
bind-address = 127.0.0.1
skip-name-resolve
innodb_buffer_pool_size = 768M
innodb_flush_log_at_trx_commit = 2
```

`innodb_flush_log_at_trx_commit=2` dipilih karena server memakai HDD lambat;
trade-off-nya transaksi terakhir bisa hilang saat listrik mati, tetapi tidak
korup. Ukuran buffer pool 768M menyisakan RAM untuk API dan worker.

Database boleh dibuat lewat menu **Database** aaPanel. Isi nama `pointse`,
pengguna `pointse_app`, dan kata sandi dari pengelola rahasia. Cara terminal yang
setara:

```sql
CREATE DATABASE pointse CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'pointse_app'@'127.0.0.1' IDENTIFIED BY '<KATA_SANDI_DARI_PENGELOLA_RAHASIA>';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, DROP,
      REFERENCES, CREATE TEMPORARY TABLES, EXECUTE
  ON pointse.* TO 'pointse_app'@'127.0.0.1';
FLUSH PRIVILEGES;
```

aaPanel sering membuat pengguna sebagai `pointse_app@localhost`. Backend
menghubungi `127.0.0.1`, jadi bila muncul `Access denied`, tambahkan pengguna
untuk host `127.0.0.1` seperti SQL di atas atau samakan `DB_HOST` dengan host
pengguna yang dibuat aaPanel.

Jangan membuka port 3306 ke internet dan jangan memberi akses ke database lain.
Untuk backup, buat `~/.my.cnf` milik root dengan mode 600 berisi kredensial
pembaca; `backup.sh` membacanya lewat `--defaults-extra-file`.

## 4. systemd

```bash
cp deploy/pointse-api.service deploy/pointse-worker.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now pointse-api.service pointse-worker.service
systemctl status pointse-api pointse-worker
```

Jika unit lama sudah terpasang dengan port 8000, salin ulang
`deploy/pointse-api.service`, jalankan `systemctl daemon-reload`, lalu
`systemctl restart pointse-api`.

API mendengarkan `127.0.0.1:8001`; port **8000 dipakai aplikasi pilar** yang sudah
ada di server. Worker memakai `--loop` dan `fcntl.flock`.
`pointse-worker.service` mengeset `WORKER_MEM_BUDGET_MB=800`, `MemoryMax=1500M`,
dan `Nice=10`. SIGTERM menyelesaikan batch berjalan lalu job dikembalikan ke
antrean.

Pastikan port 8001 belum dipakai:

```bash
ss -lntp 'sport = :8001'
curl http://127.0.0.1:8001/health
```

Admin provinsi dapat memantau worker, antrean, RAM/CPU, dan disk dari menu
**Administrasi → Status sistem**. Endpoint `GET /sistem/status` membaca kunci
worker (flock + PID di `<WORKER_LOCK_FILE>.pid`) dan metrik `/proc`; PID baru
muncul setelah service worker dijalankan ulang dengan versi ini. Halaman hanya
membaca, tidak mengubah job atau konfigurasi.

## 5. nginx aaPanel

Gunakan `deploy/nginx-pointse-api.conf.example`. Ganti `server_name` dan path
sertifikat sesuai domain API yang dikelola aaPanel. Reverse proxy harus menunjuk
ke `http://127.0.0.1:8001`, bukan 8000. Konfigurasi hanya membuka HTTPS,
membatasi 10 request/detik per IP, meneruskan body tanpa buffer, dan memakai
timeout 600 detik untuk unggahan/ekspor besar.

## 6. Migrasi dan deploy berikutnya

```bash
cd /opt/pointse/backend
.venv/bin/python -m alembic upgrade head
```

Atau jalankan `deploy/deploy.sh` (pull, install, migrasi, restart). Pastikan
script executable: `chmod +x deploy/deploy.sh deploy/backup.sh`.

## 6a. Backfill snapshot level 6 (sekali setelah migrasi 0012)

Migrasi `0012` menambah tabel `rekap_subsls`. Run yang diproses sebelum migrasi
belum punya snapshot level 6, sehingga tabulasi progres belum bisa menghitung
target per SubSLS. Isi snapshot itu dengan memproses ulang **run A terbaru dan
run B terbaru setelahnya** dari berkas mentah yang masih tersimpan; `runs.id`
dan `runs.tanggal_data` tidak berubah.

```bash
cd /opt/pointse/backend
# 0) Cadangkan DB + folder unggahan; pemrosesan ulang menghapus hasil lama run
sudo deploy/backup.sh

# 1) Lihat rencana (tidak mengubah data); uji satu kabupaten dulu, mis. Purbalingga
sudo -u pointse .venv/bin/python scripts/backfill_rekap_subsls.py \
  --env-file /etc/pointse/pointse.env --dry-run --kabupaten 3303

# 2) Hentikan worker agar run yang dipilih pasti diproses (antrean harus kosong)
sudo systemctl stop pointse-worker
sudo -u pointse .venv/bin/python scripts/backfill_rekap_subsls.py \
  --env-file /etc/pointse/pointse.env --kabupaten 3303 --jalankan
sudo systemctl start pointse-worker

# 3) Setelah angka Purbalingga benar, ulangi tanpa --kabupaten untuk semua
```

Jangan memakai `set -a; . /etc/pointse/pointse.env` sebelum menjalankan skrip:
bash membuang tanda kutip di dalam nilai, sehingga `CORS_ORIGINS` yang berformat
JSON ditolak pydantic-settings. Pakai `--env-file` seperti contoh di atas.
Jalankan sebagai pengguna `pointse` supaya berkas hasil tidak menjadi milik root.

Jalankan di `tmux`/`nohup`: Proses A Purbalingga bisa puluhan menit. Kalau
proses terputus, run yang sedang dikerjakan berstatus `jalan` dengan hasil
separuh. Pulihkan run itu lewat `--run`, lalu lanjutkan seperti biasa:

```bash
sudo -u pointse .venv/bin/python scripts/backfill_rekap_subsls.py \
  --env-file /etc/pointse/pointse.env --run 45 --jalankan
sudo -u pointse .venv/bin/python scripts/backfill_rekap_subsls.py \
  --env-file /etc/pointse/pointse.env --kabupaten 3303 --jalankan
```

Skrip melewati kabupaten/kota yang berkas mentahnya sudah dipangkas (tidak bisa
dibangun ulang) dan melaporkannya; kabupaten seperti itu perlu unggah ulang.
Setiap run diverifikasi: total `rekap_subsls` harus sama dengan
`rekap_kabupaten` untuk dasar `tugas` dan `posisi`. Jalankan di luar jam unggah
karena satu run bisa memakan waktu dan RAM seperti pemrosesan biasa
(`WORKER_MEM_BUDGET_MB` tetap berlaku).

## 7. Backup

Tambahkan cron harian:

```cron
15 2 * * * /opt/pointse/deploy/backup.sh >> /var/log/pointse-backup.log 2>&1
```

Backup disimpan di `/home/backup` dan diputar setelah 14 hari. Script juga
menulis status JSON ke `BACKUP_STATUS_FILE` (contoh di `.env.example`:
`/home/pointse-data/backup-status.json`) agar halaman Status Sistem dapat
menampilkan hasil backup terakhir. Pastikan folder tujuan dapat ditembus
pengguna `pointse`; berkas status ditulis dengan mode 0644 tanpa kredensial.
