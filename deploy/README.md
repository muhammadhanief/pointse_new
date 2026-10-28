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

### 4a. Menambah worker kedua

Satu worker memproses satu job sekaligus, jadi antrean panjang (mis. 7
kabupaten/kota) selesai berurutan. Worker tambahan dijalankan sebagai **proses
terpisah** lewat unit template `pointse-worker@.service`; jangan memakai
`MAX_WORKERS` karena nilai itu hanya untuk worker in-process
(`WORKER_ENABLED=true`) dan `--loop` mengabaikannya.

```bash
# 1) Pastikan RAM masih cukup: butuh ~700 MB x jumlah worker
free -m

# 2) Pasang unit template lalu nyalakan instance tambahan (worker #1 tetap
#    pointse-worker.service)
cp deploy/pointse-worker@.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now pointse-worker@2.service
systemctl status 'pointse-worker*'
```

Yang perlu diketahui sebelum menyalakan worker kedua:

- **Kunci terpisah wajib.** Unit template memakai
  `WORKER_LOCK_FILE=/run/pointse-%i/worker.lock`. Tanpa itu instance kedua
  langsung keluar (`worker --loop lain sedang berjalan`).
- **Anggaran memori dijumlahkan.** Instance @2 memakai
  `WORKER_MEM_BUDGET_MB=700` dan `MemoryMax=1100M`. Total dua worker ±1,4 GB
  lunak / 2,2 GB keras, ditambah API (1 GB) dan MariaDB (±0,9 GB). Kalau
  `free -m` menunjukkan tersedia di bawah ±1,5 GB, jangan menambah worker —
  turunkan anggaran atau biarkan satu worker.
- **Antrean tetap adil dan berurutan per kabupaten/kota.** Klaim job memakai
  `FOR UPDATE SKIP LOCKED` dan melewati job dengan (provinsi, kabupaten, tipe)
  yang sedang dikerjakan, jadi dua worker tidak pernah memproses dua job
  kabupaten/tipe yang sama.
- **Peta tetap diproses sebelum titik per kabupaten/kota.** Job B baru bisa
  diunggah setelah run A sukses, dan peta A disalin ke folder job B, jadi
  urutan itu tidak berubah walau ada dua worker.
- **CPU dan disk berbagi.** Di server 4 core, dua job memakai dua core dan
  menyisakan dua core untuk API/MariaDB. Karena penyimpanan HDD, kenaikan
  kecepatan biasanya ±1,3-1,6x, bukan 2x; lonjakan `iowait` terlihat di
  `iostat -x 5` atau `vmstat 5`.
- **Status sistem** hanya membaca kunci worker utama (PID di
  `<WORKER_LOCK_FILE>.pid`). Worker kedua tetap terlihat di daftar heartbeat dan
  kolom "worker aktif" bertambah otomatis.

Menghentikan worker tambahan:

```bash
systemctl disable --now pointse-worker@2.service
```

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

# 2) Antrekan ke worker (worker tetap hidup; tidak perlu stop/start)
sudo -u pointse .venv/bin/python scripts/backfill_rekap_subsls.py \
  --env-file /etc/pointse/pointse.env --kabupaten 3303 --antrekan

# 3) Setelah angka Purbalingga benar, ulangi tanpa --kabupaten untuk semua
```

Jangan memakai `set -a; . /etc/pointse/pointse.env` sebelum menjalankan skrip:
bash membuang tanda kutip di dalam nilai, sehingga `CORS_ORIGINS` yang berformat
JSON ditolak pydantic-settings. Pakai `--env-file` seperti contoh di atas.
Jalankan sebagai pengguna `pointse` supaya berkas hasil tidak menjadi milik root.

Cara yang disarankan adalah `--antrekan`: run dikembalikan ke antrean, lalu
service worker yang memproses (progress terlihat di halaman Job), sehingga tidak
perlu menunggu di terminal dan worker tidak perlu dimatikan:

```bash
sudo -u pointse .venv/bin/python scripts/backfill_rekap_subsls.py \
  --env-file /etc/pointse/pointse.env --run 45,49 --antrekan
```

Worker memproses menurut id run dan mengisi snapshot level 6 sendiri saat
sukses. `--jalankan` hanya untuk memproses langsung di depan layar; mode itu
memegang kunci worker sehingga service harus berhenti dulu (pakai `tmux`/`nohup`
karena bisa puluhan menit).

### 6b. Backfill semua kabupaten/kota (dua gelombang)

Untuk seluruh wilayah, antrekan **semua A terakhir dulu**, baru setelah selesai
antrekan **semua B terakhir**. Run yang snapshot level 6-nya sudah ada otomatis
dilewati (kecuali `--paksa`).

```bash
# Gelombang 1: semua A terakhir (worker tetap hidup)
sudo -u pointse .venv/bin/python scripts/backfill_rekap_subsls.py \
  --env-file /etc/pointse/pointse.env --dry-run --tipe A
