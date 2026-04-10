"""
将企业费控 / ERP 返回的嵌套 JSON（data.page_info + invoice_detail.Items）转为
内部发票 dict，供 _build_invoice_from_dict / process_invoice_from_dict 使用。

识别条件：顶层或 body 内含 data.page_info 为非空 list；若请求体已是标准 lines/items 则原样返回。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _page_info_list(body: Optional[dict]) -> List[dict]:
    """支持顶层 page_info，或 data.page_info（费控完整响应）。"""
    if not body or not isinstance(body, dict):
        return []
    pi = body.get("page_info")
    if isinstance(pi, list) and len(pi) > 0:
        return pi
    data = body.get("data")
    if isinstance(data, dict):
        pi2 = data.get("page_info")
        if isinstance(pi2, list) and len(pi2) > 0:
            return pi2
    return []


def is_erp_page_info_payload(body: Optional[dict]) -> bool:
    return len(_page_info_list(body)) > 0


def _ms_to_date_str(ms: Any) -> Optional[str]:
    if ms is None:
        return None
    try:
        sec = float(ms) / 1000.0
        return datetime.fromtimestamp(sec, tz=timezone.utc).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OSError):
        return None


def _parse_yyyymmdd(s: Any) -> Optional[str]:
    if not s:
        return None
    t = str(s).strip()
    if len(t) == 8 and t.isdigit():
        return f"{t[:4]}-{t[4:6]}-{t[6:8]}"
    return None


def _invoice_date_from_page(p: dict, inv_detail: dict) -> Optional[str]:
    s = _ms_to_date_str(p.get("receipt_date"))
    if s:
        return s
    d = inv_detail.get("Date")
    if d:
        ds = str(d).strip()
        if " " in ds:
            return ds.split()[0]
        if len(ds) >= 10 and ds[4] == "-" and ds[7] == "-":
            return ds[:10]
    ii = p.get("invoice_input") or {}
    s2 = _parse_yyyymmdd(ii.get("Date"))
    if s2:
        return s2
    return None


def _lines_from_invoice_detail_items(items: List[dict]) -> List[dict]:
    lines = []
    for it in items:
        if not isinstance(it, dict):
            continue
        name = (it.get("Name") or it.get("name") or "").strip()
        try:
            amount = float(it.get("Amount", it.get("amount", 0)))
        except (TypeError, ValueError):
            amount = 0.0
        qty = it.get("Quantity", it.get("quantity"))
        try:
            qf = float(qty) if qty is not None and str(qty).strip() != "" else None
        except (TypeError, ValueError):
            qf = None
        unit = (it.get("Unit") or it.get("unit") or "") or None
        unit = str(unit).strip() if unit else None
        up = it.get("Price", it.get("price"))
        try:
            unit_price = float(up) if up is not None and str(up).strip() != "" else None
        except (TypeError, ValueError):
            unit_price = None
        lines.append(
            {
                "name": name,
                "amount": amount,
                "quantity": qf,
                "unit": unit,
                "unit_price": unit_price,
            }
        )
    return lines


def _lines_from_expense_items(items: List[dict]) -> List[dict]:
    lines = []
    for it in items:
        if not isinstance(it, dict):
            continue
        name = (
            it.get("material_name")
            or it.get("comments")
            or it.get("Name")
            or ""
        )
        name = str(name).strip()
        try:
            amount = float(
                it.get("receipt_amount", it.get("original_amount", it.get("Amount", 0)))
            )
        except (TypeError, ValueError):
            amount = 0.0
        qty = it.get("quantity", it.get("Quantity"))
        try:
            qf = float(qty) if qty is not None and str(qty).strip() != "" else None
        except (TypeError, ValueError):
            qf = None
        up = it.get("net_price", it.get("Price"))
        try:
            unit_price = float(up) if up is not None and str(up).strip() != "" else None
        except (TypeError, ValueError):
            unit_price = None
        lines.append(
            {
                "name": name,
                "amount": amount,
                "quantity": qf,
                "unit": None,
                "unit_price": unit_price,
            }
        )
    return lines


def erp_payload_to_invoice_dict(body: dict) -> dict:
    """
    从 ERP 费控信封解析为内部发票 dict。
    仅使用 page_info[0]（首张票据）；多张请分次提交或扩展为多张发票接口。
    """
    page_info = _page_info_list(body)
    if not page_info:
        raise ValueError("page_info 为空")
    p = page_info[0]
    if not isinstance(p, dict):
        raise ValueError("page_info[0] 格式错误")

    inv_detail = p.get("invoice_detail") or {}
    lines: List[dict] = []

    id_items = inv_detail.get("Items")
    if isinstance(id_items, list) and len(id_items) > 0:
        lines = _lines_from_invoice_detail_items(id_items)
    else:
        exp_items = p.get("items")
        if isinstance(exp_items, list) and len(exp_items) > 0:
            lines = _lines_from_expense_items(exp_items)

    if not lines:
        raise ValueError("未能从 invoice_detail.Items 或 items 解析出明细行")

    inv_no = (
        (p.get("invoice_num") or "").strip()
        or str(inv_detail.get("No") or "").strip()
        or str((p.get("invoice_input") or {}).get("No") or "").strip()
    )

    try:
        total = float(
            p.get("receipt_amount")
            or p.get("original_amount")
            or inv_detail.get("SummaryAmount")
            or sum(float(x.get("amount", 0)) for x in lines)
        )
    except (TypeError, ValueError):
        total = sum(float(x.get("amount", 0)) for x in lines)

    seller_name = (
        (p.get("shop_name") or p.get("saler_name") or "").strip()
        or str((inv_detail.get("Saler") or {}).get("Name") or "").strip()
    )

    buyer_name = str((inv_detail.get("Buyer") or {}).get("Name") or "").strip()
    inv_date = _invoice_date_from_page(p, inv_detail)

    out: Dict[str, Any] = {
        "invoice_number": inv_no or None,
        "date": inv_date,
        "total_amount": total,
        "lines": lines,
        "source_format": "ERP_JSON",
    }
    if seller_name:
        out["seller"] = {"name": seller_name}
    if buyer_name:
        out["buyer"] = {"name": buyer_name}
    return out


def normalize_invoice_request_body(body: Optional[dict]) -> dict:
    """
    若为 ERP page_info 信封则展开为标准发票 dict；否则返回原 body 的拷贝/引用。
    """
    if not body or not isinstance(body, dict):
        return body or {}
    if body.get("lines") or body.get("items"):
        return body
    if is_erp_page_info_payload(body):
        return erp_payload_to_invoice_dict(body)
    return body
