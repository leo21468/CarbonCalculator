"""
FastAPI 后端：产品碳足迹查询 API + 自定义数据新增。
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from typing import List, Optional
from fastapi import FastAPI, HTTPException
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


class InvoiceLineRequest(BaseModel):
    name: str
    tax_classification_code: Optional[str] = None
    tax_classification_name: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    unit_price: Optional[float] = None
    amount: float = 0.0
    remark: Optional[str] = None


class SellerRequest(BaseModel):
    name: str
    tax_id: Optional[str] = None
    address: Optional[str] = None


class InvoiceUploadRequest(BaseModel):
    invoice_number: Optional[str] = None
    lines: List[InvoiceLineRequest]
    seller: Optional[SellerRequest] = None


# ---------- 静态文件 ----------
frontend_dir = ROOT / "frontend"
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")


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
def upload_invoice(req: InvoiceUploadRequest):
    """
    上传发票数据，分类发票明细行并记录类别统计到数据库。
    返回分类结果及排放核算摘要。
    """
    if not req.lines:
        raise HTTPException(status_code=400, detail="发票明细不能为空")

    # 构建 pipeline 输入 dict
    invoice_dict = {
        "invoice_number": req.invoice_number,
        "lines": [line.model_dump() for line in req.lines],
    }
    if req.seller:
        invoice_dict["seller"] = req.seller.model_dump()

    pipeline = _get_pipeline()
    result = pipeline.process_invoice_from_dict(invoice_dict, ref_invoice_id=req.invoice_number)

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
            invoice_number=req.invoice_number,
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
