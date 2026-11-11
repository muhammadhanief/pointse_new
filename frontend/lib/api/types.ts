export type TipeRun = "A" | "B" | "V";
export type StatusRun =
  | "menunggu"
  | "jalan"
  | "sukses"
  | "sukses_catatan"
  | "belum_clean"
  | "gagal"
  | "belum_unggah";

export type Run = {
  id: number;
  nomor_urut: number | null;
  tipe: TipeRun;
  kdprov: string;
  kdkab: string;
  user: string | null;
  status: StatusRun;
  nama_file_input: string;
  nama_file_peta: string;
  layer_input: string | null;
  layer_peta: string | null;
  jumlah_baris: number | null;
  jumlah_tanpa_wilayah: number | null;
  detail_tersedia: boolean;
  pesan: string | null;
  tanggal_data: string;
  created_at: string;
  started_at: string | null;
  heartbeat_at: string | null;
  finished_at: string | null;
  geotag_master_id: number | null;
  geotag_master_nomor: number | null;
  sumber_run_a_id: number | null;
  sumber_run_a_nomor: number | null;
  semester: string | null;
  antrean_ke: number | null;
};

export type DaftarRun = {
  total: number;
  baris: Run[];
};

export type ValidasiRingkasanBaris = {
  kdprov: string;
  kdkab: string;
  run_id: number | null;
  status: StatusRun;
  tanggal_data: string;
  semester: string | null;
  selesai_pada: string | null;
  petugas: string | null;
  total: number;
  per_jenis: Record<string, number>;
  target: number | null;
  selesai: number | null;
  sisa: number | null;
  terkonfirmasi?: number;
  akan_diperbaiki?: number;
  sesuai_kenyataan?: number;
  disetujui?: number;
  ditolak?: number;
  menunggu_persetujuan?: number;
};

export type ValidasiRingkasan = {
  baris: ValidasiRingkasanBaris[];
};

export type KonfirmasiValidasiSls = {
  status: "akan_diperbaiki" | "sesuai_kenyataan" | string;
  label: string;
  catatan: string | null;
  oleh: string | null;
  username: string | null;
  peran: string | null;
  pada: string | null;
  kunci: string | null;
  persetujuan_status: "disetujui" | "ditolak" | null;
  persetujuan_catatan: string | null;
  persetujuan_oleh: string | null;
  persetujuan_pada: string | null;
};

export type ValidasiUnmatchBaris = {
  id: number;
  jenis: string;
  idsls_peta: string | null;
  idsubsls_peta: string | null;
  idsls_master: string | null;
  idsubsls_master: string | null;
  nmsls: string | null;
  catatan: string | null;
  kunci: string | null;
  konfirmasi: KonfirmasiValidasiSls | null;
};

export type ValidasiUnmatch = {
  run_id: number;
  total: number;
  limit: number;
  offset: number;
  baris: ValidasiUnmatchBaris[];
};

export type MasterGeotag = {
  id: number;
  nomor_versi: number | null;
  kdprov: string;
  kdkab: string;
  tanggal_data: string;
  nama_file: string;
  layer: string | null;
  jumlah_baris: number | null;
  user: string | null;
  created_at: string;
};

export type DaftarMaster = {
  total: number;
  baris: MasterGeotag[];
};

export type JobSistem = {
  id: number;
  tipe: TipeRun;
  kdprov: string;
  kdkab: string;
  user: string | null;
  status: StatusRun;
  jumlah_baris: number | null;
  jumlah_tanpa_wilayah: number | null;
  pesan: string | null;
  created_at: string;
  started_at: string | null;
  heartbeat_at: string | null;
  finished_at: string | null;
  umur_heartbeat_detik: number | null;
};

export type RingkasanTipe = {
  tipe: TipeRun;
  run_id: number;
  tanggal_data: string;
  belum: number;
  ditindak: number;
  persen_progres: number | null;
};

export type RingkasanBaris = {
  kdprov: string;
  kdkab: string;
  nmprov: string | null;
  nmkab: string | null;
  belum_ada_upload_tipe_b: boolean;
  terakhir: RingkasanTipe[];
};

