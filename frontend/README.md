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

Backend FastAPI dijalankan terpisah di `http://127.0.0.1:8000`
(`BACKEND_URL` di `.env.local`).

## Login SSO BPS (T4)

Alur: browser -> `/login` -> `/api/auth/login` (state + nonce + PKCE S256) ->
`accounts.bps.go.id` -> `/api/auth/callback` -> tukar kode, verifikasi ID token,
ambil UserInfo, buat cookie sesi JWT httpOnly -> halaman `/`.

Variabel wajib di `.env.local` (lihat `.env.example`):

| Variabel | Keterangan |
|---|---|
| `KEYCLOAK_URL` | `https://accounts.bps.go.id` |
| `KEYCLOAK_REALM` | realm aplikasi, mis. `pegawai` |
| `KEYCLOAK_CLIENT_ID` / `KEYCLOAK_CLIENT_SECRET` | dari portal SSO BPS |
| `KEYCLOAK_REDIRECT_URI` | harus **persis** sama dengan Valid Redirect URI, mis. `http://localhost:3000/api/auth/callback` |
| `AUTH_SECRET` | minimal 32 karakter; **sama** dengan `backend/.env` |
| `AUTH_ISSUER` / `AUTH_AUDIENCE` | `pointse` / `pointse-backend` |
| `BACKEND_URL` | `http://127.0.0.1:8000` |

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

## Struktur auth

- `lib/auth/oidc.ts` — discovery, PKCE, tukar kode, verifikasi ID token, UserInfo,
  fallback API Pegawai.
- `lib/auth/jwt.ts` — token sesi HS256 + state OIDC.
- `lib/auth/session.ts` — cookie httpOnly, `wajibSesi()`.
- `app/api/auth/login|callback|logout|session/route.ts` — route OIDC.
- `app/api/backend/[...jalur]/route.ts` — BFF: meneruskan request ke FastAPI dengan
  Bearer token sesi.
- `proxy.ts` — redirect halaman terlindungi ke `/login` (Next.js 16 memakai Proxy,
  bukan Middleware).
