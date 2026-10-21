"""Konfigurasi Alembic untuk skema pointse (MySQL).

URL basis data diambil dari: ``-x url=...`` saat menjalankan alembic, lalu
``sqlalchemy.url`` di alembic.ini, terakhir dari setelan aplikasi (``DB_*`` di
``.env``). Jadi kredensial tidak pernah ditulis di repo.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import get_settings
from app.db import Base
from app.models import (  # noqa: F401 - daftar model
    Aktivitas,
    PenggunaAktif,
    RekapDesa,
    RekapKabupaten,
    Run,
    TitikHasil,
    Wilayah,
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def url_basis_data() -> str:
    """URL koneksi basis data yang dipakai alembic."""
    argumen = context.get_x_argument(as_dictionary=True)
    return (
        argumen.get("url")
        or config.get_main_option("sqlalchemy.url")
        or get_settings().database_url
    )


def run_migrations_offline() -> None:
    """Buat SQL migrasi saja (tanpa koneksi), mis. untuk ditinjau DBA."""
    context.configure(
        url=url_basis_data(),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Jalankan migrasi ke basis data."""
    bagian = config.get_section(config.config_ini_section) or {}
    bagian["sqlalchemy.url"] = url_basis_data()
    mesin = engine_from_config(bagian, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with mesin.connect() as koneksi:
        context.configure(
            connection=koneksi, target_metadata=target_metadata, compare_type=True
        )
        with context.begin_transaction():
            context.run_migrations()

    mesin.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
