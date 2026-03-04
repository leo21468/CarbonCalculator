"""测试 MyOCR2InvoiceAdapter：myocr2-invoice OCR 适配器"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest
from src.ocr_adapter import MyOCR2InvoiceAdapter
from src.invoice_parser import _build_invoice_from_dict

# ---------------------------------------------------------------------------
# 完整示例 OCR 结果（与问题描述中的样本一致）
# ---------------------------------------------------------------------------
SAMPLE_OCR = {
    "invoice_code": "012002200311",
    "invoice_number": "12345678",
    "issue_date": "2023年01月15日",
    "buyer_name": "某某公司",
    "buyer_code": "91310000XXXXXXXX",
    "seller_name": "供应商有限公司",
    "seller_code": "91310000YYYYYYYY",
    "tax_exclusive_total_amount": "¥8,849.56",
    "tax_inclusive_total_amount": "¥10,000.00",
    "tax_total_amount": "¥1,150.44",
    "items": [
        {
            "item_name": "*电子元器件*电容",
            "item_type": "规格型号A",
            "item_unit": "个",
            "item_number": "100",
            "item_price": "88.4956",
            "item_amount": "8849.56",
            "item_tax_rate": "13%",
            "item_tax": "1150.44",
            "item_serial_number": "1",
        }
    ],
}


class TestMyOCR2InvoiceAdapterConvert:
    """测试 MyOCR2InvoiceAdapter.convert 静态方法"""

    def test_full_field_conversion(self):
        """测试 1：完整字段转换（含 items）"""
        result = MyOCR2InvoiceAdapter.convert(SAMPLE_OCR)

        assert result["invoice_code"] == "012002200311"
        assert result["invoice_number"] == "12345678"
        assert result["seller"]["name"] == "供应商有限公司"
        assert result["seller"]["tax_id"] == "91310000YYYYYYYY"
        assert result["buyer"]["name"] == "某某公司"
        assert result["buyer"]["tax_id"] == "91310000XXXXXXXX"
        assert len(result["lines"]) == 1
        line = result["lines"][0]
        assert line["name"] == "*电子元器件*电容"
        assert line["unit"] == "个"

    def test_date_conversion(self):
        """测试 2：日期格式转换（YYYY年MM月DD日 → YYYY-MM-DD）"""
        result = MyOCR2InvoiceAdapter.convert(SAMPLE_OCR)
        assert result["date"] == "2023-01-15"

    def test_date_single_digit_month_day(self):
        """测试 2b：单位数月/日也能正确补零"""
        ocr = dict(SAMPLE_OCR, issue_date="2023年3月5日")
        result = MyOCR2InvoiceAdapter.convert(ocr)
        assert result["date"] == "2023-03-05"

    def test_amount_parsing(self):
        """测试 3：金额解析（¥8,849.56 → 8849.56）"""
        result = MyOCR2InvoiceAdapter.convert(SAMPLE_OCR)
        assert result["total_amount"] == pytest.approx(8849.56, rel=1e-5)
        assert result["lines"][0]["amount"] == pytest.approx(8849.56, rel=1e-5)

    def test_tax_fields_excluded_from_lines(self):
        """测试 4：item_tax_rate 和 item_tax 不出现在 lines[i] 中"""
        result = MyOCR2InvoiceAdapter.convert(SAMPLE_OCR)
        for line in result["lines"]:
            assert "item_tax_rate" not in line, "item_tax_rate 不应出现在 lines 中"
            assert "item_tax" not in line, "item_tax 不应出现在 lines 中"
            assert "tax_rate" not in line, "tax_rate 不应出现在 lines 中"
            assert "tax" not in line, "tax 不应出现在 lines 中"

    def test_empty_items_gives_empty_lines(self):
        """测试 5：items 为空时，lines = []"""
        ocr = dict(SAMPLE_OCR, items=[])
        result = MyOCR2InvoiceAdapter.convert(ocr)
        assert result["lines"] == []

    def test_missing_items_key_gives_empty_lines(self):
        """测试 5b：无 items 键时，lines = []"""
        ocr = {k: v for k, v in SAMPLE_OCR.items() if k != "items"}
        result = MyOCR2InvoiceAdapter.convert(ocr)
        assert result["lines"] == []

    def test_invalid_item_number_falls_back_to_none(self):
        """测试 6：item_number 非法值（空字符串）时，quantity = None"""
        ocr = dict(
            SAMPLE_OCR,
            items=[dict(SAMPLE_OCR["items"][0], item_number="")],
        )
        result = MyOCR2InvoiceAdapter.convert(ocr)
        assert result["lines"][0]["quantity"] is None

    def test_invalid_item_price_falls_back_to_none(self):
        """测试 6b：item_price 非法值（非数字字符串）时，unit_price = None"""
        ocr = dict(
            SAMPLE_OCR,
            items=[dict(SAMPLE_OCR["items"][0], item_price="N/A")],
        )
        result = MyOCR2InvoiceAdapter.convert(ocr)
        assert result["lines"][0]["unit_price"] is None

    def test_quantity_and_unit_price_parsed_as_float(self):
        """item_number/item_price 合法时应解析为 float"""
        result = MyOCR2InvoiceAdapter.convert(SAMPLE_OCR)
        line = result["lines"][0]
        assert line["quantity"] == pytest.approx(100.0)
        assert line["unit_price"] == pytest.approx(88.4956, rel=1e-5)

    def test_end_to_end_with_build_invoice_from_dict(self):
        """测试 7：convert 输出可直接传给 _build_invoice_from_dict（端到端验证）"""
        data = MyOCR2InvoiceAdapter.convert(SAMPLE_OCR)
        # _build_invoice_from_dict 不应抛出异常
        invoice = _build_invoice_from_dict(data)
        assert invoice.invoice_code == "012002200311"
        assert invoice.date == "2023-01-15"
        assert abs(invoice.total_amount - 8849.56) < 0.01
        assert invoice.seller is not None
        assert invoice.seller.name == "供应商有限公司"
        assert len(invoice.lines) == 1
        assert invoice.lines[0].name == "*电子元器件*电容"
        assert abs(invoice.lines[0].amount - 8849.56) < 0.01
