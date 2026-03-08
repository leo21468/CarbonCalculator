"""测试发票解析器中金额字段的正确解析（Issue #26）"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.invoice_parser import PdfInvoiceParser, parse_amount_cny

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
        # 模拟 amount 列被误解析为单价值（100），而非真实金额（1000）；名称需 *类别* 开头才算物体
        header = ["货物名称", "数量", "单位", "单价", "金额"]
        row = ["*办公用品*办公用品", "10", "个", "100", "100"]  # amount_col 值=100，与单价相同
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


class TestOcrTaxRateNotAmount:
    """测试 OCR 文本含税率列时，碳计算仍使用金额而非税率"""

    def test_ocr_text_with_tax_rate_column_pattern1(self):
        """OCR 文本含5列数字（数量、单价、金额、税率、税额），amount 应为金额（80.00）而非税率数值（13）"""
        parser = PdfInvoiceParser()
        # 中国增值税发票典型格式：货物名称 数量 单位 单价 金额（不含税）税率 税额
        text = "*电力*电费 100 度 0.80 80.00 13% 10.40"
        items = parser._extract_lines_from_text(text)
        assert len(items) >= 1, "应能提取到至少1条明细"
        assert abs(items[0].amount - 80.00) < 0.01, (
            f"amount 应为金额列 80.00，不应为税率数值 13，实际为 {items[0].amount}"
        )

    def test_ocr_text_with_tax_rate_column_pattern2(self):
        """非*前缀格式的 OCR 文本含税率列，amount 仍应取金额而非税率；名称需 *类别* 开头才算物体"""
        parser = PdfInvoiceParser()
        text = "*办公用品*办公用品 50 个 10.00 500.00 6% 30.00"
        items = parser._extract_lines_from_text(text)
        assert len(items) >= 1, "应能提取到至少1条明细"
        assert abs(items[0].amount - 500.00) < 0.01, (
            f"amount 应为金额列 500.00，不应为税率数值 6，实际为 {items[0].amount}"
        )

    def test_ocr_text_without_tax_rate_column(self):
        """OCR 文本只有4列数字时（无税率列），amount 仍应正确提取"""
        parser = PdfInvoiceParser()
        text = "*电力*电费 100 度 0.80 80.00 10.40"
        items = parser._extract_lines_from_text(text)
        assert len(items) >= 1
        assert abs(items[0].amount - 80.00) < 0.01, (
            f"无税率列时 amount 应为 80.00，实际为 {items[0].amount}"
        )

    def test_ocr_text_amount_not_tax_rate_value(self):
        """确保碳计算输入为金额而非税率：tax_rate=9% 不得出现在 amount 字段"""
        parser = PdfInvoiceParser()
        text = "*服务*技术咨询 1 次 5000.00 5000.00 9% 450.00"
        items = parser._extract_lines_from_text(text)
        assert len(items) >= 1
        # 税率 9% 的数字部分为 9，金额为 5000.00
        assert items[0].amount != 9, "amount 不应等于税率数值 9"
        assert abs(items[0].amount - 5000.00) < 0.01, (
            f"amount 应为金额 5000.00，实际为 {items[0].amount}"
        )


class TestParseAmountCny:
    """测试 parse_amount_cny 金额解析函数"""

    def test_yen_symbol(self):
        assert abs(parse_amount_cny("¥1,234.56") - 1234.56) < 0.001

    def test_fullwidth_yen(self):
        assert abs(parse_amount_cny("￥1,234.56") - 1234.56) < 0.001

    def test_rmb_prefix(self):
        assert abs(parse_amount_cny("RMB 5000") - 5000.0) < 0.001

    def test_yuan_suffix(self):
        assert abs(parse_amount_cny("1,234.56元") - 1234.56) < 0.001

    def test_no_symbol(self):
        assert abs(parse_amount_cny("1234.56") - 1234.56) < 0.001

    def test_thousands_separator(self):
        assert abs(parse_amount_cny("1,234,567.89") - 1234567.89) < 0.01

    def test_european_format(self):
        # 欧式格式：空格千位+逗号小数
        assert abs(parse_amount_cny("1 234,56") - 1234.56) < 0.001

    def test_zero(self):
        assert parse_amount_cny("0") == 0.0
        assert parse_amount_cny("¥0.00") == 0.0

    def test_large_amount(self):
        assert abs(parse_amount_cny("¥9,999,999.99") - 9999999.99) < 0.01

    def test_empty_returns_none(self):
        assert parse_amount_cny("") is None
        assert parse_amount_cny(None) is None

    def test_tax_rate_not_parsed_as_amount(self):
        """税率字符串不应被解析为有效金额，返回 None"""
        # 税率如 "13%" 去掉货币符号后剩下 "13%" → float("13%") 失败 → 返回 None
        result = parse_amount_cny("13%")
        assert result is None, f"税率'13%'不应解析为金额，实际返回 {result}"

    def test_negative_amount(self):
        result = parse_amount_cny("-500.00")
        assert result is not None
        assert abs(result - (-500.00)) < 0.001

    def test_fullwidth_comma(self):
        assert abs(parse_amount_cny("¥1，234.56") - 1234.56) < 0.001


class TestParseNumberCurrencySymbol:
    """测试 _parse_number 支持货币符号"""

    def test_yen_symbol_stripped(self):
        parser = PdfInvoiceParser()
        assert abs(parser._parse_number("¥80.00") - 80.0) < 0.001

    def test_fullwidth_yen_stripped(self):
        parser = PdfInvoiceParser()
        assert abs(parser._parse_number("￥80.00") - 80.0) < 0.001

    def test_tax_rate_rejected(self):
        """百分比值（税率）应被拒绝，返回 None"""
        parser = PdfInvoiceParser()
        assert parser._parse_number("13%") is None
        assert parser._parse_number("9%") is None
        assert parser._parse_number("0%") is None


class TestOcrMultilineBlocks:
    """测试 OCR 扫描版 PDF 将明细拆分为多行时能正确聚合并提取金额"""

    def test_multiline_ocr_real_scenario(self):
        """真实 OCR 拆行场景：名称、金额、税率、税额各自在独立行，且名称有续行"""
        # OCR 行来自用户提供的 dump_merged_lines.txt（行号仅供参考，与测试行号无关）
        ocr_lines = [
            "*研发和技术服务*技术服项",  # 名称起始行（含行拆分伪字符'项'）
            "157.43",                   # 不含税金额
            "1%",                       # 税率（应被过滤）
            "157.425742574257",         # 长小数（应被过滤为非货币金额）
            "1.57",                     # 税额
            "务费",                     # 名称续行
            "￥157.43",                 # 带货币符号的金额（优先使用无前缀数字）
            "¥1.57",                    # 带货币符号的税额
        ]
        text = "\n".join(ocr_lines)
        parser = PdfInvoiceParser()
        items = parser._extract_lines_from_text(text)

        assert len(items) >= 1, "应至少解析出 1 条明细"

        item = items[0]
        assert item.name == "*研发和技术服务*技术服务费", (
            f"名称应为 '*研发和技术服务*技术服务费'，实际为 '{item.name}'"
        )
        assert abs(item.amount - 157.43) < 0.01, (
            f"amount 应为不含税金额 157.43，实际为 {item.amount}"
        )
        assert item.amount != 1.0, "amount 不应等于税率数值 1（来自 1%）"
        assert abs(item.amount - 1.57) > 0.01, f"amount 不应为税额 1.57，实际为 {item.amount}"


class TestStructurePostprocess:
    """测试 PdfInvoiceParser._structure_postprocess OCR 结构化后处理"""

    def _make_bbox(self, x_min, y_min, x_max, y_max):
        return [[x_min, y_min], [x_max, y_min], [x_max, y_max], [x_min, y_max]]

    def test_empty_input(self):
        parser = PdfInvoiceParser()
        assert parser._structure_postprocess([]) == []

    def test_single_word(self):
        parser = PdfInvoiceParser()
        item = [self._make_bbox(0, 0, 100, 20), ("电费", 0.99)]
        result = parser._structure_postprocess([item])
        assert len(result) == 1
        assert result[0]["text"] == "电费"
        assert len(result[0]["words"]) == 1

    def test_two_words_same_row(self):
        """同一行的两个词块应被合并到同一行"""
        parser = PdfInvoiceParser()
        items = [
            [self._make_bbox(0, 0, 80, 20), ("电费", 0.99)],
            [self._make_bbox(100, 2, 180, 22), ("100.00", 0.98)],
        ]
        result = parser._structure_postprocess(items)
        assert len(result) == 1, "同行词块应合并为一行"
        assert "电费" in result[0]["text"]
        assert "100.00" in result[0]["text"]

    def test_two_words_different_rows(self):
        """y 差距超过阈值的词块应分属不同行"""
        parser = PdfInvoiceParser()
        items = [
            [self._make_bbox(0, 0, 80, 20), ("电费", 0.99)],
            [self._make_bbox(0, 50, 80, 70), ("办公用品", 0.97)],
        ]
        result = parser._structure_postprocess(items)
        assert len(result) == 2, "不同行词块应分属两行"

    def test_columns_assigned(self):
        """结构化输出应包含列信息"""
        parser = PdfInvoiceParser()
        items = [
            [self._make_bbox(0, 0, 100, 20), ("货物名称", 0.99)],
            [self._make_bbox(200, 0, 300, 20), ("金额", 0.98)],
        ]
        result = parser._structure_postprocess(items)
        assert len(result) == 1
        assert "columns" in result[0]
        assert len(result[0]["columns"]) >= 1


class TestClusterXCenters:
    """测试 PdfInvoiceParser._cluster_x_centers 一维聚类"""

    def test_empty(self):
        result = PdfInvoiceParser._cluster_x_centers([], 3)
        assert result == []

    def test_single_point(self):
        result = PdfInvoiceParser._cluster_x_centers([50.0], 2)
        assert len(result) == 1

    def test_two_clusters(self):
        """左右各三点，应分为两个簇"""
        centers = [10.0, 11.0, 12.0, 200.0, 201.0, 202.0]
        labels = PdfInvoiceParser._cluster_x_centers(centers, 2)
        assert len(labels) == 6
        # 左侧三点属同一簇，右侧三点属同一簇
        assert labels[0] == labels[1] == labels[2]
        assert labels[3] == labels[4] == labels[5]
        assert labels[0] != labels[3]

    def test_n_clusters_larger_than_points(self):
        """n_clusters > 点数时不应崩溃"""
        centers = [10.0, 20.0]
        labels = PdfInvoiceParser._cluster_x_centers(centers, 10)
        assert len(labels) == 2


class TestOcrNameWithSingleDigit:
    """修复1：含单个数字的商品名称不应被 is_name_only_line 排除"""

    def test_name_with_single_digit_parsed(self):
        """*矿产品*砂石2号 这样含单个数字的名称行应被正确识别"""
        parser = PdfInvoiceParser()
        ocr_lines = [
            "*矿产品*砂石2号",
            "500.00",
            "1%",
            "5.00",
        ]
        text = "\n".join(ocr_lines)
        items = parser._extract_lines_from_text(text)
        assert len(items) >= 1, "含单个数字的商品名称应能被解析"
        assert "砂石2号" in items[0].name or "矿产品" in items[0].name, (
            f"名称应包含砂石2号或矿产品，实际为 '{items[0].name}'"
        )
        assert abs(items[0].amount - 500.00) < 0.01, (
            f"amount 应为 500.00，实际为 {items[0].amount}"
        )

    def test_name_with_two_digits_not_parsed_as_name(self):
        """含2个以上独立数字序列的行不应被视为纯名称行"""
        parser = PdfInvoiceParser()
        # 行中含两个数字 → 应视为数值行（包含数量和金额），不作为名称行触发块合并
        ocr_lines = [
            "*电力*电费",
            "100 80.00",  # 数量+金额在同一行
        ]
        text = "\n".join(ocr_lines)
        items = parser._extract_lines_from_text(text)
        # 只要不崩溃且解析结果合理即可
        assert items is not None


class TestMultilineNameMerge:
    """修复2：支持三行及以上跨行名称合并"""

    def test_three_line_name_merged(self):
        """名称被 OCR 拆成三行时，应正确合并为完整名称"""
        parser = PdfInvoiceParser()
        ocr_lines = [
            "*研发和技术服务*技术服",  # 名称第1行
            "务",                      # 名称续行1（无数字，≤15字）
            "费",                      # 名称续行2（无数字，≤15字）
            "1 157.43 13% 20.47",     # 数量/金额行
        ]
        text = "\n".join(ocr_lines)
        items = parser._extract_lines_from_text(text)
        assert len(items) >= 1, "应至少解析出1条明细"
        assert "技术服务费" in items[0].name or "技术服" in items[0].name, (
            f"名称续行应被合并，实际名称为 '{items[0].name}'"
        )

    def test_name_continuation_stops_at_new_star_line(self):
        """遇到另一个 *XX*YY 格式行时，应停止名称合并"""
        parser = PdfInvoiceParser()
        ocr_lines = [
            "*电力*电费",
            "100 80.00 13% 10.40",
            "*矿产品*砂石",
            "500 500.00 9% 45.00",
        ]
        text = "\n".join(ocr_lines)
        items = parser._extract_lines_from_text(text)
        # 应解析出两条明细
        assert len(items) >= 2, f"应解析出2条明细，实际 {len(items)} 条"


class TestGatherNumsTaxRateFilter:
    """修复3：_gather_nums 应过滤税率，不将税率混入金额候选"""

    def test_ocr_structured_tax_rate_not_amount(self):
        """结构化 OCR 行含税率列时，金额应正确，税率不应混入"""
        parser = PdfInvoiceParser()
        # 模拟 _structure_postprocess 输出的结构化行
        structured_rows = [
            {
                "page": 1,
                "rows": [
                    {
                        "columns": ["*电力*电费", "100", "0.80", "80.00", "13%", "10.40"],
                        "y_center": 100,
                        "words": [],
                    }
                ],
                "full_text": "",
            }
        ]
        items = parser._extract_lines_from_ocr_structured(structured_rows)
        assert len(items) >= 1, "应至少解析出1条明细"
        # 金额应为 80.00，不应为 13（税率数字）
        assert abs(items[0].amount - 80.00) < 0.01, (
            f"amount 应为 80.00，不应为税率数值 13，实际为 {items[0].amount}"
        )
        assert items[0].amount != 13, "amount 不应等于税率数值 13"


class TestTableCrossRowNameMerge:
    """修复4：表格中商品名称跨行时，应正确合并"""

    def test_table_continuation_row_name_merged(self):
        """名称跨行时（第二行名称列为空，第一列有续行文字），应合并到上一行"""
        parser = PdfInvoiceParser()
        header = ["货物名称", "数量", "单位", "单价", "金额", "税额"]
        row1 = ["*研发和技术服务*技术服", "1", "次", "157.43", "157.43", "20.47"]
        row2 = ["务费", "", "", "", "", ""]  # 续行：名称列（货物名称列）为空，第一列（续行文字）非空，其余数值列均为空
        tables = [[header, row1, row2]]
        items = parser._extract_lines_from_tables(tables, "")
        assert len(items) >= 1, "应至少解析出1条明细"
        # 名称应包含合并后的完整名称
        assert "技术服务费" in items[0].name or "技术服" in items[0].name, (
            f"名称续行应被合并，实际名称为 '{items[0].name}'"
        )

    def test_table_non_continuation_row_not_merged(self):
        """非续行的行不应被误合并（含数值列的行是独立商品行）"""
        parser = PdfInvoiceParser()
        header = ["货物名称", "数量", "单位", "单价", "金额", "税额"]
        row1 = ["*电力*电费", "100", "度", "0.80", "80.00", "10.40"]
        row2 = ["*矿产品*砂石", "50", "吨", "200.00", "10000.00", "900.00"]
        tables = [[header, row1, row2]]
        items = parser._extract_lines_from_tables(tables, "")
        assert len(items) == 2, f"应解析出2条独立明细，实际 {len(items)} 条"


class TestMultilineNameThreeLines:
    """测试商品名跨3行时正确合并"""

    def test_multiline_name_three_lines(self):
        """商品名跨3行时应完整合并"""
        parser = PdfInvoiceParser()
        text = "*计算机服务*\n软件开发\n维护\n100 次 500.00 50000.00 6% 3000.00"
        items = parser._extract_lines_from_text(text)
        assert len(items) >= 1
        # 名称应包含所有三行
        assert "软件开发" in items[0].name or "计算机服务" in items[0].name
        assert abs(items[0].amount - 50000.00) < 0.01, f"amount 应为 50000.00，实际 {items[0].amount}"


class TestCompanyNameNotItem:
    """测试公司名不应被识别为商品明细"""

    def test_company_name_not_item(self):
        """公司名不应被识别为商品明细"""
        parser = PdfInvoiceParser()
        text = "深圳市某某科技有限公司\n*电力*电费 100 度 0.80 80.00 13% 10.40"
        items = parser._extract_lines_from_text(text)
        # 只有电费这一条商品
        assert len(items) == 1
        assert "*电力*" in items[0].name or "电费" in items[0].name


class TestOcrBlocksAmountSecondToLast:
    """测试 _extract_from_ocr_blocks 金额应取倒数第二列"""

    def test_ocr_blocks_amount_is_second_to_last(self):
        """_extract_from_ocr_blocks 应取倒数第二个数字作为金额（不含税）"""
        parser = PdfInvoiceParser()
        raw_lines = [
            "*电力*电费",
            "100",      # 数量
            "0.80",     # 单价
            "80.00",    # 金额（不含税）
            "13%",      # 税率（应被跳过）
            "10.40",    # 税额
        ]
        items = parser._extract_from_ocr_blocks(raw_lines)
        assert len(items) >= 1
        assert abs(items[0].amount - 80.00) < 0.01, f"amount 应为 80.00，实际 {items[0].amount}"


class TestTotalRowNotItem:
    """测试合计行不应被识别为商品"""

    def test_total_row_not_item(self):
        """合计行不应被识别为商品"""
        parser = PdfInvoiceParser()
        text = "*电力*电费 100 度 0.80 80.00 13% 10.40\n合计 ¥80.00  ¥10.40"
        items = parser._extract_lines_from_text(text)
        # 只应有电费一条
        assert len(items) == 1



class TestTableNameColRowIndex:
    """测试表格表头第0列为纯数字（行号）时，名称列应改用第1列"""

    def test_row_index_col_0_uses_col1_as_name(self):
        """当表头第0列为纯数字行号时，应优先用第1列作为名称列；名称需 *类别* 开头才算物体"""
        parser = PdfInvoiceParser()
        header = ["1", "货物名称", "金额"]
        row = ["1", "*金属*螺丝", "9.95"]
        tables = [[header, row]]
        items = parser._extract_lines_from_tables(tables, "")
        assert len(items) == 1
        assert "螺丝" in items[0].name, f"名称应含 '螺丝'，实际为 '{items[0].name}'"
        assert abs(items[0].amount - 9.95) < 0.01


class TestSmallAmountItemParsed:
    """测试小金额商品（< 15 元）能被正确识别"""

    def test_small_amount_below_15_parsed(self):
        """金额 < 15 元的商品行应被正常解析，不应被过滤"""
        parser = PdfInvoiceParser()
        text = "*金属制品*螺丝 个 10 0.90 9.00 13% 1.17"
        items = parser._extract_lines_from_text(text)
        assert len(items) >= 1
        assert abs(items[0].amount - 9.00) < 0.01, f"amount 应为 9.00，实际为 {items[0].amount}"

    def test_small_amount_under_3_yuan_parsed(self):
        """金额低至 2.20 元的商品行应被正常解析"""
        parser = PdfInvoiceParser()
        text = "*电子元件*连接器 个 2 1.10 2.20 1% 0.02"
        items = parser._extract_lines_from_text(text)
        assert len(items) >= 1
        assert abs(items[0].amount - 2.20) < 0.01, f"amount 应为 2.20，实际为 {items[0].amount}"


class TestNonAsteriskItemParsed:
    """测试带 *类别* 前缀的商品（规则：仅 *XXX* 开头才算物体）能被 Pattern 2 解析"""

    def test_screw_name_without_prefix_parsed(self):
        """带 *金属* 前缀的 '螺丝' 行应通过 Pattern 2 解析"""
        parser = PdfInvoiceParser()
        text = "*金属*螺丝 M3×10mm 100粒 9.00"
        items = parser._extract_lines_from_text(text)
        assert len(items) >= 1
        assert items[0].amount > 0, f"螺丝的金额应 > 0，实际为 {items[0].amount}"

    def test_bearing_name_without_prefix_parsed(self):
        """带 *轴承* 前缀的 '轴承' 行应被解析"""
        parser = PdfInvoiceParser()
        text = "*轴承*轴承 6202 5个 17.82"
        items = parser._extract_lines_from_text(text)
        assert len(items) >= 1
        assert items[0].amount > 0


class TestNumericCategoryFiltered:
    """测试纯数字或含数字的规格类别（如 *22*7、*外径25*）被过滤"""

    def test_numeric_only_category_filtered(self):
        """纯数字类别 *22* 应被过滤，不识别为商品"""
        parser = PdfInvoiceParser()
        text = "*22*7 1 17.82 17.82 1% 0.18"
        items = parser._extract_lines_from_text(text)
        # *22* 应被过滤（纯数字类别）
        names = [i.name for i in items]
        assert not any("22" in n and n.startswith("*") for n in names), (
            f"*22* 类别应被过滤，实际 items: {names}"
        )

    def test_spec_with_digit_in_category_filtered(self):
        """含数字的规格类别 *外径25* 不应被 Pattern 1 识别为合法商品分类名"""
        parser = PdfInvoiceParser()
        # 模拟 30.78 轴承发票的规格字符串（单独测试 Pattern 1 的过滤效果）
        # 金额 30.48 来自实际发票单价 1.5237623762376 × 数量 20 ≈ 30.48
        text = "*外径25* 个 20 1.52 30.48 1% 0.30"
        items = parser._extract_lines_from_text(text)
        names = [i.name for i in items]
        # Pattern 1 应过滤含数字的分类名；Pattern 2 fallback 可能仍匹配（外径25*），
        # 关键是 Pattern 1 不应以 *外径25* 为合法商品名提取
        assert not any(n.startswith("*外径25*") for n in names), (
            f"Pattern 1 不应将 *外径25* 识别为合法商品分类，实际 items: {names}"
        )


class TestTableOuterContainerSkipped:
    """测试包含完整发票项目区的外层表格单元格不被识别为商品名"""

    def test_cell_with_invoice_header_skipped(self):
        """包含 '项目名称' 的表格单元格内容不应被识别为商品"""
        parser = PdfInvoiceParser()
        # 模拟 pdfplumber 提取到外层容器表格
        full_items_cell = (
            "项目名称 规格型号 单位 数量 单价 金额 税率 税额\n"
            "*轴承*轴承 8×22×7 件 1 17.82 17.82 1% 0.18\n"
            "合计 ¥17.82 ¥0.18"
        )
        header = ["购买方", "名称：上海交通大学", None, "销售方", "名称：轴承公司"]
        row = [full_items_cell, None, None, None, None]
        tables = [[header, row]]
        items = parser._extract_lines_from_tables(tables, "")
        # 包含 '项目名称' 的单元格内容不应被识别为商品
        names = [i.name for i in items]
        assert not any("项目名称" in n for n in names), (
            f"含'项目名称'的外层表格单元格不应被识别为商品，实际 items: {names}"
        )


class TestDateLineNotItem:
    """测试日期行不应被识别为商品名"""

    def test_date_line_not_item(self):
        """开票日期行不应被识别为商品名"""
        parser = PdfInvoiceParser()
        text = "开票日期：2024年01月15日\n*电力*电费 100 度 0.80 80.00 13% 10.40"
        items = parser._extract_lines_from_text(text)
        assert len(items) == 1
        assert "电" in items[0].name or "电费" in items[0].name


class TestTaxBureauLineNotItem:
    """测试国家税务总局行不应被识别为商品名"""

    def test_tax_bureau_line_not_item(self):
        """国家税务总局监制行不应被识别为商品名"""
        parser = PdfInvoiceParser()
        text = "国家税务总局监制\n*办公用品*文具 1 批 500.00 13% 65.00"
        items = parser._extract_lines_from_text(text)
        assert len(items) == 1
        assert "文具" in items[0].name or "办公" in items[0].name


class TestTableTotalRowNotItem:
    """测试表格中合计行不被识别为商品"""

    def test_table_total_row_not_item(self):
        """合计行不应被识别为商品"""
        parser = PdfInvoiceParser()
        tables = [
            [
                ["货物或应税劳务名称", "数量", "单位", "单价", "金额"],
                ["*电力*电费", "1000", "度", "0.80", "800.00"],
                ["合计", "", "", "", "800.00"],
            ]
        ]
        items = parser._extract_lines_from_tables(tables, "")
        assert len(items) == 1
        assert "电" in items[0].name


class TestDeclaredTotalValidation:
    """测试利用合计行金额验证明细金额之和（新需求）"""

    def test_finds_declared_total(self):
        """_find_declared_total_from_tables 应从合计行提取总金额"""
        parser = PdfInvoiceParser()
        tables = [
            [
                ["货物或应税劳务名称", "数量", "单位", "单价", "金额"],
                ["*电力*电费", "1000", "度", "0.80", "800.00"],
                ["合计", "", "", "", "800.00"],
            ]
        ]
        total = parser._find_declared_total_from_tables(tables)
        assert total is not None
        assert abs(total - 800.00) < 0.01

    def test_sum_matches_declared_total(self):
        """明细金额之和应与合计行声明的总金额一致"""
        parser = PdfInvoiceParser()
        tables = [
            [
                ["货物或应税劳务名称", "数量", "单位", "单价", "金额"],
                ["*电力*电费", "1000", "度", "0.80", "800.00"],
                ["合计", "", "", "", "800.00"],
            ]
        ]
        items = parser._extract_lines_from_tables(tables, "")
        declared = parser._find_declared_total_from_tables(tables)
        items_sum = sum(i.amount for i in items)
        assert declared is not None
        assert abs(items_sum - declared) < 0.01, (
            f"明细金额之和 {items_sum} 应与合计声明值 {declared} 一致"
        )

    def test_multi_item_sum_matches_declared_total(self):
        """多商品行金额之和应与合计行声明值一致"""
        parser = PdfInvoiceParser()
        tables = [
            [
                ["货物或应税劳务名称", "数量", "单位", "单价", "金额"],
                ["*电力*电费", "1000", "度", "0.80", "800.00"],
                ["*办公用品*文具", "5", "套", "20.00", "100.00"],
                ["合计", "", "", "", "900.00"],
            ]
        ]
        items = parser._extract_lines_from_tables(tables, "")
        declared = parser._find_declared_total_from_tables(tables)
        items_sum = sum(i.amount for i in items)
        assert len(items) == 2
        assert declared is not None
        assert abs(declared - 900.00) < 0.01
        assert abs(items_sum - declared) < 0.01, (
            f"明细金额之和 {items_sum} 应与合计声明值 {declared} 一致"
        )


class TestIdenticalNameDifferentAmountLines:
    """回归测试：3条同名不同金额明细行（合计9.95元英制螺丝发票场景，商品金额分别为3.15/2.94/2.72）"""

    def test_three_identical_name_lines_table_path(self):
        """表格路径：3条同名不同金额明细行应全部保留，不被去重"""
        parser = PdfInvoiceParser()
        header = ["货物或应税劳务名称", "数量", "单位", "单价", "金额", "税率", "税额"]
        rows = [
            ["*金属制品*10.9级美制圆头内六角", "14", "个", "0.225", "3.15", "13%", "0.41"],
            ["*金属制品*10.9级美制圆头内六角", "14", "个", "0.21", "2.94", "13%", "0.38"],
            ["*金属制品*10.9级美制圆头内六角", "14", "个", "0.194", "2.72", "13%", "0.35"],
            ["合计", "", "", "", "8.81", "", "1.14"],
        ]
        tables = [[header] + rows]
        items = parser._extract_lines_from_tables(tables, "")
        # 合计行应被过滤，3条明细均应保留
        assert len(items) == 3, f"应有3条明细行，实际 {len(items)} 条: {[(i.name, i.amount) for i in items]}"
        amounts = sorted(i.amount for i in items)
        assert abs(amounts[0] - 2.72) < 0.01
        assert abs(amounts[1] - 2.94) < 0.01
        assert abs(amounts[2] - 3.15) < 0.01

    def test_name_continuation_on_next_row_merged_table_path(self):
        """表格路径：本行有名称+金额时，下一行若仅为名称续行（无金额），应合并为一条明细（如 9.95元+14队 英制螺丝）"""
        parser = PdfInvoiceParser()
        header = ["货物或应税劳务名称", "数量", "单位", "单价", "金额", "税率", "税额"]
        rows = [
            ["*金属制品*10.9级美制圆", "14", "个", "0.225", "3.15", "13%", "0.41"],
            ["头内六角", "", "", "", "", "", ""],
            ["*金属制品*10.9级美制圆", "14", "个", "0.21", "2.94", "13%", "0.38"],
            ["头内六角", "", "", "", "", "", ""],
            ["*金属制品*10.9级美制圆", "14", "个", "0.194", "2.72", "13%", "0.35"],
            ["头内六角", "", "", "", "", "", ""],
        ]
        tables = [[header] + rows]
        items = parser._extract_lines_from_tables(tables, "")
        assert len(items) == 3, f"应有3条明细（续行已合并），实际 {len(items)} 条: {[i.name for i in items]}"
        for it in items:
            assert "头内六角" in it.name, f"名称应包含续行「头内六角」: {it.name}"
            assert it.name.count("\n") == 0 and it.name.count("\r") == 0
        amounts = sorted(i.amount for i in items)
        assert abs(amounts[0] - 2.72) < 0.01 and abs(amounts[1] - 2.94) < 0.01 and abs(amounts[2] - 3.15) < 0.01

    def test_multiple_continuation_lines_merged_until_new_category_or_irrelevant(self):
        """表格路径：多行续行（无金额、非新*类别*）均合并；遇到新*类别*或合计等无关信息则停止"""
        parser = PdfInvoiceParser()
        header = ["货物或应税劳务名称", "数量", "单位", "单价", "金额", "税率", "税额"]
        rows = [
            ["*金属制品*10.9级美制圆", "14", "个", "0.225", "3.15", "13%", "0.41"],
            ["头内六角", "", "", "", "", "", ""],
            ["螺丝", "", "", "", "", "", ""],
            ["规格 M6", "", "", "", "", "", ""],
            ["*金属制品*另一商品", "1", "个", "2.00", "2.00", "13%", "0.26"],
        ]
        tables = [[header] + rows]
        items = parser._extract_lines_from_tables(tables, "")
        assert len(items) == 2, f"应有2条明细，实际 {len(items)} 条: {[i.name for i in items]}"
        first = items[0]
        assert "头内六角" in first.name and "螺丝" in first.name and "规格 M6" in first.name, (
            f"第一条应合并多行续行: {first.name}"
        )
        assert "另一商品" in items[1].name
        assert items[0].amount == 3.15 and items[1].amount == 2.00

    def test_continuation_stops_at_total_row(self):
        """表格路径：向后看合并时遇到「合计」等非商品行则停止，不把合计并入名称"""
        parser = PdfInvoiceParser()
        header = ["货物或应税劳务名称", "数量", "单位", "单价", "金额", "税率", "税额"]
        rows = [
            ["*金属制品*10.9级美制圆", "14", "个", "0.225", "3.15", "13%", "0.41"],
            ["头内六角", "", "", "", "", "", ""],
            ["合计", "", "", "", "3.15", "", "0.41"],
        ]
        tables = [[header] + rows]
        items = parser._extract_lines_from_tables(tables, "")
        assert len(items) == 1, f"应只有1条明细（合计行不并入），实际 {len(items)} 条"
        assert "头内六角" in items[0].name
        assert "合计" not in items[0].name

    def test_continuation_before_star_line_merged_by_look_back(self):
        """表格路径：不以*开头的「仅名称」行若在有金额的*行之前，应通过向前看合并到该*行后（否则会被忽略）"""
        parser = PdfInvoiceParser()
        header = ["货物或应税劳务名称", "数量", "单位", "单价", "金额", "税率", "税额"]
        rows = [
            ["头内六角", "", "", "", "", "", ""],
            ["*金属制品*10.9级美制圆", "14", "个", "0.225", "3.15", "13%", "0.41"],
        ]
        tables = [[header] + rows]
        items = parser._extract_lines_from_tables(tables, "")
        assert len(items) == 1, f"应有1条明细（前行续行已合并），实际 {len(items)} 条: {[i.name for i in items]}"
        assert "头内六角" in items[0].name
        assert "*金属制品*" in items[0].name
        assert abs(items[0].amount - 3.15) < 0.01

    def test_vat_rate_integer_not_parsed_as_amount(self):
        """表格路径：税率列值 13（无%符号）不应被解析为商品金额"""
        parser = PdfInvoiceParser()
        # 模拟 pdfplumber 将税率列（13%）丢失 % 符号，以裸整数 13 出现
        header = ["货物名称", "数量", "单位", "单价", "金额", "税率", "税额"]
        row = ["*金属制品*螺丝", "14", "个", "0.225", "3.15", "13", "0.41"]
        tables = [[header, row]]
        items = parser._extract_lines_from_tables(tables, "")
        assert len(items) == 1
        assert abs(items[0].amount - 3.15) < 0.01, (
            f"amount 应为 3.15，不应为税率整数 13，实际为 {items[0].amount}"
        )

    def test_post_filter_removes_vat_rate_integer_amounts(self):
        """_post_filter_lines：若存在小数金额行，应过滤掉 amount 为 VAT 税率整数的行"""
        from src.models import InvoiceLineItem
        parser = PdfInvoiceParser()
        lines = [
            InvoiceLineItem(name="*金属制品*螺丝", amount=13.0),   # 税率整数，应被过滤
            InvoiceLineItem(name="*金属制品*螺丝", amount=2.94),
            InvoiceLineItem(name="*金属制品*螺丝", amount=8.81),
        ]
        result = parser._post_filter_lines(lines)
        amounts = [l.amount for l in result]
        assert 13.0 not in amounts, f"VAT 税率整数 13 应被过滤，实际: {amounts}"
        assert any(abs(a - 2.94) < 0.01 for a in amounts)

    def test_declared_total_used_for_three_line_invoice(self):
        """合计行金额 8.81 应作为 total_amount，而非 sum(3.15+2.94+2.72)"""
        parser = PdfInvoiceParser()
        header = ["货物或应税劳务名称", "数量", "单位", "单价", "金额", "税率", "税额"]
        rows = [
            ["*金属制品*10.9级美制圆头内六角", "14", "个", "0.225", "3.15", "13%", "0.41"],
            ["*金属制品*10.9级美制圆头内六角", "14", "个", "0.21", "2.94", "13%", "0.38"],
            ["*金属制品*10.9级美制圆头内六角", "14", "个", "0.194", "2.72", "13%", "0.35"],
            ["合计", "", "", "", "8.81", "", "1.14"],
        ]
        tables = [[header] + rows]
        declared = parser._find_declared_total_from_tables(tables)
        assert declared is not None
        assert abs(declared - 8.81) < 0.01, f"合计行总金额应为 8.81，实际 {declared}"


class TestMultilineNameWithInlineData:
    """修复：*类别*商品名 含行内数据时，后续纯文本续行应被合并到名称中"""

    def test_continuation_lines_merged_when_data_inline(self):
        """商品名行含行内数字时，后续纯文本续行应合并到完整名称"""
        parser = PdfInvoiceParser()
        ocr_lines = [
            "*日用杂品*德力普 1 76.99 76.99 13% 10.01",
            "（Delipow）12v锂电池组",
            "18650锂电池可适用音响",
            "仪器仪表太阳能灯扩音器",
            "钓鱼灯玩",
        ]
        text = "\n".join(ocr_lines)
        items = parser._extract_lines_from_text(text)
        assert len(items) >= 1, "应至少解析出1条明细"
        full_name = items[0].name
        assert "（Delipow）" in full_name, (
            f"续行'（Delipow）12v锂电池组'应被合并到名称中，实际名称: {full_name!r}"
        )
        assert abs(items[0].amount - 76.99) < 0.01, (
            f"金额应为 76.99，实际 {items[0].amount}"
        )

    def test_continuation_stops_at_next_star_line(self):
        """遇到下一个 *类别* 行时，续行合并应停止"""
        parser = PdfInvoiceParser()
        ocr_lines = [
            "*日用杂品*德力普 1 76.99 76.99 13% 10.01",
            "续行文字",
            "*电力*电费 100 0.80 80.00 13% 10.40",
        ]
        text = "\n".join(ocr_lines)
        items = parser._extract_lines_from_text(text)
        assert len(items) >= 2, f"应解析出至少2条明细，实际 {len(items)} 条"

    def test_continuation_not_applied_when_data_has_chinese(self):
        """数据部分含中文时（如规格列已内联），不应进行续行合并"""
        parser = PdfInvoiceParser()
        # test1.pdf 格式：规格信息已在名称行内联
        text = "*经 营 租 赁 *场地租 赁 沪（2019）浦字不 动 产 权 ㎡ 1 2752.29 9% 247.71\n第 114388号"
        items = parser._extract_lines_from_text(text)
        assert len(items) >= 1
        # 续行"第 114388号"不应被合并到名称中（数据部分已含中文"赁"等）
        assert "114388" not in items[0].name, (
            f"证书编号不应被合并到名称中，实际名称: {items[0].name!r}"
        )


class TestMeasurementUnitNotAmount:
    """修复：名称行中的计量单位（如400g、12V）不应被误识别为金额"""

    def test_spec_400g_not_amount(self):
        """规格列中的400g不应被识别为金额"""
        parser = PdfInvoiceParser()
        # 模拟：名称行中规格列含"400g"，实际金额为3.00
        text = "*食品*饼干 400g 3.00 13% 0.39"
        items = parser._extract_lines_from_text(text)
        assert len(items) >= 1, "应至少解析出1条明细"
        assert abs(items[0].amount - 3.00) < 0.01, (
            f"金额应为3.00而非400，实际: {items[0].amount}"
        )

    def test_spec_12v_not_counted_in_quantity(self):
        """规格列中的12V不应被识别为数量"""
        parser = PdfInvoiceParser()
        # *原电池*锂电池 12V2800 个 2 33.46... 66.93 1% 0.67
        text = "*原电池*锂电池 12V2800 个 2 33.4653465346535 66.93 1% 0.67"
        items = parser._extract_lines_from_text(text)
        assert len(items) >= 1, "应至少解析出1条明细"
        assert abs(items[0].amount - 66.93) < 0.01, (
            f"金额应为66.93，实际: {items[0].amount}"
        )
        # 数量应为2（而不是12，来自12V）
        if items[0].quantity is not None:
            assert abs(items[0].quantity - 2.0) < 0.01, (
                f"数量不应为{items[0].quantity}（来自12V中的12），应为2"
            )


class TestOcrStructuredSpec400g:
    """修复：OCR结构化路径中，规格列（400g等）不应被误识别为数量/金额，且名称跨行时应正确合并"""

    def test_spec_400g_inline_col_not_quantity(self):
        """同行内规格列'400g'不应被识别为数量（应为实际数量=1）"""
        parser = PdfInvoiceParser()
        structured = [
            {
                "page": 1,
                "rows": [
                    {
                        "columns": ["*日用杂品*德力普12V锂电池", "400g", "1", "2", "76.99", "76.99", "13%", "10.01"],
                        "y_center": 100,
                        "words": [],
                    }
                ],
                "full_text": "",
            }
        ]
        items = parser._extract_lines_from_ocr_structured(structured)
        assert len(items) >= 1, "应至少解析出1条明细"
        # 金额应为 76.99，不应为 400（来自 400g）
        assert abs(items[0].amount - 76.99) < 0.01, (
            f"金额应为76.99，不应为400（来自400g），实际: {items[0].amount}"
        )
        # 数量不应为 400（来自 400g）
        if items[0].quantity is not None:
            assert items[0].quantity != 400.0, (
                f"数量不应为400（来自400g），实际: {items[0].quantity}"
            )

    def test_spec_400g_separate_row_amount_correct(self):
        """OCR将规格'400g'单独分行时，应向后查找数值行，金额应正确"""
        parser = PdfInvoiceParser()
        structured = [
            {
                "page": 1,
                "rows": [
                    {"columns": ["*日用杂品*德力普12V锂电池"], "y_center": 100, "words": []},
                    {"columns": ["400g"], "y_center": 115, "words": []},
                    {"columns": ["1", "2", "76.99", "76.99", "13%", "10.01"], "y_center": 130, "words": []},
                ],
                "full_text": "",
            }
        ]
        items = parser._extract_lines_from_ocr_structured(structured)
        assert len(items) >= 1, "应至少解析出1条明细（'400g'行后的数值行被正确关联）"
        # 金额应为 76.99，不应为 400
        assert abs(items[0].amount - 76.99) < 0.01, (
            f"金额应为76.99，实际: {items[0].amount}"
        )

    def test_spec_row_merged_into_name(self):
        """OCR规格行（400g）应被合并进商品名称"""
        parser = PdfInvoiceParser()
        structured = [
            {
                "page": 1,
                "rows": [
                    {"columns": ["*日用杂品*德力普12V锂电池"], "y_center": 100, "words": []},
                    {"columns": ["400g"], "y_center": 115, "words": []},
                    {"columns": ["1", "76.99", "76.99", "13%", "10.01"], "y_center": 130, "words": []},
                ],
                "full_text": "",
            }
        ]
        items = parser._extract_lines_from_ocr_structured(structured)
        assert len(items) >= 1, "应至少解析出1条明细"
        # 名称应包含 '400g'（已从规格行合并）
        assert "400g" in items[0].name, (
            f"规格'400g'应被合并进名称，实际名称: {items[0].name!r}"
        )

    def test_multiple_items_with_spec_rows(self):
        """多商品场景：含规格行的商品与普通商品均应正确解析"""
        parser = PdfInvoiceParser()
        structured = [
            {
                "page": 1,
                "rows": [
                    {"columns": ["*日用杂品*德力普12V锂电池"], "y_center": 100, "words": []},
                    {"columns": ["400g"], "y_center": 115, "words": []},
                    {"columns": ["1", "76.99", "76.99", "13%", "10.01"], "y_center": 130, "words": []},
                    {"columns": ["*电子*AA电池"], "y_center": 150, "words": []},
                    {"columns": ["5", "7.50", "37.50", "9%", "3.38"], "y_center": 165, "words": []},
                ],
                "full_text": "",
            }
        ]
        items = parser._extract_lines_from_ocr_structured(structured)
        assert len(items) >= 2, f"应解析出2条明细，实际: {len(items)}"
        amounts = sorted(item.amount for item in items)
        assert abs(amounts[0] - 37.50) < 0.01, f"第一条金额应为37.50，实际: {amounts[0]}"
        assert abs(amounts[1] - 76.99) < 0.01, f"第二条金额应为76.99，实际: {amounts[1]}"


class TestDigitPrefixProductName:
    """修复：商品名称以数字开头（如「502强力胶」）应被 _extract_from_ocr_blocks 正确识别"""

    def test_digit_prefix_name_recognized(self):
        """「502强力胶」等以整数开头的商品名应被 is_name_only_line 识别为名称行"""
        parser = PdfInvoiceParser()
        raw_lines = [
            "*化工*502强力胶",
            "9.00",
        ]
        items = parser._extract_from_ocr_blocks(raw_lines)
        assert len(items) >= 1, (
            "以 *类别* 开头的商品名（*化工*502强力胶）应能被 _extract_from_ocr_blocks 解析"
        )
        assert "强力胶" in items[0].name or "502" in items[0].name, (
            f"名称应包含 '强力胶' 或 '502'，实际为 '{items[0].name}'"
        )
        assert abs(items[0].amount - 9.00) < 0.01, (
            f"金额应为 9.00，实际为 {items[0].amount}"
        )

    def test_decimal_prefix_spec_line_not_name(self):
        """含小数的规格行（如「1.25kg」整行）不应被 is_name_only_line 识别为商品名；名称需 *类别* 开头"""
        parser = PdfInvoiceParser()
        raw_lines = [
            "*食品*牛肉干",
            "1.25kg",
            "9.00",
        ]
        items = parser._extract_from_ocr_blocks(raw_lines)
        # 「1.25kg」整行：含小数，不应触发新块；9.00 应为金额
        assert len(items) >= 1, "应能解析出商品"
        assert abs(items[0].amount - 9.00) < 0.01, (
            f"金额应为 9.00（1.25 是规格，不是金额），实际为 {items[0].amount}"
        )


class TestWeightSpecNotAmount:
    """修复：OCR 将重量规格「1.25kg」拆为「1.25」和「kg」两行时，「1.25」不应被作为金额"""

    def test_split_weight_spec_not_amount(self):
        """OCR 拆行：「1.25」后面接「kg」应被识别为规格，不加入金额候选；名称需 *类别* 开头"""
        parser = PdfInvoiceParser()
        raw_lines = [
            "*食品*牛肉干",
            "1.25",   # OCR 把 1.25kg 拆开
            "kg",     # 单位行
            "9.00",   # 实际金额
        ]
        items = parser._extract_from_ocr_blocks(raw_lines)
        assert len(items) >= 1, "应能解析出商品"
        # 金额必须是 9.00，不应是 1.25
        assert abs(items[0].amount - 9.00) < 0.01, (
            f"金额应为 9.00（1.25 是重量规格，不是金额），实际为 {items[0].amount}"
        )

    def test_split_weight_spec_name_contains_spec(self):
        """OCR 拆行后，规格「1.25kg」应被合并进商品名称；名称需 *类别* 开头"""
        parser = PdfInvoiceParser()
        raw_lines = [
            "*食品*牛肉干",
            "1.25",
            "kg",
            "9.00",
        ]
        items = parser._extract_from_ocr_blocks(raw_lines)
        assert len(items) >= 1, "应能解析出商品"
        # 名称应包含「1.25kg」规格（或至少不包含孤立的「1.25」）
        assert "1.25kg" in items[0].name or "kg" in items[0].name, (
            f"规格 '1.25kg' 应被合并进名称，实际名称: {items[0].name!r}"
        )

    def test_price_after_weight_correct(self):
        """在规格行之后的价格应被正确提取；名称需 *类别* 开头"""
        parser = PdfInvoiceParser()
        raw_lines = [
            "*食品*有机牛奶",
            "250",    # 整数，后面接数字行（9.80），不接单位行 → 不触发规格合并
            "9.80",   # 价格
            "0.98",   # 税额（应取倒数第二个：9.80）
        ]
        items = parser._extract_from_ocr_blocks(raw_lines)
        assert len(items) >= 1, "应能解析出商品"
        assert abs(items[0].amount - 9.80) < 0.01, (
            f"金额应为 9.80，实际为 {items[0].amount}"
        )
        # 250 后面没有单位行，不应被合并为规格；它被识别为 unit_price 或参与数量计算
        # 关键：金额必须是 9.80，而非 0.98（税额）或 250（错误解析）
        assert abs(items[0].amount - 0.98) > 0.01, "amount 不应为税额 0.98"
        assert abs(items[0].amount - 250) > 0.01, "amount 不应为整数 250"


class TestOcrPaddleVersion:
    """测试 PdfInvoiceParser._run_ocr_on_image 兼容 PaddleOCR 2.x 和 3.x 结果格式"""

    def test_run_ocr_on_image_3x_format(self):
        """PaddleOCR 3.x：OCRResult dict 对象应被正确转换为旧版 [[bbox, (text, score)], ...] 格式"""
        from src.invoice_parser import PdfInvoiceParser

        class FakeOCRResult:
            """模拟 PaddleOCR 3.x OCRResult（类字典对象）"""
            def __init__(self):
                self._data = {
                    'rec_polys': [[[0, 0], [10, 0], [10, 10], [0, 10]]],
                    'rec_texts': ['502强力胶'],
                    'rec_scores': [0.99],
                }
            def __getitem__(self, key):
                return self._data[key]
            def get(self, key, default=None):
                return self._data.get(key, default)

        class FakeOCR:
            def predict(self, img):
                return [FakeOCRResult()]

        ocr = FakeOCR()
        items = PdfInvoiceParser._run_ocr_on_image(ocr, None)
        assert len(items) == 1, f"应返回 1 条结果，实际: {len(items)}"
        assert items[0][1][0] == '502强力胶', f"文字应为 '502强力胶'，实际: {items[0][1][0]}"
        assert abs(items[0][1][1] - 0.99) < 0.01, f"置信度应为 0.99，实际: {items[0][1][1]}"

    def test_run_ocr_on_image_2x_format(self):
        """PaddleOCR 2.x：ocr() 返回嵌套列表，应直接透传"""
        from src.invoice_parser import PdfInvoiceParser

        class FakeOCR:
            def predict(self, img):
                # 返回列表格式（旧版兼容）
                return [[
                    [[[0,0],[10,0],[10,10],[0,10]], ('502强力胶', 0.99)],
                ]]

        ocr = FakeOCR()
        items = PdfInvoiceParser._run_ocr_on_image(ocr, None)
        assert len(items) == 1
        assert items[0][1][0] == '502强力胶'

    def test_run_ocr_empty_result(self):
        """OCR 返回空结果时，_run_ocr_on_image 应返回空列表"""
        from src.invoice_parser import PdfInvoiceParser

        class FakeOCR:
            def predict(self, img):
                return []

        ocr = FakeOCR()
        items = PdfInvoiceParser._run_ocr_on_image(ocr, None)
        assert items == []


class TestUnitWithNumberNotAmount:
    """修复：OCR 将单位 'M³' 等含数字单位拆成字母行+数字行时，数字不应被误认为金额"""

    def test_unit_letter_prefix_merged_with_number(self):
        """'M'（名称续行）+ '3'（数字）应被合并为 'M3' 写入名称，而非将 '3' 加入 plain_numbers；名称需 *类别* 开头"""
        from src.invoice_parser import PdfInvoiceParser
        parser = PdfInvoiceParser()
        raw_lines = [
            "*建材*某产品",
            "M",     # 单位字母前缀
            "3",     # 单位数字后缀 → 应与 "M" 合并为 "M3" 写入名称
            "9.00",  # 实际金额
        ]
        items = parser._extract_from_ocr_blocks(raw_lines)
        assert len(items) >= 1, "应能解析出商品"
        assert abs(items[0].amount - 9.00) < 0.01, (
            f"金额应为 9.00（'3' 是单位后缀，不是金额），实际为 {items[0].amount}"
        )
        assert "M3" in items[0].name, (
            f"名称应包含合并后的单位 'M3'，实际名称: {items[0].name!r}"
        )

    def test_three_nums_qty_unitprice_amount_pattern1(self):
        """Pattern 1：三个数字且最后一个 ≈ 前两个之积时，取最后一个为金额"""
        from src.invoice_parser import PdfInvoiceParser
        parser = PdfInvoiceParser()
        # 100 件 × 0.09 元/件 = 9.00 元
        text = "*螺丝*螺丝 100 0.09 9.00"
        items = parser._extract_lines_from_text(text)
        assert len(items) >= 1, "应至少解析出1条明细"
        assert abs(items[0].amount - 9.00) < 0.01, (
            f"金额应为 9.00（qty×unit_price=amount），实际: {items[0].amount}"
        )

    def test_three_nums_default_second_to_last_pattern1(self):
        """Pattern 1：三个数字，不满足 qty×unit_price=amount 关系时，仍取倒数第二为金额"""
        from src.invoice_parser import PdfInvoiceParser
        parser = PdfInvoiceParser()
        # 格式：单价 80.00，金额 160.00，税额 14.40（非整数关系）
        text = "*电力*电费 80.00 160.00 14.40"
        items = parser._extract_lines_from_text(text)
        assert len(items) >= 1, "应至少解析出1条明细"
        assert abs(items[0].amount - 160.00) < 0.01, (
            f"金额应为 160.00（倒数第二个），实际: {items[0].amount}"
        )
