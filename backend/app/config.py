"""Konfigurasi aplikasi; nilai dibaca dari variabel lingkungan / file `.env`."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Setelan aplikasi pointse."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "pointse"
    debug: bool = False

    # Basis data MySQL (hanya backend yang mengaksesnya)
    db_host: str = "localhost"
    db_port: int = 3306
    db_user: str = ""
    db_password: str = ""
    db_name: str = "pointse"

    # CORS: hanya domain frontend yang boleh memanggil API
    cors_origins: list[str] = []

    # Unggahan berkas mentah (GPKG/GeoJSON) disimpan di disk server, bukan di DB
    dir_unggahan: str = "data/unggahan"

    # Worker pemroses job Proses A/B
    worker_enabled: bool = True
    max_workers: int = 1
    interval_polling: float = 1.0
    #: 0 = titik dibaca/diproses sekaligus; > 0 = per potongan (hemat memori).
    proses_chunk_titik: int = Field(0, ge=0)
    #: Job ``jalan`` yang heartbeat-nya lebih lama dari ini dianggap terhenti.
    job_timeout_menit: int = Field(10, ge=1)

    @property
    def database_url(self) -> str:
        """URL koneksi SQLAlchemy untuk MySQL (driver PyMySQL)."""
        return (
            f"mysql+pymysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"
        )


@lru_cache
def get_settings() -> Settings:
    """Ambil setelan aplikasi (hasil dibaca sekali lalu di-cache)."""
    return Settings()
