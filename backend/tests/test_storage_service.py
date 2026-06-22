from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Syllabus
from app.services import storage_service, upload_service


def test_storage_uri_round_trip_preserves_object_key():
    uri = storage_service.build_storage_uri(
        "202610/2207/id_programa curso.pdf",
        bucket="syllabi",
    )

    assert uri == "supabase://syllabi/202610/2207/id_programa%20curso.pdf"
    assert storage_service.parse_storage_uri(uri) == (
        "syllabi",
        "202610/2207/id_programa curso.pdf",
    )


def test_materialize_remote_pdf_uses_original_filename(monkeypatch):
    monkeypatch.setattr(storage_service, "download_pdf", lambda stored_path: b"pdf-content")

    with storage_service.materialize_pdf(
        "supabase://syllabi/202610/2207/object.pdf",
        "202610-ING-2207-NRC-7542-CURSO.pdf",
    ) as path:
        assert path.name == "202610-ING-2207-NRC-7542-CURSO.pdf"
        assert path.read_bytes() == b"pdf-content"
        materialized_path = Path(path)

    assert not materialized_path.exists()


def test_zip_upload_persists_supabase_uri(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()

    monkeypatch.setattr(upload_service, "extract_pdf_text", lambda path: "contenido extraído")
    monkeypatch.setattr(
        upload_service,
        "upload_pdf",
        lambda object_key, content: f"supabase://syllabi/{object_key}",
    )
    monkeypatch.setattr(upload_service, "enqueue_report_analysis", lambda report_id: None)

    archive_bytes = BytesIO()
    with ZipFile(archive_bytes, "w") as archive:
        archive.writestr(
            "202610-ING-2207-NRC-7542-TERMODINAMICA.pdf",
            b"%PDF-fake",
        )

    result = upload_service.process_zip_upload(
        db,
        "syllabi.zip",
        archive_bytes.getvalue(),
    )

    syllabus = db.query(Syllabus).one()
    assert result["accepted_count"] == 1
    assert result["rejected_count"] == 0
    assert syllabus.stored_path.startswith("supabase://syllabi/202610/ING2207/")
    assert syllabus.text_content == "contenido extraído"

    db.close()
    engine.dispose()


def test_upload_pdf_uses_private_bucket_client(monkeypatch):
    calls = []

    class FakeBucket:
        def upload(self, **kwargs):
            calls.append(kwargs)

    class FakeStorage:
        def from_(self, bucket):
            assert bucket == "syllabi"
            return FakeBucket()

    fake_client = SimpleNamespace(storage=FakeStorage())
    monkeypatch.setattr(storage_service, "_get_client", lambda: fake_client)
    monkeypatch.setattr(
        storage_service,
        "get_settings",
        lambda: SimpleNamespace(supabase_storage_bucket="syllabi"),
    )

    uri = storage_service.upload_pdf("period/course/file.pdf", b"pdf")

    assert uri == "supabase://syllabi/period/course/file.pdf"
    assert calls == [
        {
            "path": "period/course/file.pdf",
            "file": b"pdf",
            "file_options": {"content-type": "application/pdf", "upsert": "false"},
        }
    ]
