"""
发票分析路由：/api/invoice/upload, /api/invoice/process,
              /api/invoice/categories, /api/invoice/stats
"""
from __future__ import annotations
import os
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File, Body
from fastapi import Form

from src.models import Scope
from src.invoice_parser import (
    _normalize_name_single_line,
    PdfInvoiceParser,
    parse_invoice_from_xml,
    parse_invoice_from_ofd,
)

from backend.database import (
    add_invoice_categories_batch, list_invoice_categories,
    get_invoice_category_stats, clear_invoice_categories, InvoiceCategoryRecord,
)
from backend.carbon_utils import carbon_cost_cny

router = APIRouter(prefix="/api/invoice", tags=["invoices"])


def _get_emission_data_source_label(pipeline) -> str:
    """返回当前流水线使用的排放范围映射数据来源名称。"""
    try:
        mapper = pipeline.classifier.mapper
        ref_db = getattr(mapper, "_ref_db", None)
        ref_table = getattr(mapper, "_ref_table", None)
        if ref_db and Path(ref_db).exists():
            return f"范围映射表（{Path(ref_db).name}）"
        if ref_table and Path(ref_table).exists():
            return f"范围映射表（{Path(ref_table).name}）"
    except Exception:
        pass
    return "范围映射表（tax_code_to_scope 等）"


def _line_emission_data_source(cl, mapper_source_label: str) -> str:
    """单条明细的碳排放数据来源。"""
    if cl.emission_factor_id == "cpcd_flight":
        return "CPCD 机票因子表（Emission factors.csv）"
    if cl.emission_factor_id == "cpcd_hotel":
        return "CPCD 酒店因子表（Emission factors.csv）"
    if cl.emission_factor_id and cl.emission_factor_id != "scope3_default":
        return mapper_source_label
    return "默认因子表（emission_factors.csv）"


def _get_pipeline():
    """延迟加载 pipeline（避免启动时加载大 CSV）"""
    import os, threading
    from backend.routers.match import _get_pipeline as _match_pipeline
    return _match_pipeline()


def _build_pipeline_with_carbon_price(price_per_ton: float):
    """为单次请求构建独立流水线（使用指定碳价），避免全局 singleton 被固定环境变量影响。"""
    from src.config import AppConfig, CarbonPriceConfig
    from src.pipeline import CarbonAccountingPipeline

    config = AppConfig(
        carbon_price=CarbonPriceConfig(source="internal", price_per_ton=float(price_per_ton)),
    )
    return CarbonAccountingPipeline(config=config)


