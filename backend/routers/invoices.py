from __future__ import annotations

import os
from fastapi import APIRouter, Body, File, Form, HTTPException, UploadFile

from src.models import Scope
from src.erp_invoice_normalize import normalize_invoice_request_body
from src.invoice_parser import (
    PdfInvoiceParser,
    _normalize_name_single_line,
    parse_invoice_from_ofd,
    parse_invoice_from_xml,
)
from backend.database import (
    InvoiceCategoryRecord,
    add_invoice_categories_batch,
    clear_invoice_categories,
    get_invoice_category_stats,
    list_invoice_categories,
)
from backend.carbon_utils import carbon_cost_cny

router = APIRouter(prefix="/api/invoice", tags=["invoices"])


def _get_pipeline():
    from backend.routers.match import _get_pipeline as _match_pipeline
    return _match_pipeline()


def _build_pipeline_with_carbon_price(price_per_ton: float):
    from src.config import AppConfig, CarbonPriceConfig
    from src.pipeline import CarbonAccountingPipeline

    return CarbonAccountingPipeline(
        config=AppConfig(
            carbon_price=CarbonPriceConfig(source="internal", price_per_ton=float(price_per_ton))
        )
    )


def _build_response(result: dict, carbon_price_per_ton: float, carbon_price_date: str | None):
    classified = result.get("classified", [])
    aggregate = result.get("aggregate_kg", {})
    aggregate_out = {}
    for s in (Scope.SCOPE_1, Scope.SCOPE_2, Scope.SCOPE_3):
        val = aggregate.get(s, 0.0) if hasattr(aggregate, "get") else 0.0
        aggregate_out[s.value] = round(float(val if isinstance(val, (int, float)) else 0.0), 4)

    ers = result.get("emission_results") or [None] * len(classified)
    lines = []
    for cl, er in zip(classified, ers):
        emission_kg = float(getattr(er, "emission_kg", 0.0) if er is not None else 0.0)
        lines.append(
            {
                "name": _normalize_name_single_line(cl.line.name or ""),
                "scope": cl.scope.value,
                "match_type": cl.match_type,
                "amount": cl.line.amount,
                "emission_kg": round(emission_kg, 4),
                "tax_code": cl.matched_tax_code,
                "carbon_price_per_ton": round(float(carbon_price_per_ton), 4),
                "carbon_cost_cny": round(carbon_cost_cny(emission_kg, carbon_price_per_ton), 4),
            }
        )

    return {
        "total_emissions_kg": round(sum(aggregate_out.values()), 4),
        "carbon_price_per_ton": round(float(carbon_price_per_ton), 4),
        "carbon_price_date": carbon_price_date,
        "total_carbon_cost_cny": round(sum(float(l.get("carbon_cost_cny") or 0.0) for l in lines), 4),
        "aggregate": aggregate_out,
        "lines": lines,
    }


def _persist_invoice_categories(
    invoice_number: str | None,
    carbon_price_per_ton: float,
    carbon_price_date: str | None,
    result: dict,
) -> None:
    """Persist classified invoice lines for /stats and /categories endpoints."""
    classified = result.get("classified", [])
    ers = result.get("emission_results") or [None] * len(classified)
    if not classified:
        return

    records: list[InvoiceCategoryRecord] = []
    for cl, er in zip(classified, ers):
        emission_kg = float(getattr(er, "emission_kg", 0.0) if er is not None else 0.0)
        records.append(
            InvoiceCategoryRecord(
                id=None,
                invoice_number=invoice_number,
                line_name=_normalize_name_single_line(cl.line.name or ""),
                scope=cl.scope.value,
                match_type=cl.match_type,
                amount=float(cl.line.amount or 0.0),
                emission_kg=emission_kg,
                tax_code=cl.matched_tax_code,
                carbon_price_per_ton=float(carbon_price_per_ton),
                carbon_price_date=carbon_price_date,
                carbon_cost_cny=float(carbon_cost_cny(emission_kg, carbon_price_per_ton)),
            )
        )
    add_invoice_categories_batch(records)


@router.post("/upload")
async def upload_invoice(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="请上传文件")
    ext = os.path.splitext(file.filename.lower())[1]
    if ext not in (".pdf", ".xml", ".ofd"):
        raise HTTPException(status_code=400, detail="仅支持 PDF、OFD 和 XML 格式的发票文件")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="文件内容为空")

    if ext == ".pdf":
        invoice = PdfInvoiceParser().parse(content)
    elif ext == ".xml":
        invoice = parse_invoice_from_xml(content)
    else:
        invoice = parse_invoice_from_ofd(content)
    if not invoice.lines:
        raise HTTPException(status_code=400, detail="未能从文件中提取到发票明细行")

    pipeline = _get_pipeline()
    result = pipeline.process_invoice(invoice, ref_invoice_id=invoice.invoice_number)
    carbon_price_per_ton = float(getattr(pipeline.config.carbon_price, "price_per_ton", 100.0))
    _persist_invoice_categories(invoice.invoice_number, carbon_price_per_ton, invoice.date, result)
    data = _build_response(result, carbon_price_per_ton, invoice.date)
    data["invoice_number"] = invoice.invoice_number
    data["seller"] = invoice.seller.name if invoice.seller else None
    return {"success": True, "data": data, "message": f"发票处理完成，共 {len(data['lines'])} 条明细"}


