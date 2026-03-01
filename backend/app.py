"""
FastAPI 后端：产品碳足迹查询 API + 自定义数据新增。
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from typing import List, Optional
from fastapi import FastAPI, HTTPException, UploadFile, File, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.carbon_utils import parse_carbon_footprint, carbon_cost_cny
from backend.database import (
    add_product, list_products, find_by_name, CustomProduct,
    add_invoice_categories_batch, list_invoice_categories,
    get_invoice_category_stats, InvoiceCategoryRecord,
)

# 延迟导入 CPCD matcher（避免启动时加载大 CSV）
_cpcd_matcher = None
_pipeline = None
_CARBON_PRICE = 100.0  # 元/吨


def _get_matcher():
    global _cpcd_matcher
    if _cpcd_matcher is None:
        from src.cpcd_matcher import CPCDNLPMatcher
        _cpcd_matcher = CPCDNLPMatcher()
        _cpcd_matcher.load()
    return _cpcd_matcher


def _get_pipeline():
    global _pipeline
    if _pipeline is None:
        from src.pipeline import CarbonAccountingPipeline
        from src.config import AppConfig, CarbonPriceConfig
        config = AppConfig(
            carbon_price=CarbonPriceConfig(source="internal", price_per_ton=_CARBON_PRICE),
        )
        _pipeline = CarbonAccountingPipeline(config=config)
    return _pipeline


app = FastAPI(title="碳足迹 Agent API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ---------- Pydantic 模型 ----------
class MatchRequest(BaseModel):
    product_name: str


class ProductAddRequest(BaseModel):
    product_name: str
    carbon_type: str
    carbon_footprint: str = ""
    co2_per_unit: float
    unit: str
    price_per_ton: float = 100.0
    remark: str = ""


# ---------- 静态文件 ----------
frontend_dir = ROOT / "frontend"
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")


# ---------- 健康检查 ----------
@app.get("/api/health")
def health():
    """服务健康检查，用于前端判断接口可用性"""
    return {"status": "ok", "service": "碳足迹 Agent API"}


# ---------- API ----------
@app.get("/", include_in_schema=False)
def index():
    """返回前端 Agent 页面"""
    front = ROOT / "frontend" / "index.html"
    if front.exists():
        return FileResponse(str(front))
    return {"msg": "请放置 frontend/index.html"}


@app.post("/api/match")
def match_product(req: MatchRequest):
    """
    输入产品名称，返回碳种类、碳足迹、二氧化碳当量及碳成本价格。
    优先查自定义数据库，若无则用 CPCD NLP 匹配。
    """
    name = (req.product_name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="产品名称不能为空")

    # 1) 先查自定义数据库
    custom = find_by_name(name)
    if custom:
        cost = carbon_cost_cny(custom.co2_per_unit, custom.price_per_ton)
        return {
            "source": "custom",
            "product_name": custom.product_name,
            "carbon_type": custom.carbon_type,
            "carbon_footprint": custom.carbon_footprint,
            "co2_per_unit_kg": custom.co2_per_unit,
            "unit": custom.unit,
            "carbon_cost_cny": round(cost, 2),
            "price_per_ton": custom.price_per_ton,
        }

    # 2) CPCD NLP 匹配
    matcher = _get_matcher()
    matches = matcher.match(name, top_k=1, min_similarity=0.01)
    if not matches:
        return {
            "source": "none",
            "product_name": name,
            "carbon_type": "-",
            "carbon_footprint": "-",
            "co2_per_unit_kg": None,
            "unit": "-",
            "carbon_cost_cny": None,
            "price_per_ton": _CARBON_PRICE,
            "message": "未找到匹配产品，可添加自定义数据",
        }
    m = matches[0]
    co2_kg, unit = parse_carbon_footprint(m.carbon_footprint)
    cost = carbon_cost_cny(co2_kg, _CARBON_PRICE) if co2_kg > 0 else None
    return {
        "source": "cpcd",
        "product_name": m.product_name,
        "carbon_type": m.accounting_boundary or m.data_type or "-",
        "carbon_footprint": m.carbon_footprint,
        "co2_per_unit_kg": round(co2_kg, 4) if co2_kg > 0 else None,
        "unit": unit or "-",
        "carbon_cost_cny": round(cost, 2) if cost is not None else None,
        "price_per_ton": _CARBON_PRICE,
        "similarity": round(m.similarity, 3),
    }


@app.get("/api/products")
def get_products():
    """列出所有自定义产品"""
    prods = list_products()
    return [{"id": p.id, "product_name": p.product_name, "carbon_type": p.carbon_type, "carbon_footprint": p.carbon_footprint, "co2_per_unit": p.co2_per_unit, "unit": p.unit, "price_per_ton": p.price_per_ton} for p in prods]


@app.post("/api/products")
def create_product(req: ProductAddRequest):
    """新增自定义产品碳足迹"""
    p = CustomProduct(
        id=None,
        product_name=req.product_name.strip(),
        carbon_type=req.carbon_type.strip(),
        carbon_footprint=req.carbon_footprint.strip(),
        co2_per_unit=req.co2_per_unit,
        unit=req.unit.strip(),
        price_per_ton=req.price_per_ton,
        remark=req.remark.strip(),
    )
    if not p.product_name:
        raise HTTPException(status_code=400, detail="产品名称不能为空")
    pid = add_product(p)
    return {"id": pid, "message": "添加成功"}


@app.post("/api/invoice/upload")
async def upload_invoice(file: UploadFile = File(...)):
    """
    上传 PDF 发票文件，解析发票明细、分类并记录类别统计到数据库。
    返回分类结果及排放核算摘要。
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="请上传文件")
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="仅支持 PDF 格式的发票文件")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="文件内容为空")

    # 使用 PDF 解析器提取发票数据
    from src.invoice_parser import PdfInvoiceParser
    parser = PdfInvoiceParser()
    try:
        invoice = parser.parse(content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"PDF 解析失败：{e}")

    if not invoice.lines:
        raise HTTPException(status_code=400, detail="未能从 PDF 中提取到发票明细行")

    # 使用 pipeline 分类与核算
    pipeline = _get_pipeline()
    result = pipeline.process_invoice(invoice, ref_invoice_id=invoice.invoice_number)

    classified = result.get("classified", [])
    emission_results = result.get("emission_results", [])

    # 构建 emission_kg 映射（按行索引）
    emission_map = {}
    for i, er in enumerate(emission_results):
        emission_map[i] = er.emission_kg

    # 将分类结果存入数据库
    records = []
    for i, cl in enumerate(classified):
        records.append(InvoiceCategoryRecord(
            id=None,
            invoice_number=invoice.invoice_number,
            line_name=cl.line.name,
            scope=cl.scope.value,
            match_type=cl.match_type,
            amount=cl.line.amount,
            emission_kg=emission_map.get(i, 0.0),
            tax_code=cl.matched_tax_code,
        ))
    if records:
        add_invoice_categories_batch(records)

    # 构建响应
    aggregate = result.get("aggregate_kg", {})
    total_emissions_kg = sum(aggregate.values()) if aggregate else 0.0
    lines_result = []
    for i, cl in enumerate(classified):
        lines_result.append({
            "name": cl.line.name,
            "scope": cl.scope.value,
            "match_type": cl.match_type,
            "amount": cl.line.amount,
            "emission_kg": round(emission_map.get(i, 0.0), 4),
            "tax_code": cl.matched_tax_code,
        })

    return {
        "message": f"发票处理完成，共 {len(classified)} 条明细",
        "invoice_number": invoice.invoice_number,
        "seller": invoice.seller.name if invoice.seller else None,
        "total_emissions_kg": round(total_emissions_kg, 4),
        "lines": lines_result,
        "aggregate": {
            scope.value: round(kg, 4)
            for scope, kg in aggregate.items()
        },
    }


