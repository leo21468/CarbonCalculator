"""
第一步：数据采集 - 发票结构化提取。
系统通过接口提取电子发票（OFD/PDF/XML）的结构化数据。
核心抓取字段：货物或应税劳务名称、税收分类编码、金额/单价/数量、销方信息。

碳排放计算输入字段说明
-----------------------
碳排放核算**始终使用"金额"（amount）字段**作为 EEIO 支出法的输入：
    碳排放量(kgCO2e) = 金额(CNY) × 碳排放强度(kgCO2e/元)

金额字段解析支持以下常见格式（由 ``parse_amount_cny`` 处理）：
    "¥1,234.56"  → 1234.56
    "￥1,234.56" → 1234.56
    "RMB 5000"   → 5000.0
    "1,234.56元" → 1234.56
    "1 234,56"   → 1234.56（欧式千位空格+逗号小数点）

**不应**使用税率（税率字段，如"13%"、"9%"）作为金额来源。
"""
from __future__ import annotations
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional, Union

# 预编译常用正则，提升性能（在 parse_amount_cny、_parse_number 及文本解析中复用）
_RE_PERCENT = re.compile(r'\d+(?:\.\d+)?%')   # 税率百分比（如"13%"）
_RE_CURRENCY = re.compile(r'[¥￥]')            # 人民币货币符号
_RE_RMBORЦNY = re.compile(r'\b(RMB|CNY)\b', re.IGNORECASE)  # 货币名称缩写
_RE_TAX_RATE_COL = re.compile(r'\d+(?:\.\d+)?%')  # 发票行中的税率列值

from .models import Invoice, InvoiceLineItem, SellerInfo


