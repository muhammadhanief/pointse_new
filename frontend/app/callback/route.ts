// Callback SSO BPS didaftarkan di portal sebagai `/callback` (bukan
// `/api/auth/callback`). Handler-nya sama dengan route API agar redirect URI
// lokal dan produksi cocok persis dengan Detail Client.
export { GET } from "../api/auth/callback/route";
