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
  peringatan: string[];
};
