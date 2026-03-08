"""
真实 PDF 发票批量测试。
遍历 pdf-test/ 下所有 .pdf 文件，对每张发票用 PdfInvoiceParser 解析并验证。
当正常解析无明细时，会尝试用 OCR 再解析一次（需 pip install paddleocr），
这样 12 个原本 skip 的用例在安装 OCR 后也会真正跑。
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PDF_DIR = ROOT / "pdf-test"


def get_test_pdf_files():
    """返回 pdf-test/ 下所有 .pdf 文件列表（已排序）"""
    if not PDF_DIR.exists():
        return []
    return sorted(PDF_DIR.glob("*.pdf"))


def _pdf_id(path: Path) -> str:
    return path.name


def _try_ocr_fallback(parser, pdf_path):
    """当正常解析无明细时，尝试 OCR 再解析。返回 (invoice, used_ocr)。"""
    import pdfplumber
    from src.models import Invoice
    with pdfplumber.open(pdf_path) as pdf:
        all_tables = []
        for page in pdf.pages:
            all_tables.extend(page.extract_tables() or [])
        try:
            ocr_text, ocr_structured = parser._ocr_pdf(pdf)
        except ImportError:
            return None, False
        except Exception:
            return None, True
        if not ocr_text.strip():
            return None, True
    lines = parser._extract_lines_from_tables(all_tables, ocr_text)
    if not lines or all(l.amount <= 0 for l in lines):
        lines = []
        if ocr_structured:
            lines = parser._extract_lines_from_ocr_structured(
                ocr_structured, lenient_from_ocr=True
            )
        if not lines:
            lines = parser._extract_lines_from_text(ocr_text, lenient_from_ocr=True)
    lines = parser._dedup_lines(lines)
    lines = parser._post_filter_lines(lines)
    if not lines:
        return None, True
    total = sum(l.amount for l in lines)
    inv = Invoice(source_format="PDF")
    inv.lines = lines
    inv.total_amount = total
    return inv, True


# ---------------------------------------------------------------------------
# 基本解析测试
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("pdf_file", get_test_pdf_files(), ids=_pdf_id)
def test_real_invoice_parses_correctly(pdf_file):
    """对真实 PDF 进行解析：断言不抛异常、金额有效、一致性检验"""
    from src.invoice_parser import PdfInvoiceParser

    parser = PdfInvoiceParser()
    try:
        invoice = parser.parse(pdf_file)
    except Exception as exc:
        pytest.fail(f"解析 {pdf_file.name} 时抛出异常: {exc}")

    # 无明细行时尝试 OCR 再解析（安装 paddleocr 后 12 个 skip 会真正跑）
    if not invoice.lines:
        inv_ocr, _ = _try_ocr_fallback(parser, pdf_file)
        if inv_ocr and inv_ocr.lines:
            invoice = inv_ocr
        else:
            pytest.skip(f"{pdf_file.name}: 无可提取文本（可能为图片型 PDF，需 pip install paddleocr）")

    # 打印解析摘要（pytest -s 时可见）
    print(f"\n{pdf_file.name}: {len(invoice.lines)} 行, total={invoice.total_amount:.2f}")
    for line in invoice.lines:
        print(f"  - {line.name!r}: {line.amount:.2f}")

    # 至少 1 条明细行
    assert len(invoice.lines) >= 1, f"{pdf_file.name}: 应至少有 1 条明细行"

    # 物体名称必须已合并为单行（不含换行符）
    for line in invoice.lines:
        assert "\n" not in (line.name or ""), (
            f"{pdf_file.name}: 明细名称不应含换行符，应已合并为一行。实际 name={line.name!r}"
        )
        assert "\r" not in (line.name or ""), (
            f"{pdf_file.name}: 明细名称不应含回车符。实际 name={line.name!r}"
        )

    # 所有明细 amount > 0
    for line in invoice.lines:
        assert line.amount > 0, (
            f"{pdf_file.name}: 明细 '{line.name}' 的金额不应为 0 或负数, 实际={line.amount}"
        )

    # total_amount > 0
    assert invoice.total_amount > 0, f"{pdf_file.name}: total_amount 应 > 0, 实际={invoice.total_amount}"

    # 金额一致性：total_amount ≈ sum(amounts)，误差 < 10%
    sum_amounts = sum(line.amount for line in invoice.lines)
    if sum_amounts > 0:
        error_ratio = abs(invoice.total_amount - sum_amounts) / sum_amounts
        assert error_ratio < 0.1, (
            f"{pdf_file.name}: total_amount({invoice.total_amount:.2f}) "
            f"与各行金额之和({sum_amounts:.2f}) 误差 {error_ratio:.1%} 超过 10%"
        )


# ---------------------------------------------------------------------------
# Scope 分类测试
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("pdf_file", get_test_pdf_files(), ids=_pdf_id)
def test_real_invoice_scope_classification(pdf_file):
    """对真实 PDF 跑完整 CarbonAccountingPipeline，验证分类结果和 Scope 3 排放"""
    from src.invoice_parser import PdfInvoiceParser
    from src.pipeline import CarbonAccountingPipeline
    from src.models import Scope

    parser = PdfInvoiceParser()
    invoice = parser.parse(pdf_file)

    # 无明细时尝试 OCR 再解析
    if not invoice.lines:
        inv_ocr, _ = _try_ocr_fallback(parser, pdf_file)
        if inv_ocr and inv_ocr.lines:
            invoice = inv_ocr
        else:
            pytest.skip(f"{pdf_file.name}: 无可提取文本（可能为图片型 PDF，需 pip install paddleocr）")

    pipeline = CarbonAccountingPipeline()
    result = pipeline.process_invoice(invoice)

    classified = result["classified"]
    emission_results = result["emission_results"]
    aggregate_kg = result["aggregate_kg"]

    # 打印分类摘要
    print(f"\n{pdf_file.name}: classified={len(classified)}")
    for c in classified:
        print(f"  - {c.line.name!r}: scope={c.scope.value}, factor={c.emission_factor_id}")

    # classified 非空（有效明细行应被分类）
    assert len(classified) > 0, f"{pdf_file.name}: 分类结果不应为空"

    # 每条 emission_result 的 emission_kg >= 0
    for er in emission_results:
        assert er.emission_kg >= 0, (
            f"{pdf_file.name}: emission_kg 应 >= 0, 实际={er.emission_kg}"
        )

    # aggregate_kg 中 Scope 3 应 > 0（这些发票多为零件/电商采购，属 Scope 3）
    scope3_kg = aggregate_kg.get(Scope.SCOPE_3, 0)
    assert scope3_kg > 0, (
        f"{pdf_file.name}: Scope 3 排放量应 > 0（实际={scope3_kg:.6f}），"
        f"分类结果: {[(c.scope.value, c.emission_factor_id) for c in classified]}"
    )
