"""
第一步：数据采集 - 发票结构化提取。
系统通过接口提取 PDF 电子发票的结构化数据。
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
# 规格/单位令牌过滤：含 ASCII 字母的 token（如"400g"、"12V"、"100mAh"）不应被解析为金额/数量
_RE_ASCII_LETTER = re.compile(r'[a-zA-Z]')
# Issue 3: 扩展日期格式，增加 YYYYMMDD 纯数字格式（如 20250403，范围 2000-2099 年）
_RE_DATE = re.compile(
    r'\d{4}(?:年\d{1,2}月\d{1,2}日?|[-/]\d{1,2}[-/]\d{1,2})'
    r'|(?<!\d)20[0-9]{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])(?!\d)'
)
# Issue 2: 匹配「国家税务总局」的 OCR 噪音变体（如国家报务总码、国家批务总局、国家报务总构）
_RE_TAX_AUTHORITY = re.compile(r'国家.{0,3}[税报批][务]总[局码构]')
# Issue 1b: 中国增值税常见税率（整数，OCR 有时丢失 '%' 符号）
_CN_VAT_RATES = frozenset({1, 3, 5, 6, 9, 10, 11, 13, 16, 17})
# OCR 拆行时常见的计量单位令牌（纯 ASCII 字母，用于识别「数字+单位」规格行）
# 例如 OCR 将「1.25kg」拆为「1.25」和「kg」两行，「kg」即为单位令牌
_RE_UNIT_TOKEN = re.compile(r'^[a-zA-Z]{1,6}$')

# 发票非商品行关键词：这些行不应被识别为商品明细
_INVOICE_NON_ITEM_KEYWORDS = (
    "合计", "价税合计", "小计",
    "购买方", "销售方", "购方", "销方",
    "发票号码", "发票代码", "开票日期", "开票人",
    "国家税务总局", "监制", "防伪税控",
    "税率", "单价", "数量", "规格型号", "单位",  # 表头
    "备注", "收款人", "复核",
    "税务局",          # Issue 4: 过滤含税务机构名称的行（如上海市税务局）
    "名称", "项目名称",  # Issue 5: 过滤表头类标签行
)

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
    """发票解析器抽象基类：支持 PDF 等格式"""

    @abstractmethod
    def parse(self, source: Union[str, Path, bytes]) -> Invoice:
        """
        解析电子发票，返回结构化 Invoice。
        source: 文件路径或已读取的字节内容。
        """
        pass

    @abstractmethod
    def supported_formats(self) -> List[str]:
        """返回支持的格式列表，如 ['PDF']"""
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


def _build_invoice_from_dict(data: dict) -> Invoice:
    """从 API 返回的 dict 构建 Invoice。"""
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

    def _ocr_pdf(self, pdf) -> tuple[str, list]:
        """使用 PaddleOCR 对 PDF 各页图片进行 OCR，返回 (拼接文本, 结构化页列表) 元组"""
        try:
            from paddleocr import PaddleOCR
        except ImportError:
            raise ImportError("图片型 PDF 需要 PaddleOCR：pip install paddleocr")

        if not hasattr(PdfInvoiceParser, '_ocr_instance') or PdfInvoiceParser._ocr_instance is None:
            PdfInvoiceParser._ocr_instance = PaddleOCR(use_textline_orientation=True, lang='ch')
        ocr = PdfInvoiceParser._ocr_instance

        import numpy as np
        structured = []
        for page_idx, page in enumerate(pdf.pages):
            img = page.to_image(resolution=150).original  # PIL Image
            result = ocr.ocr(np.array(img), cls=True)
            if result and result[0]:
                rows = self._structure_postprocess(result[0])
            else:
                rows = []
            full_text = "\n".join(row["text"] for row in rows)
            structured.append({"page": page_idx + 1, "rows": rows, "full_text": full_text})

        ocr_text = "\n".join(page["full_text"] for page in structured)
        return ocr_text, structured

    def _structure_postprocess(self, page_items: list) -> list:
        """对单页 PaddleOCR 识别结果进行结构化后处理，降低列串位。

        参数:
            page_items: 单页 OCR 结果列表，每元素为 [bbox, (text, score)]，
                        其中 bbox 为 4 点坐标列表 [[x0,y0],[x1,y0],[x1,y1],[x0,y1]]。

        返回:
            list of dict，每个元素描述一行：
            {
                "text": str,                          # 行内所有词块以空格拼接
                "y_center": float,
                "words": [{"text": ..., "x_center": ..., ...}],
                "columns": [str, ...],                # 按列对齐的文本列表
            }
        """
        import statistics

        if not page_items:
            return []

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

        # ── 4. 为每行添加 text 字段（行内词块以空格拼接）────────────────
        for row in rows:
            row["text"] = " ".join(w["text"] for w in row["words"])

        return rows

    @staticmethod
    def _fit_kmeans_1d(x_centers: list, n_clusters: int):
        """对 1-D x 坐标列表拟合 KMeans，返回拟合后的 KMeans 实例，失败返回 None。

        抽取公共逻辑，避免在 _cluster_columns 和 _cluster_x_centers 中重复
        导入 sklearn/numpy 及构造 KMeans 的样板代码。

        参数:
            x_centers: x 坐标列表。
            n_clusters: 目标簇数（已由调用方校验 >= 1 且 <= len(x_centers)）。

        返回:
            拟合完成的 KMeans 实例；若 sklearn/numpy 未安装或拟合失败则返回 None
            （调用方应降级到备用算法）。
        """
        try:
            from sklearn.cluster import KMeans
            import numpy as np
        except ImportError:
            return None
        try:
            arr = np.array(x_centers).reshape(-1, 1)
            km = KMeans(n_clusters=n_clusters, random_state=0, n_init="auto")
            km.fit(arr)
            return km
        except (ValueError, RuntimeError):
            return None

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

        km = PdfInvoiceParser._fit_kmeans_1d(x_centers, n_cols)
        if km is not None:
            return sorted(float(c[0]) for c in km.cluster_centers_)

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

    @staticmethod
    def _cluster_x_centers(centers: list, n_clusters: int) -> list:
        """对 x 坐标列表做 1-D 聚类，返回每个点的簇标签列表。

        参数:
            centers: x 坐标列表。
            n_clusters: 目标簇数（若超过点数则自动压缩为点数）。

        返回:
            与 centers 等长的整数列表，每个元素为该点所属簇的标签（0-based）。
            空输入返回空列表。
        """
        if not centers:
            return []
        n = len(centers)
        k = min(n_clusters, n)
        km = PdfInvoiceParser._fit_kmeans_1d(centers, k)
        if km is not None:
            return list(km.labels_)
        # 降级：按坐标排序后等分 k 个簇，返回原始位置对应的标签
        sorted_pairs = sorted(enumerate(centers), key=lambda x: x[1])
        labels = [0] * n
        chunk = n / k
        for rank, (orig_idx, _) in enumerate(sorted_pairs):
            labels[orig_idx] = min(int(rank / chunk), k - 1)
        return labels

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

        # 仅对图片型 PDF（pdfplumber 无法提取文本）使用 OCR
        if not all_text.strip():
            try:
                ocr_text, ocr_structured = self._ocr_pdf(pdf)
                if ocr_text.strip():
                    all_text = ocr_text
            except Exception:
                pass

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

        # 若表格解析未得到有效明细行（空或所有金额均为0），回退到文本/OCR提取
        if not inv.lines or all(l.amount <= 0 for l in inv.lines):
            inv.lines = []  # 清空无效行，避免遮蔽后续回退路径
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

        # 后置过滤：去除非商品行、日期行、零金额行
        # Issue 6: 先去重（按名称+金额），防止同一明细被多个解析路径重复输出
        inv.lines = self._dedup_lines(inv.lines)
        inv.lines = self._post_filter_lines(inv.lines)

        # 计算总金额：优先使用发票表格中合计行声明的值，用于验证明细金额之和是否一致
        declared_total = self._find_declared_total_from_tables(all_tables)
        if declared_total and declared_total > 0:
            inv.total_amount = declared_total
        elif inv.lines:
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
        tax_rate_keywords = ("税率",)

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
            tax_rate_col = self._find_col_index(header_str, tax_rate_keywords)

            if name_col is None and len(header_str) >= 1:
                # 若第0列表头为纯数字（行号列），优先用第1列作为名称列
                if re.match(r'^\d+$', header_str[0].strip()) and len(header_str) >= 2:
                    name_col = 1
                else:
                    name_col = 0

            if name_col is None:
                continue

            if amount_col is None and len(header_str) >= 5:
                fallback = min(5, len(header_str) - 2)
                # 不能选税率列作为 amount_col
                if tax_rate_col is not None and fallback == tax_rate_col:
                    fallback = fallback - 1 if fallback > 0 else fallback + 1
                amount_col = fallback

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
                if not name:
                    continue
                if any(kw in name for kw in _INVOICE_NON_ITEM_KEYWORDS):
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
        _pure_num_re = re.compile(r'^[\d,，.\s]+$')
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
                    # 名称续行：不是纯数字/货币行、不是税率、不含新 *类别* 格式、长度≤20
                    # 允许含数字的续行（如型号 500g、100mAh）
                    if (not _pure_num_re.match(nxt)
                            and not re.search(r'\d+(?:\.\d+)?%', nxt)
                            and not nxt.startswith('*')
                            and len(nxt) <= 20):
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
                # 当前行是 *XX*YY + 数据 格式（名称行含有行内数字，如 *类别*商品名 1 76.99 76.99 13% 10.01）
                # 此时仍需向前看，将后续纯文本续行合并到名称中
                # 仅在数据部分不含中文（即规格列与名称列已在同行的情况下不适用）时才合并续行
                if line.strip().startswith("*") and re.search(r'\d', line):
                    star_m = re.match(r'(\*+[^*\n]+\*+[^\s]*)', line.strip())
                    if star_m:
                        name_part = star_m.group(1)
                        data_part = line.strip()[len(name_part):]
                        # 若数据部分含中文字符（说明规格信息已内联），不进行续行合并
                        data_has_chinese = bool(re.search(r'[\u4e00-\u9fff]', data_part))
                        if not data_has_chinese:
                            j = i + 1
                            continuation = ""
                            while j < len(raw_lines):
                                nxt = raw_lines[j].strip()
                                if not nxt:
                                    j += 1
                                    continue
                                if nxt.startswith("*"):
                                    break
                                # 检查关键词时同时考虑含空格的变体（如"合 计"→"合计"）
                                nxt_nospace = nxt.replace(' ', '')
                                if any(kw in nxt or kw in nxt_nospace for kw in _INVOICE_NON_ITEM_KEYWORDS):
                                    break
                                # 续行条件：不含小数金额、不含税率、不是纯数字行
                                if (_RE_PERCENT.search(nxt)
                                        or re.search(r'(?<![a-zA-Z\u4e00-\u9fff])\d+\.\d+', nxt)
                                        or _pure_num_re.match(nxt)):
                                    break
                                continuation += nxt
                                j += 1
                            if continuation:
                                merged_lines.append(name_part + continuation + data_part)
                                i = j
                                continue
                merged_lines.append(line)
                i += 1
        processed_text = "\n".join(merged_lines)

        # Pattern 1: *类别*名称 或 **类别**名称 + numbers
        # 使用前瞻断言确保名称行后续有数字（避免纯文本行误匹配），
        # 不强制要求中间部分格式——兼容规格编码含字母数字混合的情况（如 M3、SCSAW4、8#-32*1/2）
        # [^*\n]+ 限制类别名不跨行，避免规格中的 * 字符（如 8#-32*1/2）被误认为类别分隔符
        pattern = re.compile(
            r"(\*+[^*\n]+\*+[^\s]*)(?=[^\n]*\d)"  # name + 前瞻：同行有数字
        )
        for m in pattern.finditer(processed_text):
            name = m.group(1).strip()
            if any(kw in name for kw in _INVOICE_NON_ITEM_KEYWORDS):
                continue
            # 跳过类别不符合标准税收分类格式的情况（真实税收分类仅含汉字/字母/空格，无数字、斜杠等特殊字符）
            # 例如 *22*、*外径25*、*12吨*、*1/2* 均来自产品规格而非商品名
            # 长度约束：2-15 个字符（真实税收分类通常 2-8 个汉字）
            m_cat = re.search(r'\*([^*]+)\*', name)
            if m_cat:
                cat = m_cat.group(1).strip()
                if not re.match(r'^[a-zA-Z\u4e00-\u9fff\s]{2,15}$', cat):
                    continue
            # 提取本行名称之后的所有数字，按位置取值
            name_end = m.start(1) + len(m.group(1))
            eol = processed_text.find('\n', name_end)
            line_rest = processed_text[name_end: eol if eol != -1 else len(processed_text)]
            # 过滤税率列：先移除形如"13%"、"9%"等百分比值，避免税率数字被误认为金额
            # 中国增值税发票税率列（如"13%"、"9%"）不参与碳排放量化，碳计算仅使用金额字段
            line_rest_no_rate = _RE_PERCENT.sub('', line_rest)
            # Issue: 规格列中的计量单位（如 400g、12V、2800mAh）不应被误识别为金额或数量
            # 按空白分词后保留纯数字 token（仅含数字、千位逗号或小数点），排除混合字母的规格字符串
            all_nums = [w for w in line_rest_no_rate.split()
                        if re.match(r'^[\d,，]+(?:\.\d+)?$', w)]
            # Issue 1: 过滤名称本身含有的纯数字（如 12V 中的 12），防止其混入金额列计算
            # 比较整数部分，避免 12.5 被误过滤（仅精确整数匹配）
            name_embedded_digits = set(re.findall(r'\d+', name))
            all_nums = [n for n in all_nums if n.split('.')[0] not in name_embedded_digits or '.' in n]
            # Issue 9 (revised): 检验 all_nums 中是否存在「a+b=c」的合计关系
            # 若存在，输出 a 和 b 两个明细，跳过合计值 c（不依赖 '=' '+'  等文本符号）
            nums_f = [self._parse_number(n) for n in all_nums]
            nums_f = [v for v in nums_f if v is not None and v > 0]
            sub_amounts = self._find_sub_amounts(nums_f)
            if sub_amounts:
                for sub_amt in sub_amounts:
                    lines.append(InvoiceLineItem(
                        name=name,
                        tax_classification_name=name,
                        amount=sub_amt,
                    ))
                continue
            if len(all_nums) >= 4:
                # 中国增值税发票固定列顺序：数量, 单价, 金额（不含税）, 税额
                # 倒数第二个数字为金额（不含税），最后一个为税额（忽略）
                quantity = self._parse_number(all_nums[0])
                unit_price = self._parse_number(all_nums[-3])
                amount = self._parse_number(all_nums[-2]) or 0.0
            elif len(all_nums) >= 2:
                # 两个数字时：取倒数第二个为金额（最后一个可能是税额）
                amount = self._parse_number(all_nums[-2]) or 0.0
                quantity = None
                unit_price = None
            elif len(all_nums) == 1:
                amount = self._parse_number(all_nums[0]) or 0.0
                quantity = None
                unit_price = None
            else:
                continue  # 无数字则跳过
            unit = None
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
                if any(kw in name for kw in _INVOICE_NON_ITEM_KEYWORDS):
                    continue
                # 额外：非 *类别* 格式时，名称不应超过 30 字（过长说明是段落文本而非商品名）
                if len(name) > 30:
                    continue
                # Issue 4: 名称过短（如单个货币字符 '元'）或含机构/地理词，跳过
                if len(name) < 2:
                    continue
                # 提取本行名称之后的所有数字，按位置取值
                name_end = m.start(1) + len(m.group(1))
                eol = processed_text.find('\n', name_end)
                line_rest = processed_text[name_end: eol if eol != -1 else len(processed_text)]
                # 过滤税率列：先移除百分比值，避免税率数字被误认为金额
                line_rest_no_rate = _RE_PERCENT.sub('', line_rest)
                # 排除混合字母+数字的规格字符串（如 400g、12V），与 Pattern 1 保持一致
                all_nums = [w for w in line_rest_no_rate.split()
                            if re.match(r'^[\d,，]+(?:\.\d+)?$', w)]
                if len(all_nums) >= 4:
                    quantity = self._parse_number(all_nums[0])
                    unit_price = self._parse_number(all_nums[-3])
                    amount = self._parse_number(all_nums[-2]) or 0.0
                else:
                    # Issue 8: 少于4个数字时，若有2+个数字取倒数第二（金额），避免最后一个税额被误用
                    if len(all_nums) >= 2:
                        amount = self._parse_number(all_nums[-2]) or 0.0
                        quantity = self._parse_number(m.group(2)) if m.group(2) else None
                        unit_price = self._parse_number(m.group(4)) if m.group(4) else None
                    elif len(all_nums) == 1:
                        amount = self._parse_number(all_nums[0]) or 0.0
                        quantity = self._parse_number(m.group(2)) if m.group(2) else None
                        unit_price = self._parse_number(m.group(4)) if m.group(4) else None
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
            # 过滤非商品行
            if any(kw in name_val for kw in _INVOICE_NON_ITEM_KEYWORDS):
                continue

            # 收集数值列（start 为名称列索引，-1 表示从第 0 列起）
            def _gather_nums(cols: list, start: int) -> list:
                out = []
                subset = cols[start + 1:] if start >= 0 else cols
                for col in subset:
                    col = _RE_PERCENT.sub('', col.strip()).strip()
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

            # 名称行有内容但本行无数值：可能是名称与数值分行，尝试向后查找数值行。
            # 允许中间最多 2 行规格/续行（如"400g"、"1pcs"），向后最多查看 3 行。
            if not all_nums:
                _pending: list = []      # row indices between name row and nums row
                _name_cont: list = []    # text collected from continuation rows
                for _look_j in range(ri + 1, min(ri + 4, len(all_rows))):
                    _look_cols = all_rows[_look_j].get("columns", [])
                    # 发现新商品名称行 → 停止向前看
                    if any(_re_name_prefix.search(str(c))
                           for c in _look_cols[: min(2, len(_look_cols))] if c):
                        break
                    _look_nums = _gather_nums(_look_cols, -1)
                    if _look_nums:
                        all_nums = _look_nums
                        # 消耗所有中间续行及数值行
                        for _k in _pending:
                            consumed_next.add(_k)
                        consumed_next.add(_look_j)
                        # 将续行文字合并进名称（如"400g"、"（礼盒装）"）
                        if _name_cont:
                            name_val = name_val + "".join(_name_cont)
                        break
                    # 无数值 → 视为规格/续行，收集文字并继续向前看
                    _cont_text = "".join(c.strip() for c in _look_cols if c.strip())
                    if _cont_text:
                        _name_cont.append(_cont_text)
                    _pending.append(_look_j)

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
            """True if line looks like a product name with no inline numbers/currency/percent.

            Accepts both *cat*name format and pure Chinese product names (Issue 10).
            """
            s = line.strip()
            # *cat*name 格式 或 含至少3个汉字的中文商品名（Issue 10；3+字符避免误识别续行片段如「务费」）
            # 规格行（如「（礼盒装）1.25kg」）含小数数字，应排除；但商品型号前缀（如「502强力胶」）
            # 只含整数，不应被排除——故只排除含小数的行，而非排除所有含数字的行。
            has_star_cat = bool(re.search(r'\*+[^*]+\*+', s))
            has_chinese_name = (bool(re.search(r'[\u4e00-\u9fff]{3,}', s))
                                and not re.search(r'\d+\.\d+', s))
            if not has_star_cat and not has_chinese_name:
                return False
            if re.search(r'[¥￥%]', s):
                return False
            # 过滤非商品行关键词
            if any(kw in s for kw in _INVOICE_NON_ITEM_KEYWORDS):
                return False
            # Issue 2: 过滤国家税务总局 OCR 变体
            if _RE_TAX_AUTHORITY.search(s):
                return False
            # 允许名称中含单个数字（如型号），含2个以上独立数字序列才排除
            s_clean = re.sub(r'\*[^*]+\*', '', s)
            num_sequences = re.findall(r'\b\d+(?:\.\d+)?\b', s_clean)
            if len(num_sequences) >= 2:
                return False
            return True

        bare_number_pat = re.compile(r'^\s*[\d,]+(?:\.\d+)?\s*$')
        tax_rate_pat = re.compile(r'^\s*\d+(?:\.\d+)?%\s*$')
        currency_pat = re.compile(r'^\s*[¥￥][\d,]+(?:\.\d+)?\s*$')
        # Name continuation: not a pure number/currency/tax-rate, not a new *cat* line,
        # at most 20 chars. Handles "500g", "100mAh", "A型", etc.
        def is_name_continuation(s: str) -> bool:
            return (
                not bare_number_pat.match(s)
                and not tax_rate_pat.match(s)
                and not currency_pat.match(s)
                and len(s) <= 20
                and not re.search(r'\*+[^*]+\*+', s)
                and not any(kw in s for kw in _INVOICE_NON_ITEM_KEYWORDS)
            )

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
                        # Lookahead: if the next non-empty line is a pure ASCII unit string
                        # (e.g. "kg", "g", "ml"), the current number is a weight/volume
                        # specification, not a monetary amount.  Combine as name continuation.
                        # Example: OCR splits "1.25kg" into "1.25" (this line) + "kg" (next line).
                        la = j + 1
                        while la < len(raw_lines) and not raw_lines[la].strip():
                            la += 1
                        next_s = raw_lines[la].strip() if la < len(raw_lines) else ""
                        if _RE_UNIT_TOKEN.match(next_s):
                            # number + unit → treat as spec, append to name and skip both lines
                            name_parts.append(nxt.strip() + next_s)
                            j = la + 1
                            continue
                        v = self._parse_number(nxt)
                        if v is not None:
                            # Issue 1b: 跳过裸整数形式的常见增值税税率（如 OCR 将 13% 识别为 13）
                            # 仅在 plain_numbers 中已有小数金额时才跳过，避免误过滤数量值
                            if (abs(v - round(v)) < 1e-9 and int(v) in _CN_VAT_RATES
                                    and any(abs(p - round(p)) > 1e-9 for p in plain_numbers)):
                                j += 1
                                continue
                            plain_numbers.append(v)
                        j += 1
                        continue
                    # Name continuation → part of the item name
                    if is_name_continuation(nxt):
                        name_parts.append(nxt)
                        j += 1
                        continue
                    # Anything else ends the block
                    break

                # Only emit an item when block data was actually collected
                if len(name_parts) > 1 or plain_numbers:
                    name = self._merge_ocr_name_parts(name_parts)
                    # 增值税发票固定列顺序（税率行已被 tax_rate_pat 过滤）：
                    # 数量, 单价, 金额（不含税）, 税额
                    # → 金额取倒数第二个，单价取倒数第三个，数量取第一个
                    reasonable_nums = [v for v in plain_numbers if has_reasonable_decimals(v)]
                    if len(reasonable_nums) >= 3:
                        # 标准格式：数量、单价、金额、税额（4个）或 单价、金额、税额（3个）
                        quantity = reasonable_nums[0] if len(reasonable_nums) >= 4 else None
                        unit_price = reasonable_nums[-3] if len(reasonable_nums) >= 3 else None
                        amount = reasonable_nums[-2]  # 倒数第二 = 金额（不含税）
                    elif len(reasonable_nums) == 2:
                        a, b = reasonable_nums[0], reasonable_nums[1]
                        # Issue 7: 区分 [数量, 金额] 和 [金额, 税额] 两种情况
                        # 若首数为纯整数且第二数更大，则判断为 [数量, 金额] 格式
                        if abs(a - round(a)) < 1e-9 and b >= a:
                            quantity = int(a)
                            unit_price = None
                            amount = b
                        else:
                            # 标准 [金额, 税额] 格式：取首个（=倒数第二）作为金额
                            quantity = None
                            unit_price = None
                            amount = a
                    elif len(reasonable_nums) == 1:
                        quantity = None
                        unit_price = None
                        amount = reasonable_nums[0]
                    else:
                        quantity = None
                        unit_price = None
                        amount = None
                    if name and amount is not None and amount > 0:
                        items.append(InvoiceLineItem(
                            name=name,
                            tax_classification_name=name,
                            quantity=quantity if quantity and quantity > 0 else None,
                            unit_price=unit_price if unit_price and unit_price > 0 else None,
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
    def _dedup_lines(lines: "List[InvoiceLineItem]") -> "List[InvoiceLineItem]":
        """Issue 6: 按名称+金额去重，防止同一明细被多个解析路径重复输出。"""
        seen: set = set()
        result = []
        for line in lines:
            key = (line.name, line.amount)
            if key not in seen:
                seen.add(key)
                result.append(line)
        return result

    @staticmethod
    def _find_sub_amounts(nums: list) -> "Optional[list]":
        """检验数字列表中是否存在「某一个数等于其余所有数之和」的合计关系。

        Issue 9: 合计行金额 = 所有其他明细行金额之和。
        若找到这样的合计值 v（满足 2*v ≈ sum(nums)），则返回其余明细金额列表；
        否则返回 None。

        算法复杂度 O(n)：先求总和，再遍历一次判断每个元素是否等于其余之和。
        容差 0.01 元（等于 sum 误差 0.01 / 2，即单个金额精度约 ±0.005 元）。
        """
        if len(nums) < 2:
            return None
        total = sum(nums)
        for k, v in enumerate(nums):
            if abs(2 * v - total) < 0.01:
                return [nums[idx] for idx in range(len(nums)) if idx != k]
        return None

    @staticmethod
    def _post_filter_lines(lines: "List[InvoiceLineItem]") -> "List[InvoiceLineItem]":
        """后置过滤：从解析结果中移除非商品行（合计、日期、零金额等）。"""
        result = []
        for line in lines:
            name = (line.name or "").strip()
            if not name:
                continue
            if any(kw in name for kw in _INVOICE_NON_ITEM_KEYWORDS):
                continue
            if _RE_DATE.search(name):
                continue
            # Issue 2: 过滤「国家税务总局」OCR 变体（如国家报务总码、国家批务总局）
            if _RE_TAX_AUTHORITY.search(name):
                continue
            if line.amount <= 0:
                continue
            # Issue 3: 过滤金额看起来像 8 位纯数字日期（YYYYMMDD，范围 20000101-20991231）
            amt_int = int(line.amount)
            if abs(line.amount - amt_int) < 1e-9 and 20000101 <= amt_int <= 20991231:
                mm = (amt_int // 100) % 100
                dd = amt_int % 100
                if 1 <= mm <= 12 and 1 <= dd <= 31:
                    continue
            result.append(line)

        # Issue 11: 若 amount 为常见增值税税率整数（如 13），且同时存在有小数的金额行，
        # 则该行极可能是 pdfplumber 将税率列误解析为商品行，应过滤
        has_decimal_amounts = any(
            abs(l.amount - round(l.amount)) > 1e-9 for l in result
        )
        if has_decimal_amounts:
            result = [
                l for l in result
                if not (abs(l.amount - round(l.amount)) < 1e-9
                        and int(round(l.amount)) in _CN_VAT_RATES)
            ]

        # Issue 9: 过滤合计行——若某行金额等于所有其他行金额之和，则该行为汇总行，应移除
        # 算法：sum(all) = 2*total，即满足 2*v ≈ total_sum 的那行是合计行
        if len(result) >= 2:
            amounts = [l.amount for l in result]
            total = sum(amounts)
            for k, v in enumerate(amounts):
                if abs(2 * v - total) < 0.01:
                    result = [l for idx, l in enumerate(result) if idx != k]
                    break

        return result

    def _find_declared_total_from_tables(self, tables: list) -> "Optional[float]":
        """从表格中提取合计/价税合计行的声明总金额，用于验证明细金额之和是否一致。"""
        _total_kws = ("价税合计", "合计")
        for table in tables:
            if not table or len(table) < 2:
                continue
            header = table[0]
            if header is None:
                continue
            header_str = [str(h).strip() if h else "" for h in header]
            amount_col = self._find_amount_col_index(header_str)
            for row in table[1:]:
                if row is None:
                    continue
                row_str = [str(c).strip() if c else "" for c in row]
                is_total_row = any(any(kw in cell for kw in _total_kws) for cell in row_str)
                if not is_total_row:
                    continue
                if amount_col is not None and amount_col < len(row_str):
                    amt = self._parse_number(row_str[amount_col])
                    if amt and amt > 0:
                        return amt
                # Fallback: largest positive number in the row
                candidates = [self._parse_number(c) for c in row_str]
                valid = [v for v in candidates if v and v > 0]
                if valid:
                    return max(valid)
        return None

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
            # Skip tokens that still contain ASCII letters after currency/percent removal.
            # These are alphanumeric spec/unit tokens (e.g. "400g", "12V", "100mAh") that
            # should not be treated as monetary amounts or quantities.
            if _RE_ASCII_LETTER.search(p):
                continue
            p = re.sub(r"[^\d.\-]", "", p)
            if not p:
                continue
            try:
                result.append(float(p))
            except (ValueError, TypeError):
                pass
        return result
