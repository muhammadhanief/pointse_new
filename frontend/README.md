# Frontend pointse

Next.js 16 (App Router, Cache Components) + React 19 + Tailwind 4. Frontend hanya
memanggil backend lewat API; tidak pernah mengakses MySQL langsung.

## Jalan

```powershell
npm install
Copy-Item .env.example .env.local   # isi kredensial SSO + AUTH_SECRET
npm run dev                         # http://localhost:3000
npm run lint
npm run build
```

Backend FastAPI dijalankan terpisah di AlmaLinux (lihat `../deploy/README.md`).
Di production cPanel, frontend berjalan sebagai Node.js App. Server cPanel
**tidak** menjangkau backend. Browser memanggil backend langsung memakai
`NEXT_PUBLIC_API_BASE=https://backend-pointse.feinah.web.id` dan header
`Authorization: Bearer`. Callback SSO menulis token ke cookie non-httpOnly
`pointse_api_token` agar dapat dibaca JavaScript; cookie `pointse_session`
tetap httpOnly untuk penjagaan halaman. Tidak ada route proxy API. Nilai
`NEXT_PUBLIC_API_BASE` dibaca saat build, jadi build ulang setelah mengubahnya.

## Login SSO BPS (T4)

Alur: browser -> `/login` -> `/api/auth/login` (state + nonce + PKCE S256) ->
`accounts.bps.go.id` -> `/api/auth/callback` -> tukar kode, verifikasi ID token,
ambil UserInfo, buat cookie sesi JWT httpOnly + cookie token API non-httpOnly
(yang dibaca browser untuk memanggil backend) -> halaman `/`.

Variabel wajib di `.env.local` (lihat `.env.example`):

| Variabel | Keterangan |
|---|---|
| `KEYCLOAK_URL` | `https://accounts.bps.go.id` |
| `KEYCLOAK_REALM` | realm aplikasi, mis. `pegawai` |
| `KEYCLOAK_CLIENT_ID` / `KEYCLOAK_CLIENT_SECRET` | dari portal SSO BPS |
| `KEYCLOAK_REDIRECT_URI` | harus **persis** sama dengan Valid Redirect URI, mis. `http://localhost:3000/api/auth/callback` |
| `AUTH_SECRET` | minimal 32 karakter; **sama** dengan `backend/.env` |
| `AUTH_ISSUER` / `AUTH_AUDIENCE` | `pointse` / `pointse-backend` |
| `APP_URL` | URL publik frontend, mis. `https://pointse.web.bps.go.id`; dipakai untuk redirect di balik cPanel |

Catatan:

- Uji lokal memakai client Alih Audio (`33000-alihaudio-4s8`) yang redirect URI-nya
  `http://localhost:3000/api/auth/callback`. Jangan pakai client/secret itu untuk
  produksi; produksi harus mendaftarkan client sendiri untuk domain `*.bps.go.id`.
- Client OIDC belum tentu mengirim atribut `org` di UserInfo/ID token. Bila tidak ada,
  frontend memakai **REST API Data Pegawai BPS** dengan service account (Client
  Credentials) untuk mencari pegawai lewat username/email/NIP. API mengembalikan
  `attributes.org`, `provinceCode`, dan `cityCode`.
- Kode wilayah kerja dipilih dari `org`; bila awalan provinsi `org` tidak cocok dengan
  `provinceCode` (mis. `org=92000` tetapi `provinceCode=33`), dipakai
  `provinceCode`+`cityCode` (mis. `3300`). `cityCode=00` berarti tingkat provinsi.
- Role sementara: `3300`/`33000` = admin provinsi `33`; `3307`/`33070` = petugas
  kabupaten/kota `3307`. Pemetaan ini perlu diuji dengan akun SSO nyata.
- Logout hanya menghapus cookie sesi aplikasi; sesi SSO di `accounts.bps.go.id`
  tetap hidup.
- Server Next.js memanggil `accounts.bps.go.id` lewat binary **`curl`** karena
  Cloudflare memblokir fingerprint TLS Node/undici (HTTP 403 "Just a moment").
  `curl` tersedia di Windows 10+ dan hampir semua Linux. Bila `curl` tidak ada,
  kode jatuh ke `fetch` bawaan, tetapi Cloudflare bisa menolaknya.

## Kerangka dashboard (T5)

Route group `app/(dashboard)/` memakai satu layout: sidebar desktop, menu
off-canvas di layar kecil, header wilayah kerja, dan kartu pengguna. Menu
dibatasi per peran; `Master geotag` dan `Status sistem` hanya tampil untuk admin
provinsi.

| Route | Isi |
|---|---|
| `/` | Ringkasan, alur kerja, dan status data kosong |
| `/proses` | Redirect ke `/proses/identifikasi` |
| `/proses/identifikasi` | 1. Identifikasi Titik: unggah peta |
| `/proses/pengecekan` | 2. Pengecekan Titik: pilih sumber dan unggah GPKG edit |
| `/rekap` | Tabel contoh yang diberi label data tiruan |
| `/ekspor` | Unduhan per job dan rekap CSV |
| `/master-geotag` | Khusus admin provinsi: unggah dan daftar versi |
| `/sistem` | Khusus admin provinsi: worker, antrean, RAM/CPU, dan disk |

