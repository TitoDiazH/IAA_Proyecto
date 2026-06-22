import time
from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from sqlalchemy.exc import OperationalError

from app.config import get_settings


settings = get_settings()

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def _is_postgres_url(url: URL) -> bool:
    return url.drivername.startswith("postgresql")


def _database_missing(exc: Exception, database_name: str) -> bool:
    message = str(exc).lower()
    return "does not exist" in message and database_name.lower() in message


def _connection_error_is_non_retryable(exc: Exception) -> bool:
    """Avoid hammering the remote pooler with invalid credentials."""

    message = str(exc).lower()
    return any(
        marker in message
        for marker in (
            "password authentication failed",
            "too many authentication failures",
            "ecircuitbreaker",
            "tenant or user not found",
        )
    )


def _ensure_database_exists() -> None:
    """Create the configured PostgreSQL database when a reused volume lacks it."""

    url = make_url(settings.database_url)
    database_name = url.database
    if not database_name or not _is_postgres_url(url):
        return

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return
    except OperationalError as exc:
        if not _database_missing(exc, database_name):
            raise

    maintenance_url = url.set(database="postgres")
    maintenance_engine = create_engine(maintenance_url, isolation_level="AUTOCOMMIT", pool_pre_ping=True)
    try:
        with maintenance_engine.connect() as connection:
            quoted_database = maintenance_engine.dialect.identifier_preparer.quote(database_name)
            connection.execute(text(f"CREATE DATABASE {quoted_database}"))
    finally:
        maintenance_engine.dispose()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db(max_attempts: int = 30, delay_seconds: float = 1.5) -> None:
    """Wait for PostgreSQL and create tables for the MVP.

    The project intentionally avoids Alembic migrations to keep the demo easy to
    run. For a production system, replace this with versioned migrations.
    """

    from app import models  # noqa: F401  Import model metadata before create_all.

    last_error: Exception | None = None
    for _ in range(max_attempts):
        try:
            _ensure_database_exists()
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            Base.metadata.create_all(bind=engine)
            return
        except Exception as exc:  # pragma: no cover - defensive startup loop
            last_error = exc
            if _connection_error_is_non_retryable(exc):
                break
            time.sleep(delay_seconds)

    raise RuntimeError("Could not connect to the database") from last_error
