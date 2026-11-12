"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { PenandaUrut, type ArahUrut } from "@/components/dashboard/tabel-urut";
import { EmptyState, Panel, TombolAksi } from "@/components/dashboard/ui";
import {
  KesalahanApi,
  adalahBatal,
  ambilJson,
  pesanKesalahan,
} from "@/lib/api/klien";
import type { Aktivitas, DaftarAktivitas } from "@/lib/api/types";
import { labelWilayah } from "@/lib/auth/peran";
import { formatWaktu } from "@/lib/format";

const LABEL_AKSI: Record<string, string> = {
  unggah_a: "Unggah peta SLS/SubSLS",
  unggah_b: "Unggah titik hasil perbaikan",
  unggah_master: "Unggah master geotag",
  unggah_ditolak: "Unggahan ditolak",
  login: "Login",
};

const GAYA_AKSI: Record<string, string> = {
  unggah_a: "border-brand/25 bg-brand-soft text-brand-strong",
  unggah_b: "border-accent/30 bg-accent-soft text-accent-strong",
  unggah_master: "border-success/30 bg-success-soft text-success",
  unggah_ditolak: "border-danger/30 bg-danger-soft text-danger",
  login: "border-line bg-paper text-muted",
};

function labelObjek(item: Aktivitas): string {
  if (item.objek === "run") {
    return item.objek_id ? `Job #${item.objek_id}` : "Job";
  }
  if (item.objek === "geotag_master") {
    return item.objek_id ? `Master #${item.objek_id}` : "Master geotag";
  }
  if (item.objek === "unggahan") {
    return "Berkas unggahan";
  }
  return item.objek;
}

type KunciUrutAktivitas = "waktu" | "nama" | "aksi" | "objek" | "detail" | "wilayah";

const KOLOM_AKTIVITAS: { kunci: KunciUrutAktivitas; label: string }[] = [
  { kunci: "waktu", label: "Waktu" },
  { kunci: "nama", label: "Pengguna" },
  { kunci: "aksi", label: "Aksi" },
  { kunci: "objek", label: "Objek" },
  { kunci: "detail", label: "Detail" },
  { kunci: "wilayah", label: "Wilayah" },
];

/** Nilai yang dibandingkan saat kolom diurutkan (selalu teks, gaya tampilan). */
function nilaiUrutAktivitas(item: Aktivitas, kunci: KunciUrutAktivitas): string {
  switch (kunci) {
    case "waktu":
      return item.created_at ?? "";
    case "nama":
      return item.nama ?? "";
    case "aksi":
      return LABEL_AKSI[item.aksi] ?? item.aksi;
    case "objek":
      return labelObjek(item);
    case "detail":
      return item.detail ?? "";
    case "wilayah":
      return labelWilayah(item.kdprov, item.kdkab);
  }
}

function FotoPelaku({ item }: { item: Aktivitas }) {
  const [gagal, setGagal] = useState(false);
  const inisial = item.nama.trim().charAt(0).toUpperCase() || "?";

  if (item.foto_url && !gagal) {
    return (
      <img
        src={item.foto_url}
        alt={item.nama}
        loading="lazy"
        onError={() => setGagal(true)}
        className="h-8 w-8 shrink-0 rounded-md border border-line object-cover"
      />
    );
  }

  return (
    <div
      aria-hidden="true"
      className="grid h-8 w-8 shrink-0 place-items-center rounded-md bg-brand-soft text-xs font-semibold text-brand-strong"
    >
      {inisial}
    </div>
  );
}

