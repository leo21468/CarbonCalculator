"""
对 pdf-test/ 下指定或全部 PDF 运行 PdfInvoiceParser，打印每条明细名称与金额。
对「无明细」的 PDF 可强制跑 OCR 再解析（需安装 paddleocr），从而把 pytest 里跳过的 12 个也真正跑一遍。
用法（在项目根目录）：
  python scripts/run_pdf_test.py
  python scripts/run_pdf_test.py "9元"
  python scripts/run_pdf_test.py --force-ocr
  python scripts/run_pdf_test.py --force-ocr "9元" test3 test4
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PDF_DIR = ROOT / "pdf-test"


def _parse_with_ocr(parser, path):
    """对 PDF 强制跑 OCR 后解析，返回 (lines, total_amount, ocr_used)。"""
    import pdfplumber
    with pdfplumber.open(path) as pdf:
        all_tables = []
        for page in pdf.pages:
            all_tables.extend(page.extract_tables() or [])
        try:
            ocr_text, ocr_structured = parser._ocr_pdf(pdf)
        except ImportError:
            return [], 0.0, False
        except Exception:
            return [], 0.0, True
        if not ocr_text.strip():
            return [], 0.0, True
        all_text = ocr_text
    lines = parser._extract_lines_from_tables(all_tables, all_text)
    if not lines or all(l.amount <= 0 for l in lines):
        lines = []
        if ocr_structured:
            lines = parser._extract_lines_from_ocr_structured(
                ocr_structured, lenient_from_ocr=True
            )
        if not lines:
            lines = parser._extract_lines_from_text(all_text, lenient_from_ocr=True)
    lines = parser._dedup_lines(lines)
    lines = parser._post_filter_lines(lines)
    total = sum(l.amount for l in lines) if lines else 0.0
    return lines, total, True


def main():
    if not PDF_DIR.exists():
        print("pdf-test 目录不存在")
        return
    argv = [a for a in sys.argv[1:] if not a.startswith("-")]
    force_ocr = "--force-ocr" in sys.argv[1:]
    pdfs = sorted(PDF_DIR.glob("*.pdf"))
    if argv:
        pdfs = [p for p in pdfs if any(f in p.name for f in argv)]
    if not pdfs:
        print("没有匹配的 PDF")
        return
    from src.invoice_parser import PdfInvoiceParser
    parser = PdfInvoiceParser()
    skipped_ran = 0
    for path in pdfs:
        print(f"\n{'='*60}\n{path.name}\n{'='*60}")
        try:
            inv = parser.parse(path.read_bytes())
            n = len(inv.lines)
            if n > 0:
                print(f"total_amount: {inv.total_amount}")
                print(f"lines: {n}")
                for i, line in enumerate(inv.lines):
                    print(f"  [{i+1}] name={line.name!r} amount={line.amount}")
            else:
                print("lines: 0 (无明细)")
                if force_ocr:
                    print("  正在强制 OCR 再解析...")
                    lines, total, ocr_used = _parse_with_ocr(parser, path)
                    if not ocr_used:
                        print("  OCR 不可用（请 pip install paddleocr）")
                    elif lines:
                        skipped_ran += 1
                        print(f"  [OCR] total_amount: {total}")
                        print(f"  [OCR] lines: {len(lines)}")
                        for i, line in enumerate(lines):
                            print(f"    [{i+1}] name={line.name!r} amount={line.amount}")
                    else:
                        print("  [OCR] 仍无明细")
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()
    if force_ocr and skipped_ran > 0:
        print(f"\n共对 {skipped_ran} 个原本无明细的 PDF 用 OCR 跑出了明细。")


if __name__ == "__main__":
    main()