@router.post("/upload_with_daily_carbon_price")
async def upload_invoice_with_daily_carbon_price(
    file: UploadFile = File(...),
    carbon_price_per_ton: float = Form(...),
    carbon_price_date: str | None = Form(None),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="请上传文件")
    ext = os.path.splitext(file.filename.lower())[1]
    if ext not in (".pdf", ".xml", ".ofd"):
        raise HTTPException(status_code=400, detail="仅支持 PDF、OFD 和 XML 格式的发票文件")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="文件内容为空")

    if ext == ".pdf":
        invoice = PdfInvoiceParser().parse(content)
    elif ext == ".xml":
        invoice = parse_invoice_from_xml(content)
    else:
        invoice = parse_invoice_from_ofd(content)
    if not invoice.lines:
        raise HTTPException(status_code=400, detail="未能从文件中提取到发票明细行")

    price = float(carbon_price_per_ton)
    date = carbon_price_date or invoice.date
    pipeline = _build_pipeline_with_carbon_price(price)
    result = pipeline.process_invoice(invoice, ref_invoice_id=invoice.invoice_number)
    _persist_invoice_categories(invoice.invoice_number, price, date, result)
    data = _build_response(result, price, date)
    data["invoice_number"] = invoice.invoice_number
    data["seller"] = invoice.seller.name if invoice.seller else None
    return {"success": True, "data": data, "message": f"发票处理完成（含指定碳价），共 {len(data['lines'])} 条明细"}


@router.post("/process")
def process_invoice_json(body: dict = Body(...)):
    if not body:
        raise HTTPException(status_code=400, detail="请求体不能为空")
    body = normalize_invoice_request_body(body)
    if not body.get("lines") and not body.get("items"):
        raise HTTPException(status_code=400, detail="请求体需含 lines/items，或费控格式 data.page_info")
    pipeline = _get_pipeline()
    result = pipeline.process_invoice_from_dict(body)
    carbon_price_per_ton = float(getattr(pipeline.config.carbon_price, "price_per_ton", 100.0))
    invoice_number = (body.get("invoice_number") or "").strip() or None
    _persist_invoice_categories(invoice_number, carbon_price_per_ton, body.get("date"), result)
    data = _build_response(result, carbon_price_per_ton, body.get("date"))
    data["invoice_number"] = invoice_number
    if isinstance(body.get("seller"), dict):
        data["seller"] = body.get("seller", {}).get("name")
    return {"success": True, "data": data, "message": f"发票处理完成，共 {len(data['lines'])} 条明细"}


@router.post("/process_with_daily_carbon_price")
def process_invoice_json_with_daily_carbon_price(body: dict = Body(...)):
    if not body:
        raise HTTPException(status_code=400, detail="请求体不能为空")
    body = normalize_invoice_request_body(body)
    if not body.get("lines") and not body.get("items"):
        raise HTTPException(status_code=400, detail="请求体需含 lines/items，或费控格式 data.page_info")
    carbon_price_per_ton = float(body.get("carbon_price_per_ton"))
    pipeline = _build_pipeline_with_carbon_price(carbon_price_per_ton)
    result = pipeline.process_invoice_from_dict(body)
    invoice_number = (body.get("invoice_number") or "").strip() or None
    carbon_price_date = body.get("carbon_price_date") or body.get("date")
    _persist_invoice_categories(invoice_number, carbon_price_per_ton, carbon_price_date, result)
    data = _build_response(result, carbon_price_per_ton, carbon_price_date)
    data["invoice_number"] = invoice_number
    return {"success": True, "data": data, "message": f"发票处理完成（含指定碳价），共 {len(data['lines'])} 条明细"}


@router.get("/categories")
def get_invoice_categories():
    records = list_invoice_categories()
    return {
        "success": True,
        "data": [
            {
                "id": r.id,
                "invoice_number": r.invoice_number,
                "line_name": _normalize_name_single_line(r.line_name or ""),
                "scope": r.scope,
                "match_type": r.match_type,
                "amount": r.amount,
                "emission_kg": r.emission_kg,
                "tax_code": r.tax_code,
                "created_at": r.created_at,
            }
            for r in records
        ],
        "message": "",
    }


@router.get("/stats")
def get_invoice_stats():
    return {"success": True, "data": get_invoice_category_stats(), "message": ""}


@router.post("/clear")
def clear_invoice_records():
    deleted = clear_invoice_categories()
    return {"success": True, "data": {"deleted": deleted}, "message": f"已清空 {deleted} 条记录"}

