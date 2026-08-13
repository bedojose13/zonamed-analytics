"""Motor SQLAlchemy y utilidades de sesión. SQLite por defecto (cámbialo vía ZONAMED_DATABASE_URL a Postgres en producción)."""
from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()


def _normalize_database_url(url: str) -> str:
    """Neon/Render suelen entregar URLs `postgresql://...`, que SQLAlchemy intenta abrir con
    psycopg2 por defecto. Este proyecto instala psycopg (v3) vía `psycopg[binary]`, así que
    reescribimos al dialecto explícito para que funcione sin que el usuario tenga que recordar
    el sufijo `+psycopg` al pegar la connection string."""
    if url.startswith("postgresql://") or url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1).replace("postgresql://", "postgresql+psycopg://", 1)
    return url


_database_url = _normalize_database_url(settings.database_url)
_connect_args = {"check_same_thread": False} if _database_url.startswith("sqlite") else {}
engine = create_engine(_database_url, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    """Dependencia de FastAPI: una sesión por request, cerrada siempre al final."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Uso fuera de FastAPI (scripts de seed/entrenamiento)."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    from app import models  # noqa: F401  (registra las tablas en Base.metadata)

    Base.metadata.create_all(bind=engine)
