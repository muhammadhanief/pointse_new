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

Frontend memakai route server Next.js, jadi **bukan** static export dan tidak
diunggah sebagai `out/`.

## 2. Environment

Isi di cPanel Node.js App, lalu restart:

```dotenv
NODE_ENV=production
APP_URL=https://pointse.web.bps.go.id
KEYCLOAK_REDIRECT_URI=https://pointse.web.bps.go.id/api/auth/callback

NEXT_PUBLIC_API_BASE=/api/backend
BACKEND_URL=https://backend-pointse.feinah.web.id

AUTH_SECRET=<sama dengan backend>
AUTH_ISSUER=pointse
AUTH_AUDIENCE=pointse-backend
```

`NEXT_PUBLIC_API_BASE` dibaca saat build; `BACKEND_URL` dibaca saat runtime.
Jangan isi `BACKEND_URL` dengan `127.0.0.1` karena frontend berada di server
cPanel yang berbeda dari backend.

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
Browser -> https://pointse.web.bps.go.id/api/backend/...
Next.js -> baca cookie sesi httpOnly -> Authorization: Bearer
Next.js -> https://backend-pointse.feinah.web.id/...
```

Browser tetap satu origin, jadi tidak ada CORS dan cookie sesi tetap `httpOnly`.
Route `app/api/backend/[...jalur]/route.ts` yang menambahkan Bearer. Jangan hapus
route itu selama frontend memakai Node.js App.

## 5. Batas cPanel

- Memori akun **1 GB TOTAL**; idle ±366 MB; proses di atas ±1.110 MB dimatikan
  tanpa pesan.
- Jangan menjalankan worker atau proses latar di cPanel. Worker ada di server
  backend (`pointse-worker.service`).
- Sertifikat SSL frontend harus valid agar cookie `Secure` dan unggahan berjalan.
- Jangan menjalankan `npm run dev` di production; selalu `npm run build` lalu
  restart Node.js App.