export type Ringkasan = {
  baris: RingkasanBaris[];
};

export type RekapBaris = {
  kode: string | null;
  nama: string | null;
  jumlah: number;
  belum: number;
  ditindak_posisi_benar: number;
  ditindak_posisi_salah: number;
  benar_awal: number;
  digeser: number;
  tanpa_wilayah: number;
  persen_progres: number | null;
};

export type Rekap = {
  run_id: number;
  tingkat: string;
  dasar: string;
  total: number;
  belum: number;
  ditindak_posisi_benar: number;
  ditindak_posisi_salah: number;
  benar_awal: number;
  digeser: number;
  tanpa_wilayah: number;
  persen_progres: number | null;
  baris: RekapBaris[];
};

export type RekapDetailBaris = {
  kode: string | null;
  nama: string | null;
  belum: number;
  ditindak: number;
  persen_progres: number | null;
};

export type RekapDetail = {
  run_id: number;
  tingkat: string;
  dasar: string;
  belum: number;
  ditindak: number;
  persen_progres: number | null;
  baris: RekapDetailBaris[];
};

export type ProgresBTarget = {
  run_a_id: number;
  nomor_urut: number | null;
  tanggal_data: string;
  total: number;
  flag_1: number;
};

export type ProgresBBaris = {
  run_id: number;
  nomor_urut: number | null;
  tanggal_data: string;
  selesai_pada: string | null;
  total: number;
  sisa_flag_1: number;
  beres: number;
  persen: number | null;
  perubahan: number;
};

export type ProgresB = {
  kdprov: string;
  kdkab: string;
  nmprov: string | null;
  nmkab: string | null;
  target: ProgresBTarget | null;
  baris: ProgresBBaris[];
};

export type TabulasiProgresRun = {
  run_id: number;
  nomor_urut: number | null;
  tanggal_data: string;
  pengunggah: string | null;
};

export type TabulasiProgresBaris = {
  kode: string | null;
  induk: string | null;
  nama: string | null;
  level: string;
  jumlah: number;
  target: number;
  selesai: number;
  sisa: number;
  persen: number | null;
  status: string;
  ada_b: boolean;
  pengunggah: string | null;
  cakupan_ada: number;
  cakupan_total: number;
  cakupan_unit: string | null;
};

export type TabulasiProgres = {
  tingkat: string;
  dasar: string;
  kdprov: string;
  kdkab: string | null;
  kdkec: string | null;
  nmprov: string | null;
  nmkab: string | null;
  nmkec: string | null;
  target: TabulasiProgresRun | null;
  pembanding: TabulasiProgresRun | null;
  baris: TabulasiProgresBaris[];
};

export type WorkerHeartbeat = {
  worker_id: string;
  pid: number | null;
  run_id: number | null;
  hostname: string | null;
  status: string;
  started_at: string;
  heartbeat_at: string;
  umur_heartbeat_detik: number;
  aktif: boolean;
};

export type WorkerEvent = {
  id: number;
  worker_id: string | null;
  run_id: number | null;
  level: string;
  jenis: string;
  pesan: string;
  created_at: string;
};

export type Backup = {
  dikonfigurasi: boolean;
  file_ada: boolean;
  status: string;
  waktu_mulai: string | null;
  waktu_selesai: string | null;
  berkas: string | null;
  ukuran_bytes: number | null;
  pesan: string | null;
  umur_jam: number | null;
};