@app.get("/api/invoice/categories")
def get_invoice_categories():
    """列出所有发票类别记录"""
    records = list_invoice_categories()
    return [
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
    ]


@app.get("/api/invoice/stats")
def get_invoice_stats():
    """按 Scope 汇总发票类别统计"""
    return get_invoice_category_stats()


@app.post("/api/invoice/process")
def process_invoice_json(body: dict = Body(...)):
    """
    直接提交发票 JSON 进行分类与核算（无需上传文件）。
    请求体格式：{ "lines": [{ "name", "amount", "tax_classification_code?", "quantity?", "unit?" }], "seller": { "name" }, "invoice_number?", "total_amount?" }
    """
    if not body:
        raise HTTPException(status_code=400, detail="请求体不能为空")
    pipeline = _get_pipeline()
    try:
        result = pipeline.process_invoice_from_dict(body)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"发票数据解析失败：{e}")

    classified = result.get("classified", [])
    emission_results = result.get("emission_results", [])
    aggregate = result.get("aggregate_kg", {})

    emission_map = {}
    for i, er in enumerate(emission_results):
        emission_map[i] = er.emission_kg

    invoice_number = (body.get("invoice_number") or "").strip() or None
    seller_name = None
    if isinstance(body.get("seller"), dict):
        seller_name = body["seller"].get("name")
    elif body.get("seller"):
        seller_name = str(body["seller"])

    # 写入类别统计（若有发票号）
    if invoice_number and classified:
        records = []
        for i, cl in enumerate(classified):
            records.append(InvoiceCategoryRecord(
                id=None,
                invoice_number=invoice_number,
                line_name=cl.line.name,
                scope=cl.scope.value,
                match_type=cl.match_type,
                amount=cl.line.amount,
                emission_kg=emission_map.get(i, 0.0),
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
            "emission_kg": round(emission_map.get(i, 0.0), 4),
            "tax_code": cl.matched_tax_code,
        }
        for i, cl in enumerate(classified)
    ]

    return {
        "message": f"发票处理完成，共 {len(classified)} 条明细",
        "invoice_number": invoice_number,
        "seller": seller_name,
        "total_emissions_kg": round(total_emissions_kg, 4),
        "lines": lines_result,
        "aggregate": {
            scope.value: round(kg, 4)
            for scope, kg in aggregate.items()
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
