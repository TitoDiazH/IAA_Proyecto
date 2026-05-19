from pathlib import Path
import re
from typing import Any

from pypdf import PdfReader

try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover - fallback for minimal local envs
    fitz = None


def clean_pdf_text(text: str) -> str:
    """Normalize extracted PDF text while preserving line structure."""

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"(\w)-\n(\w)", r"\1\2", normalized)
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def split_pymupdf_page_marked_text(text: str) -> list[dict[str, Any]]:
    """Split marked PDF text into per-page blocks preserving page numbers."""

    pages: list[dict[str, Any]] = []
    current_page = 0
    current_lines: list[str] = []

    for line in text.splitlines():
        match = re.match(r"^--- Página (\d+) ---$", line.strip())
        if match:
            if current_page:
                pages.append({"page_number": current_page, "text": "\n".join(current_lines).strip()})
            current_page = int(match.group(1))
            current_lines = []
            continue

        current_lines.append(line)

    if current_page:
        pages.append({"page_number": current_page, "text": "\n".join(current_lines).strip()})

    return pages


def _extract_pdf_text_with_pymupdf(path: str | Path) -> str:
    document = fitz.open(str(path))
    pages: list[str] = []
    try:
        for index, page in enumerate(document, start=1):
            text = page.get_text("text") or ""
            pages.append(f"\n--- Página {index} ---\n{text}")
    finally:
        document.close()
    return clean_pdf_text("\n".join(pages))


def _extract_pdf_text_with_pypdf(path: str | Path) -> str:
    reader = PdfReader(str(path))
    pages: list[str] = []
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append(f"\n--- Página {index} ---\n{text}")
    return clean_pdf_text("\n".join(pages))


def extract_pdf_text(path: str | Path) -> str:
    """Extract text from a PDF, preferring PyMuPDF and falling back to pypdf.

    Scanned image-only PDFs will return little or no text. OCR is intentionally
    outside the MVP scope and is documented in README limitations.
    """

    if fitz is not None:
        return _extract_pdf_text_with_pymupdf(path)
    return _extract_pdf_text_with_pypdf(path)
