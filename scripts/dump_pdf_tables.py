"""Dump raw tables and text from PDF files for debugging."""
import argparse
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dump text and extracted tables from PDF files.")
    parser.add_argument("pdf_path", help="Path to first PDF")
    parser.add_argument("second_pdf_path", nargs="?", default=None, help="Optional second PDF")
    return parser.parse_args()


def _dump_pdf(path: Path, label: str = "PAGE") -> None:
    import pdfplumber

    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            tables = page.extract_tables() or []
            print(f"=== {label} {i + 1} ===")
            print("--- text (first 2000 chars) ---")
            print(text[:2000])
            print("--- tables ---")
            for ti, table in enumerate(tables):
                print(f"Table {ti}: {len(table)} rows")
                for ri, row in enumerate(table[:12]):
                    print(f"  [{ri}]", row)
            if len(tables) and len(tables[0]) > 12:
                print("  ...")


def main():
    args = _parse_args()
    first = Path(args.pdf_path).expanduser().resolve()
    if not first.exists():
        print("File not found:", first)
        return
    _dump_pdf(first, "PAGE")

    if args.second_pdf_path:
        second = Path(args.second_pdf_path).expanduser().resolve()
        if not second.exists():
            print("Second file not found:", second)
            return
        print("\n" + "=" * 60 + "\nSECOND PDF\n" + "=" * 60)
        _dump_pdf(second, "SECOND PAGE")


if __name__ == "__main__":
    main()