sudo -u pointse .venv/bin/python scripts/backfill_rekap_subsls.py \
  --env-file /etc/pointse/pointse.env --tipe A --antrekan

# Gelombang 2: semua B terakhir, otomatis menunggu gelombang A selesai
sudo -u pointse nohup .venv/bin/python scripts/backfill_rekap_subsls.py \
  --env-file /etc/pointse/pointse.env --tipe B --antrekan --tunggu \
  > /home/pointse-data/backfill-b.log 2>&1 &

# Periksa hasil (baca saja, kapan saja)
sudo -u pointse .venv/bin/python scripts/backfill_rekap_subsls.py \
  --env-file /etc/pointse/pointse.env --periksa
```

`--tunggu` memeriksa antrean tiap `--interval-tunggu` detik (default 30) dan
baru mengantrekan B setelah tidak ada job `menunggu`/`jalan`. Aman ditinggal:
worker tidak perlu dihentikan, dan `--antrekan` menolak run yang sedang
dikerjakan (heartbeat baru) supaya tidak terjadi pemrosesan ganda.

`--periksa` menampilkan run **terakhir** per tipe beserta statusnya. Run yang
sedang menunggu/diproses wajar masih `snapshot=0`; laporan baru bermakna setelah
antrean kosong. Baris `B#49 sebelum A#112: perlu B baru` berarti B itu dibuat
sebelum target A terbaru sehingga harus diunggah ulang, bukan dihitung mundur.

Kabupaten/kota tanpa run A sukses atau yang berkas mentahnya sudah dipangkas
dilewati dan dilaporkan; yang seperti itu perlu unggah ulang. Bisa juga tanpa
`--tipe` untuk mengantrekan A dan B sekaligus per kabupaten, tetapi urutan
pemrosesan mengikuti id run, bukan urutan gelombang.

Skrip melewati kabupaten/kota yang berkas mentahnya sudah dipangkas (tidak bisa
dibangun ulang) dan melaporkannya; kabupaten seperti itu perlu unggah ulang.
Setiap run diverifikasi: total `rekap_subsls` harus sama dengan
`rekap_kabupaten` untuk dasar `tugas` dan `posisi`. Jalankan di luar jam unggah
karena satu run bisa memakan waktu dan RAM seperti pemrosesan biasa
(`WORKER_MEM_BUDGET_MB` tetap berlaku).

## 6c. Capaian per `assignment_id` (setelah migrasi 0013)

Migrasi `0013` menambah tabel `rekap_target`. Tabel itu menyimpan capaian B
terhadap target A yang dicocokkan lewat `assignment_id`, bukan lewat jumlah
titik per `level_6_full_code`. Tujuannya: operator yang mengubah
`level_6_full_code` di berkas B tidak lagi membuat kode asal "kehilangan" titik,
sehingga rekap tidak menampilkan sisa palsu (kasus Batang 3325: 8 titik).

Setelah `alembic upgrade head` tidak ada backfill: job B lama sudah kehilangan
titik `flag_repair=0` di `titik_hasil`, jadi pencocokan per `assignment_id` tidak
bisa dibangun ulang. Job lama tetap memakai hitungan lama (angka historis
stabil); angka baru muncul untuk **job B yang diproses ulang**. Untuk
kabupaten/kota yang angkanya masih janggal, unggah ulang berkas B terbaru
(berkas mentah masih tersimpan), bukan mengunggah ulang berkas A.

Yang dihitung untuk setiap kode level 6 milik A:

- `target`: titik A ber-`flag_repair=1` pada kode itu (kode penugasan, dari A);
- `belum`: target yang tidak ada di B **atau** masih `flag_repair=1` di B;
- `hilang`: target yang tidak ada di B sama sekali (penanda "B tidak lengkap");
- `regresi`: titik yang bukan target A tapi `flag_repair=1` di B (kerusakan baru,
  mis. titik yang tadinya benar menjadi salah). Ini yang membuat capaian masih
  bisa **turun**.

Dasar `posisi` memakai SubSLS hasil join peta B (posisi sekarang), dasar `tugas`
memakai kode penugasan A.

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
