"""
myocr2-invoice OCR 适配器。

将 myocr2-invoice 服务（POST /invoice_ocr）返回的 JSON 格式，
转换为 CarbonAccountingPipeline.process_invoice_from_dict 期望的 dict 格式。

字段映射：
    item_name                    → lines[i].name
    item_number                  → lines[i].quantity  (解析为 float)
    item_unit                    → lines[i].unit
    item_price                   → lines[i].unit_price (解析为 float)
    item_amount                  → lines[i].amount    (解析为 float, 去除¥/,)
    item_tax_rate                → 忽略（不参与碳排放计算）
    item_tax                     → 忽略（不参与碳排放计算）
    issue_date                   → date (转换为 YYYY-MM-DD)
    tax_exclusive_total_amount   → total_amount (解析为 float)
    buyer_name                   → buyer.name
    buyer_code                   → buyer.tax_id
    seller_name                  → seller.name
    seller_code                  → seller.tax_id
    invoice_code                 → invoice_code
    invoice_number               → invoice_number
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional, Union

from .invoice_parser import parse_amount_cny

_RE_CN_DATE = re.compile(r'(\d{4})[年/\-](\d{1,2})[月/\-](\d{1,2})日?')


def _parse_cn_date(date_str: str) -> Optional[str]:
    """将 ``YYYY年MM月DD日`` 或类似格式转换为 ``YYYY-MM-DD``。"""
    if not date_str:
        return None
    m = _RE_CN_DATE.search(date_str)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return date_str


def _safe_float(val: str) -> Optional[float]:
    """将字符串安全解析为 float，失败返回 None。"""
    if val is None:
        return None
    try:
        return float(str(val).strip())
    except (ValueError, TypeError):
        return None


class MyOCR2InvoiceAdapter:
    """
    将 myocr2-invoice OCR 服务的输出 JSON 转换为
    CarbonAccountingPipeline.process_invoice_from_dict 可接受的 dict 格式。
    """

    @staticmethod
    def convert(ocr_result: dict) -> dict:
        """将 OCR 输出 dict 转换为 CarbonCalculator pipeline 期望的 dict。"""
        lines = []
        for item in ocr_result.get("items", []):
            line: dict = {}
            if "item_name" in item:
                line["name"] = item["item_name"]
            if "item_number" in item:
                line["quantity"] = _safe_float(item["item_number"])
            if "item_unit" in item:
                line["unit"] = item["item_unit"]
            if "item_price" in item:
                line["unit_price"] = _safe_float(item["item_price"])
            if "item_amount" in item:
                line["amount"] = parse_amount_cny(str(item["item_amount"]))
            # item_tax_rate and item_tax are intentionally omitted
            lines.append(line)

        result: dict = {
            "invoice_code": ocr_result.get("invoice_code"),
            "invoice_number": ocr_result.get("invoice_number"),
            "date": _parse_cn_date(ocr_result.get("issue_date", "")),
            "total_amount": parse_amount_cny(
                str(ocr_result.get("tax_exclusive_total_amount", ""))
            ),
            "seller": {
                "name": ocr_result.get("seller_name"),
                "tax_id": ocr_result.get("seller_code"),
            },
            "buyer": {
                "name": ocr_result.get("buyer_name"),
                "tax_id": ocr_result.get("buyer_code"),
            },
            "lines": lines,
        }
        return result

    @staticmethod
    def from_service(
        image_path_or_bytes: Union[str, Path, bytes],
        ocr_service_url: str = "http://localhost:5000/invoice_ocr",
    ) -> dict:
        """
        调用 myocr2-invoice OCR 服务，获取结果并转换。

        Args:
            image_path_or_bytes: 图片/PDF 文件路径（str 或 Path）或字节内容（bytes）。
            ocr_service_url: OCR 服务端点，默认 ``http://localhost:5000/invoice_ocr``。

        Returns:
            转换后的 dict，可直接传给 ``pipeline.process_invoice_from_dict()``。

        Raises:
            ImportError: 若 ``requests`` 库不可用。
        """
        try:
            import requests  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError(
                "MyOCR2InvoiceAdapter.from_service 需要 'requests' 库，"
                "请执行: pip install requests"
            ) from exc

        if isinstance(image_path_or_bytes, bytes):
            files = {"file": ("image", image_path_or_bytes)}
            response = requests.post(ocr_service_url, files=files, timeout=60)
        else:
            with open(Path(image_path_or_bytes), "rb") as fh:
                files = {"file": fh}
                response = requests.post(ocr_service_url, files=files, timeout=60)
        response.raise_for_status()
        ocr_result = response.json()
        return MyOCR2InvoiceAdapter.convert(ocr_result)
