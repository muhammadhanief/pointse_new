# Catatan Server

Ringkasan batas lingkungan, Oktober 2026. Dokumen ini hanya memuat angka dan
batasan; tidak memuat kredensial, cookie, token, atau alamat internal.

## Server AlmaLinux (aaPanel)

- AlmaLinux 8, **4 core (i5)**, RAM **7,6 GB** (sekitar **2,8 GB tersedia**),
  disk **HDD**, dan swap **8 GB** (lambat; bukan pengganti RAM).
- **systemd 239**, nginx aaPanel, dan akses root/SSH.
- Python **3.6** adalah versi bawaan sistem dan **tidak dipakai**; backend wajib
  Python **3.11+** di virtualenv.
- **MariaDB 10.11.10**. Setelan yang dipakai:
  - `innodb_buffer_pool_size=768M` agar RAM tersisa untuk API dan worker;
  - `innodb_flush_log_at_trx_commit=2` karena HDD lambat;
  - `bind-address=127.0.0.1`, `skip-name-resolve`;
  - satu database dan satu pengguna aplikasi yang hanya boleh dari `127.0.0.1`.
- **API**: FastAPI/uvicorn langsung (ASGI, bukan Passenger), satu worker,
  mendengarkan loopback dan diproksikan nginx. `MemoryMax=1G`.
- **Worker**: service systemd `python -m app.worker --loop`, polling **5 detik**,
  `fcntl.flock` (bukan `GET_LOCK`), heartbeat tiap **15 detik** dan tiap batch.
  `MemoryMax=1500M`, `Nice=10`, `WORKER_MEM_BUDGET_MB=800`. SIGTERM menyelesaikan
  batch berjalan lalu job dikembalikan ke antrean; `--once` tetap tersedia.
- **Path API**: mengikuti `API_PREFIX` (default kosong), bukan `/backend`.
- **CORS**: origin frontend saja, `Authorization: Bearer`, tanpa credentials.
  `ENV=production` menolak `AUTH_MODE=dev` dan mewajibkan `AUTH_SECRET`.
- **Nginx**: HTTPS saja, `client_max_body_size 512m`,
  `client_body_timeout 600s`, `proxy_read_timeout 600s`,
  `proxy_request_buffering off`, `limit_req` **10 r/s per IP**.
- **Backup**: `deploy/backup.sh` menjalankan `mysqldump` harian ke `/home/backup`,
  kredensial dari `~/.my.cnf` mode 600, rotasi **14 hari**; uji restore wajib.

## Frontend cPanel (batas tetap)

- Frontend statis tetap dilayani **cPanel shared**; tidak ada backend Python di
  akun cPanel.
- Memori akun **1 GB TOTAL** untuk frontend dan proses cPanel lain. Saat idle
  terpakai ±**366 MB**.
- Uji memori cPanel: **1010 MB** lolos; **±1110 MB** proses dimatikan tanpa pesan
  galat di log aplikasi. Batas efektif berada di antara 1010 MB dan 1110 MB.
- Frontend memanggil API lintas origin memakai `NEXT_PUBLIC_API_BASE` yang diisi
  saat build. Tidak ada cookie sesi, rewrite `/backend`, `proxy.ts`, atau rute API
  Next.js di production.

## Uji batas body request

| Uji | Hasil |
|---|---|
| Body tepat **128 MiB** (134.217.728 byte) | Lolos. |
| Body **129 MiB** (135.266.304 byte) | **413**, berupa halaman HTML dari server. |
| Body berlabel form di atas **±1 MB** | **413**. |
| Isi biner berlabel form | **403** diblokir WAF. |
| Body **`application/octet-stream`** | Lolos. |

Kesimpulan:

- Jangan memakai `FormData`/`multipart` untuk berkas. WAF memblokir isi biner
  berlabel form dengan **403**, dan body form di atas ±1 MB dengan **413**.
- Batas body per request adalah **128 MiB**. Berkas besar harus diunggah
  berpotongan, default **16 MiB** per potongan, dengan `Content-Type:
  application/octet-stream`, hash per potongan, dan resume.
- Pesan 413 dari server berupa HTML; frontend harus menampilkan pesan yang jelas,
  bukan mencoba mengurai JSON.

## SSL dan SSO

- Sertifikat SSL cPanel saat ini **kedaluwarsa dan self-signed**. Browser akan
  memperingatkan; callback SSO production tidak boleh diuji sebelum sertifikat
  diperbarui.
- Domain API baru harus memakai sertifikat valid dari aaPanel sebelum frontend
  statis diarahkan ke sana dan sebelum SSO production diaktifkan.
- Mode login **bypass tidak boleh aktif** di production, termasuk saat uji SSL.

## Dampak ke arsitektur

- Frontend statis dan backend berada di origin berbeda; semua panggilan API
  memakai `NEXT_PUBLIC_API_BASE` dan header Bearer. Jangan menambah proxy,
  rewrite, atau rute API Next.js di production.
- Worker berjalan sebagai service systemd `--loop`, dengan flock, checkpoint, dan
  heartbeat. Cron `--once` hanya alternatif manual; flock mencegah tumpang tindih.
- Perubahan batas WAF/F5/SSL berada di luar kendali aplikasi; aplikasi harus tetap
  berjalan dalam batas yang ada.
- Pantau worker dengan `python scripts/pantau_worker.py` (status job, heartbeat,
  proses, lock, dan log) agar proses yang dimatikan server cepat terlihat.
- Admin provinsi juga dapat membuka **Administrasi → Status sistem** untuk melihat
  status flock/PID worker, antrean, RAM API/worker, RAM server, CPU load, dan disk.
  Endpoint `GET /sistem/status` hanya membaca; metrik worker baru lengkap setelah
  service worker dijalankan ulang dengan versi yang menulis `<lock>.pid`.