export type StatusSistem = {
  waktu: string;
  sistem: {
    hostname: string;
    cpu: number | null;
    load_1: number | null;
    load_5: number | null;
    load_15: number | null;
    memori: {
      total_mb: number | null;
      tersedia_mb: number | null;
      terpakai_mb: number | null;
      persen_terpakai: number | null;
      swap_total_mb: number | null;
      swap_terpakai_mb: number | null;
      api_rss_mb: number | null;
      worker_rss_mb: number | null;
    };
    disk: {
      total_mb: number | null;
      terpakai_mb: number | null;
      tersedia_mb: number | null;
      persen_terpakai: number | null;
    };
  };
  worker: {
    aktif: boolean;
    pid: number | null;
    rss_mb: number | null;
    batas_memori_mb: number;
    jumlah_proses: number;
  };
  konfigurasi: {
    poll_detik: number;
    heartbeat_detik: number;
    timeout_menit: number;
    chunk_titik: number;
    max_workers: number;
  };
  antrean: {
    menunggu: number;
    jalan: number;
    sukses: number;
    belum_clean: number;
    gagal: number;
    total: number;
    tertua_menunggu: string | null;
  };
  job_aktif: JobSistem[];
  job_terakhir: JobSistem | null;
  heartbeats: WorkerHeartbeat[];
  kejadian: WorkerEvent[];
  backup: Backup;
  peringatan: string[];
};

export type PenggunaAktif = {
  sub: string;
  username: string;
  nama: string;
  nip: string | null;
  email: string | null;
  org: string;
  peran: string;
  kdprov: string;
  kdkab: string | null;
  foto_url: string | null;
  login_pada: string;
  terakhir_aktif: string;
  online: boolean;
};

export type DaftarPenggunaAktif = {
  total: number;
  online: number;
  baris: PenggunaAktif[];
};

export type Aktivitas = {
  id: number;
  sub: string;
  username: string;
  nama: string;
  nip: string | null;
  peran: string;
  kdprov: string;
  kdkab: string | null;
  foto_url: string | null;
  aksi: string;
  objek: string;
  objek_id: number | null;
  detail: string | null;
  created_at: string;
};

export type DaftarAktivitas = {
  total: number;
  baris: Aktivitas[];
};

export type AnomaliRun = {
  run_id: number;
  tanggal_data: string;
  pengunggah: string | null;
  kdkab: string | null;
  target: number;
  selesai: number;
  anomali_versi: number;
  jumlah_anomali: number | null;
};

export type DaftarAnomaliRun = {
  baris: AnomaliRun[];
};

export type AnomaliJenis = {
  kode: string;
  label: string;
  jumlah: number;
};

export type AnomaliBaris = {
  id: number | null;
  jenis: string;
  kdkab: string | null;
  assignment_id: string | null;
  assignment_id_baru: string | null;
  unique_bang: string | null;
  level_6_full_code: string | null;
  level_6_full_code_b: string | null;
  wilayah: string | null;
  latitude: number | null;
  longitude: number | null;
  flag_unggah: number | null;
  flag_model: number | null;
  keterangan: string | null;
  kunci: string | null;
  konfirmasi: KonfirmasiAnomali | null;
};

export type KonfirmasiAnomali = {
  status: string;
  label: string;
  catatan: string | null;
  oleh: string | null;
  peran: string | null;
  pada: string | null;
  kunci: string | null;
  perlu_klarifikasi: boolean;
  klarifikasi_catatan: string | null;
  klarifikasi_oleh: string | null;
  klarifikasi_pada: string | null;
};

export type StatusKonfirmasi = {
  kode: string;
  label: string;
  jumlah: number;
};

export type RingkasanKonfirmasi = {
  total: number;
  terkonfirmasi: number;
  belum: number;
  per_status: StatusKonfirmasi[];
};

export type Anomali = {
  run: AnomaliRun | null;
  runs: AnomaliRun[];
  jenis: AnomaliJenis[];
  total: number;
  baris: AnomaliBaris[];
  ringkasan: RingkasanKonfirmasi;
  status_pilihan: StatusKonfirmasi[];
};

export type GeserRun = {
  run_id: number;
  tanggal_data: string;
  pengunggah: string | null;
  kdkab: string | null;
  target: number;
  selesai: number;
  jumlah_geser: number;
};

export type DaftarGeserRun = {
  baris: GeserRun[];
};

export type GeserBaris = {
  id: number | null;
  kdkab: string | null;
  assignment_id: string | null;
  unique_bang: string | null;
  level_6_full_code: string | null;
  level_6_full_code_b: string | null;
  wilayah: string | null;
  latitude: number | null;
  longitude: number | null;
  jarak_geser_m: number | null;
  flag_unggah: number | null;
  flag_model: number | null;
  keterangan: string | null;
};

