from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import fitz

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.pdf_extractor import clean_pdf_text
from app.services.section_extractor import extract_sections_from_text


@dataclass(frozen=True)
class Word:
    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    block_no: int
    line_no: int
    word_no: int


def _safe_name(path: Path) -> str:
    name = path.stem.strip() or "pdf"
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("._") or "pdf"


def _selected_pages(total_pages: int, pages: set[int] | None) -> Iterable[int]:
    for page_number in range(1, total_pages + 1):
        if not pages or page_number in pages:
            yield page_number


def _write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _write_blocks(path: Path, block_rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["page", "x0", "y0", "x1", "y1", "block_no", "block_type", "text"],
            delimiter="\t",
        )
        writer.writeheader()
        writer.writerows(block_rows)


def _write_words(path: Path, words: list[Word]) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file, delimiter="\t")
        writer.writerow(["page", "x0", "y0", "x1", "y1", "block_no", "line_no", "word_no", "text"])
        for word in words:
            writer.writerow(
                [
                    word.page,
                    f"{word.x0:.2f}",
                    f"{word.y0:.2f}",
                    f"{word.x1:.2f}",
                    f"{word.y1:.2f}",
                    word.block_no,
                    word.line_no,
                    word.word_no,
                    word.text,
                ]
            )


def _group_words_into_rows(words: list[Word], y_tolerance: float) -> list[list[Word]]:
    rows: list[list[Word]] = []
    row_baselines: list[float] = []

    for word in sorted(words, key=lambda item: (item.page, item.y0, item.x0)):
        matched_index: int | None = None
        for index, baseline in enumerate(row_baselines):
            same_page = rows[index] and rows[index][0].page == word.page
            if same_page and abs(word.y0 - baseline) <= y_tolerance:
                matched_index = index
                break

        if matched_index is None:
            rows.append([word])
            row_baselines.append(word.y0)
            continue

        rows[matched_index].append(word)
        row_baselines[matched_index] = (
            row_baselines[matched_index] * (len(rows[matched_index]) - 1) + word.y0
        ) / len(rows[matched_index])

    return [sorted(row, key=lambda item: item.x0) for row in rows]


def _format_rows(words: list[Word], y_tolerance: float) -> str:
    lines: list[str] = []
    current_page: int | None = None
    for row in _group_words_into_rows(words, y_tolerance):
        if not row:
            continue
        page = row[0].page
        if page != current_page:
            current_page = page
            lines.append(f"\n=== PAGE {page} VISUAL ROWS ===")
        y0 = sum(word.y0 for word in row) / len(row)
        text = " ".join(word.text for word in row)
        lines.append(f"y={y0:.2f}\t{text}")
    return "\n".join(lines).strip() + "\n"


def _format_blocks(block_rows: list[dict[str, object]]) -> str:
    lines: list[str] = []
    current_page: int | None = None
    for block in block_rows:
        page = int(block["page"])
        if page != current_page:
            current_page = page
            lines.append(f"\n=== PAGE {page} BLOCKS ===")
        lines.append(
            "[{x0:.2f},{y0:.2f},{x1:.2f},{y1:.2f}] b{block_no} t{block_type}: {text!r}".format(
                x0=float(block["x0"]),
                y0=float(block["y0"]),
                x1=float(block["x1"]),
                y1=float(block["y1"]),
                block_no=block["block_no"],
                block_type=block["block_type"],
                text=block["text"],
            )
        )
    return "\n".join(lines).strip() + "\n"


