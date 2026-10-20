import { istilahProses } from "@/lib/istilah";
import { ambilToken } from "@/lib/api/token";

//: URL backend diisi saat build. Relatif (mis. /api/backend) berarti lewat
//: proxy Next.js; kosong juga dianggap satu origin.
const API_BASE = (process.env.NEXT_PUBLIC_API_BASE ?? "").trim().replace(/\/+$/, "");

/** True bila API dipanggil ke origin yang sama (cookie sesi ikut dikirim). */
export const API_SATU_ASAL = !/^https?:\/\//i.test(API_BASE);

export function urlApi(jalur: string): string {
  const bersih = jalur.startsWith("/") ? jalur : `/${jalur}`;
  return API_BASE ? `${API_BASE}${bersih}` : bersih;
}

function pasangBearer(headers: Headers): void {
  const token = ambilToken();
  if (token && !headers.has("authorization")) {
    headers.set("authorization", `Bearer ${token}`);
  }
}

export class KesalahanApi extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "KesalahanApi";
    this.status = status;
    this.detail = detail;
  }
}

export function detailKesalahan(data: unknown): string | null {
  if (!data || typeof data !== "object" || !("detail" in data)) {
    return null;
  }

  const detail = (data as { detail: unknown }).detail;
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    const bagian = detail.map((satu) => {
      if (satu && typeof satu === "object" && "msg" in satu) {
        return String((satu as { msg: unknown }).msg);
      }
      return String(satu);
    });
    return bagian.filter(Boolean).join("; ") || null;
  }
  return null;
}

async function bacaDetail(resp: Response): Promise<string> {
  const tipe = resp.headers.get("content-type") ?? "";
  if (tipe.includes("application/json")) {
    const data = await resp.json().catch(() => null);
    return detailKesalahan(data) ?? `HTTP ${resp.status}`;
  }

  const teks = await resp.text().catch(() => "");
  return teks.trim().slice(0, 300) || `HTTP ${resp.status}`;
}

function namaBerkas(disposisi: string, cadangan: string): string {
  const utf8 = /filename\*=UTF-8''([^;]+)/i.exec(disposisi);
  if (utf8?.[1]) {
    try {
      return decodeURIComponent(utf8[1].trim());
    } catch {
      return cadangan;
    }
  }
  const biasa = /filename="([^"]+)"/i.exec(disposisi);
  return biasa?.[1]?.trim() || cadangan;
}

/**
 * Unduh berkas API dengan Bearer, lalu picu unduhan browser.
 *
 * Tautan ``<a href>`` tidak bisa mengirim header Authorization, jadi semua
 * ekspor memakai fetch + blob. Kembaliannya nama berkas yang dipakai.
 */
export async function unduhBerkas(
  jalur: string,
  namaCadangan = "unduhan",
): Promise<string> {
  const headers = new Headers({ accept: "*/*" });
  pasangBearer(headers);
  const resp = await fetch(urlApi(jalur), {
    cache: "no-store",
    credentials: "same-origin",
    headers,
  });
  if (!resp.ok) {
    throw new KesalahanApi(resp.status, await bacaDetail(resp));
  }

  const blob = await resp.blob();
  const nama = namaBerkas(
    resp.headers.get("content-disposition") ?? "",
    namaCadangan,
  );
  if (typeof document === "undefined") {
    return nama;
  }
  const url = URL.createObjectURL(blob);
  const tautan = document.createElement("a");
  tautan.href = url;
  tautan.download = nama;
  document.body.appendChild(tautan);
  tautan.click();
  tautan.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  return nama;
}

export function buatFormUrlEncoded(
  nilai: Record<string, string | number | null | undefined>,
): URLSearchParams {
  // Metadata job tidak perlu multipart; WAF lebih ketat pada body form.
  const data = new URLSearchParams();
  for (const [kunci, isi] of Object.entries(nilai)) {
    if (isi !== null && isi !== undefined && isi !== "") {
      data.append(kunci, String(isi));
    }
  }
  return data;
}

export function adalahBatal(galat: unknown): boolean {
  return (
    galat instanceof DOMException
      ? galat.name === "AbortError"
      : galat instanceof Error && galat.name === "AbortError"
  );
}

export async function ambilJson<T>(
  jalur: string,
  init?: RequestInit,
): Promise<T> {
  const alamat = jalur.startsWith("/") ? jalur : `/${jalur}`;
  const headers = new Headers(init?.headers);
  if (!headers.has("accept")) {
    headers.set("accept", "application/json");
  }
  pasangBearer(headers);
  // Parameter unik untuk GET: cegah cache perantara pada respons status job.
  const metode = (init?.method ?? "GET").toUpperCase();
  const alamatAkhir =
    metode === "GET"
      ? `${alamat}${alamat.includes("?") ? "&" : "?"}_=${Date.now()}`
      : alamat;

  const resp = await fetch(urlApi(alamatAkhir), {
    ...init,
    cache: "no-store",
    credentials: "same-origin",
    headers,
  });

  if (!resp.ok) {
    throw new KesalahanApi(resp.status, await bacaDetail(resp));
  }
  return (await resp.json()) as T;
}

export function pesanKesalahan(galat: unknown): string {
  if (galat instanceof KesalahanApi) {
    if (galat.status === 401) {
      return "Sesi sudah habis. Muat ulang halaman, lalu masuk lagi.";
    }
    if (galat.status === 502) {
      return "Backend tidak dapat dihubungi. Periksa koneksi server lalu coba lagi.";
    }
    return istilahProses(galat.detail);
  }
  return "Backend tidak dapat dihubungi. Periksa koneksi lalu coba lagi.";
}
