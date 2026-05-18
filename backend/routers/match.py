"""
碳足迹匹配路由：/api/match, /api/pipeline
"""
from __future__ import annotations
import os
import threading
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(tags=["match"])

_cpcd_matcher = None
_pipeline = None
_singleton_lock = threading.Lock()

# 碳价从环境变量读取，默认 100.0 元/吨
_CARBON_PRICE = float(os.environ.get("CARBON_PRICE_PER_TON", "100.0"))


def _get_matcher():
    global _cpcd_matcher
    if _cpcd_matcher is None:
        with _singleton_lock:
            if _cpcd_matcher is None:
                from src.cpcd_matcher import CPCDNLPMatcher
                _cpcd_matcher = CPCDNLPMatcher()
                _cpcd_matcher.load()
    return _cpcd_matcher


def _get_pipeline():
    global _pipeline
    if _pipeline is None:
        with _singleton_lock:
            if _pipeline is None:
                from src.pipeline import CarbonAccountingPipeline
                from src.config import AppConfig, CarbonPriceConfig
                config = AppConfig(
                    carbon_price=CarbonPriceConfig(source="internal", price_per_ton=_CARBON_PRICE),
                )
                _pipeline = CarbonAccountingPipeline(config=config)
    return _pipeline


class MatchRequest(BaseModel):
    product_name: str


def _external_suggestions_for(name: str) -> dict:
    """Best-effort联网候选，失败时不影响 /api/match 的旧行为。"""
    try:
        from backend.factor_search import search_factors
        data = search_factors(product_name=name, include_external=True)
        return {
            "external_suggestions": data.get("external_candidates", []),
            "external_enabled": data.get("external_enabled", False),
            "external_attempted": data.get("external_attempted", False),
            "external_errors": data.get("external_errors", []),
        }
    except Exception:
        return {
            "external_suggestions": [],
            "external_enabled": False,
            "external_attempted": False,
            "external_errors": [],
        }


@router.post(
    "/api/match",
    summary="碳足迹匹配",
    description="输入产品名称，返回碳种类、碳足迹、CO2当量及碳成本。优先查自定义数据库，若无则用 CPCD NLP 匹配。",
)
def match_product(req: MatchRequest):
    """输入产品名称，返回碳种类、碳足迹、二氧化碳当量及碳成本价格。"""
    from backend.database import find_by_name
    from backend.carbon_utils import parse_carbon_footprint, carbon_cost_cny

    name = (req.product_name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="产品名称不能为空")

    try:
        # 1) 先查自定义数据库
        custom = find_by_name(name)
        if custom:
            cost = carbon_cost_cny(custom.co2_per_unit, custom.price_per_ton)
            return {
                "success": True,
                "data": {
                    "source": "custom",
                    "product_name": custom.product_name,
                    "carbon_type": custom.carbon_type,
                    "carbon_footprint": custom.carbon_footprint,
                    "co2_per_unit_kg": custom.co2_per_unit,
                    "unit": custom.unit,
                    "unit_weight_kg": getattr(custom, "unit_weight_kg", None),
                    "carbon_cost_cny": round(cost, 2),
                    "price_per_ton": custom.price_per_ton,
                },
                "message": "",
            }

        # 2) CPCD NLP 匹配
        matcher = _get_matcher()
        matches = matcher.match(name, top_k=1, min_similarity=0.01)
        if not matches:
            suggestions = _external_suggestions_for(name)
            return {
                "success": True,
                "data": {
                    "source": "none",
                    "product_name": name,
                    "carbon_type": "-",
                    "carbon_footprint": "-",
                    "co2_per_unit_kg": None,
                    "unit": "-",
                    "carbon_cost_cny": None,
                    "price_per_ton": _CARBON_PRICE,
                    **suggestions,
                },
                "message": "未找到匹配产品，可添加自定义数据",
            }
        m = matches[0]
        co2_kg, unit = parse_carbon_footprint(m.carbon_footprint)
        cost = carbon_cost_cny(co2_kg, _CARBON_PRICE) if co2_kg > 0 else None
        suggestions = _external_suggestions_for(name) if float(m.similarity or 0.0) < 0.30 else {}
        return {
            "success": True,
            "data": {
                "source": "cpcd",
                "product_name": m.product_name,
                "carbon_type": m.accounting_boundary or m.data_type or "-",
                "carbon_footprint": m.carbon_footprint,
                "co2_per_unit_kg": round(co2_kg, 4) if co2_kg > 0 else None,
                "unit": unit or "-",
                "carbon_cost_cny": round(cost, 2) if cost is not None else None,
                "price_per_ton": _CARBON_PRICE,
                "similarity": round(m.similarity, 3),
                **suggestions,
            },
            "message": "",
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=f"CPCD 数据文件未就绪：{e!s}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询失败：{e!s}")
