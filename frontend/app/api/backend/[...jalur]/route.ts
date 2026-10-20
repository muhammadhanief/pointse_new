import { cookies } from "next/headers";
import { type NextRequest, NextResponse } from "next/server";

import { NAMA_COOKIE_SESI } from "@/lib/auth/konstanta";
import { ambilSesi } from "@/lib/auth/session";
import { asalDiizinkan } from "@/lib/http/origin";

type Konteks = { params: Promise<{ jalur: string[] }> };

const HEADER_PERMINTAAN = ["accept", "content-type", "range", "if-none-match"];
const HEADER_BALASAN = [
  "content-type",
  "content-disposition",
  "content-length",
  "cache-control",
  "etag",
  "last-modified",
  "accept-ranges",
  "content-range",
];

function tanpaBadan(method: string): boolean {
  return method === "GET" || method === "HEAD";
}

async function teruskan(
  request: NextRequest,
  konteks: Konteks,
): Promise<NextResponse> {
  const sesi = await ambilSesi();
  if (!sesi) {
    return NextResponse.json({ detail: "belum login" }, { status: 401 });
  }

  // Cegah CSRF untuk permintaan yang mengubah data. SameSite=Lax pada cookie
  // sesi juga menahan permintaan lintas situs.
  if (!tanpaBadan(request.method) && !asalDiizinkan(request)) {
    return NextResponse.json(
      { detail: "asal permintaan tidak valid" },
      { status: 403 },
    );
  }

  const { jalur } = await konteks.params;
  if (
    !jalur?.length ||
    jalur.some(
      (satu) =>
        !satu ||
        satu === "." ||
        satu === ".." ||
        satu.includes("/") ||
        satu.includes("\\"),
    )
  ) {
    return NextResponse.json({ detail: "jalur tidak valid" }, { status: 400 });
  }

  const dasar = process.env.BACKEND_URL?.trim();
  if (!dasar) {
    return NextResponse.json(
      { detail: "BACKEND_URL belum dikonfigurasi" },
      { status: 500 },
    );
  }

  const target = new URL(
    `${dasar.replace(/\/+$/, "")}/${jalur.map(encodeURIComponent).join("/")}`,
  );
  target.search = request.nextUrl.search;

  const token = (await cookies()).get(NAMA_COOKIE_SESI)?.value;
  const headers = new Headers();
  for (const nama of HEADER_PERMINTAAN) {
    const nilai = request.headers.get(nama);
    if (nilai) headers.set(nama, nilai);
  }
  if (token) headers.set("authorization", `Bearer ${token}`);

  const init: RequestInit & { duplex?: "half" } = {
    method: request.method,
    headers,
    redirect: "manual",
    cache: "no-store",
  };
  if (!tanpaBadan(request.method) && request.body) {
    init.body = request.body;
    // Node fetch membutuhkan duplex untuk body streaming (unggahan besar).
    init.duplex = "half";
  }

  try {
    const resp = await fetch(target, init);

    const keluar = new Headers();
    for (const nama of HEADER_BALASAN) {
      const nilai = resp.headers.get(nama);
      if (nilai) keluar.set(nama, nilai);
    }
    if (resp.status === 204 || resp.status === 304) {
      return new NextResponse(null, { status: resp.status, headers: keluar });
    }
    return new NextResponse(resp.body, {
      status: resp.status,
      headers: keluar,
    });
  } catch {
    return NextResponse.json(
      { detail: "backend tidak dapat dihubungi" },
      { status: 502 },
    );
  }
}

export const GET = teruskan;
export const HEAD = teruskan;
export const POST = teruskan;
export const PUT = teruskan;
export const PATCH = teruskan;
export const DELETE = teruskan;