export type Geser = {
  run: GeserRun | null;
  runs: GeserRun[];
  total: number;
  min_meter: number;
  baris: GeserBaris[];
};

export type PermintaanKonfirmasi = {
  status?: string;
  catatan?: string | null;
  anomali_ids?: number[];
  kdprov?: string;
  kdkab?: string[];
  jenis?: string[];
  q?: string;
  run_b_id?: number;
  status_filter?: string;
  semua?: boolean;
};

export type HasilKonfirmasi = {
  jumlah: number;
};

export type KategoriKomunitas =
  | "peta_2026_s1"
  | "peta_2025_s2"
  | "geotagging"
  | "lainnya";

export type StatusKomunitas = "terbuka" | "terpecahkan" | "jadi_rule";

export type RuleTargetKomunitas = "identifikasi" | "pengecekan" | "validasi";

export type KomunitasKomentar = {
  id: number;
  topik_id: number;
  kdprov: string;
  kdkab: string | null;
  isi: string;
  adalah_solusi: boolean;
  oleh: string;
  username: string;
  peran: string;
  created_at: string;
};

export type KomunitasTopik = {
  id: number;
  kdprov: string;
  kdkab: string | null;
  kategori: KategoriKomunitas | string;
  judul: string;
  error_txt: string | null;
  deskripsi: string;
  solusi_awal: string | null;
  status: StatusKomunitas | string;
  solusi_komentar_id: number | null;
  rule_target: RuleTargetKomunitas | string | null;
  rule_catatan: string | null;
  rule_oleh: string | null;
  rule_pada: string | null;
  jumlah_komentar: number;
  jumlah_dukungan: number;
  didukung_saya: boolean;
  oleh: string;
  username: string;
  peran: string;
  created_at: string;
  updated_at: string;
};

export type KomunitasTopikDetail = KomunitasTopik & {
  komentar: KomunitasKomentar[];
};

export type DaftarKomunitasTopik = {
  total: number;
  terbuka: number;
  terpecahkan: number;
  jadi_rule: number;
  baris: KomunitasTopik[];
};

export type StatusRekonsiliasiBatas =
  | "clean"
  | "belum_clean"
  | "menunggu_tetangga"
  | "belum_unggah";

export type RekonsiliasiBatasPasangBaris = {
  kdkab_a: string;
  nmkab_a: string;
  kdkab_b: string;
  nmkab_b: string;
  run_a_id: number | null;
  run_b_id: number | null;
  tanggal_a: string | null;
  tanggal_b: string | null;
  waktu_a?: string | null;
  waktu_b?: string | null;
  pengunggah_a?: string | null;
  pengunggah_b?: string | null;
  ada_peta_a?: boolean;
  ada_peta_b?: boolean;
  status: StatusRekonsiliasiBatas | string;
  jumlah_overlap: number;
  jumlah_gap: number;
  total_temuan: number;
  total_luas_overlap_m2: number;
  total_luas_gap_m2: number;
  ada_geojson: boolean;
  pesan: string | null;
  updated_at: string | null;
};

export type RekonsiliasiBatasRingkasan = {
  total_pasang: number;
  clean: number;
  belum_clean: number;
  menunggu_tetangga: number;
  belum_unggah: number;
  total_overlap: number;
  total_gap: number;
  total_luas_overlap_m2?: number;
  total_luas_gap_m2?: number;
  baris: RekonsiliasiBatasPasangBaris[];
};

export type RekonsiliasiBatasTemuan = {
  id: number;
  jenis: "overlap" | "gap" | string;
  tingkat: "sliver" | "sedang" | "besar" | string;
  idsls_a: string | null;
  idsubsls_a: string | null;
  nmsls_a: string | null;
  idsls_b: string | null;
  idsubsls_b: string | null;
  nmsls_b: string | null;
  luas_m2: number;
  lat: number;
  lon: number;
  catatan: string | null;
};

export type RekonsiliasiBatasDetail = RekonsiliasiBatasPasangBaris & {
  temuan: RekonsiliasiBatasTemuan[];
};
