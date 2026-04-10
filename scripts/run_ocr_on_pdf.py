"""Run OCR on a PDF and print raw text and structured rows."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run OCR on a PDF and print summary output.")
    parser.add_argument("pdf_path", help="Path to input PDF file")
    return parser.parse_args()


def main():
    args = _parse_args()
    path = Path(args.pdf_path).expanduser().resolve()
    if not path.exists():
        print("Not found:", path)
        return

    import pdfplumber

    with pdfplumber.open(path) as pdf:
        text = "\n".join((p.extract_text() or "") for p in pdf.pages)
        print("extract_text length:", len(text))
        print("text preview:", repr(text[:500]))

    print("\n--- Trying OCR ---")
    try:
        from src.invoice_parser import PdfInvoiceParser

        parser = PdfInvoiceParser()
        with pdfplumber.open(path) as pdf:
            ocr_text, ocr_structured = parser._ocr_pdf(pdf)
        print("OCR text length:", len(ocr_text))
        print("OCR text preview:", repr(ocr_text[:1500]))
        print("OCR structured pages:", len(ocr_structured))
        for page in ocr_structured[:1]:
            for j, row in enumerate(page.get("rows", [])[:20]):
                print("  row", j, row.get("columns") or row.get("text"))
    except Exception as exc:
        print("OCR failed:", exc)
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
