from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.airports_distance import great_circle_distance_km, resolve_airport

router = APIRouter(prefix="/api/airports", tags=["airports"])


class CommuteDistanceRequest(BaseModel):
    from_airport: str = Field(..., description="起点机场名称（中文/英文）或 IATA 三字码（如 PEK）")
    to_airport: str = Field(..., description="终点机场名称（中文/英文）或 IATA 三字码（如 PVG）")
    unit: Optional[Literal["km", "m"]] = Field(default="km", description="返回单位：km 或 m（默认 km）")


@router.post(
    "/commute-distance",
    summary="机场通勤距离计算（大圆定律）",
    description="基于 airport.xlsx 的机场经纬度，使用大圆距离（球面 Haversine）计算两机场直线距离，并支持中文输入的机场名称匹配。",
)
def commute_distance(req: CommuteDistanceRequest):
    from_str = (req.from_airport or "").strip()
    to_str = (req.to_airport or "").strip()
    if not from_str or not to_str:
        raise HTTPException(status_code=400, detail="from_airport / to_airport 不能为空")

    from_rec, _, _ = resolve_airport(from_str)
    to_rec, _, _ = resolve_airport(to_str)

    dist_km = great_circle_distance_km(
        from_rec.latitude_deg,
        from_rec.longitude_deg,
        to_rec.latitude_deg,
        to_rec.longitude_deg,
    )

    unit = req.unit or "km"
    dist_out = dist_km if unit == "km" else dist_km * 1000

    return {
        "success": True,
        "data": {
            "from_input": from_str,
            "to_input": to_str,
            "from": {
                "iata_code": from_rec.iata_code,
                "ident": from_rec.ident,
                "name": from_rec.name,
                "latitude_deg": from_rec.latitude_deg,
                "longitude_deg": from_rec.longitude_deg,
            },
            "to": {
                "iata_code": to_rec.iata_code,
                "ident": to_rec.ident,
                "name": to_rec.name,
                "latitude_deg": to_rec.latitude_deg,
                "longitude_deg": to_rec.longitude_deg,
            },
            "distance_km": dist_km,
            "distance_out": dist_out,
            "distance_unit": unit,
            "method": "great_circle_haversine",
        },
        "message": "",
    }

