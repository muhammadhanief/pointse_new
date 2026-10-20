import type { Metadata } from "next";

import {
  BarProgres,
  CatatanContoh,
  EmptyState,
  PageHeader,
  Panel,
  TautanAksi,
} from "@/components/dashboard/ui";

export const metadata: Metadata = {
  title: "Rekap progres",
};

type BarisContoh = {
  wilayah: string;
  jumlah: number;
  belum: number;
  benarAwal: number;
  tindakBenar: number;
  tindakSalah: number;
  digeser: number;
  tanpaWilayah: number;
  progres: number;
};

const CONTOH: BarisContoh[] = [
  {
    wilayah: "Contoh Kecamatan A / Desa A1",
    jumlah: 24,
    belum: 9,
    benarAwal: 8,
    tindakBenar: 5,
    tindakSalah: 2,
    digeser: 3,
    tanpaWilayah: 0,
    progres: 44,
  },
  {
    wilayah: "Contoh Kecamatan A / Desa A2",
    jumlah: 18,
    belum: 5,
    benarAwal: 4,
    tindakBenar: 7,
    tindakSalah: 2,
    digeser: 1,
    tanpaWilayah: 1,
    progres: 64,
  },
  {
    wilayah: "Contoh Kecamatan B / Desa B1",
    jumlah: 30,
    belum: 14,
    benarAwal: 6,
    tindakBenar: 8,
    tindakSalah: 2,
    digeser: 4,
    tanpaWilayah: 0,
    progres: 42,
  },
];

function Angka({ nilai }: { nilai: number }) {
  return <span className="tabular-nums">{nilai}</span>;
}

export default function RekapPage() {
  return (
    <div className="space-y-8">
      <PageHeader
        judul="Rekap progres"
        deskripsi="Jumlah titik dibagi menjadi belum, benar sejak awal, dan sudah ditindak. Rekap disimpan per job agar angka historis tidak berubah."
        meta={
          <div className="sm:text-right">
            <p className="font-semibold text-ink">Data asli belum tersedia</p>
            <p className="mt-0.5 text-xs">Database pengembangan masih kosong.</p>
          </div>
        }
      />

      <Panel
        judul="Rekap per desa"
        deskripsi="Bentuk tabel mengikuti kolom rekap yang dipakai dashboard nanti."
      >
        <div className="mt-5">
          <CatatanContoh>
            Angka di bawah hanya untuk melihat bentuk tabel. Ini bukan hasil
            langkah 1 atau 2.
          </CatatanContoh>
        </div>

        <div
          role="region"
          aria-label="Tabel contoh rekap per desa"
          tabIndex={0}
          className="mt-5 overflow-x-auto"
        >
          <table className="w-full min-w-[64rem] border-collapse text-sm">
            <caption className="sr-only">
              Contoh rekap progres per desa dengan angka tiruan.
            </caption>
            <thead>
              <tr className="border-b border-line text-left text-xs font-semibold text-muted">
                <th scope="col" className="py-2.5 pr-4">
                  Wilayah
                </th>
                <th scope="col" className="px-3 py-2.5 text-right">
                  Jumlah
                </th>
                <th scope="col" className="px-3 py-2.5 text-right">
                  Belum
                </th>
                <th scope="col" className="px-3 py-2.5 text-right">
                  Benar awal
                </th>
                <th scope="col" className="px-3 py-2.5 text-right">
                  Ditindak benar
                </th>
                <th scope="col" className="px-3 py-2.5 text-right">
                  Ditindak salah
                </th>
                <th scope="col" className="px-3 py-2.5 text-right">
                  Digeser
                </th>
                <th scope="col" className="px-3 py-2.5 text-right">
                  Tanpa wilayah
                </th>
                <th scope="col" className="px-3 py-2.5 text-right">
                  Progres
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {CONTOH.map((baris) => (
                <tr key={baris.wilayah}>
                  <th
                    scope="row"
                    className="py-3 pr-4 text-left font-medium text-ink"
                  >
                    {baris.wilayah}
                  </th>
                  <td className="px-3 py-3 text-right font-semibold text-ink">
                    <Angka nilai={baris.jumlah} />
                  </td>
                  <td className="px-3 py-3 text-right text-muted">
                    <Angka nilai={baris.belum} />
                  </td>
                  <td className="px-3 py-3 text-right text-muted">
                    <Angka nilai={baris.benarAwal} />
                  </td>
                  <td className="px-3 py-3 text-right text-muted">
                    <Angka nilai={baris.tindakBenar} />
                  </td>
                  <td className="px-3 py-3 text-right text-muted">
                    <Angka nilai={baris.tindakSalah} />
                  </td>
                  <td className="px-3 py-3 text-right text-muted">
                    <Angka nilai={baris.digeser} />
                  </td>
                  <td className="px-3 py-3 text-right text-muted">
                    <Angka nilai={baris.tanpaWilayah} />
                  </td>
                  <td className="px-3 py-3 text-right text-ink">
                    <BarProgres nilai={baris.progres} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <p className="mt-4 text-xs leading-5 text-muted">
          Persentase dihitung dari (ditindak benar + ditindak salah) dibagi
          (belum + ditindak benar + ditindak salah). Benar awal dan digeser
          tidak masuk penyebut.
        </p>
      </Panel>

      <Panel
        judul="Data asli"
        deskripsi="Rekap nyata baru tersedia setelah job pertama berhasil."
      >
        <EmptyState
          judul="Belum ada hasil proses"
          aksi={
            <TautanAksi href="/proses/identifikasi">
              Lihat langkah 1
            </TautanAksi>
          }
        >
          Setelah langkah 1 atau 2 sukses, rekap per kabupaten/kota, kecamatan,
          desa, dan SLS/SubSLS akan dihitung dari snapshot job tersebut.
        </EmptyState>
      </Panel>
    </div>
  );
}
