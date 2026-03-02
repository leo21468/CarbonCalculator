"""
第一步：数据采集 - 发票结构化提取。
系统通过接口提取电子发票（OFD/PDF/XML）的结构化数据。
核心抓取字段：货物或应税劳务名称、税收分类编码、金额/单价/数量、销方信息。
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Union

from .models import Invoice, InvoiceLineItem, SellerInfo


class BaseInvoiceParser(ABC):
    """发票解析器抽象基类：支持 OFD / PDF / XML 等格式"""

    @abstractmethod
    def parse(self, source: Union[str, Path, bytes]) -> Invoice:
        """
        解析电子发票，返回结构化 Invoice。
        source: 文件路径或已读取的字节内容。
        """
        pass

    @abstractmethod
    def supported_formats(self) -> List[str]:
        """返回支持的格式列表，如 ['XML', 'PDF']"""
        pass


def _seller_from_dict(d: dict) -> SellerInfo:
    return SellerInfo(
        name=d.get("name", ""),
        tax_id=d.get("tax_id"),
        address=d.get("address"),
    )


def _line_from_dict(d: dict) -> InvoiceLineItem:
    try:
        amount = float(d.get("amount", 0))
    except (ValueError, TypeError):
        amount = 0.0
    return InvoiceLineItem(
        name=d.get("name", ""),
        tax_classification_code=d.get("tax_classification_code"),
        tax_classification_name=d.get("tax_classification_name"),
        quantity=d.get("quantity"),
        unit=d.get("unit"),
        unit_price=d.get("unit_price"),
        amount=amount,
        remark=d.get("remark"),
    )


class JsonXmlInvoiceParser(BaseInvoiceParser):
    """
    从 JSON 或类 XML 解析后的 dict 构造 Invoice。
    用于对接「通过 API 解析电子发票文件（XML 或 JSON）获取后台结构化数据」。
    """

    def supported_formats(self) -> List[str]:
        return ["JSON", "XML"]

    def parse(self, source: Union[str, Path, bytes]) -> Invoice:
        import json
        if isinstance(source, (str, Path)):
            path = Path(source)
            try:
                if path.suffix.lower() == ".json":
                    raw = json.loads(path.read_text(encoding="utf-8"))
                else:
                    # 若为 XML，可在此用 lxml 解析为 dict，这里简化为期望已是 dict 形态
                    text = path.read_text(encoding="utf-8")
                    raw = self._xml_to_dict(text) if ".xml" in path.suffix.lower() else json.loads(text)
            except (FileNotFoundError, UnicodeDecodeError) as e:
                raise ValueError(f"Cannot read invoice file: {e}")
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON format: {e}")
        else:
            try:
                raw = json.loads(source.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                raise ValueError(f"Invalid source data: {e}")

        return self._build_invoice(raw)

    def _xml_to_dict(self, xml_text: str) -> dict:
        """简单占位：实际可用 lxml 解析 XML 为统一 dict 结构"""
        try:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(xml_text)
            return self._element_to_dict(root)
        except ET.ParseError as e:
            # Specific exception for XML parsing errors
            return {}

    def _element_to_dict(self, el) -> dict:
        """将 XML 节点转为 dict（简化版，可按实际发票 XML 结构扩展）"""
        d = {}
        for child in el:
            if len(child) == 0:
                d[child.tag] = child.text or ""
            else:
                d[child.tag] = self._element_to_dict(child)
        return d

    def from_dict(self, data: dict) -> Invoice:
        """直接从 API 返回的 dict 构建 Invoice（推荐：接口解析后调用此方法）"""
        return self._build_invoice(data)

    def _build_invoice(self, data: dict) -> Invoice:
        inv = Invoice(
            invoice_code=data.get("invoice_code"),
            invoice_number=data.get("invoice_number"),
            date=data.get("date"),
            total_amount=float(data.get("total_amount", 0)),
            source_format=data.get("source_format"),
        )
        if data.get("seller"):
            inv.seller = _seller_from_dict(
                data["seller"] if isinstance(data["seller"], dict) else {"name": str(data["seller"])}
            )
        if data.get("buyer"):
            inv.buyer = _seller_from_dict(
                data["buyer"] if isinstance(data["buyer"], dict) else {"name": str(data["buyer"])}
            )
        for item in data.get("lines", data.get("items", [])):
            inv.lines.append(_line_from_dict(item if isinstance(item, dict) else {"name": str(item), "amount": 0}))
        return inv


class PdfInvoiceParser(BaseInvoiceParser):
    """
    从 PDF 电子发票中提取结构化数据。
    使用 pdfplumber 提取表格与文本，解析中国增值税发票的标准字段：
    货物或应税劳务名称、税收分类编码、金额/单价/数量、销方信息。
    """

    def supported_formats(self) -> List[str]:
        return ["PDF"]

    def parse(self, source: Union[str, Path, bytes]) -> Invoice:
        import io
        try:
            import pdfplumber
        except ImportError:
            raise ImportError("请安装 pdfplumber: pip install pdfplumber")

        if isinstance(source, (str, Path)):
            pdf = pdfplumber.open(str(source))
        else:
            pdf = pdfplumber.open(io.BytesIO(source))

        try:
            return self._extract_invoice(pdf)
        finally:
            pdf.close()

    def _ocr_pdf(self, pdf) -> str:
        """使用 PaddleOCR 对 PDF 各页图片进行 OCR，返回拼接文本"""
        try:
            from paddleocr import PaddleOCR
        except ImportError:
            raise ImportError("图片型 PDF 需要 PaddleOCR：pip install paddleocr")

        if not hasattr(PdfInvoiceParser, '_ocr_instance') or PdfInvoiceParser._ocr_instance is None:
            import os
            use_gpu = os.environ.get("PADDLE_USE_GPU", "1").strip() not in ("0", "false", "False", "no")
            PdfInvoiceParser._ocr_instance = PaddleOCR(use_angle_cls=True, lang='ch', show_log=False, use_gpu=use_gpu)
        ocr = PdfInvoiceParser._ocr_instance

        import numpy as np
        lines_all = []
        for page in pdf.pages:
            img = page.to_image(resolution=150).original  # PIL Image
            result = ocr.ocr(np.array(img), cls=True)
            if not result or not result[0]:
                continue
            items = sorted(result[0], key=lambda x: x[0][0][1])
            for item in items:
                text = item[1][0]
                lines_all.append(text)

        return "\n".join(lines_all)

    def _extract_invoice(self, pdf) -> Invoice:
        """从 PDF 中提取发票信息"""
        import re

        all_text = ""
        all_tables = []
        for page in pdf.pages:
            text = page.extract_text() or ""
            all_text += text + "\n"
            tables = page.extract_tables() or []
            all_tables.extend(tables)

        # 若文本过少（图片型 PDF），尝试 OCR 兜底
        if len(all_text.strip()) < 20:
            all_text = self._ocr_pdf(pdf)

        inv = Invoice(source_format="PDF")

        # 提取发票号码
        m = re.search(r"发票号码[：:\s]*(\d+)", all_text)
        if m:
            inv.invoice_number = m.group(1)

        # 提取发票代码
        m = re.search(r"发票代码[：:\s]*(\d+)", all_text)
        if m:
            inv.invoice_code = m.group(1)

        # 提取日期
        m = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", all_text)
        if m:
            inv.date = f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"

        # 提取销方信息
        seller_name = self._extract_field(all_text, [
            r"销\s*售\s*方[：:\s]*名\s*称[：:\s]*(.+)",
            r"销\s*方[：:\s]*(.+?)(?:\n|税)",
            r"收款单位[：:\s]*(.+)",
        ])
        if seller_name:
            inv.seller = SellerInfo(name=seller_name.strip())

        # 提取购方信息
        buyer_name = self._extract_field(all_text, [
            r"购\s*买\s*方[：:\s]*名\s*称[：:\s]*(.+)",
            r"购\s*方[：:\s]*(.+?)(?:\n|税)",
        ])
        if buyer_name:
            inv.buyer = SellerInfo(name=buyer_name.strip())

        # 从表格中提取明细行
        inv.lines = self._extract_lines_from_tables(all_tables, all_text)

        # 若表格解析未得到明细行，尝试从全文正则提取
        if not inv.lines:
            inv.lines = self._extract_lines_from_text(all_text)

        # 计算总金额
        if inv.lines:
            inv.total_amount = sum(l.amount for l in inv.lines)

        return inv

    def _extract_field(self, text: str, patterns: List[str]) -> Union[str, None]:
        """按多个正则模式尝试提取字段"""
        import re
        for pat in patterns:
            m = re.search(pat, text)
            if m:
                return m.group(1).strip()
        return None

    def _extract_lines_from_tables(self, tables: list, full_text: str) -> List[InvoiceLineItem]:
        """从 PDF 表格中提取发票明细行"""
        import re

        lines = []
        # 中国发票表格列名关键词
        name_keywords = ("货物", "名称", "劳务", "项目", "服务")
        qty_keywords = ("数量",)
        unit_keywords = ("单位",)
        price_keywords = ("单价",)
        tax_code_keywords = ("编码", "税收分类", "分类编码")

        for table in tables:
            if not table or len(table) < 2:
                continue
            # 识别表头
            header = table[0]
            if header is None:
                continue
            header_str = [str(h).strip() if h else "" for h in header]

            name_col = self._find_col_index(header_str, name_keywords)
            amount_col = self._find_amount_col_index(header_str)
            qty_col = self._find_col_index(header_str, qty_keywords)
            unit_col = self._find_col_index(header_str, unit_keywords)
            price_col = self._find_col_index(header_str, price_keywords)
            tax_code_col = self._find_col_index(header_str, tax_code_keywords)

            if name_col is None:
                continue

            for row in table[1:]:
                if row is None:
                    continue
                row_str = [str(c).strip() if c else "" for c in row]
                name = row_str[name_col] if name_col < len(row_str) else ""
                if not name or name in ("合计", "价税合计", "小计", ""):
                    continue
                # 跳过包含"合计"的汇总行
                if any(kw in name for kw in ("合计", "价税合计", "小计")):
                    continue

                # 提取税收分类名称（如 *成品油*汽油）
                tax_name = None
                m_tax = re.search(r"\*(.+?\*.+)", name)
                if m_tax:
                    tax_name = m_tax.group(0)

                amount = self._parse_number(
                    row_str[amount_col] if amount_col is not None and amount_col < len(row_str) else ""
                )
                quantity = self._parse_number(
                    row_str[qty_col] if qty_col is not None and qty_col < len(row_str) else ""
                )
                unit = (
                    row_str[unit_col] if unit_col is not None and unit_col < len(row_str) else None
                ) or None
                unit_price = self._parse_number(
                    row_str[price_col] if price_col is not None and price_col < len(row_str) else ""
                )
                tax_code = (
                    row_str[tax_code_col] if tax_code_col is not None and tax_code_col < len(row_str) else None
                ) or None

                # 若 amount 与 unit_price 接近（差距 < 2%），且 quantity > 1，
                # 则认为 amount 实为单价被误存，纠正为 unit_price * quantity
                if (unit_price and quantity and quantity > 1 and amount
                        and abs(amount - unit_price) / (unit_price + 1e-9) < 0.02):  # 2% 误差阈值
                    amount = unit_price * quantity

                lines.append(InvoiceLineItem(
                    name=name,
                    tax_classification_code=tax_code,
                    tax_classification_name=tax_name,
                    quantity=quantity if quantity and quantity > 0 else None,
                    unit=unit if unit else None,
                    unit_price=unit_price if unit_price and unit_price > 0 else None,
                    amount=amount or 0.0,
                ))

        return lines

    def _extract_lines_from_text(self, text: str) -> List[InvoiceLineItem]:
        """当表格提取失败时，从全文正则提取明细行（兜底）"""
        import re

        lines = []

        # Pre-process: merge lines where a *category*name is split across lines.
        # A line that starts with '*' but contains no digits is likely a broken item name;
        # merge it with the following line.
        raw_lines = text.split("\n")
        merged_lines = []
        i = 0
        while i < len(raw_lines):
            line = raw_lines[i]
            if line.strip().startswith("*") and not re.search(r"\d", line):
                next_line = raw_lines[i + 1] if i + 1 < len(raw_lines) else ""
                merged_lines.append(line.rstrip() + next_line.lstrip())
                i += 2
            else:
                merged_lines.append(line)
                i += 1
        processed_text = "\n".join(merged_lines)

        # Pattern 1: *类别*名称 + numbers (existing pattern)
        pattern = re.compile(
            r"(\*[^*]+\*[^\s]+)\s+"
            r"(?:(\d+(?:\.\d+)?)\s+)?"  # 数量（可选）
            r"(?:([^\d\s]+)\s+)?"       # 单位（可选）
            r"(?:(\d+(?:\.\d+)?)\s+)?"  # 单价（可选）
            r"(\d+(?:\.\d+)?)"          # 金额
        )
        for m in pattern.finditer(processed_text):
            name = m.group(1).strip()
            # 提取本行名称之后的所有数字，按位置取值
            name_end = m.start(1) + len(m.group(1))
            eol = processed_text.find('\n', name_end)
            line_rest = processed_text[name_end: eol if eol != -1 else len(processed_text)]
            all_nums = re.findall(r'\d+(?:\.\d+)?', line_rest)
            if len(all_nums) >= 4:
                # 中国增值税发票固定列顺序：数量, 单价, 金额（不含税）, 税额
                # 倒数第二个数字为金额（不含税），最后一个为税额（忽略）
                quantity = self._parse_number(all_nums[0])
                unit_price = self._parse_number(all_nums[-3])
                amount = self._parse_number(all_nums[-2]) or 0.0
            else:
                quantity = self._parse_number(m.group(2)) if m.group(2) else None
                unit_price = self._parse_number(m.group(4)) if m.group(4) else None
                amount = self._parse_number(m.group(5)) or 0.0
            unit = m.group(3).strip() if m.group(3) else None
            lines.append(InvoiceLineItem(
                name=name,
                tax_classification_name=name,
                quantity=quantity if quantity and quantity > 0 else None,
                unit=unit,
                unit_price=unit_price if unit_price and unit_price > 0 else None,
                amount=amount,
            ))

        # Pattern 2 (fallback): non-asterisk item names followed by numbers
        if not lines:
            pattern2 = re.compile(
                r"([\u4e00-\u9fffA-Za-z][^\n]*?)\s+"
                r"(?:(\d+(?:\.\d+)?)\s+)?"  # 数量（可选）
                r"(?:([^\d\s]+)\s+)?"        # 单位（可选）
                r"(?:(\d+(?:\.\d+)?)\s+)?"   # 单价（可选）
                r"(\d+(?:\.\d+)?)"           # 金额
            )
            for m in pattern2.finditer(processed_text):
                name = m.group(1).strip()
                # Skip summary / header lines
                if any(kw in name for kw in ("合计", "价税合计", "小计", "名称", "单价", "数量")):
                    continue
                # 提取本行名称之后的所有数字，按位置取值
                name_end = m.start(1) + len(m.group(1))
                eol = processed_text.find('\n', name_end)
                line_rest = processed_text[name_end: eol if eol != -1 else len(processed_text)]
                all_nums = re.findall(r'\d+(?:\.\d+)?', line_rest)
                if len(all_nums) >= 4:
                    quantity = self._parse_number(all_nums[0])
                    unit_price = self._parse_number(all_nums[-3])
                    amount = self._parse_number(all_nums[-2]) or 0.0
                else:
                    quantity = self._parse_number(m.group(2)) if m.group(2) else None
                    unit_price = self._parse_number(m.group(4)) if m.group(4) else None
                    amount = self._parse_number(m.group(5)) or 0.0
                unit = m.group(3).strip() if m.group(3) else None
                if amount <= 0:
                    continue
                lines.append(InvoiceLineItem(
                    name=name,
                    tax_classification_name=None,
                    quantity=quantity if quantity and quantity > 0 else None,
                    unit=unit,
                    unit_price=unit_price if unit_price and unit_price > 0 else None,
                    amount=amount,
                ))

        return lines

    @staticmethod
    def _find_col_index(header: List[str], keywords: tuple) -> Union[int, None]:
        """在表头中查找包含关键词的列索引"""
        for i, h in enumerate(header):
            for kw in keywords:
                if kw in h:
                    return i
        return None

    @staticmethod
    def _find_amount_col_index(header: List[str]) -> Union[int, None]:
        """查找金额（不含税）列，优先精确匹配，显式排除含"税"字的列被误认为金额列"""
        # 第一优先：精确匹配"不含税"相关列名
        for i, h in enumerate(header):
            if any(kw in h for kw in ("金额（不含税）", "不含税金额", "合计金额")):
                return i
        # 第二优先：含"金额"但不含"税"字（排除"税额"等列）
        for i, h in enumerate(header):
            if "金额" in h and "税" not in h:
                return i
        # 兜底：价税合计
        for i, h in enumerate(header):
            if "价税合计" in h:
                return i
        return None

    @staticmethod
    def _parse_number(val: str) -> Union[float, None]:
        """安全解析数值字符串"""
        if not val:
            return None
        import re
        cleaned = re.sub(r"[,，\s]", "", str(val).strip())
        try:
            return float(cleaned)
        except (ValueError, TypeError):
            return None
