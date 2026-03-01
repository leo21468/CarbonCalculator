"""
产品增删改查路由：/api/products, /api/products/{id}
"""
from __future__ import annotations
import os
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.database import (
    add_product, list_products, find_by_name, delete_product, update_product,
    CustomProduct,
)

router = APIRouter(prefix="/api/products", tags=["products"])


class ProductAddRequest(BaseModel):
    product_name: str
    carbon_type: str
    carbon_footprint: str = ""
    co2_per_unit: float
    unit: str
    price_per_ton: float = 100.0
    remark: str = ""


class ProductUpdateRequest(BaseModel):
    product_name: Optional[str] = None
    carbon_type: Optional[str] = None
    carbon_footprint: Optional[str] = None
    co2_per_unit: Optional[float] = None
    unit: Optional[str] = None
    price_per_ton: Optional[float] = None
    remark: Optional[str] = None


@router.get(
    "",
    summary="列出自定义产品",
    description="列出所有自定义产品碳足迹，支持关键词过滤与分页。",
)
def get_products(
    page: int = Query(1, ge=1, description="页码，从1开始"),
    page_size: int = Query(20, ge=1, le=200, description="每页条数"),
    product_name: Optional[str] = Query(None, description="按产品名称关键词过滤"),
):
    """列出所有自定义产品，支持分页与关键词搜索"""
    prods = list_products(name_filter=product_name)
    total = len(prods)
    start = (page - 1) * page_size
    end = start + page_size
    page_data = prods[start:end]
    return {
        "success": True,
        "data": [
            {
                "id": p.id,
                "product_name": p.product_name,
                "carbon_type": p.carbon_type,
                "carbon_footprint": p.carbon_footprint,
                "co2_per_unit": p.co2_per_unit,
                "unit": p.unit,
                "price_per_ton": p.price_per_ton,
            }
            for p in page_data
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "message": "",
    }


@router.post(
    "",
    summary="新增自定义产品",
    description="新增一条自定义产品碳足迹记录。",
)
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
    return {"success": True, "data": {"id": pid}, "message": "添加成功"}


@router.put(
    "/{product_id}",
    summary="更新自定义产品",
    description="根据 ID 更新自定义产品碳足迹记录（部分更新）。",
)
def update_product_route(product_id: int, req: ProductUpdateRequest):
    """更新自定义产品碳足迹"""
    updated = update_product(product_id, req.dict(exclude_none=True))
    if not updated:
        raise HTTPException(status_code=404, detail="产品不存在")
    return {"success": True, "data": None, "message": "更新成功"}


@router.delete(
    "/{product_id}",
    summary="删除自定义产品",
    description="根据 ID 删除一条自定义产品碳足迹记录。",
)
def delete_product_route(product_id: int):
    """删除自定义产品碳足迹"""
    deleted = delete_product(product_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="产品不存在")
    return {"success": True, "data": None, "message": "删除成功"}
