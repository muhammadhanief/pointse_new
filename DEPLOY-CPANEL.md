# Deploy frontend Node.js di cPanel

Backend **tidak** memakai cPanel/Passenger. Backend FastAPI dijalankan di
AlmaLinux/aaPanel; lihat `deploy/README.md`. Dokumen ini hanya untuk frontend
Next.js sebagai **Node.js App** cPanel.

## 1. Aplikasi cPanel

Di **Setup Node.js App**:

| Isi | Nilai |
|---|---|
| Application root | `/home/<user>/pointse` |
| Application URL | `https://pointse.web.bps.go.id` |
| Application startup file | `server.js` |
| Node.js version | 22 |

Frontend memakai route server Next.js untuk halaman dan callback SSO, jadi
**bukan** static export dan tidak diunggah sebagai `out/`. Panggilan API tetap
dilakukan browser langsung ke backend, bukan oleh server cPanel.

## 2. Environment

Isi di cPanel Node.js App, lalu restart:

```dotenv
NODE_ENV=production
APP_URL=https://pointse.web.bps.go.id
KEYCLOAK_REDIRECT_URI=https://pointse.web.bps.go.id/api/auth/callback

NEXT_PUBLIC_API_BASE=https://backend-pointse.feinah.web.id

AUTH_SECRET=<sama dengan backend>
AUTH_ISSUER=pointse
AUTH_AUDIENCE=pointse-backend
```

`NEXT_PUBLIC_API_BASE` dibaca saat **build**, bukan runtime. Setelah mengubah
nilainya, jalankan ulang `npm run build`, lalu restart aplikasi. Browser
memanggil backend langsung, jadi server cPanel tidak perlu akses ke domain luar.
Tidak ada `BACKEND_URL` dan tidak ada route proxy API.

## 3. Build dan restart

Dari terminal cPanel, di application root:

```bash
npm install
npm run build
```

Lalu **Restart** aplikasi. Startup file `server.js` menjalankan Next.js hasil
build.

## 4. Alur request

```text
Browser -> https://backend-pointse.feinah.web.id/...
           Authorization: Bearer <token dari cookie pointse_api_token>
```

Request API terjadi **client-side** (langsung dari browser), bukan dari server
cPanel. Callback SSO tetap di server Next.js dan menulis token ke cookie
non-httpOnly `pointse_api_token`; cookie `pointse_session` tetap httpOnly untuk
penjaga halaman. Backend hanya menerima Bearer, tanpa cookie/credentials.

Backend wajib mengizinkan origin frontend di `CORS_ORIGINS` dan mengizinkan
header `Authorization`, `Content-Type`, `Accept`, dan `X-SHA256`. Pengaturan ini
sudah ada di `backend/app/main.py`.

## 5. Batas cPanel

- Memori akun **1 GB TOTAL**; idle ±366 MB; proses di atas ±1.110 MB dimatikan
  tanpa pesan.
- Jangan menjalankan worker atau proses latar di cPanel. Worker ada di server
  backend (`pointse-worker.service`).
- Sertifikat SSL frontend harus valid agar cookie `Secure` dan unggahan berjalan.
- Jangan menjalankan `npm run dev` di production; selalu `npm run build` lalu
  restart Node.js App.