@router.post(
    "/upload",
    summary="上传发票（PDF / OFD / XML）",
    description="上传 PDF、OFD 或 XML 格式的发票文件，解析明细、分类至 Scope 1/2/3 并存入数据库，返回分类结果及排放核算摘要。",
)
async def upload_invoice(file: UploadFile = File(...)):
    """上传发票文件（PDF、OFD 或 XML），解析发票明细、分类并记录类别统计到数据库。"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="请上传文件")
    ext = os.path.splitext(file.filename.lower())[1]
    if ext not in (".pdf", ".xml", ".ofd"):
        raise HTTPException(status_code=400, detail="仅支持 PDF、OFD 和 XML 格式的发票文件")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="文件内容为空")

    if ext == ".pdf":
        parser = PdfInvoiceParser()
        try:
            invoice = parser.parse(content)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"PDF 解析失败：{e}")
    elif ext == ".xml":
        invoice = parse_invoice_from_xml(content)
    else:
        invoice = parse_invoice_from_ofd(content)

    if not invoice.lines:
        raise HTTPException(status_code=400, detail="未能从文件中提取到发票明细行")

    pipeline = _get_pipeline()
    mapper_source_label = _get_emission_data_source_label(pipeline)
    result = pipeline.process_invoice(invoice, ref_invoice_id=invoice.invoice_number)
    classified = result.get("classified", [])
    carbon_price_per_ton = float(getattr(pipeline.config.carbon_price, "price_per_ton", 100.0))
    carbon_price_date = invoice.date

    per_item_emissions = []
    for cl in classified:
        er = pipeline.calculator.calculate_line(cl)
        per_item_emissions.append(er.emission_kg if er is not None else 0.0)

    records = []
    for cl, emission_kg in zip(classified, per_item_emissions):
        carbon_cost = carbon_cost_cny(float(emission_kg), carbon_price_per_ton)
        records.append(InvoiceCategoryRecord(
            id=None,
            invoice_number=invoice.invoice_number,
            line_name=_normalize_name_single_line(cl.line.name or ""),
            scope=cl.scope.value,
            match_type=cl.match_type,
            amount=cl.line.amount,
            emission_kg=emission_kg,
            tax_code=cl.matched_tax_code,
            carbon_price_per_ton=carbon_price_per_ton,
            carbon_price_date=carbon_price_date,
            carbon_cost_cny=carbon_cost,
        ))
    if records:
        add_invoice_categories_batch(records)

    aggregate = result.get("aggregate_kg", {})
    # 始终返回三个 scope 的键，避免前端拿到空或不完整结构；键用枚举的 value 保证一致
    aggregate_out = {}
    for s in (Scope.SCOPE_1, Scope.SCOPE_2, Scope.SCOPE_3):
        val = aggregate.get(s, 0.0) if hasattr(aggregate, "get") else 0.0
        if not isinstance(val, (int, float)):
            val = 0.0
        aggregate_out[s.value] = round(float(val), 4)
    total_emissions_kg = sum(aggregate_out.values())
    lines_result = [
        {
            "name": _normalize_name_single_line(cl.line.name or ""),
            "scope": cl.scope.value,
            "match_type": cl.match_type,
            "amount": cl.line.amount,
            "emission_kg": round(emission_kg, 4),
            "tax_code": cl.matched_tax_code,
            "emission_data_source": _line_emission_data_source(cl, mapper_source_label),
            "carbon_price_per_ton": round(carbon_price_per_ton, 4),
            "carbon_cost_cny": round(carbon_cost_cny(float(emission_kg), carbon_price_per_ton), 4),
        }
        for cl, emission_kg in zip(classified, per_item_emissions)
    ]

    return {
        "success": True,
        "data": {
            "invoice_number": invoice.invoice_number,
            "seller": invoice.seller.name if invoice.seller else None,
            "total_emissions_kg": round(total_emissions_kg, 4),
            "lines": lines_result,
            "aggregate": aggregate_out,
        },
        "message": f"发票处理完成，共 {len(classified)} 条明细",
    }


@router.post(
    "/process",
    summary="提交发票 JSON 核算",
    description="直接提交发票 JSON 进行分类与核算（无需上传文件）。请求体需含 lines 或 items 数组。",
)
def process_invoice_json(body: dict = Body(...)):
    """直接提交发票 JSON 进行分类与核算（无需上传文件）。"""
    if not body:
        raise HTTPException(status_code=400, detail="请求体不能为空")
    pipeline = _get_pipeline()
    mapper_source_label = _get_emission_data_source_label(pipeline)
    carbon_price_per_ton = float(getattr(pipeline.config.carbon_price, "price_per_ton", 100.0))
    carbon_price_date = body.get("date")
    try:
        result = pipeline.process_invoice_from_dict(body)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"发票数据解析失败：{e}")

    classified = result.get("classified", [])
    aggregate = result.get("aggregate_kg", {})
    aggregate_out = {}
    for s in (Scope.SCOPE_1, Scope.SCOPE_2, Scope.SCOPE_3):
        val = aggregate.get(s, 0.0) if hasattr(aggregate, "get") else 0.0
        if not isinstance(val, (int, float)):
            val = 0.0
        aggregate_out[s.value] = round(float(val), 4)

    per_item_emissions = []
    for cl in classified:
        er = pipeline.calculator.calculate_line(cl)
        per_item_emissions.append(er.emission_kg if er is not None else 0.0)

    invoice_number = (body.get("invoice_number") or "").strip() or None
    seller_name = None
    if isinstance(body.get("seller"), dict):
        seller_name = body["seller"].get("name")
    elif body.get("seller"):
        seller_name = str(body["seller"])

    if invoice_number and classified:
        records = []
        for cl, emission_kg in zip(classified, per_item_emissions):
            carbon_cost = carbon_cost_cny(float(emission_kg), carbon_price_per_ton)
            records.append(InvoiceCategoryRecord(
                id=None,
                invoice_number=invoice_number,
                line_name=_normalize_name_single_line(cl.line.name or ""),
                scope=cl.scope.value,
                match_type=cl.match_type,
                amount=cl.line.amount,
                emission_kg=emission_kg,
                tax_code=cl.matched_tax_code,
                carbon_price_per_ton=carbon_price_per_ton,
                carbon_price_date=carbon_price_date,
                carbon_cost_cny=carbon_cost,
            ))
        add_invoice_categories_batch(records)

    total_emissions_kg = sum(aggregate_out.values())
    lines_result = [
        {
            "name": _normalize_name_single_line(cl.line.name or ""),
            "scope": cl.scope.value,
            "match_type": cl.match_type,
            "amount": cl.line.amount,
            "emission_kg": round(emission_kg, 4),
            "tax_code": cl.matched_tax_code,
            "emission_data_source": _line_emission_data_source(cl, mapper_source_label),
            "carbon_price_per_ton": round(carbon_price_per_ton, 4),
            "carbon_cost_cny": round(carbon_cost_cny(float(emission_kg), carbon_price_per_ton), 4),
        }
        for cl, emission_kg in zip(classified, per_item_emissions)
    ]

    return {
        "success": True,
        "data": {
            "invoice_number": invoice_number,
            "seller": seller_name,
            "total_emissions_kg": round(total_emissions_kg, 4),
            "lines": lines_result,
            "aggregate": aggregate_out,
        },
        "message": f"发票处理完成，共 {len(classified)} 条明细",
    }


@router.post(
    "/process_with_daily_carbon_price",
    summary="发票核算（指定每日碳价）",
    description="提交发票 JSON，并传入指定日期的碳价；用于计算碳成本并在统计报表中体现。",
)
def process_invoice_json_with_daily_carbon_price(body: dict = Body(...)):
    if not body:
        raise HTTPException(status_code=400, detail="请求体不能为空")

    invoice_number = (body.get("invoice_number") or "").strip() or None
    invoice_date = (body.get("date") or body.get("invoice_date") or body.get("carbon_price_date") or "").strip() or None

    carbon_price_per_ton = body.get("carbon_price_per_ton")
    carbon_price_date = body.get("carbon_price_date") or invoice_date

    # 支持 carbon_prices: [{date, price_per_ton}, ...]
    carbon_prices = body.get("carbon_prices")
    if carbon_price_per_ton is None and carbon_prices and invoice_date:
        for item in carbon_prices:
            if not isinstance(item, dict):
                continue
            if str(item.get("date", "")).strip() == str(invoice_date).strip():
                carbon_price_per_ton = item.get("price_per_ton")
                break

    if carbon_price_per_ton is None:
        raise HTTPException(status_code=400, detail="carbon_price_per_ton / carbon_prices 不能为空")
    if carbon_price_date is None:
        carbon_price_date = invoice_date

    carbon_price_per_ton = float(carbon_price_per_ton)

    pipeline = _build_pipeline_with_carbon_price(carbon_price_per_ton)
    mapper_source_label = _get_emission_data_source_label(pipeline)
    try:
        result = pipeline.process_invoice_from_dict(body)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"发票数据解析失败：{e}")

    classified = result.get("classified", [])
    aggregate = result.get("aggregate_kg", {})
    aggregate_out = {}
    for s in (Scope.SCOPE_1, Scope.SCOPE_2, Scope.SCOPE_3):
        val = aggregate.get(s, 0.0) if hasattr(aggregate, "get") else 0.0
        if not isinstance(val, (int, float)):
            val = 0.0
        aggregate_out[s.value] = round(float(val), 4)

    per_item_emissions = []
    for cl in classified:
        er = pipeline.calculator.calculate_line(cl)
        per_item_emissions.append(er.emission_kg if er is not None else 0.0)

    if invoice_number and classified:
        records = []
        for cl, emission_kg in zip(classified, per_item_emissions):
            carbon_cost = carbon_cost_cny(float(emission_kg), carbon_price_per_ton)
            records.append(InvoiceCategoryRecord(
                id=None,
                invoice_number=invoice_number,
                line_name=_normalize_name_single_line(cl.line.name or ""),
                scope=cl.scope.value,
                match_type=cl.match_type,
                amount=cl.line.amount,
                emission_kg=emission_kg,
                tax_code=cl.matched_tax_code,
                carbon_price_per_ton=carbon_price_per_ton,
                carbon_price_date=carbon_price_date,
                carbon_cost_cny=carbon_cost,
            ))
        add_invoice_categories_batch(records)

    total_emissions_kg = sum(aggregate_out.values())
    lines_result = [
        {
            "name": _normalize_name_single_line(cl.line.name or ""),
            "scope": cl.scope.value,
            "match_type": cl.match_type,
            "amount": cl.line.amount,
            "emission_kg": round(emission_kg, 4),
            "tax_code": cl.matched_tax_code,
            "emission_data_source": _line_emission_data_source(cl, mapper_source_label),
            "carbon_price_per_ton": round(carbon_price_per_ton, 4),
            "carbon_cost_cny": round(carbon_cost_cny(float(emission_kg), carbon_price_per_ton), 4),
        }
        for cl, emission_kg in zip(classified, per_item_emissions)
    ]

    return {
        "success": True,
        "data": {
            "invoice_number": invoice_number,
            "total_emissions_kg": round(total_emissions_kg, 4),
            "lines": lines_result,
            "aggregate": aggregate_out,
            "carbon_price_per_ton": round(carbon_price_per_ton, 4),
            "carbon_price_date": carbon_price_date,
        },
        "message": f"发票处理完成（含指定碳价），共 {len(classified)} 条明细",
    }


@router.post(
    "/upload_with_daily_carbon_price",
    summary="上传发票（指定每日碳价）",
    description="上传 PDF/OFD/XML 发票，并传入指定日期的碳价，用于计算碳成本并在统计报表中体现。",
)
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
        parser = PdfInvoiceParser()
        try:
            invoice = parser.parse(content)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"PDF 解析失败：{e}")
    elif ext == ".xml":
        invoice = parse_invoice_from_xml(content)
    else:
        invoice = parse_invoice_from_ofd(content)

    if not invoice.lines:
        raise HTTPException(status_code=400, detail="未能从文件中提取到发票明细行")

    if carbon_price_date is None:
        carbon_price_date = invoice.date
    carbon_price_per_ton = float(carbon_price_per_ton)

    pipeline = _build_pipeline_with_carbon_price(carbon_price_per_ton)
    mapper_source_label = _get_emission_data_source_label(pipeline)
    result = pipeline.process_invoice(invoice, ref_invoice_id=invoice.invoice_number)
    classified = result.get("classified", [])

    per_item_emissions = []
    for cl in classified:
        er = pipeline.calculator.calculate_line(cl)
        per_item_emissions.append(er.emission_kg if er is not None else 0.0)

    records = []
    for cl, emission_kg in zip(classified, per_item_emissions):
        carbon_cost = carbon_cost_cny(float(emission_kg), carbon_price_per_ton)
        records.append(InvoiceCategoryRecord(
            id=None,
            invoice_number=invoice.invoice_number,
            line_name=_normalize_name_single_line(cl.line.name or ""),
            scope=cl.scope.value,
            match_type=cl.match_type,
            amount=cl.line.amount,
            emission_kg=emission_kg,
            tax_code=cl.matched_tax_code,
            carbon_price_per_ton=carbon_price_per_ton,
            carbon_price_date=carbon_price_date,
            carbon_cost_cny=carbon_cost,
        ))
    if records:
        add_invoice_categories_batch(records)

    aggregate = result.get("aggregate_kg", {})
    aggregate_out = {}
    for s in (Scope.SCOPE_1, Scope.SCOPE_2, Scope.SCOPE_3):
        val = aggregate.get(s, 0.0) if hasattr(aggregate, "get") else 0.0
        if not isinstance(val, (int, float)):
            val = 0.0
        aggregate_out[s.value] = round(float(val), 4)

    total_emissions_kg = sum(aggregate_out.values())
    lines_result = [
        {
            "name": _normalize_name_single_line(cl.line.name or ""),
            "scope": cl.scope.value,
            "match_type": cl.match_type,
            "amount": cl.line.amount,
            "emission_kg": round(emission_kg, 4),
            "tax_code": cl.matched_tax_code,
            "emission_data_source": _line_emission_data_source(cl, mapper_source_label),
            "carbon_price_per_ton": round(carbon_price_per_ton, 4),
            "carbon_cost_cny": round(carbon_cost_cny(float(emission_kg), carbon_price_per_ton), 4),
        }
        for cl, emission_kg in zip(classified, per_item_emissions)
    ]

    return {
        "success": True,
        "data": {
            "invoice_number": invoice.invoice_number,
            "seller": invoice.seller.name if invoice.seller else None,
            "total_emissions_kg": round(total_emissions_kg, 4),
            "lines": lines_result,
            "aggregate": aggregate_out,
            "carbon_price_per_ton": round(carbon_price_per_ton, 4),
            "carbon_price_date": carbon_price_date,
        },
        "message": f"发票处理完成（含指定碳价），共 {len(classified)} 条明细",
    }


@router.get(
    "/categories",
    summary="发票类别记录列表",
    description="列出所有已录入的发票类别统计记录。",
)
def get_invoice_categories():
    """列出所有发票类别记录"""
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


@router.get(
    "/stats",
    summary="发票类别统计",
    description="按 Scope 汇总发票类别统计（总金额、总排放量、条目数）。",
)
def get_invoice_stats():
    """按 Scope 汇总发票类别统计"""
    return {"success": True, "data": get_invoice_category_stats(), "message": ""}


@router.post(
    "/clear",
    summary="清空发票类别记录",
    description="清空数据库中所有发票类别统计记录，返回删除条数。",
)
def clear_invoice_records():
    """清空所有发票类别记录"""
    deleted = clear_invoice_categories()
    return {"success": True, "data": {"deleted": deleted}, "message": f"已清空 {deleted} 条记录"}
