"""测试发票解析器中金额字段的正确解析（Issue #26）"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.invoice_parser import PdfInvoiceParser, JsonXmlInvoiceParser


class TestTableAmountNotUnitPrice:
    """测试表格解析时 amount 取金额列而非单价列"""

    def _make_parser(self):
        return PdfInvoiceParser()

    def test_table_amount_not_unit_price(self):
        """表头含 货物名称/数量/单位/单价/金额/税额 时，amount 应为金额列，而非单价列"""
        parser = self._make_parser()
        header = ["货物名称", "数量", "单位", "单价", "金额", "税额"]
        row = ["*电力*电费", "100", "度", "0.80", "80.00", "10.00"]
        tables = [[header, row]]
        items = parser._extract_lines_from_tables(tables, "")
        assert len(items) == 1
        assert abs(items[0].amount - 80.00) < 0.01, (
            f"amount 应为金额列 80.00，实际为 {items[0].amount}"
        )

    def test_table_amount_prefers_no_tax_column(self):
        """当表头同时含 价税合计 和 金额（不含税）时，应优先取不含税金额列"""
        parser = self._make_parser()
        header = ["货物名称", "数量", "单位", "单价", "价税合计", "金额（不含税）", "税额"]
        row = ["*电力*电费", "100", "度", "0.80", "90.80", "80.00", "10.00"]
        tables = [[header, row]]
        items = parser._extract_lines_from_tables(tables, "")
        assert len(items) == 1
        assert abs(items[0].amount - 80.00) < 0.01, (
            f"amount 应为不含税金额列 80.00，实际为 {items[0].amount}"
        )


class TestTableAmountConsistencyCheck:
    """测试单价×数量≈金额一致性校验"""

    def test_table_amount_consistency_check(self):
        """当金额列与单价列数值接近且数量>1时，纠正 amount = unit_price * quantity"""
        parser = PdfInvoiceParser()
        # 模拟 amount 列被误解析为单价值（100），而非真实金额（1000）
        header = ["货物名称", "数量", "单位", "单价", "金额"]
        row = ["办公用品", "10", "个", "100", "100"]  # amount_col 值=100，与单价相同
        tables = [[header, row]]
        items = parser._extract_lines_from_tables(tables, "")
        assert len(items) == 1
        assert abs(items[0].amount - 1000.0) < 0.01, (
            f"amount 应被纠正为 unit_price×quantity=1000，实际为 {items[0].amount}"
        )


class TestTableTaxAmountNotParsedAsAmount:
    """测试税额列的值不会被赋给 InvoiceLineItem.amount"""

    def test_table_tax_amount_not_parsed_as_amount(self):
        """含税额列的表格，税额列数值不应出现在 amount 字段"""
        parser = PdfInvoiceParser()
        header = ["货物名称", "数量", "单位", "单价", "金额", "税额"]
        row = ["*电力*电费", "100", "度", "0.80", "80.00", "10.00"]
        tables = [[header, row]]
        items = parser._extract_lines_from_tables(tables, "")
        assert len(items) == 1
        # 税额为 10.00，金额为 80.00，amount 不应等于税额
        assert abs(items[0].amount - 10.00) > 0.01, (
            f"amount 不应为税额 10.00，实际为 {items[0].amount}"
        )
        assert abs(items[0].amount - 80.00) < 0.01, (
            f"amount 应为金额列 80.00，实际为 {items[0].amount}"
        )


class TestTextExtractionUnitPriceNotAmount:
    """测试文本模式下 amount 取金额列而非单价或税额"""

    def test_text_extraction_unit_price_not_amount(self):
        """文本行 *电力*电费 100 度 0.80 80.00 12.00，amount 应为 80.00（金额），非 12.00（税额）或 0.80（单价）"""
        parser = PdfInvoiceParser()
        text = "*电力*电费 100 度 0.80 80.00 12.00"
        items = parser._extract_lines_from_text(text)
        assert len(items) >= 1
        assert abs(items[0].amount - 80.00) < 0.01, (
            f"amount 应为金额 80.00，实际为 {items[0].amount}"
        )
        # 单价也应正确
        if items[0].unit_price is not None:
            assert abs(items[0].unit_price - 0.80) < 0.01, (
                f"unit_price 应为 0.80，实际为 {items[0].unit_price}"
            )


class TestJsonParserAmountField:
    """测试 JsonXmlInvoiceParser 正确区分 amount 与 unit_price 字段"""

    def test_json_parser_amount_field(self):
        """从含 amount 和 unit_price 键的 dict 中，amount 和 unit_price 应各自正确"""
        parser = JsonXmlInvoiceParser()
        data = {
            "invoice_number": "12345",
            "total_amount": 500.0,
            "lines": [
                {
                    "name": "电费",
                    "amount": 500.0,
                    "unit_price": 0.80,
                    "quantity": 625,
                    "unit": "度",
                }
            ],
        }
        inv = parser.from_dict(data)
        assert len(inv.lines) == 1
        assert abs(inv.lines[0].amount - 500.0) < 0.01, (
            f"amount 应为 500.0，实际为 {inv.lines[0].amount}"
        )
        assert inv.lines[0].unit_price == 0.80, (
            f"unit_price 应为 0.80，实际为 {inv.lines[0].unit_price}"
        )