def debug_pdf(path: Path, output_root: Path, max_chars: int, pages: set[int] | None, y_tolerance: float) -> Path:
    if not path.exists():
        raise FileNotFoundError(path)
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a PDF file: {path}")

    output_dir = output_root / _safe_name(path)
    output_dir.mkdir(parents=True, exist_ok=True)

    plain_pages: list[str] = []
    sorted_pages: list[str] = []
    block_rows: list[dict[str, object]] = []
    words: list[Word] = []

    document = fitz.open(str(path))
    try:
        selected = set(_selected_pages(document.page_count, pages))
        for page_number in selected:
            page = document.load_page(page_number - 1)
            plain_pages.append(f"\n--- Pagina {page_number} ---\n{page.get_text('text') or ''}")
            sorted_pages.append(
                f"\n--- Pagina {page_number} ---\n{page.get_text('text', sort=True) or ''}"
            )

            for block in page.get_text("blocks", sort=True):
                x0, y0, x1, y1, text, block_no, block_type = block[:7]
                block_rows.append(
                    {
                        "page": page_number,
                        "x0": f"{x0:.2f}",
                        "y0": f"{y0:.2f}",
                        "x1": f"{x1:.2f}",
                        "y1": f"{y1:.2f}",
                        "block_no": block_no,
                        "block_type": block_type,
                        "text": text,
                    }
                )

            for raw_word in page.get_text("words", sort=True):
                x0, y0, x1, y1, text, block_no, line_no, word_no = raw_word[:8]
                words.append(
                    Word(
                        page=page_number,
                        x0=x0,
                        y0=y0,
                        x1=x1,
                        y1=y1,
                        text=text,
                        block_no=block_no,
                        line_no=line_no,
                        word_no=word_no,
                    )
                )
    finally:
        document.close()

    plain_raw = "\n".join(plain_pages)
    sorted_raw = "\n".join(sorted_pages)
    plain_clean = clean_pdf_text(plain_raw)
    sorted_clean = clean_pdf_text(sorted_raw)
    sections = extract_sections_from_text(plain_clean, max_chars)

    _write_text(output_dir / "text_raw_current_pymupdf.txt", plain_raw.strip() + "\n")
    _write_text(output_dir / "text_clean_current_app.txt", plain_clean + "\n")
    _write_text(output_dir / "text_sorted_pymupdf.txt", sorted_clean + "\n")
    _write_blocks(output_dir / "blocks.tsv", block_rows)
    _write_text(output_dir / "blocks.txt", _format_blocks(block_rows))
    _write_words(output_dir / "words.tsv", words)
    _write_text(output_dir / "visual_rows_from_words.txt", _format_rows(words, y_tolerance))
    _write_text(
        output_dir / "sections.json",
        json.dumps(sections, ensure_ascii=False, indent=2) + "\n",
    )

    sections_dir = output_dir / "sections"
    sections_dir.mkdir(exist_ok=True)
    for section_key, section in sections.items():
        _write_text(sections_dir / f"{section_key}.txt", str(section.get("source_excerpt") or "") + "\n")

    manifest = {
        "pdf": str(path),
        "output_dir": str(output_dir),
        "pages": sorted(selected),
        "max_chars": max_chars,
        "y_tolerance": y_tolerance,
        "files": [
            "text_raw_current_pymupdf.txt",
            "text_clean_current_app.txt",
            "text_sorted_pymupdf.txt",
            "blocks.tsv",
            "blocks.txt",
            "words.tsv",
            "visual_rows_from_words.txt",
            "sections.json",
            "sections/*.txt",
        ],
    }
    _write_text(output_dir / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return output_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dump PyMuPDF text, blocks, words, visual rows and app section cuts for syllabus PDFs."
    )
    parser.add_argument("pdfs", nargs="+", type=Path, help="PDF file path(s) to inspect.")
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=Path("debug_pdf_output"),
        help="Directory where debug artifacts will be written.",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=50000,
        help="Maximum characters per extracted section, matching the app setting by default.",
    )
    parser.add_argument(
        "--page",
        action="append",
        type=int,
        dest="pages",
        help="Restrict output to a page number. Repeat the option for multiple pages.",
    )
    parser.add_argument(
        "--y-tolerance",
        type=float,
        default=3.0,
        help="Vertical tolerance used to reconstruct visual rows from words.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    page_filter = set(args.pages) if args.pages else None
    args.output_dir.mkdir(parents=True, exist_ok=True)

    for pdf in args.pdfs:
        output_dir = debug_pdf(pdf, args.output_dir, args.max_chars, page_filter, args.y_tolerance)
        print(output_dir)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
