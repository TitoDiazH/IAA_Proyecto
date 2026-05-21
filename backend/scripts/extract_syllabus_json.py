from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.filename_parser import FilenameParseError, parse_syllabus_filename
from app.services.syllabus_extractor import extract_normalized_syllabus_json_from_pdf


def build_syllabus(pdf_path: Path) -> SimpleNamespace:
    try:
        parsed = parse_syllabus_filename(pdf_path.name)
        return SimpleNamespace(
            stored_path=str(pdf_path),
            original_filename=pdf_path.name,
            academic_period=parsed.academic_period,
            course_code=parsed.course_code,
            course_name=parsed.course_name,
            nrc=parsed.nrc,
        )
    except FilenameParseError:
        return SimpleNamespace(
            stored_path=str(pdf_path),
            original_filename=pdf_path.name,
            academic_period="",
            course_code="",
            course_name=pdf_path.stem,
            nrc="",
        )


def extract_pdf(pdf_path: Path, output_dir: Path) -> Path:
    syllabus = build_syllabus(pdf_path)
    result = extract_normalized_syllabus_json_from_pdf(syllabus)

    output_path = output_dir / f"{pdf_path.stem}.json"
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Extrae JSON normalizado desde PDFs de syllabus.")
    parser.add_argument(
        "input",
        nargs="?",
        default=None,
        help="PDF o carpeta con PDFs. Por defecto: storage de la raíz del proyecto.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Carpeta donde se guardan los JSON. Por defecto: storage/json de la raíz del proyecto.",
    )
    args = parser.parse_args()

    input_path = Path(args.input).resolve() if args.input else PROJECT_ROOT / "storage"
    output_dir = Path(args.output_dir).resolve() if args.output_dir else PROJECT_ROOT / "storage" / "json"
    output_dir.mkdir(parents=True, exist_ok=True)

    if input_path.is_file():
        pdfs = [input_path]
    else:
        pdfs = sorted(input_path.glob("*.pdf"))

    if not pdfs:
        print(f"No se encontraron PDFs en {input_path}")
        return 1

    for pdf_path in pdfs:
        output_path = extract_pdf(pdf_path, output_dir)
        print(f"{pdf_path.name} -> {output_path}")

    print(f"\nListo. JSON generados: {len(pdfs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
