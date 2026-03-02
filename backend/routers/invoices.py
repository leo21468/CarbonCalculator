"""
发票分析路由：/api/invoice/upload, /api/invoice/process,
              /api/invoice/categories, /api/invoice/stats
"""
from __future__ import annotations
import io
from fastapi import APIRouter, HTTPException, UploadFile, File, Body

from backend.database import (
    add_invoice_categories_batch, list_invoice_categories,
    get_invoice_category_stats, InvoiceCategoryRecord,
)

router = APIRouter(prefix="/api/invoice", tags=["invoices"])


def _get_pipeline():
    """延迟加载 pipeline（避免启动时加载大 CSV）"""
    import os, threading
    from backend.routers.match import _get_pipeline as _match_pipeline
    return _match_pipeline()


@router.post(
    "/upload",
    summary="上传 PDF/XML/OFD 发票",
    description="上传 PDF、XML 或 OFD 发票文件，解析明细、分类至 Scope 1/2/3 并存入数据库，返回分类结果及排放核算摘要。",
)
async def upload_invoice(file: UploadFile = File(...)):
    """上传 PDF/XML/OFD 发票文件，解析发票明细、分类并记录类别统计到数据库。"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="请上传文件")
    ext = file.filename.lower().rsplit(".", 1)[-1] if "." in file.filename else ""
    if ext not in ("pdf", "xml", "ofd"):
        raise HTTPException(status_code=400, detail="仅支持 PDF、XML、OFD 格式的发票文件")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="文件内容为空")

    try:
        if ext == "pdf":
            from src.invoice_parser import PdfInvoiceParser
            invoice = PdfInvoiceParser().parse(content)
        elif ext == "xml":
            import tempfile
            import os
            from src.invoice_parser import JsonXmlInvoiceParser
            fd, tmp_path = tempfile.mkstemp(suffix=".xml")
            try:
                os.write(fd, content)
                os.close(fd)
                invoice = JsonXmlInvoiceParser().parse(tmp_path)
            finally:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
        else:  # ofd
            import tempfile
            import os
            import zipfile
            from src.invoice_parser import JsonXmlInvoiceParser
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as zf:
                    xml_names = [n for n in zf.namelist() if n.lower().endswith(".xml")]
                    if not xml_names:
                        raise HTTPException(status_code=400, detail="OFD 文件中未找到 XML 内容")
                    # 优先选择包含 document/invoice 关键字的 XML
                    preferred = next(
                        (n for n in xml_names if any(k in n.lower() for k in ("document", "invoice"))),
                        xml_names[0],
                    )
                    xml_bytes = zf.read(preferred)
            except (zipfile.BadZipFile, KeyError) as e:
                raise HTTPException(status_code=400, detail=f"OFD 文件解析失败：{e}")
            fd, tmp_path = tempfile.mkstemp(suffix=".xml")
            try:
                os.write(fd, xml_bytes)
                os.close(fd)
                invoice = JsonXmlInvoiceParser().parse(tmp_path)
            finally:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"发票解析失败：{e}")

    if not invoice.lines:
        raise HTTPException(status_code=400, detail="未能从发票中提取到明细行")

    pipeline = _get_pipeline()
    result = pipeline.process_invoice(invoice, ref_invoice_id=invoice.invoice_number)
    classified = result.get("classified", [])

    per_item_emissions = []
    for cl in classified:
        er = pipeline.calculator.calculate_line(cl)
        per_item_emissions.append(er.emission_kg if er is not None else 0.0)

    records = []
    for cl, emission_kg in zip(classified, per_item_emissions):
        records.append(InvoiceCategoryRecord(
            id=None,
            invoice_number=invoice.invoice_number,
            line_name=cl.line.name,
            scope=cl.scope.value,
            match_type=cl.match_type,
            amount=cl.line.amount,
            emission_kg=emission_kg,
            tax_code=cl.matched_tax_code,
        ))
    if records:
        add_invoice_categories_batch(records)

    aggregate = result.get("aggregate_kg", {})
    total_emissions_kg = sum(aggregate.values()) if aggregate else 0.0
    lines_result = [
        {
            "name": cl.line.name,
            "scope": cl.scope.value,
            "match_type": cl.match_type,
            "amount": cl.line.amount,
            "emission_kg": round(emission_kg, 4),
            "tax_code": cl.matched_tax_code,
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
            "aggregate": {
                scope.value: round(kg, 4)
                for scope, kg in aggregate.items()
            },
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
    try:
        result = pipeline.process_invoice_from_dict(body)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"发票数据解析失败：{e}")

    classified = result.get("classified", [])
    aggregate = result.get("aggregate_kg", {})

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
            records.append(InvoiceCategoryRecord(
                id=None,
                invoice_number=invoice_number,
                line_name=cl.line.name,
                scope=cl.scope.value,
                match_type=cl.match_type,
                amount=cl.line.amount,
                emission_kg=emission_kg,
                tax_code=cl.matched_tax_code,
            ))
        add_invoice_categories_batch(records)

    total_emissions_kg = sum(aggregate.values()) if aggregate else 0.0
    lines_result = [
        {
            "name": cl.line.name,
            "scope": cl.scope.value,
            "match_type": cl.match_type,
            "amount": cl.line.amount,
            "emission_kg": round(emission_kg, 4),
            "tax_code": cl.matched_tax_code,
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
            "aggregate": {
                scope.value: round(kg, 4)
                for scope, kg in aggregate.items()
            },
        },
        "message": f"发票处理完成，共 {len(classified)} 条明细",
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
                "line_name": r.line_name,
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
