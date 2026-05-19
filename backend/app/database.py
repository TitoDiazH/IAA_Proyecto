import time
from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.config import get_settings


settings = get_settings()

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


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
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            Base.metadata.create_all(bind=engine)
            return
        except Exception as exc:  # pragma: no cover - defensive startup loop
            last_error = exc
            time.sleep(delay_seconds)

    raise RuntimeError("Could not connect to the database") from last_error

