import { timingSafeEqual } from "node:crypto";
import { type NextRequest, NextResponse } from "next/server";

import {
  PERAN_ADMIN_PROVINSI,
  PERAN_PETUGAS_KABKOT,
} from "@/lib/auth/peran";
import { simpanSesi } from "@/lib/auth/session";
import { asalDiizinkan, urlPublik } from "@/lib/http/origin";
import {
  daftarKabupaten,
  namaKabupaten,
} from "@/lib/wilayah/kabupaten";

function sama(teks: string, rahasia: string): boolean {
  const kiri = Buffer.from(teks);
  const kanan = Buffer.from(rahasia);
  return kiri.length === kanan.length && timingSafeEqual(kiri, kanan);
}

/**
 * Login bypass untuk pengujian.
 *
 * Aktif hanya bila AUTH_BYPASS_ENABLED=true. Di production wajib ada
 * AUTH_BYPASS_SECRET dan kode yang dikirim harus cocok.
 */
export async function POST(request: NextRequest): Promise<NextResponse> {
  if (process.env.AUTH_BYPASS_ENABLED !== "true") {
    return NextResponse.json(
      { detail: "bypass login tidak aktif" },
      { status: 404 },
    );
  }

  const rahasia = (process.env.AUTH_BYPASS_SECRET ?? "").trim();
  if (process.env.NODE_ENV === "production" && !rahasia) {
    return NextResponse.json(
      { detail: "AUTH_BYPASS_SECRET wajib di production" },
      { status: 404 },
    );
  }

  if (!asalDiizinkan(request)) {
    return NextResponse.json(
      { detail: "asal permintaan tidak valid" },
      { status: 403 },
    );
  }

  const data = await request.formData();
  const kodeBypass = String(data.get("kode") ?? "");
  if (rahasia && !sama(kodeBypass, rahasia)) {
    return NextResponse.redirect(
      urlPublik(request, "/login?error=bypass"),
      { status: 303 },
    );
  }

  const peran = String(data.get("peran") ?? "petugas_kabkot").trim();

  if (peran === "admin_prov") {
    await simpanSesi({
      sub: "bypass-3300",
      username: "bypass-3300",
      nama: "Bypass Admin Provinsi 33",
      nip: null,
      email: null,
      org: "3300",
      peran: PERAN_ADMIN_PROVINSI,
      kdprov: "33",
      kdkab: null,
    });
    return NextResponse.redirect(urlPublik(request, "/"), { status: 303 });
  }

  if (peran !== "petugas_kabkot") {
    return NextResponse.redirect(
      urlPublik(request, "/login?error=bypass"),
      { status: 303 },
    );
  }

  const kode = String(data.get("kdkab") ?? "").trim();
  const valid =
    /^\d{4}$/.test(kode) &&
    kode.startsWith("33") &&
    daftarKabupaten("33").some((satu) => satu.kode === kode);

  if (!valid) {
    return NextResponse.redirect(
      urlPublik(request, "/login?error=bypass"),
      { status: 303 },
    );
  }

  const nama = namaKabupaten("33", kode) ?? kode;
  await simpanSesi({
    sub: `bypass-${kode}`,
    username: `bypass-${kode}`,
    nama: `Bypass ${nama}`,
    nip: null,
    email: null,
    org: kode,
    peran: PERAN_PETUGAS_KABKOT,
    kdprov: "33",
    kdkab: kode,
  });

  return NextResponse.redirect(urlPublik(request, "/"), { status: 303 });
}