Token warna, tipografi, dan focus ring ada di `app/globals.css`. Halaman
memakai `PageHeader`, `Panel`, `EmptyState`, dan `TautanAksi` dari
`components/dashboard/ui.tsx` agar bentuknya konsisten.

## Unggah dan status job (T6)

- Halaman 1. Identifikasi Titik dan 2. Pengecekan Titik memanggil
  `POST {NEXT_PUBLIC_API_BASE}/runs` lewat `urlApi()` langsung dari browser.
  Nilainya URL FastAPI absolut, mis. `https://backend-pointse.feinah.web.id`
  di production atau `http://localhost:8000` di lokal. Request membawa
  `Authorization: Bearer` dari `lib/api/token.ts`.
- Berkas dikirim berpotongan: `POST /unggahan/mulai`, lalu
  `POST /unggahan/{id}/potongan/{n}` dengan body mentah
  (`Content-Type: application/octet-stream`) dan header `X-Sha256`, lalu
  `POST /unggahan/{id}/selesai`, dan akhirnya `POST /runs` atau
  `/geotag-master` dengan `unggahan_id`. Semua lewat `urlApi()` yang menambahkan
  `NEXT_PUBLIC_API_BASE`. Berkas tidak dibungkus `FormData`; WAF menolak biner
  berlabel multipart.
- Unggahan memakai `XMLHttpRequest` per potongan agar progres byte bisa
  ditampilkan. Maksimal 2 potongan dikirim bersamaan (atur lewat
  `NEXT_PUBLIC_UNGGAH_PARALEL`, 1-4). Ada tombol batal, batas waktu 30 menit
  per potongan, peringatan sebelum menutup halaman, dan pesan khusus untuk
  403, 413, 409, 422, 401, 502, serta koneksi putus.
- Sesi unggahan disimpan di `localStorage` berdasarkan nama, ukuran, dan
  `lastModified` berkas. Setelah koneksi putus atau halaman dimuat ulang,
  pilih berkas yang sama; frontend memanggil `GET {NEXT_PUBLIC_API_BASE}/unggahan/{id}`
  dan melanjutkan potongan yang belum diterima. Potongan yang sama aman
  dikirim ulang (idempoten), dan galat jaringan/429/5xx dicoba ulang dengan
  backoff.
- Form 2. Pengecekan Titik memilih hasil 1. Identifikasi Titik dari
  `GET /runs?tipe=A&status=sukses` dan mengirim `sumber_run_a_id`. Backend
  memvalidasi tipe, status, dan wilayah run sumber sebelum menyalin petanya.
  Jalankan ulang backend setelah perubahan `api.py` agar parameter ini aktif.
- Nomor job di layar dihitung per (`kdprov`, `kdkab`, `tipe`), bukan memakai id
  global. Master geotag diberi nomor versi per kabupaten/kota. Dropdown
  kabupaten/kota memakai kode BPS Provinsi Jawa Tengah.
- Riwayat job memanggil `GET /runs?limit=20` setiap 5 detik. Status `jalan`
  ditampilkan sebagai "Diproses", heartbeat ditampilkan, dan pesan
  "proses terhenti" dari worker ditandai terpisah.
- Master geotag memanggil `POST /geotag-master` dan `GET /geotag-master`.
  1. Identifikasi Titik memakai versi terbaru per kabupaten/kota.
- Nama berkas unduhan diawali kode wilayah 4 digit, misalnya
  `3307_hasil_identifikasi_titik_ke1.gpkg`. Setiap tombol unduh memunculkan
  notifikasi di halaman, termasuk status saat rekap CSV sedang disiapkan.

## Bypass login lokal

Untuk pengujian lokal tanpa SSO, set di `.env.local`:

```env
AUTH_BYPASS_ENABLED=true
```

Halaman login menampilkan tombol masuk sebagai admin Provinsi 33 dan dropdown
kabupaten/kota Jawa Tengah untuk masuk sebagai petugas.

Untuk pengujian di production, wajib tambahkan kode rahasia:

```env
AUTH_BYPASS_ENABLED=true
AUTH_BYPASS_SECRET=isi-dengan-rahasia-panjang-acak
```

Di production, form bypass meminta kode tersebut. Tanpa `AUTH_BYPASS_SECRET`,
route bypass membalas 404 dan form tidak ditampilkan. Matikan
`AUTH_BYPASS_ENABLED` segera setelah pengujian selesai. Jangan menaruh nilai
secret di repository atau membagikannya ke pengguna umum.

## Struktur auth

- `lib/auth/oidc.ts` — discovery, PKCE, tukar kode, verifikasi ID token, UserInfo,
  fallback API Pegawai.
- `lib/auth/jwt.ts` — token sesi HS256 + state OIDC.
- `lib/auth/session.ts` - cookie sesi httpOnly + cookie token API non-httpOnly,
  `wajibSesi()`.
- `app/api/auth/login|callback|logout|session/route.ts` - route OIDC.
- `NEXT_PUBLIC_API_BASE` - URL backend absolut; browser memanggilnya langsung
  dan mengirim Bearer dari `lib/api/token.ts` (cookie/memori/`sessionStorage`).
- Tidak ada `app/api/backend`; server cPanel tidak boleh menjadi perantara API.
- `proxy.ts` — redirect halaman terlindungi ke `/login` (Next.js 16 memakai Proxy,
  bukan Middleware).
