"""Konfigurasi aplikasi; nilai dibaca dari variabel lingkungan / file `.env`."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    """Setelan aplikasi pointse."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "pointse"
    debug: bool = False
    #: ``production`` mengaktifkan pemeriksaan keamanan saat aplikasi start.
    env: str = "development"
    #: Prefix URL API (mis. ``/api``); kosong berarti API di akar domain.
    api_prefix: str = ""

    # Basis data MySQL (hanya backend yang mengaksesnya)
    db_host: str = "localhost"
    db_port: int = 3306
    db_user: str = ""
    db_password: str = ""
    db_name: str = "pointse"

    # CORS: hanya origin frontend yang boleh memanggil API dari browser.
    cors_origins: list[str] = Field(
        default_factory=lambda: ["https://pointse.web.bps.go.id"]
    )

    # Autentikasi: frontend mengirim token sesi HS256 sebagai Bearer, bukan
    # cookie. Tidak ada nilai bawaan untuk kunci penanda tangan.
    auth_mode: Literal["dev", "jwt"] = "jwt"
    auth_secret: str = ""
    auth_issuer: str = "pointse"
    auth_audience: str = "pointse-backend"

    # Unggahan berkas mentah (GPKG/GeoJSON) disimpan di disk server, bukan di DB
    dir_unggahan: str = "data/unggahan"
    #: Geotag master per kabupaten (permanen, tidak ikut pemangkasan run).
    dir_master: str = "data/master"

    # Unggahan body mentah: batas ukuran per berkas dan umur berkas sementara.
    unggah_maks_bytes: int = Field(300 * 1024**2, ge=1_048_576)
    #: Ukuran satu potongan. Di atas 100 MiB ditolak saat startup karena body
    #: request dibatasi proxy pusat 128 MiB.
    unggah_potongan_bytes: int = Field(
        16 * 1024**2,
        ge=1_048_576,
        le=100 * 1024**2,
    )
    unggah_kedaluwarsa_jam: int = Field(24, ge=1)

    # Worker pemroses job Proses A/B
    worker_enabled: bool = True
    max_workers: int = 1
    #: Jeda polling mode ``--loop`` (detik).
    worker_poll_detik: float = Field(5.0, gt=0)
    #: Heartbeat job saat worker menganggur/berjalan (detik).
    worker_heartbeat_detik: float = Field(15.0, gt=0)
    #: 0 = titik dibaca/diproses sekaligus; > 0 = per potongan (hemat memori).
    proses_chunk_titik: int = Field(0, ge=0)
    #: Job ``jalan`` yang heartbeat-nya lebih lama dari ini dianggap terhenti.
    job_timeout_menit: int = Field(10, ge=1)
    #: Anggaran RSS worker; 0 berarti tidak memeriksa.
    worker_mem_budget_mb: int = Field(800, ge=0)
    #: Berkas flock worker; kosong = ``<induk DIR_UNGGAHAN>/worker.lock``.
    worker_lock_file: str = ""
    #: Worker dianggap mati bila heartbeat lebih lama dari ini (detik).
    worker_heartbeat_timeout_detik: int = Field(60, ge=15)
    #: Retensi dan jumlah maksimum baris ``worker_event``.
    worker_event_retensi_hari: int = Field(7, ge=1)
    worker_event_maks: int = Field(5000, ge=100)

    #: Berkas JSON status backup yang ditulis ``deploy/backup.sh``. Kosong =
    #: status backup tidak dibaca (halaman menampilkan "belum dikonfigurasi").
    backup_status_file: str = ""

    @field_validator("api_prefix")
    @classmethod
    def _rapikan_prefix(cls, nilai: str) -> str:
        """Normalisasi prefix: diawali ``/`` dan tanpa ``/`` di akhir."""
        bersih = nilai.strip()
        if not bersih:
            return ""
        if not bersih.startswith("/"):
            bersih = f"/{bersih}"
        return bersih.rstrip("/")

    @field_validator("cors_origins")
    @classmethod
    def _rapikan_origin(cls, nilai: list[str]) -> list[str]:
        """Buang spasi/trailing slash agar cocok dengan header Origin browser."""
        return [satu.strip().rstrip("/") for satu in nilai if satu.strip()]

    @model_validator(mode="after")
    def _validasi_keamanan(self) -> "Settings":
        """Tolak konfigurasi auth yang berbahaya di production."""
        mode = self.env.strip().lower()
        if mode == "production" and self.auth_mode == "dev":
            raise ValueError(
                "AUTH_MODE=dev tidak boleh dipakai saat ENV=production"
            )
        if (
            mode == "production"
            and self.auth_mode == "jwt"
            and len(self.auth_secret.strip()) < 32
        ):
            raise ValueError(
                "AUTH_SECRET wajib diisi minimal 32 karakter saat ENV=production"
            )
        return self

    @property
    def database_url(self) -> str:
        """URL koneksi SQLAlchemy, dengan user/password di-escape dengan benar."""
        return URL.create(
            "mysql+pymysql",
            username=self.db_user,
            password=self.db_password,
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
            query={"charset": "utf8mb4"},
        ).render_as_string(hide_password=False)


@lru_cache
def get_settings() -> Settings:
    """Ambil setelan aplikasi (hasil dibaca sekali lalu di-cache)."""
    return Settings()
