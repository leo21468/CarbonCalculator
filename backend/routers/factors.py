"""联网因子候选搜索与采纳 API。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.factor_search import adopt_candidate, search_factors

router = APIRouter(prefix="/api/factors", tags=["factors"])


class FactorSearchRequest(BaseModel):
    product_name: str
    region: Optional[str] = None
    year: Optional[str] = None
    include_external: bool = True


class FactorAdoptRequest(BaseModel):
    id: int
    carbon_type: str
    price_per_ton: float = 100.0
    remark: str = ""


@router.post("/search", summary="搜索本地与联网候选碳因子")
def search_factor_candidates(req: FactorSearchRequest):
    name = (req.product_name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="产品名称不能为空")
    try:
        data = search_factors(
            product_name=name,
            region=(req.region or "").strip() or None,
            year=(req.year or "").strip() or None,
            include_external=req.include_external,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "data": data, "message": ""}


@router.post("/adopt", summary="采纳联网候选到自定义产品库")
def adopt_factor_candidate(req: FactorAdoptRequest):
    try:
        product_id = adopt_candidate(
            candidate_id=req.id,
            carbon_type=req.carbon_type,
            price_per_ton=req.price_per_ton,
            remark=req.remark,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "data": {"id": product_id}, "message": "已采纳到自定义产品库"}
