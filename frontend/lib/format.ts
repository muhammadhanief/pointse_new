const formatterWaktu = new Intl.DateTimeFormat("id-ID", {
  dateStyle: "medium",
  // Status job diperbarui tiap 5 detik; tampilkan detik agar heartbeat dan
  // waktu selesai bisa dibedakan.
  timeStyle: "medium",
});

const formatterTanggal = new Intl.DateTimeFormat("id-ID", {
  dateStyle: "medium",
});

const formatterAngka = new Intl.NumberFormat("id-ID");

/** Waktu API dikirim sebagai UTC tanpa zona; tambahkan Z sebelum ditampilkan. */
export function formatWaktu(nilai: string | null | undefined): string {
  if (!nilai) {
    return "-";
  }
  const iso = /[zZ]$|[+-]\d{2}:\d{2}$/.test(nilai) ? nilai : `${nilai}Z`;
  const tanggal = new Date(iso);
  return Number.isNaN(tanggal.getTime()) ? "-" : formatterWaktu.format(tanggal);
}

/** Tanggal data tidak punya zona; baca sebagai tanggal lokal, bukan UTC. */
export function formatTanggal(nilai: string | null | undefined): string {
  if (!nilai) {
    return "-";
  }
  const bagian = nilai.slice(0, 10).split("-").map(Number);
  if (bagian.length !== 3 || bagian.some((angka) => !Number.isFinite(angka))) {
    return "-";
  }
  const tanggal = new Date(bagian[0], bagian[1] - 1, bagian[2]);
  return Number.isNaN(tanggal.getTime())
    ? "-"
    : formatterTanggal.format(tanggal);
}

export function formatAngka(nilai: number | null | undefined): string {
  return nilai == null ? "-" : formatterAngka.format(nilai);
}

/**
 * Persentase penyelesaian: 4 angka di belakang koma, tanpa nol berekor
 * (``50%``, bukan ``50,0000%``). Empat angka itu perlu supaya wilayah yang
 * masih menyisakan 1 titik tidak tampil bulat 100% (``99,999%``, bukan ``100%``).
 */
export function formatPersen(nilai: number | null | undefined): string {
  if (nilai == null) {
    return "-";
  }
  return `${nilai.toLocaleString("id-ID", {
    maximumFractionDigits: 4,
    minimumFractionDigits: 0,
  })}%`;
}

export function formatBytes(nilai: number | null | undefined): string {
  if (nilai == null || !Number.isFinite(nilai) || nilai < 0) {
    return "-";
  }
  if (nilai < 1024) {
    return `${nilai} B`;
  }

  const satuan = ["KB", "MB", "GB"];
  let angka = nilai / 1024;
  let indeks = 0;
  while (angka >= 1024 && indeks < satuan.length - 1) {
    angka /= 1024;
    indeks += 1;
  }

  const desimal = angka >= 100 ? 0 : 1;
  return `${new Intl.NumberFormat("id-ID", {
    maximumFractionDigits: desimal,
    minimumFractionDigits: 0,
  }).format(angka)} ${satuan[indeks]}`;
}
