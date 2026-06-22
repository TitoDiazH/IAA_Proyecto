from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterator
from urllib.parse import quote, unquote, urlparse

from supabase import Client, create_client

from app.config import get_settings


STORAGE_SCHEME = "supabase"


class StorageError(RuntimeError):
    """Raised when a PDF cannot be persisted in or read from object storage."""


@lru_cache
def _get_client() -> Client:
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_backend_key:
        raise StorageError(
            "Faltan SUPABASE_URL y SUPABASE_SECRET_KEY "
            "(o SUPABASE_SERVICE_ROLE_KEY) en la configuración del backend"
        )
    return create_client(settings.supabase_url, settings.supabase_backend_key)


def build_storage_uri(object_key: str, bucket: str | None = None) -> str:
    selected_bucket = bucket or get_settings().supabase_storage_bucket
    clean_key = object_key.strip("/")
    if not selected_bucket or not clean_key:
        raise ValueError("El bucket y la clave del objeto son obligatorios")
    return f"{STORAGE_SCHEME}://{selected_bucket}/{quote(clean_key, safe='/')}"


def parse_storage_uri(value: str) -> tuple[str, str] | None:
    parsed = urlparse(value)
    if parsed.scheme != STORAGE_SCHEME:
        return None
    bucket = parsed.netloc
    object_key = unquote(parsed.path.lstrip("/"))
    if not bucket or not object_key:
        raise StorageError("La referencia de almacenamiento Supabase no es válida")
    return bucket, object_key


def upload_pdf(object_key: str, content: bytes) -> str:
    settings = get_settings()
    bucket = settings.supabase_storage_bucket
    try:
        _get_client().storage.from_(bucket).upload(
            path=object_key,
            file=content,
            file_options={"content-type": "application/pdf", "upsert": "false"},
        )
    except Exception as exc:
        raise StorageError(f"No se pudo subir el PDF a Supabase Storage: {exc}") from exc
    return build_storage_uri(object_key, bucket)


def download_pdf(stored_path: str) -> bytes:
    remote = parse_storage_uri(stored_path)
    if remote is None:
        path = Path(stored_path)
        if not path.is_file():
            raise StorageError("El archivo PDF ya no existe en el almacenamiento local")
        return path.read_bytes()

    bucket, object_key = remote
    try:
        return _get_client().storage.from_(bucket).download(object_key)
    except Exception as exc:
        raise StorageError(f"No se pudo descargar el PDF desde Supabase Storage: {exc}") from exc


def delete_pdf(stored_path: str) -> None:
    remote = parse_storage_uri(stored_path)
    if remote is None:
        path = Path(stored_path)
        if path.is_file():
            path.unlink()
        return

    bucket, object_key = remote
    try:
        _get_client().storage.from_(bucket).remove([object_key])
    except Exception as exc:
        raise StorageError(f"No se pudo eliminar el PDF de Supabase Storage: {exc}") from exc


@contextmanager
def materialize_pdf_bytes(content: bytes, original_filename: str) -> Iterator[Path]:
    safe_filename = Path(original_filename).name or "syllabus.pdf"
    with TemporaryDirectory(prefix="syllabus-") as temp_dir:
        temp_path = Path(temp_dir) / safe_filename
        temp_path.write_bytes(content)
        yield temp_path


@contextmanager
def materialize_pdf(stored_path: str, original_filename: str) -> Iterator[Path]:
    """Yield a local path for extractors, downloading remote objects temporarily."""

    local_path = Path(stored_path)
    if parse_storage_uri(stored_path) is None and local_path.is_file():
        yield local_path
        return

    with materialize_pdf_bytes(download_pdf(stored_path), original_filename) as temp_path:
        yield temp_path
