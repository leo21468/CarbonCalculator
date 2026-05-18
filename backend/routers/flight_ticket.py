from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from backend.flight_ticket_service import FlightTicketError, analyze_flight_ticket_image

router = APIRouter(prefix="/api/flight-ticket", tags=["flight-ticket"])


@router.post("/analyze", summary="机票图片独立核算")
async def analyze_flight_ticket(
    file: UploadFile = File(...),
    carbon_price_per_ton: Optional[float] = Form(None),
    carbon_price_date: Optional[str] = Form(None),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="请上传机票图片")
    content = await file.read()
    try:
        data = analyze_flight_ticket_image(
            content=content,
            filename=file.filename,
            content_type=file.content_type,
            carbon_price_per_ton=carbon_price_per_ton,
            carbon_price_date=carbon_price_date,
        )
    except FlightTicketError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "data": data, "message": "机票核算完成"}
