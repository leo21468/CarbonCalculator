"""Dump raw tables and text from a PDF for debugging."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/dump_pdf_tables.py <pdf_path> [second_pdf_path]")
        return
    path = Path(sys.argv[1]).expanduser().resolve()
    if not path.exists():
        print("File not found:", path)
        return
    import pdfplumber
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            tables = page.extract_tables() or []
            print("=== PAGE", i + 1, "===")
            print("--- text (first 2000 chars) ---")
            print(text[:2000])
            print("--- tables ---")
            for ti, t in enumerate(tables):
                print(f"Table {ti}: {len(t)} rows")
                for ri, row in enumerate(t[:12]):
                    print(f"  [{ri}]", row)
            if len(tables) and len(tables[0]) > 12:
                print("  ...")
    path2 = None
    if len(sys.argv) >= 3:
        path2 = Path(sys.argv[2]).expanduser().resolve()
    if path2 and path2.exists():
        print("\n" + "=" * 60 + "\nSECOND PDF\n" + "=" * 60)
        with pdfplumber.open(path2) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                tables = page.extract_tables() or []
                print("--- text len:", len(text), "---")
                print(text[:1500])
                print("--- tables ---")
                for ti, t in enumerate(tables):
                    print(f"Table {ti}: {len(t)} rows")
                    for ri, row in enumerate(t[:15]):
                        print(f"  [{ri}]", row)

if __name__ == "__main__":
    main()
