# Deploy frontend statis di cPanel

Backend **tidak lagi** memakai cPanel/Passenger. Backend FastAPI dijalankan di
AlmaLinux/aaPanel; lihat `deploy/README.md`. Dokumen ini hanya untuk frontend
statis dan batas akun cPanel.

> Catatan status: konfigurasi `output: "export"` dan pemindahan sesi SSO ke alur
> Bearer belum diterapkan di repo ini. Jangan mengunggah `out/` sebelum
> `npm run build` menghasilkan static export tanpa rute server Next.js.

## 1. Build

Isi URL API backend lebih dulu (harus HTTPS dan dapat diakses browser):

```bash
cd frontend
NEXT_PUBLIC_API_BASE="https://<domain-api>" npm run build
```

`NEXT_PUBLIC_API_BASE` dibaca saat build; mengubahnya setelah build tidak
berpengaruh. Jangan memakai `localhost` untuk build production.

## 2. Unggah

Unggah isi folder hasil static export (`out/`) ke document root domain frontend
di cPanel. Jangan memakai Node.js App atau Python App cPanel untuk backend.
Pastikan tidak ada `proxy.ts`, rewrites `/backend`, atau rute API Next.js di
production.

## 3. CORS dan autentikasi

- Backend hanya mengizinkan origin frontend dari `CORS_ORIGINS`.
- Frontend mengirim `Authorization: Bearer`; tidak memakai cookie atau
  `credentials: "include"`.
- Token disimpan di memori/`sessionStorage`; jangan di `localStorage`.

## 4. Batas cPanel

- Memori akun **1 GB TOTAL**; idle ±366 MB; proses di atas ±1.110 MB dimatikan
  tanpa pesan.
- Jangan menjalankan worker atau proses latar di cPanel. Worker ada di server
  backend (`pointse-worker.service`).
- Sertifikat SSL frontend harus valid agar halaman dan unggahan berjalan di
  HTTPS.
