"""Koneksi basis data (SQLAlchemy) dan sesi ORM.

Hanya backend yang mengakses MySQL (PRD §3). Engine dibuat malas (``lazy``)
supaya tes bisa memakai engine sendiri tanpa perlu server MySQL hidup.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    """Kelas dasar semua model ORM (lihat :mod:`app.models`)."""


def buat_engine(url: str, **kwargs: object) -> Engine:
    """Buat engine SQLAlchemy untuk ``url`` (dipakai app maupun tes).

    MySQL memakai ``READ COMMITTED``: dengan dua worker, ``REPEATABLE READ``
    menahan gap lock pada rentang indeks yang berdekatan, sehingga job yang
    menulis ``rekap_target``/``anomali_titik`` untuk satu kabupaten memblokir
    job kabupaten lain sampai ``Lock wait timeout exceeded`` (1205). ``READ
    COMMITTED`` hanya mengunci baris yang benar-benar disentuh. SQLite tidak
    mengenal tingkat ini, jadi hanya dipasang untuk MySQL/MariaDB.
    """
    if url.startswith("mysql"):
        kwargs.setdefault("isolation_level", "READ COMMITTED")
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_recycle=3600,
        **kwargs,  # type: ignore[arg-type]
    )


_engine: Engine | None = None
_pabrik_sesi: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    """Engine aplikasi (dibuat sekali dari ``DATABASE_URL``/``.env``)."""
    global _engine
    if _engine is None:
        _engine = buat_engine(get_settings().database_url)
    return _engine


def get_sessionmaker() -> sessionmaker[Session]:
    """Pabrik sesi aplikasi (dipakai worker dan dependency API)."""
    global _pabrik_sesi
    if _pabrik_sesi is None:
        _pabrik_sesi = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _pabrik_sesi


def get_session() -> Iterator[Session]:
    """Dependency FastAPI: satu sesi basis data per request."""
    with get_sessionmaker()() as sesi:
        yield sesi