def parse_amount_cny(val: str) -> Optional[float]:
    """解析带货币符号的金额字符串为人民币浮点数（CNY）。

    碳排放计算使用此函数将发票/收据中的金额字段统一转为 float，
    **不接受税率（如"13%"）作为金额**。

    支持格式：
        - "¥1,234.56" / "￥1,234.56"    → 1234.56
        - "RMB 1,234.56" / "CNY 5000"   → 1234.56 / 5000.0
        - "1,234.56元" / "1234元"        → 1234.56 / 1234.0
        - "1 234,56"（欧式：空格千位+逗号小数）→ 1234.56
        - "1,234,567.89"（标准千位分隔）  → 1234567.89
        - 负数、超大金额均正常解析

    遇到无法解析的格式（如纯百分比"13%"）返回 None，调用方应
    降级到其他字段或记录日志，不得使用税率作为金额替代。

    Args:
        val: 待解析的金额字符串。

    Returns:
        解析后的浮点数（元），无法解析时返回 None。
    """
    if not val:
        return None
    s = str(val).strip()
    # 拒绝百分比值（税率如"13%"、"9%"），碳排放计算不使用税率字段
    if _RE_PERCENT.search(s):
        return None
    # 去除货币符号与中文单位前缀/后缀
    s = _RE_CURRENCY.sub('', s)
    s = _RE_RMBORЦNY.sub('', s)
    s = re.sub(r'元\s*$', '', s)
    s = s.strip()
    # 全角字符规范化
    s = s.replace('，', ',').replace('。', '.').replace('　', ' ')
    # 同时含逗号和点：按标准格式（逗号=千位符，点=小数点）处理
    if ',' in s and '.' in s:
        s = s.replace(',', '')
    elif ',' in s:
        # 仅有逗号：若逗号后恰好跟3位数字则视为千位符，否则视为小数点
        last_comma = s.rfind(',')
        after = s[last_comma + 1:]
        if re.fullmatch(r'\d{3}', after):
            s = s.replace(',', '')
        else:
            s = s.replace(',', '.')
    # 去掉剩余空格（欧式千位空格如"1 234"）
    s = re.sub(r'\s', '', s)
    # 保留数字、小数点、负号
    s = re.sub(r'[^\d.\-]', '', s)
    if not s:
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


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
        """解析 XML 为 _build_invoice 期望的 dict 结构（含 lines、invoice_number 等）。"""
        try:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(xml_text)
            return self._xml_to_invoice_dict(root)
        except ET.ParseError:
            return {}

    def _xml_to_invoice_dict(self, root) -> dict:
        """从 XML 根节点提取发票字段，映射为 {lines, invoice_number, seller, ...}"""
        # 去除可能的命名空间前缀，便于匹配
        def tag(el):
            return el.tag.split("}")[-1] if el.tag and "}" in el.tag else (el.tag or "")

        def text(el, default: str = ""):
            return (el.text or "").strip() if el is not None else default

        def find_text(parent, *names):
            if parent is None:
                return None
            names_set = {n for n in names}
            for child in parent:
                if tag(child) in names_set:
                    t = text(child)
                    if t:
                        return t
            return None

        def find_text_excluding(parent, accept: tuple, exclude: tuple):
            """查找文本，接受 accept 中的标签，排除 exclude（如税额 se）"""
            if parent is None:
                return None
            ex_set = {str(x) for x in exclude}
            acc_set = {str(x) for x in accept}
            for child in parent:
                if tag(child) in ex_set:
                    continue
                if tag(child) in acc_set:
                    t = text(child)
                    if t:
                        return t
            return None

        def find_text_recursive(node, *names):
            """递归查找首个匹配的叶子文本（用于嵌套结构如 REQUEST/BODY/Invoice）"""
            if node is None:
                return None
            names_set = {n for n in names}
            if tag(node) in names_set:
                t = text(node)
                if t:
                    return t
            for child in node:
                v = find_text_recursive(child, *names)
                if v:
                    return v
            return None

        # 递归收集所有 19 位税收编码
        def collect_tax_codes(node, acc: list):
            if node is None:
                return
            t = text(node) if hasattr(node, "text") else ""
            if t and len(t.replace(" ", "")) == 19 and t.replace(" ", "").isdigit():
                acc.append(t.replace(" ", ""))
            for child in node:
                collect_tax_codes(child, acc)

        tax_codes = []
        collect_tax_codes(root, tax_codes)

        detail_paths = [
            "EInvoiceData", "eInvoiceData", "FPDetail", "FPMX", "FPDMX", "fpDetail", "fpmx", "fpdmx",
            "Detail", "Details", "Items", "items", "Goods", "goods", "COMMON_FPKJ_XMXXS", "COMMON_FPKJ_XMXX",
            "FPMXXX", "fpmxxx", "HXMX", "hxmx", "XMX", "xmx", "MXXX", "mxxx",
        ]
        row_tags = ["IssuItemInformation", "issuItemInformation", "Item", "item", "Row", "row", "COMMON_FPKJ_XMXX"]

        # 递归查找明细容器节点
        def find_container(node, paths_set):
            if node is None:
                return None
            if tag(node) in paths_set:
                return node
            for child in node:
                found = find_container(child, paths_set)
                if found:
                    return found
            return None

        paths_set = set(detail_paths)
        items_container = find_container(root, paths_set)

        def collect_row_like_nodes(node, acc: list):
            """递归收集形如明细行的节点（含金额且含名称或数量，排除税额）"""
            if node is None:
                return
            name_ok = find_text(node, "name", "Name", "hwmc", "XMMC", "xmmc", "spmc", "项目名称")
            amount_ok = find_text_excluding(node, ("amount", "je", "JE", "XMJE", "xmje", "金额"), ("se", "SE", "税额"))
            qty_ok = find_text(node, "quantity", "sl", "XMSL", "xmsl", "数量")
            if amount_ok and (name_ok or qty_ok):
                acc.append(node)
            for child in node:
                collect_row_like_nodes(child, acc)

        lines = []
        if items_container is not None:
            candidates = []
            for child in items_container:
                if tag(child) in row_tags:
                    candidates.append(child)
                elif tag(child) in ("Item", "COMMON_FPKJ_XMXX"):
                    candidates.append(child)
            if not candidates:
                for child in items_container:
                    for sub in child:
                        if tag(sub) in row_tags:
                            candidates.append(sub)
            if not candidates:
                collect_row_like_nodes(root, candidates)
            for idx, row in enumerate(candidates):
                name = find_text(row, "name", "Name", "ItemName", "itemName", "hwmc", "HWMC", "goodsName", "spmc", "SPMC", "XMMC", "xmmc", "项目名称")
                tax_code = find_text(row, "taxCode", "TaxCode", "TaxClassificationCode", "taxClassificationCode", "spbm", "SPBM", "ssbm", "ssflbm", "税收分类编码")
                if not tax_code and idx < len(tax_codes):
                    tax_code = tax_codes[idx]
                if tax_code and (len(tax_code) != 19 or not tax_code.isdigit()):
                    tax_code = "".join(c for c in tax_code if c.isdigit())
                    tax_code = tax_code if len(tax_code) == 19 else None
                amount_s = find_text_excluding(
                    row,
                    ("amount", "Amount", "je", "JE", "XMJE", "xmje", "金额", "hj", "HJ"),
                    ("se", "SE", "ComTaxAm", "comTaxAm", "税额"),  # 排除税额
                )
                amount = float(amount_s) if amount_s else 0.0
                quantity_s = find_text(row, "quantity", "Quantity", "Quantity", "sl", "SL", "XMSL", "xmsl", "数量")
                quantity = float(quantity_s) if quantity_s else None
                unit = find_text(row, "unit", "Unit", "MeaUnits", "meaUnits", "dw", "DW", "单位")
                price_s = find_text(row, "price", "Price", "UnPrice", "unPrice", "dj", "DJ", "XMDJ", "xmdj", "单价")
                unit_price = float(price_s) if price_s else None
                lines.append({
                    "name": name or "",
                    "amount": amount,
                    "tax_classification_code": tax_code,
                    "quantity": quantity,
                    "unit": unit,
                    "unit_price": unit_price,
                })

        total_amount = 0.0
        total_s = find_text_recursive(root, "totalAmount", "TotalAmount", "TotalAmWithoutTax", "totalAmWithoutTax", "TotalTax-includedAmount", "hjje", "HJJE", "价税合计", "合计金额")
        if total_s:
            try:
                total_amount = float(total_s)
            except ValueError:
                pass
        if not total_amount and lines:
            total_amount = sum(line.get("amount", 0) or 0 for line in lines)

        invoice_number = find_text_recursive(root, "invoiceNumber", "InvoiceNumber", "EIid", "eiid", "fpdm", "FPDM", "invoiceNo", "发票代码", "发票号码")
        invoice_date = find_text_recursive(root, "invoiceDate", "IssueTime", "issueTime", "kprq", "KPRQ", "date", "开票日期")
        seller_name = find_text_recursive(root, "sellerName", "SellerName", "sellerName", "xfmc", "XFMC", "销方名称", "销售方")
        buyer_name = find_text_recursive(root, "buyerName", "BuyerName", "buyerName", "gfmc", "GFMC", "购方名称", "购买方")

        return {
            "invoice_number": invoice_number,
            "date": invoice_date,
            "total_amount": total_amount,
            "lines": lines,
            "seller": {"name": seller_name} if seller_name else None,
            "buyer": {"name": buyer_name} if buyer_name else None,
        }

    def _element_to_dict(self, el) -> dict:
        """将 XML 节点转为 dict（兼容旧逻辑，现由 _xml_to_invoice_dict 主导）"""
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

    @staticmethod
    def clear_ocr_cache():
        """清空 OCR 引擎实例缓存，强制下次调用时重新初始化。

        适用场景：
        - 切换 GPU/CPU 模式后需要重新初始化
        - 内存占用过高需要释放模型
        - 单元测试之间需要隔离状态
        """
        PdfInvoiceParser._ocr_instance = None
        PdfInvoiceParser._ppstructure_instance = None

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

    def _ocr_pdf_ppstructure(self, pdf) -> tuple[List[list], str, list]:
        """使用百度 PP-Structure（版面分析+表格识别）处理图片型 PDF。

        返回 (all_tables, all_text, ocr_structured)：
        - all_tables: 每页表格的列表 [[row,...], ...]，可直接用于 _extract_lines_from_tables
        - all_text: 拼接的全文（含 Text 区域 OCR 结果）
        - ocr_structured: 与 _ocr_pdf 相同的页列表，供 _extract_lines_from_ocr_structured 兜底
        """
        try:
            from paddleocr import PPStructure
        except ImportError:
            raise ImportError("PP-Structure 需要 paddleocr：pip install paddleocr")

        if not hasattr(PdfInvoiceParser, '_ppstructure_instance') or PdfInvoiceParser._ppstructure_instance is None:
            PdfInvoiceParser._ppstructure_instance = PPStructure(
                show_log=False, table=True, layout=True, ocr=True
            )
        engine = PdfInvoiceParser._ppstructure_instance

        import numpy as np
        try:
            import cv2
        except ImportError:
            cv2 = None

        all_tables: List[list] = []
        all_text_parts: List[str] = []
        all_page_ocr: list = []  # 兼容 _extract_lines_from_ocr_structured 的格式

        for page_idx, page in enumerate(pdf.pages):
            img_pil = page.to_image(resolution=150).original
            img_np = np.array(img_pil)
            if cv2 is not None and len(img_np.shape) == 3 and img_np.shape[2] == 3:
                img_np = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
            try:
                result = engine(img_np)
            except Exception:
                result = []
            if not result:
                all_text_parts.append("")
                all_page_ocr.append({"page": page_idx + 1, "rows": [], "full_text": ""})
                continue

            page_texts = []
            page_rows_for_ocr = []
            for region in result:
                rtype = region.get("type", "")
                res = region.get("res")
                if rtype == "table" and res and isinstance(res, dict):
                    html = res.get("html")
                    if html:
                        tbl = self._parse_ppstructure_table_html(html)
                        if tbl and len(tbl) >= 2:
                            all_tables.append(tbl)
                elif rtype == "text" and res:
                    rec_res = res[1] if isinstance(res, (list, tuple)) and len(res) >= 2 else res
                    for item in (rec_res if isinstance(rec_res, (list, tuple)) else [rec_res]):
                        t = item[0] if isinstance(item, (list, tuple)) else str(item)
                        page_texts.append(t)
                        page_rows_for_ocr.append({"columns": [t], "y_center": 0})
            text_line = " ".join(page_texts)
            all_text_parts.append(text_line)
            if page_rows_for_ocr:
                all_page_ocr.append({
                    "page": page_idx + 1,
                    "rows": page_rows_for_ocr,
                    "full_text": text_line,
                })
            else:
                all_page_ocr.append({"page": page_idx + 1, "rows": [], "full_text": text_line})

        all_text = "\n".join(all_text_parts)
        return all_tables, all_text, all_page_ocr

    def _parse_ppstructure_table_html(self, html: str) -> Optional[list]:
        """将 PP-Structure 表格 HTML 解析为 [[cell,...], ...] 行列表"""
        if not html or not html.strip():
            return None
        try:
            import pandas as pd
            dfs = pd.read_html(html)
        except Exception:
            return None
        if not dfs:
            return None
        df = dfs[0]
        rows = []
        for _, r in df.iterrows():
            row = []
            for v in r.tolist():
                if v is None or (isinstance(v, float) and (v != v or v == float("inf"))):
                    row.append("")
                else:
                    row.append(str(v).strip())
            rows.append(row)
        if not rows:
            header = [str(c).strip() for c in df.columns.tolist()]
            if header:
                rows = [header]
        else:
            header = [str(c).strip() for c in df.columns.tolist()]
            if header and (not rows or [str(x) for x in rows[0]] != header):
                rows.insert(0, header)
        return rows if rows else None

    def _ocr_pdf(self, pdf) -> tuple[str, list]:
        """使用 PaddleOCR 对 PDF 各页图片进行 OCR，返回 (拼接文本, 结构化页列表) 元组"""
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
        all_page_results = []
        for page in pdf.pages:
            img = page.to_image(resolution=150).original  # PIL Image
            result = ocr.ocr(np.array(img), cls=True)
            if result and result[0]:
                all_page_results.append(result[0])

        structured = self._structure_postprocess(all_page_results)
        ocr_text = "\n".join(page["full_text"] for page in structured)
        return ocr_text, structured

    def _structure_postprocess(self, all_page_results: list) -> list:
        """对 PaddleOCR 识别结果进行结构化后处理，降低列串位。

        参数:
            all_page_results: 每页 OCR 结果的列表（每元素为 PaddleOCR 单页结果列表）。

        返回:
            list of dict，每个元素描述一页：
            {
                "page": int,
                "rows": [{"y_center": float, "words": [...], "columns": [...]}],
                "full_text": str,
            }
        """
        import statistics

        pages_output = []

        for page_idx, page_items in enumerate(all_page_results):
            if not page_items:
                pages_output.append({"page": page_idx + 1, "rows": [], "full_text": ""})
                continue

            # ── 1. 从 bbox 计算每个词块的中心坐标 ──────────────────────────
            words = []
            for item in page_items:
                bbox = item[0]   # 4 点坐标：[[x0,y0],[x1,y0],[x1,y1],[x0,y1]]
                text = item[1][0]
                score = item[1][1] if len(item[1]) > 1 else 1.0
                xs = [pt[0] for pt in bbox]
                ys = [pt[1] for pt in bbox]
                x0, x1 = min(xs), max(xs)
                y0, y1 = min(ys), max(ys)
                x_center = (x0 + x1) / 2.0
                y_center = (y0 + y1) / 2.0
                words.append({
                    "text": text,
                    "x_center": x_center,
                    "x0": x0, "x1": x1,
                    "y0": y0, "y1": y1,
                    "y_center": y_center,
                    "score": score,
                })

            # ── 2. 行归并：按 y_center 聚合，自适应阈值 ──────────────────────
            heights = [w["y1"] - w["y0"] for w in words if w["y1"] > w["y0"]]
            if heights:
                median_h = statistics.median(heights)
                row_threshold = max(median_h * 0.6, 5.0)
            else:
                row_threshold = 10.0

            sorted_words = sorted(words, key=lambda w: w["y_center"])
            rows: list = []
            for word in sorted_words:
                placed = False
                for row in rows:
                    if abs(word["y_center"] - row["y_center"]) <= row_threshold:
                        row["words"].append(word)
                        # 更新行的 y_center 为均值
                        row["y_center"] = sum(w["y_center"] for w in row["words"]) / len(row["words"])
                        placed = True
                        break
                if not placed:
                    rows.append({"y_center": word["y_center"], "words": [word]})

            # 行内按 x 升序排列
            for row in rows:
                row["words"].sort(key=lambda w: w["x_center"])

            # ── 3. 列识别：对所有词块 x_center 做 1-D 聚类 ────────────────────
            all_x = [w["x_center"] for w in words]
            if all_x:
                col_centers = self._cluster_columns(all_x)
            else:
                col_centers = []

            # 为每个 row 生成按列对齐的列文本列表
            if col_centers:
                num_cols = len(col_centers)
                for row in rows:
                    col_texts = [""] * num_cols
                    for word in row["words"]:
                        # 找到最近的列
                        col_idx = min(
                            range(num_cols),
                            key=lambda i: abs(col_centers[i] - word["x_center"]),
                        )
                        col_texts[col_idx] = (col_texts[col_idx] + " " + word["text"]).strip()
                    row["columns"] = col_texts
            else:
                for row in rows:
                    row["columns"] = [w["text"] for w in row["words"]]

            # ── 4. 构建 full_text（行内以空格分隔，行间以换行分隔）────────────
            line_texts = [" ".join(w["text"] for w in row["words"]) for row in rows]
            full_text = "\n".join(line_texts)

            pages_output.append({
                "page": page_idx + 1,
                "rows": rows,
                "full_text": full_text,
            })

        return pages_output

    @staticmethod
    def _cluster_columns(x_centers: list) -> list:
        """对 x 坐标列表做轻量 1-D 聚类，返回各列中心点列表（升序）。

        优先尝试 sklearn KMeans；若不可用则使用基于间距的分箱算法。
        """
        if not x_centers:
            return []

        # 中国发票通常为 8 列；避免过度压缩导致名称与数值混列
        n = len(x_centers)
        n_cols = min(max(6, n // max(2, n // 10)), n, 12)

        try:
            from sklearn.cluster import KMeans
            import numpy as np
            arr = np.array(x_centers).reshape(-1, 1)
            km = KMeans(n_clusters=n_cols, random_state=0)
            km.fit(arr)
            centers = sorted(float(c[0]) for c in km.cluster_centers_)
            return centers
        except Exception:
            pass

        # 降级：基于相邻间距的分箱
        sorted_x = sorted(x_centers)
        if len(sorted_x) < 2:
            return sorted_x[:]

        gaps = [sorted_x[i + 1] - sorted_x[i] for i in range(len(sorted_x) - 1)]
        avg_gap = sum(gaps) / len(gaps)
        split_threshold = avg_gap * 1.5

        clusters: list = [[sorted_x[0]]]
        for x in sorted_x[1:]:
            if x - clusters[-1][-1] > split_threshold:
                clusters.append([x])
            else:
                clusters[-1].append(x)

        return [sum(c) / len(c) for c in clusters]

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

        ocr_structured = []

        # 新优先级（从高到低）：
        # 1. PaddleOCR（最高精度，始终首选）
        # 2. PP-Structure（仅当 PaddleOCR 不可用时）
        # 3. pdfplumber 原生文本（最低优先级/兜底，已在上方采集）
        def _try_ppstructure():
            try:
                nonlocal all_text, all_tables, ocr_structured
                pp_tables_tmp, pp_text_tmp, ocr_structured = self._ocr_pdf_ppstructure(pdf)
                if pp_text_tmp.strip():
                    all_text = pp_text_tmp
                if pp_tables_tmp:
                    all_tables = pp_tables_tmp
            except Exception:
                pass

        try:
            ocr_text, ocr_structured = self._ocr_pdf(pdf)
            if ocr_text.strip():
                all_text = ocr_text
        except Exception:
            # PaddleOCR 未安装（ImportError）或运行异常 → 降级到 PP-Structure
            _try_ppstructure()

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

        # 从表格中提取明细行（优先）
        inv.lines = self._extract_lines_from_tables(all_tables, all_text)

        # 若表格解析未得到明细行，使用 OCR 结构化输出
        if not inv.lines:
            if ocr_structured:
                inv.lines = self._extract_lines_from_ocr_structured(ocr_structured)
            if not inv.lines:
                inv.lines = self._extract_lines_from_text(all_text)
            # 若仍无明细，尝试 VI-LayoutXLM KIE（需配置 PADDLEOCR_ROOT + USE_KIE=1）
            if not inv.lines and ocr_structured:
                try:
                    from .kie_extractor import try_kie_extract
                    import tempfile
                    import os
                    tmp_path = None
                    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                        tmp_path = tmp.name
                        pdf.pages[0].to_image(resolution=150).original.save(tmp_path)
                        inv.lines = try_kie_extract(tmp_path)
                    if tmp_path and os.path.exists(tmp_path):
                        os.unlink(tmp_path)
                except Exception:
                    pass

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
                # 中国发票表格列名关键词（列序：项目名称、规格型号、单位、数量、单价、金额、税率、税额）
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

            if name_col is None and len(header_str) >= 1:
                name_col = 0

            if name_col is None:
                continue

            if amount_col is None and len(header_str) >= 5:
                amount_col = min(5, len(header_str) - 2)

            # 预处理：合并名称跨行（第二行名称列为空且其他数值列也为空时，
            # 将第一列的续行文字追加到上一行的名称列）
            merged_rows: list = []
            for row in table[1:]:
                if row is None:
                    merged_rows.append(row)
                    continue
                row_str = [str(c).strip() if c else "" for c in row]
                row_name = row_str[name_col] if name_col < len(row_str) else ""
                # 判断是否为续行：名称列为空，且所有金额/数值列也为空
                # 排除第0列（可能含续行文字）和名称列自身
                value_cols_empty = all(
                    not row_str[k]
                    for k in range(len(row_str))
                    if k != 0 and k != name_col  # col 0 is checked separately as continuation text
                )
                first_col_text = row_str[0] if row_str else ""
                is_continuation = (
                    not row_name
                    and merged_rows
                    and merged_rows[-1] is not None
                    and value_cols_empty
                    and first_col_text
                    and not re.match(r'^[¥￥\d,，.\s%]+$', first_col_text)
                )
                if is_continuation:
                    prev_row = list(merged_rows[-1])
                    prev_name = str(prev_row[name_col]).strip() if name_col < len(prev_row) and prev_row[name_col] else ""
                    if prev_name:
                        prev_row[name_col] = prev_name + first_col_text
                        merged_rows[-1] = prev_row
                        continue
                merged_rows.append(row)

            for row in merged_rows:
                if row is None:
                    continue
                row_str = [str(c).strip() if c else "" for c in row]
                name = row_str[name_col] if name_col < len(row_str) else ""
                if not name or name.strip() == "":
                    for j, cell in enumerate(row_str):
                        if j != amount_col and cell and not re.match(r'^[¥￥\d,，.\s%]+$', str(cell)):
                            if any('\u4e00' <= c <= '\u9fff' for c in str(cell)):
                                name = cell.strip()
                                break
                if not name or name in ("合计", "价税合计", "小计", ""):
                    continue
                if any(kw in name for kw in ("合计", "价税合计", "小计")):
                    continue

                # 提取税收分类名称（如 *成品油*汽油）
                tax_name = None
                m_tax = re.search(r"\*(.+?\*.+)", name)
                if m_tax:
                    tax_name = m_tax.group(0)

                amount_cell = row_str[amount_col] if amount_col is not None and amount_col < len(row_str) else ""
                qty_cell = row_str[qty_col] if qty_col is not None and qty_col < len(row_str) else ""
                nums_amount = self._parse_numbers_from_cell(amount_cell)
                nums_qty = self._parse_numbers_from_cell(qty_cell)
                if len(nums_amount) > 1:
                    amts = [n for n in nums_amount if 0.01 < n < 1e8 and abs(n - round(n, 2)) < 1e-9]
                    amount = max(amts) if amts else nums_amount[-1]
                elif nums_amount:
                    amount = nums_amount[-1]
                else:
                    amount = self._parse_number(amount_cell)
                quantity = nums_qty[0] if nums_qty else self._parse_number(qty_cell)
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

        raw_lines = text.split("\n")

        # First attempt: block-based multi-line OCR merging (handles scanned PDFs where
        # each field of an item is on its own line).  If blocks are found we return early
        # to avoid the existing 2-line pre-processing from mangling the multi-line text
        # (e.g. merging a name-only line with the first number, which causes the old
        # pattern to capture the tax rate digit as the amount instead of the real amount).
        block_items = self._extract_from_ocr_blocks(raw_lines)
        if block_items:
            return block_items
        merged_lines = []
        i = 0
        while i < len(raw_lines):
            line = raw_lines[i]
            # 当前行是 *XX*YY 格式名称行（无小数、少于2个独立整数）→ 循环向前看，支持三行以上跨行名称合并
            is_star_name = (line.strip().startswith("*")
                            and not re.search(r'\d+\.\d+', line)
                            and len(re.findall(r'\b\d+\b', line)) < 2)
            if is_star_name:
                merged = line.rstrip()
                j = i + 1
                while j < len(raw_lines):
                    nxt = raw_lines[j].strip()
                    if not nxt:
                        j += 1
                        continue
                    # 另一个 *XX*YY 格式行 → 新商品，停止合并
                    if nxt.startswith("*"):
                        break
                    # 无数字且长度≤15的中文片段 → 名称续行，继续合并
                    if not re.search(r'\d', nxt) and len(nxt) <= 15:
                        merged = merged + nxt
                        j += 1
                        continue
                    # 含数字 → 本商品数量/金额行，合并后停止
                    merged = merged + " " + nxt
                    j += 1
                    break
                merged_lines.append(merged)
                i = j
            else:
                merged_lines.append(line)
                i += 1
        processed_text = "\n".join(merged_lines)

        # Pattern 1: *类别*名称 或 **类别**名称 + numbers
        pattern = re.compile(
            r"(\*+[^*]+\*+[^\s]*)\s+"
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
            # 过滤税率列：先移除形如"13%"、"9%"等百分比值，避免税率数字被误认为金额
            # 中国增值税发票税率列（如"13%"、"9%"）不参与碳排放量化，碳计算仅使用金额字段
            line_rest_no_rate = _RE_TAX_RATE_COL.sub('', line_rest)
            all_nums = re.findall(r'\d+(?:\.\d+)?', line_rest_no_rate)
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
                # 过滤税率列：先移除百分比值，避免税率数字被误认为金额
                line_rest_no_rate = _RE_TAX_RATE_COL.sub('', line_rest)
                all_nums = re.findall(r'\d+(?:\.\d+)?', line_rest_no_rate)
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

    def _extract_lines_from_ocr_structured(self, structured_rows: list) -> List[InvoiceLineItem]:
        """从 _structure_postprocess 输出的结构化页列表中提取发票明细行。

        利用列对齐信息，将数值列（金额/数量/税额）与名称列区分，
        减少数量/金额/税额串位的概率。

        structured_rows: 页列表 [{page, rows: [{columns: [...]}, ...], full_text}, ...]，
        需先按行展开再处理。
        """
        import re

        # 展开页列表为行列表（修复：原逻辑误将“页”当作“行”遍历）
        all_rows = []
        for page_dict in structured_rows:
            for row in page_dict.get("rows", []):
                all_rows.append(row)

        _re_name_prefix = re.compile(r'\*+[^*]+\*+')  # *类别*名称 或 **类别**名称 格式
        _re_has_chinese = re.compile(r'[\u4e00-\u9fff]{2,}')  # 至少2个汉字
        _re_pure_number = re.compile(r'^[¥￥\d,，.\s]+$')  # 纯数字/货币
        _re_tax_rate = re.compile(r'\d+(?:\.\d+)?%')

        items: List[InvoiceLineItem] = []
        consumed_next = set()  # 已被「名称行+下一行」合并占用的下一行索引
        for ri, row in enumerate(all_rows):
            if ri in consumed_next:
                continue
            columns = row.get("columns", [])
            if not columns:
                continue
            # 名称列：优先 *cat*name 格式，否则取第一个含汉字且非纯数字的列（避免漏掉"办公用品"等）
            name_col_idx = None
            name_val = ""
            for i, col in enumerate(columns):
                c = col.strip()
                if not c:
                    continue
                if _re_name_prefix.search(c):
                    name_col_idx = i
                    name_val = c
                    break
            if name_col_idx is None:
                for i, col in enumerate(columns):
                    c = col.strip()
                    if c and _re_has_chinese.search(c) and not _re_pure_number.match(c) and not _re_tax_rate.search(c):
                        name_col_idx = i
                        name_val = c
                        break

            if name_col_idx is None or not name_val:
                continue

            # 收集数值列（start 为名称列索引，-1 表示从第 0 列起）
            def _gather_nums(cols: list, start: int) -> list:
                out = []
                subset = cols[start + 1:] if start >= 0 else cols
                for col in subset:
                    col = _RE_TAX_RATE_COL.sub('', col.strip()).strip()
                    if not col:
                        continue
                    nums = self._parse_numbers_from_cell(col)
                    if nums:
                        out.append(nums)
                flat = []
                for nlist in out:
                    flat.extend(nlist)
                return flat

            all_nums = _gather_nums(columns, name_col_idx)

            # 名称行有内容但本行无数值：可能是名称与数值分行，尝试用下一行的数值
            if not all_nums and ri + 1 < len(all_rows):
                next_row = all_rows[ri + 1]
                next_cols = next_row.get("columns", [])
                # 下一行首列无 *XXX* 名称（避免误合并到下一个商品）
                has_name_in_next = False
                for c in next_cols[: min(2, len(next_cols))]:
                    if c and _re_name_prefix.search(str(c)):
                        has_name_in_next = True
                        break
                if not has_name_in_next:
                    all_nums = _gather_nums(next_cols, -1)  # 从第 0 列开始收集
                    if all_nums:
                        consumed_next.add(ri + 1)

            if not all_nums:
                continue

            # 空间位置启发式：列序为 项目名称、规格型号、单位、数量、单价、金额、税率、税额
            def looks_like_amount(v: float) -> bool:
                """金额通常有 2 位小数，且为正值"""
                if v <= 0:
                    return False
                return abs(v - round(v, 2)) < 1e-9

            def looks_like_quantity(v: float) -> bool:
                """数量多为正整数或简单小数"""
                if v <= 0:
                    return False
                return abs(v - round(v, 4)) < 1e-9

            qty_candidates = [n for n in all_nums if looks_like_quantity(n) and n <= 99999]
            # 排除税额：最右列为税额，倒数第二列为金额；列序：…数量、单价、金额、税率、税额
            nums_excl_tax = all_nums[:-1] if len(all_nums) >= 2 else all_nums
            amount_candidates = [n for n in nums_excl_tax if looks_like_amount(n) and n > 1 and (n < 0.2 or n > 1)]

            if len(all_nums) >= 4:
                # 列序 …数量、单价、金额、税率、税额；金额取倒数第二列（排除税额）
                quantity = all_nums[0] if qty_candidates and all_nums[0] in qty_candidates else (qty_candidates[0] if qty_candidates else None)
                unit_price = all_nums[-3] if len(all_nums) >= 3 else None
                amount = all_nums[-2]  # 明确取倒数第二列（金额），最后一列是税额
            elif len(all_nums) >= 2:
                amount = all_nums[-2] if len(all_nums) >= 2 else all_nums[-1]
                quantity = qty_candidates[0] if qty_candidates and qty_candidates[0] != amount else None
                unit_price = None
            else:
                amount = all_nums[-1]
                quantity = None
                unit_price = None

            if amount and amount > 0:
                items.append(InvoiceLineItem(
                    name=name_val,
                    tax_classification_name=name_val,
                    quantity=quantity if quantity and quantity > 0 else None,
                    unit_price=unit_price if unit_price and unit_price > 0 else None,
                    amount=amount,
                ))

        return items

    def _extract_from_ocr_blocks(self, raw_lines: list) -> List[InvoiceLineItem]:
        """Block-based multi-line OCR merging for scanned/image PDFs.

        When OCR splits a single invoice item across multiple lines (item name on one
        line, numeric fields on subsequent lines, name continuation even later), this
        method groups those lines into logical blocks and extracts InvoiceLineItem
        objects directly.

        Returns a non-empty list when multi-line blocks are detected; returns [] so
        the caller falls back to the existing single-line pattern matching.
        """
        import re

        def is_name_only_line(line: str) -> bool:
            """True if line is a *cat*name line with no inline numbers/currency/percent."""
            s = line.strip()
            if not re.search(r'\*+[^*]+\*+', s):
                return False
            if re.search(r'[¥￥%]', s):
                return False
            # 允许名称中含单个数字（如型号），含2个以上独立数字序列才排除
            s_without_categories = re.sub(r'\*[^*]+\*', '', s)
            num_sequences = re.findall(r'\b\d+(?:\.\d+)?\b', s_without_categories)
            if len(num_sequences) >= 2:
                return False
            return True

        bare_number_pat = re.compile(r'^\s*[\d,]+(?:\.\d+)?\s*$')
        tax_rate_pat = re.compile(r'^\s*\d+(?:\.\d+)?%\s*$')
        currency_pat = re.compile(r'^\s*[¥￥][\d,]+(?:\.\d+)?\s*$')
        # Short Chinese continuation fragment: 1–6 Chinese chars, nothing else
        cn_fragment_pat = re.compile(r'^\s*[\u4e00-\u9fff]{1,6}\s*$')

        def has_reasonable_decimals(v: float) -> bool:
            """True if v has at most 2 decimal places (monetary amount, not a ratio)."""
            return abs(v - round(v, 2)) < 1e-9

        items: List[InvoiceLineItem] = []
        i = 0
        while i < len(raw_lines):
            line = raw_lines[i]
            if is_name_only_line(line):
                name_parts = [line.strip()]
                plain_numbers: List[float] = []
                j = i + 1
                while j < len(raw_lines):
                    nxt = raw_lines[j].strip()
                    if not nxt:
                        j += 1
                        continue
                    # 任何以 *cat* 或 **cat** 开头的行都视为新商品块的起点
                    if re.search(r'\*+[^*]+\*+', nxt):
                        break
                    # New item block starts → end current block
                    if is_name_only_line(raw_lines[j]):
                        break
                    # Tax rate line → skip (must not become amount)
                    if tax_rate_pat.match(nxt):
                        j += 1
                        continue
                    # Currency-prefixed amount → skip (prefer plain numbers for amount)
                    if currency_pat.match(nxt):
                        j += 1
                        continue
                    # Bare decimal number
                    if bare_number_pat.match(nxt):
                        v = self._parse_number(nxt)
                        if v is not None:
                            plain_numbers.append(v)
                        j += 1
                        continue
                    # Short Chinese continuation → part of the item name
                    if cn_fragment_pat.match(nxt):
                        name_parts.append(nxt)
                        j += 1
                        continue
                    # Anything else ends the block
                    break

                # Only emit an item when block data was actually collected
                if len(name_parts) > 1 or plain_numbers:
                    name = self._merge_ocr_name_parts(name_parts)
                    # Amount = first plain number with ≤2 decimal places.
                    # Chinese VAT invoices always list fields in the order:
                    # quantity → unit_price → amount_excl_tax → tax_rate → tax_amount,
                    # so OCR lines appear in that same order and the first reasonable
                    # bare number is the pre-tax amount, not the smaller tax amount.
                    reasonable_nums = [v for v in plain_numbers if has_reasonable_decimals(v)]
                    amount = reasonable_nums[0] if reasonable_nums else None
                    if name and amount is not None and amount > 0:
                        items.append(InvoiceLineItem(
                            name=name,
                            tax_classification_name=name,
                            amount=amount,
                        ))

                i = j
            else:
                i += 1

        return items

    @staticmethod
    def _merge_ocr_name_parts(parts: list) -> str:
        """Merge OCR name fragments, removing line-break artifacts.

        When a *category*name is split across lines, the last character of the
        first fragment is sometimes an OCR artifact (e.g. '项' replacing the true
        last character).  Strip a trailing '项' before appending the continuation.
        """
        if not parts:
            return ""
        result = parts[0]
        for cont in parts[1:]:
            # '项' at the end of a split name is a common OCR line-break artifact
            if result.endswith('项'):
                result = result[:-1]
            result = result.rstrip() + cont.strip()
        return result.strip()

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
        """安全解析数值字符串，支持货币符号（¥、￥）与千位分隔符。

        不解析百分比值（如"13%"），此类值为税率而非金额，
        碳排放计算不使用税率字段。
        """
        if not val:
            return None
        cleaned = str(val).strip()
        # 拒绝百分比值（税率），避免误用税率作为金额
        if _RE_PERCENT.search(cleaned):
            return None
        # 去除货币符号与中文单位
        cleaned = _RE_CURRENCY.sub('', cleaned)
        cleaned = _RE_RMBORЦNY.sub('', cleaned)
        cleaned = cleaned.rstrip('元').strip()
        # 去除千位分隔符与空白
        cleaned = re.sub(r"[,，\s]", "", cleaned)
        try:
            return float(cleaned)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_numbers_from_cell(cell: str) -> List[float]:
        """从可能混合「数量+金额」的单元格中解析出多个数值。

        当 OCR 将数量与金额识别到同一列（如 "2 80.00"）时，按空白拆分，
        返回按出现顺序的数值列表。用于空间位置判别：通常金额有 2 位小数，数量多为整数。
        """
        if not cell or not str(cell).strip():
            return []
        import re
        cleaned = str(cell).strip()
        # 含税率时只剔除百分比部分，仍解析金额等数值（避免"80.00 13%"整格被丢弃导致漏产品）
        cleaned = _RE_PERCENT.sub("", cleaned)
        cleaned = _RE_CURRENCY.sub("", cleaned)
        cleaned = re.sub(r"[,，\s]+", " ", cleaned).strip()
        parts = re.split(r"\s+", cleaned)
        result = []
        for p in parts:
            p = re.sub(r"[^\d.\-]", "", p)
            if not p:
                continue
            try:
                result.append(float(p))
            except (ValueError, TypeError):
                pass
        return result
