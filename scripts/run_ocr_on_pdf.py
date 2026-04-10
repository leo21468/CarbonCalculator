"""Run OCR on a PDF and print raw text and structured rows."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/run_ocr_on_pdf.py <pdf_path>")
        return
    path = Path(sys.argv[1]).expanduser().resolve()
    if not path.exists():
        print("Not found:", path)
        return
    import pdfplumber
    with pdfplumber.open(path) as pdf:
        text = ""
        for p in pdf.pages:
            text += (p.extract_text() or "") + "\n"
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
        for i, page in enumerate(ocr_structured[:1]):
            for j, row in enumerate(page.get("rows", [])[:20]):
                print("  row", j, row.get("columns") or row.get("text"))
    except Exception as e:
        print("OCR failed:", e)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