export function LogAktivitasClient() {
  const [data, setData] = useState<DaftarAktivitas | null>(null);
  const [memuat, setMemuat] = useState(true);
  const [galat, setGalat] = useState<string | null>(null);
  const [diperbarui, setDiperbarui] = useState<string | null>(null);
  const [cari, setCari] = useState("");
  const [kataKunci, setKataKunci] = useState("");
  const [urutKolom, setUrutKolom] = useState<KunciUrutAktivitas | null>(null);
  const [urutArah, setUrutArah] = useState<ArahUrut>("asc");
  const kendaliRef = useRef<AbortController | null>(null);

  const muat = useCallback(async (senyap = false) => {
    kendaliRef.current?.abort();
    const kendali = new AbortController();
    kendaliRef.current = kendali;

    if (!senyap) {
      setMemuat(true);
    }
    setGalat(null);

    try {
      const hasil = await ambilJson<DaftarAktivitas>("/aktivitas?limit=200", {
        signal: kendali.signal,
      });
      if (!kendali.signal.aborted) {
        setData(hasil);
        setDiperbarui(new Date().toISOString());
      }
    } catch (kesalahan) {
      if (!adalahBatal(kesalahan)) {
        setGalat(
          kesalahan instanceof KesalahanApi && kesalahan.status === 404
            ? "Endpoint log aktivitas belum tersedia di backend (404). Deploy backend dan jalankan migrasi 0011."
            : pesanKesalahan(kesalahan),
        );
      }
    } finally {
      if (!kendali.signal.aborted) {
        setMemuat(false);
      }
    }
  }, []);

  useEffect(() => {
    void muat();
    const timer = window.setInterval(() => void muat(true), 30_000);
    return () => {
      window.clearInterval(timer);
      kendaliRef.current?.abort();
    };
  }, [muat]);

  // Saringan lokal supaya search tetap bekerja walau endpoint aktivitas belum
  // mengenal parameter pencarian.
  const baris = useMemo(() => {
    const daftar = data?.baris ?? [];
    const kata = kataKunci.trim().toLowerCase();
    if (!kata) {
      return daftar;
    }
    return daftar.filter((item) =>
      [
        item.nama,
        item.username,
        item.nip ?? "",
        item.aksi,
        item.objek,
        item.detail ?? "",
        labelWilayah(item.kdprov, item.kdkab),
      ].some((nilai) => nilai.toLowerCase().includes(kata)),
    );
  }, [data, kataKunci]);

  const barisTerurut = useMemo(() => {
    const daftar = [...baris];
    if (!urutKolom) {
      return daftar;
    }
    const arah = urutArah === "asc" ? 1 : -1;
    daftar.sort(
      (a, b) =>
        arah *
        nilaiUrutAktivitas(a, urutKolom).localeCompare(
          nilaiUrutAktivitas(b, urutKolom),
          "id",
        ),
    );
    return daftar;
  }, [baris, urutKolom, urutArah]);

  function urutkan(kunci: KunciUrutAktivitas) {
    if (urutKolom === kunci) {
      setUrutArah(urutArah === "asc" ? "desc" : "asc");
      return;
    }
    setUrutKolom(kunci);
    setUrutArah("asc");
  }

  return (
    <Panel
      judul="Log aktivitas"
      deskripsi="Rekaman tindakan pengguna beserta identitas SSO pelakunya. Diperbarui otomatis setiap 30 detik."
    >
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-3 text-xs text-muted">
          <span>
            <strong className="text-ink">{baris.length}</strong> aktivitas
          </span>
          {kataKunci ? (
            <span>memuat &ldquo;{kataKunci}&rdquo;</span>
          ) : null}
          {diperbarui ? (
            <span>Diperbarui {formatWaktu(diperbarui)}</span>
          ) : null}
        </div>
        <TombolAksi
          varian="sekunder"
          className="min-h-8 px-2.5 text-xs"
          onClick={() => void muat()}
          disabled={memuat}
        >
          {memuat ? "Memuat..." : "Muat ulang"}
        </TombolAksi>
      </div>

      <form
        className="mt-3 flex flex-wrap items-end gap-2"
        onSubmit={(kejadian) => {
          kejadian.preventDefault();
          setKataKunci(cari.trim());
        }}
      >
        <label className="min-w-0 flex-1 text-sm font-medium text-ink">
          Cari aktivitas
          <input
            type="search"
            value={cari}
            onChange={(kejadian) => setCari(kejadian.target.value)}
            placeholder="nama, aksi, detail, atau wilayah"
            className="mt-label block min-h-9 w-full rounded-lg border border-line-strong bg-surface px-input py-input text-sm text-ink"
          />
        </label>
        <TombolAksi type="submit" varian="sekunder" className="min-h-9 px-2.5 text-xs">
          Cari
        </TombolAksi>
        {kataKunci ? (
          <TombolAksi
            varian="sekunder"
            className="min-h-9 px-2.5 text-xs"
            onClick={() => {
              setCari("");
              setKataKunci("");
            }}
          >
            Reset
          </TombolAksi>
        ) : null}
      </form>

      {galat ? (
        <div
          role="alert"
          className="mt-3 rounded-lg border border-danger/30 bg-danger-soft/50 px-3 py-2 text-sm text-ink"
        >
          {galat}
        </div>
      ) : null}

      {memuat && data == null ? (
        <div className="mt-3 space-y-2" aria-label="Memuat aktivitas">
          {[0, 1, 2, 3].map((baris) => (
            <div
              key={baris}
              className="h-11 animate-pulse rounded-lg bg-paper"
            />
          ))}
        </div>
      ) : null}

      {!memuat && data && baris.length === 0 ? (
        kataKunci ? (
          <EmptyState judul="Tidak ada aktivitas yang cocok">
            Tidak ada nama, aksi, detail, atau wilayah yang memuat
            &ldquo;{kataKunci}&rdquo;. Coba kata kunci lain.
          </EmptyState>
        ) : (
          <EmptyState judul="Belum ada aktivitas tercatat">
            Aktivitas login dan unggahan akan muncul setelah pengguna memakai
            aplikasi.
          </EmptyState>
        )
      ) : null}

      {data && baris.length > 0 ? (
        <div className="mt-3 max-h-[32rem] overflow-auto overscroll-contain rounded-lg border border-line">
          <table className="w-full min-w-[58rem] border-collapse text-[13px]">
            <thead className="sticky top-0 z-10 bg-paper">
              <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-muted">
                {KOLOM_AKTIVITAS.map((kolom) => (
                  <th
                    key={kolom.kunci}
                    scope="col"
                    aria-sort={
                      urutKolom === kolom.kunci
                        ? urutArah === "asc"
                          ? "ascending"
                          : "descending"
                        : "none"
                    }
                    className="p-0 font-semibold"
                  >
                    <button
                      type="button"
                      onClick={() => urutkan(kolom.kunci)}
                      title={`Urutkan menurut ${kolom.label}`}
                      className="group inline-flex min-h-9 w-full items-center gap-1 px-3 py-2 text-left uppercase tracking-wide hover:text-ink"
                    >
                      <span>{kolom.label}</span>
                      <PenandaUrut
                        aktif={urutKolom === kolom.kunci}
                        arah={urutArah}
                      />
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {barisTerurut.map((item) => (
                <tr
                  key={item.id}
                  className="border-b border-line/70 last:border-0"
                >
                  <td className="whitespace-nowrap px-3 py-2 tabular-nums text-muted">
                    {formatWaktu(item.created_at)}
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-2">
                      <FotoPelaku item={item} />
                      <div className="min-w-0">
                        <p className="truncate font-medium text-ink">
                          {item.nama}
                        </p>
                        <p className="truncate text-[11px] text-muted">
                          {item.username}
                          {item.nip ? ` · ${item.nip}` : ""}
                        </p>
                      </div>
                    </div>
                  </td>
                  <td className="px-3 py-2">
                    <span
                      className={`inline-flex whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-semibold ${
                        GAYA_AKSI[item.aksi] ??
                        "border-line bg-paper text-muted"
                      }`}
                    >
                      {LABEL_AKSI[item.aksi] ?? item.aksi}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 text-muted">
                    {labelObjek(item)}
                  </td>
                  <td className="max-w-[22rem] px-3 py-2 text-muted">
                    <span className="block truncate" title={item.detail ?? ""}>
                      {item.detail ?? "-"}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-muted">
                    {labelWilayah(item.kdprov, item.kdkab)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </Panel>
  );
}
