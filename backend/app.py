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
from backend.database import add_product, list_products, find_by_name, CustomProduct

# 延迟导入 CPCD matcher（避免启动时加载大 CSV）
_cpcd_matcher = None
_CARBON_PRICE = 100.0  # 元/吨


def _get_matcher():
    global _cpcd_matcher
    if _cpcd_matcher is None:
        from src.cpcd_matcher import CPCDNLPMatcher
        _cpcd_matcher = CPCDNLPMatcher()
        _cpcd_matcher.load()
    return _cpcd_matcher


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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
