export type TipeRun = "A" | "B";
export type StatusRun = "menunggu" | "jalan" | "sukses" | "gagal";

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
};

export type DaftarRun = {
  total: number;
  baris: Run[];
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
