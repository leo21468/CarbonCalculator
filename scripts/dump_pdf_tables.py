"""Dump raw tables and text from a PDF for debugging."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def main():
    path = ROOT / "pdf-test" / "9.95元+14队+英制螺丝.pdf"
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
    path2 = ROOT / "pdf-test" / "9元+14队+502强力胶.pdf"
    if path2.exists():
        print("\n" + "="*60 + "\n9元 PDF\n" + "="*60)
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
