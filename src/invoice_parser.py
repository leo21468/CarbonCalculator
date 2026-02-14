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
